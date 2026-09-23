"""Contract tests plus local real-pilot tests; never fetch source URLs."""
import copy
import json
import unittest
from pathlib import Path

from sources import ValidationError, load_json, load_sources
from staging import COLUMNS, build_rows
import test_pipeline as fixtures


class ReviewedContractTests(unittest.TestCase):
    setUp = fixtures.PipelineTests.setUp
    save = fixtures.PipelineTests.save

    def reviewed(self, rule='university_standard'):
        self.source.update(evidence_kind='reviewed_findings', checked_date=None)
        self.save('sources.json', [self.source])
        self.sources = load_sources(self.root / 'sources.json')
        return {**self.candidate, 'selection_rule': rule, 'source_concept': 'tuition_only',
                'review': {'flag_reason': '', 'review_notes': ''}, 'alternatives': [], 'components': []}

    def rows(self, c, current=None):
        return build_rows([c], self.current if current is None else current, self.sources)

    def test_standard_unknown_checked_date_honestly_retained(self):
        c = self.reviewed()
        row = self.rows(c)[0]
        self.assertEqual(row['candidate_value'], 100)
        self.assertEqual(row['selection_rule'], 'university_standard')
        self.assertIsNone(row['checked_date'])
        self.assertIn('checked_date not supplied', row['flag_reason'])
        self.assertIn('reviewed_findings', row['evidence'])
        self.assertIn('not fetched', row['review_notes'])

    def test_source_snapshot_still_requires_date_and_url(self):
        for field in ('checked_date', 'source_url'):
            with self.subTest(field=field), self.assertRaises(ValidationError):
                self.save('sources.json', [{**self.source, field: None}])
                load_sources(self.root / 'sources.json')

    def test_missing_url_not_allowed_for_selected_values(self):
        c = self.reviewed()
        self.sources['synthetic']['source_url'] = None
        with self.assertRaises(ValidationError):
            self.rows(c)

    def test_source_conflict_retains_observation_without_selection(self):
        c = self.reviewed('unresolved_source_conflict')
        c.update(field='first_year_enrollment', population='first_year', candidate_value=None,
                 source_concept='unreconciled_first_year_enrollment', confidence='medium')
        c['review']['flag_reason'] = 'Conflicting report requires official reconciliation.'
        c['alternatives'] = [{'label': 'Unreconciled report', 'candidate_value': 0,
                              'evidence': 'First-year enrollment: 0.'}]
        self.sources['synthetic']['source_url'] = None
        current = [{'school_id': 'nyu', 'field': 'first_year_enrollment', 'current_value': 10, 'current_year': None}]
        row = self.rows(c, current)[0]
        self.assertIsNone(row['candidate_value'])
        self.assertEqual(row['current_value'], 10)
        self.assertIsNone(row['current_year'])
        self.assertIn('Unreconciled report', row['evidence'])
        self.assertIn('Current academic year unknown', row['review_notes'])
        c['candidate_value'] = 0
        with self.assertRaises(ValidationError):
            self.rows(c, current)

    def test_high_confidence_living_ambiguity_has_no_selection(self):
        c = self.reviewed('living_arrangement_ambiguous')
        c.update(field='coa', candidate_value=None, source_concept='living_arrangement_coa')
        c['alternatives'] = [{'label': 'Hall', 'candidate_value': 100, 'evidence': c['evidence']},
                             {'label': 'Apartment', 'candidate_value': 200, 'evidence': 'C: 200 USD.'}]
        c['review']['flag_reason'] = 'Living arrangements differ; choose none.'
        row = self.rows(c)[0]
        self.assertIsNone(row['candidate_value'])
        self.assertEqual(row['confidence'], 'high')
        self.assertIn('Apartment', row['evidence'])
        c['candidate_value'] = 100
        with self.assertRaises(ValidationError):
            self.rows(c)

    def test_resident_standard_retains_unknown_exception(self):
        c = self.reviewed('resident_standard')
        c.update(field='coa', source_concept='resident_standard')
        c['alternatives'] = [{'label': 'Special first-year case', 'candidate_value': None, 'evidence': 'Unknown amount.'}]
        c['review']['flag_reason'] = 'Exception amount not supplied.'
        row = self.rows(c)[0]
        self.assertEqual(row['candidate_value'], 100)
        self.assertIn('Special first-year case', row['evidence'])
        self.assertIn('null', row['evidence'])
        c['review']['flag_reason'] = ''
        with self.assertRaises(ValidationError):
            self.rows(c)

    def test_tuition_and_fees_needs_semantic_flag(self):
        c = self.reviewed()
        c['source_concept'] = 'tuition_and_fees'
        with self.assertRaises(ValidationError):
            self.rows(c)
        c['review']['flag_reason'] = 'Includes fees; not tuition-only.'
        row = self.rows(c)[0]
        self.assertEqual(row['candidate_value'], 100)
        self.assertIn('tuition_and_fees', row['evidence'])

    def test_enrollment_component_sum_is_checked_and_retained(self):
        c = self.reviewed('cds_reported')
        self.sources['synthetic']['source_type'] = 'CDS'
        c.update(field='first_year_enrollment', population='first_year', candidate_value=300,
                 source_concept='cds_first_year_enrollment')
        c['components'] = [{'label': 'Component A', 'candidate_value': 100, 'evidence': 'A and B: 100 USD.'},
                           {'label': 'Component B', 'candidate_value': 200, 'evidence': 'C: 200 USD.'}]
        row = self.rows(c)[0]
        self.assertEqual(row['candidate_value'], 300)
        self.assertIn('Component A', row['evidence'])
        c['candidate_value'] = 301
        with self.assertRaises(ValidationError):
            self.rows(c)

    def test_cds_rule_rejects_wrong_provenance(self):
        c = self.reviewed('cds_reported')
        c.update(field='first_year_enrollment', population='first_year')
        with self.assertRaises(ValidationError):
            self.rows(c)

    def test_year_difference_not_presented_as_same_year_change(self):
        row = self.rows(self.reviewed(), [{**self.current[0], 'current_year': '2025-26'}])[0]
        self.assertEqual(row['current_year'], '2025-26')
        self.assertEqual(row['academic_year'], '2026-27')
        self.assertIn('not a like-for-like', row['review_notes'])

    def counted(self):
        c = self.reviewed('majority_undergraduate_schools')
        for field in ('candidate_value', 'alternatives', 'components'):
            del c[field]
        c.update(coverage_denominator=10, observations=[
            {'label': 'Reviewed aggregate', 'candidate_value': 100, 'coverage_count': 8, 'evidence': c['evidence']},
            {'label': 'Exception', 'candidate_value': None, 'coverage_count': 2, 'evidence': 'Unknown amount.'}])
        return c

    def test_counted_majority_preserves_assertion_boundary(self):
        row = self.rows(self.counted())[0]
        self.assertEqual((row['candidate_value'], row['coverage_numerator'], row['coverage_denominator']), (100, 8, 10))
        self.assertIn('not an independently checked unit roster', row['flag_reason'])

    def test_counted_half_does_not_select(self):
        c = self.counted()
        c['observations'][0]['coverage_count'] = 5
        row = self.rows(c)[0]
        self.assertIsNone(row['candidate_value'])
        self.assertIsNone(row['coverage_numerator'])

    def test_count_overflow_bool_and_duplicate_groups_rejected(self):
        c = self.counted()
        for update in [{'coverage_count': 11}, {'coverage_count': True}, {'label': 'Exception'}]:
            bad = copy.deepcopy(c)
            bad['observations'][0].update(update)
            with self.subTest(update=update), self.assertRaises(ValidationError):
                self.rows(bad)

    def test_no_new_status_or_columns_can_be_injected(self):
        c = self.reviewed()
        c['status'] = 'approved'
        with self.assertRaises(ValidationError):
            self.rows(c)


PILOT = Path(__file__).parent / 'inputs' / 'pilot-01'


@unittest.skipUnless((PILOT / 'sources.json').exists(), 'Private local pilot fixtures not installed')
class RealPilotTests(unittest.TestCase):
    def setUp(self):
        self.sources = load_sources(PILOT / 'sources.json')
        self.candidates = load_json(PILOT / 'candidates.json')
        self.current = load_json(PILOT / 'current.json')
        self.rows = build_rows(self.candidates, self.current, self.sources)

    def test_exact_nine_rows_pending_and_schema(self):
        self.assertEqual(len(self.rows), 9)
        self.assertEqual(len({(r['school_id'], r['field']) for r in self.rows}), 9)
        for row in self.rows:
            self.assertEqual(tuple(row), COLUMNS)
            self.assertEqual(row['status'], 'pending')
            self.assertIsNone(row['checked_date'])
            self.assertIn('reviewed_findings', row['evidence'])

    def test_expected_values_years_and_majorities(self):
        expected = [68576, 100998, None, 73024, 98419, 3449, 18214, None, 6724]
        self.assertEqual([r['candidate_value'] for r in self.rows], expected)
        for row in self.rows[:2]:
            self.assertEqual((row['coverage_numerator'], row['coverage_denominator']), (8, 10))
        self.assertEqual([r['academic_year'] for r in self.rows], ['2026-27', '2026-27', '2025-26'] * 3)

    def test_nyu_conflict_and_missing_details_not_fabricated(self):
        row = self.rows[2]
        self.assertEqual(row['current_value'], 5723)
        self.assertIsNone(row['current_year'])
        self.assertIsNone(row['source_url'])
        self.assertIn('5662', row['evidence'])
        self.assertIn('eligibility', row['flag_reason'])
        self.assertIn('names were not supplied', self.rows[0]['flag_reason'])
        self.assertIn('amounts were not supplied', self.rows[1]['flag_reason'])
        self.assertIn('components were not supplied', self.rows[5]['flag_reason'])

    def test_bu_exception_berkeley_semantics_and_alternatives(self):
        self.assertIn('College of General Studies', self.rows[4]['evidence'])
        self.assertIn('tuition AND fees', self.rows[6]['flag_reason'])
        self.assertEqual(self.rows[7]['confidence'], 'high')
        for value in [54674, 56334, 49692, 39428]:
            self.assertIn(str(value), self.rows[7]['evidence'])
        self.assertIn('new_first_time_college_entrants', self.rows[8]['evidence'])

    def test_reproducible_generated_output(self):
        output = Path(__file__).parent / 'output' / 'pilot-01-staging.json'
        self.assertTrue(output.exists(), 'Generate the private pilot output before this local test')
        self.assertEqual(load_json(output), self.rows)
        self.assertEqual(build_rows(self.candidates, self.current, self.sources), self.rows)


if __name__ == '__main__':
    unittest.main()
