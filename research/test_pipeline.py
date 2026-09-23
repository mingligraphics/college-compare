"""Synthetic fixtures only; no factual pilot-school values and no network access."""
import copy
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from sources import ValidationError, load_json, load_sources
from staging import COLUMNS, build_rows


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.evidence = 'SYNTHETIC TEST ONLY. University-wide tuition: 100 USD. First-year enrollment: 0. A and B: 100 USD. C: 200 USD. Unknown amount.'
        (self.root / 'evidence.txt').write_text(self.evidence, encoding='utf-8')
        self.source = dict(source_id='synthetic', source_name='Synthetic university fixture',
                           source_url='https://example.edu/synthetic', source_type='university',
                           approved_by='test-reviewer', checked_date='2026-01-01',
                           evidence_file='evidence.txt', sha256=hashlib.sha256(self.evidence.encode()).hexdigest())
        self.save('sources.json', [self.source])
        self.sources = load_sources(self.root / 'sources.json')
        self.candidate = dict(school_id='nyu', field='tuition', academic_year='2026-27',
                              source_id='synthetic', evidence='University-wide tuition: 100 USD.',
                              confidence='high', population='undergraduate', selection_rule='direct',
                              candidate_value=100)
        self.current = [dict(school_id='nyu', field='tuition', current_value=100, current_year='2026-27')]

    def save(self, name, data):
        (self.root / name).write_text(json.dumps(data), encoding='utf-8')

    def rows(self, candidate=None, current=None):
        return build_rows([self.candidate if candidate is None else candidate],
                          self.current if current is None else current, self.sources)

    def majority(self):
        record = {k: v for k, v in self.candidate.items() if k != 'candidate_value'}
        record.update(selection_rule='majority_gt_50', coverage_basis='schools', coverage_units=['A', 'B', 'C'], observations=[
            dict(candidate_value=100, covered_units=['A', 'B'], evidence='A and B: 100 USD.'),
            dict(candidate_value=200, covered_units=['C'], evidence='C: 200 USD.')])
        return record

    def test_exact_schema_pending_provenance(self):
        row = self.rows()[0]
        self.assertEqual(tuple(row), COLUMNS)
        self.assertEqual(len(row), 18)
        self.assertEqual(row['status'], 'pending')
        self.assertEqual(row['candidate_value'], 100)
        self.assertEqual(row['checked_date'], '2026-01-01')
        self.assertIn(self.source['sha256'], row['evidence'])
        self.assertIn('Same value', row['review_notes'])

    def test_majority_strictly_over_half(self):
        row = self.rows(self.majority())[0]
        self.assertEqual((row['candidate_value'], row['coverage_numerator'], row['coverage_denominator']), (100, 2, 3))
        self.assertEqual(row['flag_reason'], '')

    def test_exact_half_does_not_select_or_average(self):
        c = self.majority()
        c['coverage_units'] = ['A', 'B']
        c['observations'][0]['covered_units'] = ['A']
        c['observations'][1]['covered_units'] = ['B']
        row = self.rows(c)[0]
        self.assertIsNone(row['candidate_value'])
        self.assertIsNone(row['coverage_numerator'])
        self.assertTrue(row['flag_reason'])
        self.assertEqual(row['confidence'], 'low')
        self.assertIn('200', row['evidence'])

    def test_equal_values_aggregate_units(self):
        c = self.majority()
        c['observations'][0]['covered_units'] = ['A']
        c['observations'][1].update(candidate_value=100, covered_units=['B'])
        row = self.rows(c)[0]
        self.assertEqual(row['coverage_numerator'], 2)
        self.assertEqual(row['candidate_value'], 100)

    def test_unknown_coverage_flagged(self):
        c = self.majority()
        c['coverage_units'] = None
        for obs in c['observations']:
            obs['covered_units'] = None
        row = self.rows(c)[0]
        self.assertIsNone(row['candidate_value'])
        self.assertIsNone(row['coverage_denominator'])
        self.assertIn('unknown', row['flag_reason'])

    def test_missing_unit_does_not_shrink_denominator(self):
        c = self.majority()
        c['coverage_units'] += ['D']
        c['observations'] = c['observations'][:1]
        self.assertIsNone(self.rows(c)[0]['candidate_value'])

    def test_known_population_unknown_coverage_flagged(self):
        c = self.majority()
        c['observations'][1]['covered_units'] = None
        self.assertIsNone(self.rows(c)[0]['candidate_value'])

    def test_null_amount_not_counted_as_zero(self):
        c = self.majority()
        c['observations'][0]['candidate_value'] = None
        self.assertIsNone(self.rows(c)[0]['candidate_value'])
        c['observations'][0]['candidate_value'] = 0
        self.assertEqual(self.rows(c)[0]['candidate_value'], 0)

    def test_overlapping_units_rejected(self):
        c = self.majority()
        c['observations'][1]['covered_units'] = ['B']
        with self.assertRaises(ValidationError):
            self.rows(c)

    def test_duplicate_population_units_rejected(self):
        c = self.majority()
        c['coverage_units'].append('A')
        with self.assertRaises(ValidationError):
            self.rows(c)

    def test_outside_population_rejected(self):
        c = self.majority()
        c['observations'][1]['covered_units'] = ['D']
        with self.assertRaises(ValidationError):
            self.rows(c)

    def test_first_year_only(self):
        c = {**self.candidate, 'field': 'first_year_enrollment', 'population': 'first_year',
             'candidate_value': 0, 'evidence': 'First-year enrollment: 0.'}
        self.assertEqual(self.rows(c)[0]['candidate_value'], 0)
        c['population'] = 'undergraduate'
        with self.assertRaises(ValidationError):
            self.rows(c)
        c['field'] = 'undergrad_enrollment'
        with self.assertRaises(ValidationError):
            self.rows(c)

    def test_enrollment_fraction_rejected(self):
        c = {**self.candidate, 'field': 'first_year_enrollment', 'population': 'first_year', 'candidate_value': 1.5}
        with self.assertRaises(ValidationError):
            self.rows(c)

    def test_enrollment_majority_rejected(self):
        c = {**self.majority(), 'field': 'first_year_enrollment', 'population': 'first_year'}
        with self.assertRaises(ValidationError):
            self.rows(c)

    def test_unknown_value_remains_null(self):
        row = self.rows({**self.candidate, 'candidate_value': None})[0]
        self.assertIsNone(row['candidate_value'])
        self.assertTrue(row['flag_reason'])
        self.assertEqual(row['status'], 'pending')

    def test_changed_value_and_year_comparisons(self):
        row = self.rows(current=[{**self.current[0], 'current_value': 0}])[0]
        self.assertEqual(row['current_value'], 0)
        self.assertIn('Different value', row['review_notes'])
        row = self.rows(current=[{**self.current[0], 'current_year': '2025-26'}])[0]
        self.assertEqual(row['academic_year'], '2026-27')
        self.assertEqual(row['current_year'], '2025-26')
        self.assertIn('not a like-for-like', row['review_notes'])

    def test_missing_current_distinct_from_explicit_null(self):
        missing = self.rows(current=[])[0]
        known_unknown = self.rows(current=[{**self.current[0], 'current_value': None}])[0]
        self.assertIn('not supplied', missing['review_notes'])
        self.assertIn('unknown', known_unknown['review_notes'])

    def test_invalid_values_rejected(self):
        for value in [True, '100', '', -1, 1.001, float('nan'), float('inf')]:
            with self.subTest(value=value), self.assertRaises(ValidationError):
                self.rows({**self.candidate, 'candidate_value': value})

    def test_invalid_years_rejected(self):
        for value in [None, '2026', '2026-28', ' 2026-27', '2026-2027']:
            with self.subTest(value=value), self.assertRaises(ValidationError):
                self.rows({**self.candidate, 'academic_year': value})

    def test_unknown_extra_and_status_fields_rejected(self):
        for update in [{'school_id': 'other'}, {'field': 'coa_total'}, {'confidence': 'certain'},
                       {'status': 'approved'}, {'candidate_value': 100, 'extra': 1}]:
            with self.subTest(update=update), self.assertRaises(ValidationError):
                self.rows({**self.candidate, **update})

    def test_duplicate_candidate_and_current_rejected(self):
        with self.assertRaises(ValidationError):
            build_rows([self.candidate, self.candidate], self.current, self.sources)
        with self.assertRaises(ValidationError):
            self.rows(current=self.current * 2)

    def test_bad_evidence_or_source_rejected(self):
        for update in [{'source_id': 'missing'}, {'evidence': 'Not in source'}]:
            with self.assertRaises(ValidationError):
                self.rows({**self.candidate, **update})
        c = self.majority()
        c['observations'][0]['evidence'] = 'Invented excerpt'
        with self.assertRaises(ValidationError):
            self.rows(c)

    def test_hash_mismatch_rejected(self):
        (self.root / 'evidence.txt').write_text('Changed source', encoding='utf-8')
        with self.assertRaises(ValidationError):
            load_sources(self.root / 'sources.json')

    def test_source_metadata_rejected(self):
        for update in [{'source_type': 'blog'}, {'approved_by': ''}, {'checked_date': '2999-01-01'},
                       {'checked_date': '2026-02-30'}, {'source_url': 'http://example.edu'},
                       {'evidence_file': '../outside.txt'}]:
            with self.subTest(update=update), self.assertRaises(ValidationError):
                self.save('sources.json', [{**self.source, **update}])
                load_sources(self.root / 'sources.json')

    def test_all_source_types_retained(self):
        for kind in ['university', 'CDS', 'nonprofit_research']:
            self.save('sources.json', [{**self.source, 'source_type': kind}])
            sources = load_sources(self.root / 'sources.json')
            self.assertEqual(build_rows([self.candidate], [], sources)[0]['source_type'], kind)

    def test_json_duplicates_and_nonfinite_rejected(self):
        for raw in ['{"a":1,"a":2}', '[NaN]', '[Infinity]', '{']:
            (self.root / 'bad.json').write_text(raw)
            with self.assertRaises(ValidationError):
                load_json(self.root / 'bad.json')

    def test_batch_inputs_not_mutated(self):
        c, current, sources = copy.deepcopy(self.candidate), copy.deepcopy(self.current), copy.deepcopy(self.sources)
        self.rows()
        self.assertEqual((self.candidate, self.current, self.sources), (c, current, sources))

    def test_original_source_preference_preserves_both_candidates(self):
        nonprofit = {**self.sources['synthetic'], 'source_id': 'nonprofit', 'source_type': 'nonprofit_research'}
        sources = {**self.sources, 'nonprofit': nonprofit}
        rows = build_rows([self.candidate, {**self.candidate, 'source_id': 'nonprofit'}], [], sources)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1]['status'], 'pending')
        self.assertIn('prefer original evidence', rows[1]['flag_reason'])

    def test_three_way_no_majority(self):
        c = self.majority()
        c['observations'][0]['covered_units'] = ['A']
        c['observations'].append(dict(candidate_value=300, covered_units=['B'], evidence='Unknown amount.'))
        self.assertIsNone(self.rows(c)[0]['candidate_value'])

    def test_invalid_coverage_basis(self):
        c = self.majority()
        c['coverage_basis'] = 'students'
        with self.assertRaises(ValidationError):
            self.rows(c)

    def test_coa_and_all_pilot_schools(self):
        for school in ['nyu', 'bu', 'ucb']:
            c = {**self.majority(), 'school_id': school, 'field': 'coa'}
            self.assertEqual(self.rows(c)[0]['candidate_value'], 100)

    def test_cli_local_output_and_no_overwrite(self):
        # Run in a disposable copy: no repository fixtures/output or production files are touched.
        app = self.root / 'research'
        app.mkdir()
        for name in ['sources.py', 'staging.py', 'collect.py']:
            shutil.copyfile(Path(__file__).parent / name, app / name)
        self.save('candidates.json', [self.candidate])
        self.save('current.json', self.current)
        command = [sys.executable, '-B', str(app / 'collect.py'), '--sources', str(self.root / 'sources.json'),
                   '--candidates', str(self.root / 'candidates.json'), '--current', str(self.root / 'current.json'),
                   '--output', str(app / 'output' / 'staging.json')]
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        result_rows = load_json(app / 'output' / 'staging.json')
        self.assertEqual(result_rows, self.rows())
        self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
        command[-1] = str(self.root / 'school.csv')
        self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
        self.assertFalse((self.root / 'school.csv').exists())
        command[-1] = str(app / 'output' / 'invalid.json')
        self.save('candidates.json', [self.candidate, {**self.candidate, 'candidate_value': 'invalid'}])
        self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
        self.assertFalse((app / 'output' / 'invalid.json').exists())


if __name__ == '__main__':
    unittest.main()
