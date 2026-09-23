"""No Google credentials/network. Transport tests use an injected fake Sheets service."""
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from sources import ValidationError, load_json
from staging import COLUMNS, build_rows
from staging_sync import ConflictError, plan_sync, snapshot, validate_rows
from staging_transport import (GoogleSheetsStaging, LiveWritesDisabled, MemoryStaging,
                               decode_grid, encode, write_request)
from upload_staging import dry_run
import test_pipeline as fixtures


class FakeCall:
    def __init__(self, result):
        self.result = result

    def execute(self):
        return self.result


class FakeSheets:
    def __init__(self, grid):
        self.grid = grid
        self.reads = []
        self.writes = []

    def spreadsheets(self):
        return self

    def values(self):
        return self

    def get(self, **kwargs):
        self.reads.append(kwargs)
        return FakeCall({'values': deepcopy(self.grid)})

    def batchUpdate(self, **kwargs):
        self.writes.append(kwargs)
        return FakeCall({})


@contextmanager
def fake_exclusive_window():
    # Test only. Not a real cross-client lock and never used against Google.
    yield


class SyncTests(unittest.TestCase):
    setUp = fixtures.PipelineTests.setUp
    save = fixtures.PipelineTests.save

    def row(self, **updates):
        row = build_rows([self.candidate], self.current, self.sources)[0]
        return {**row, **updates}

    def test_empty_staging_inserts(self):
        row = self.row()
        plan = plan_sync([row], snapshot([]))
        self.assertEqual(plan.actions[0].kind, 'INSERT')
        self.assertEqual(plan.actions[0].values, tuple(row[c] for c in COLUMNS))
        mock = MemoryStaging()
        mock.apply(plan)
        self.assertEqual(mock.read_staging().records(), [row])

    def test_pending_update_preserves_human_notes_and_status(self):
        old = self.row(review_notes='Human: check residency')
        candidate = self.row(candidate_value=200, review_notes='Machine refresh')
        mock = MemoryStaging([old])
        plan = plan_sync([candidate], mock.read_staging())
        self.assertEqual(plan.actions[0].kind, 'UPDATE')
        mock.apply(plan)
        actual = mock.read_staging().records()[0]
        self.assertEqual(actual['candidate_value'], 200)
        self.assertEqual(actual['status'], 'pending')
        self.assertEqual(actual['review_notes'], old['review_notes'])

    def test_noop_ignores_new_machine_notes(self):
        plan = plan_sync([self.row(review_notes='new machine note')],
                         snapshot([self.row(review_notes='human')]))
        self.assertEqual(plan.actions[0].kind, 'NOOP')
        self.assertEqual(write_request(plan)['data'], [])

    def test_approved_and_rejected_always_win(self):
        for status in ('approved', 'rejected'):
            old = self.row(status=status, review_notes='Reviewer decision')
            mock = MemoryStaging([old])
            plan = plan_sync([self.row(candidate_value=200)], mock.read_staging())
            self.assertEqual(plan.actions[0].kind, 'SKIP_' + status.upper())
            mock.apply(plan)
            self.assertEqual(mock.read_staging().records(), [old])
            self.assertEqual(mock.write_count, 0)

    def test_null_checked_date_is_not_upload_date(self):
        row = self.row(checked_date=None)
        plan = plan_sync([row], snapshot([self.row()]))
        self.assertIsNone(plan.actions[0].values[-1])
        request = write_request(plan)
        self.assertEqual(request['data'][1]['values'], [['']])
        self.assertIsNone(decode_grid([list(COLUMNS), encode(tuple(row[c] for c in COLUMNS))]).records()[0]['checked_date'])

    def test_zero_preserved_separately_from_null(self):
        row = self.row(candidate_value=0, current_value=None)
        result = decode_grid([list(COLUMNS), encode(tuple(row[c] for c in COLUMNS))]).records()[0]
        self.assertEqual(result['candidate_value'], 0)
        self.assertIsNone(result['current_value'])

    def test_missing_extra_columns_and_invalid_controls(self):
        bad_rows = [self.row(extra='x'), self.row(status='done'), self.row(confidence='certain'),
                    self.row(source_type='blog'), self.row(selection_rule='guess'),
                    self.row(candidate_value='100'), self.row(candidate_value=True),
                    self.row(candidate_value=float('nan')), self.row(academic_year='2026-28'),
                    self.row(checked_date='not-a-date'), self.row(checked_date='2026-02-30')]
        missing = self.row()
        del missing['evidence']
        bad_rows.append(missing)
        for bad in bad_rows:
            with self.subTest(bad=list(bad)), self.assertRaises(ValidationError):
                plan_sync([bad], snapshot([]))

    def test_incoming_approved_cannot_insert(self):
        with self.assertRaises(ValidationError):
            plan_sync([self.row(status='approved')], snapshot([]))

    def test_duplicate_keys_incoming_even_different_sources_rejected(self):
        with self.assertRaises(ValidationError):
            plan_sync([self.row(), self.row(source_name='Other original source')], snapshot([]))

    def test_duplicate_existing_keys_rejected(self):
        with self.assertRaises(ValidationError):
            snapshot([self.row(), self.row(status='approved')])

    def test_different_year_is_separate_identity(self):
        plan = plan_sync([self.row(academic_year='2027-28')], snapshot([self.row()]))
        self.assertEqual(plan.actions[0].kind, 'INSERT')

    def test_pending_to_approved_or_rejected_prevents_all_writes(self):
        for status in ('approved', 'rejected'):
            mock = MemoryStaging([self.row()])
            plan = plan_sync([self.row(candidate_value=200)], mock.read_staging())
            mock.replace_for_test([self.row(status=status)])
            with self.assertRaises(ConflictError):
                mock.apply(plan)
            self.assertEqual(mock.write_count, 0)
            self.assertEqual(mock.read_staging().records()[0]['status'], status)

    def test_changed_notes_deleted_or_inserted_rows_prevent_writes(self):
        for change in [[self.row(review_notes='new human edit')], [],
                       [self.row(), self.row(school_id='bu')]]:
            mock = MemoryStaging([self.row()])
            plan = plan_sync([self.row(candidate_value=200)], mock.read_staging())
            mock.replace_for_test(change)
            with self.assertRaises(ConflictError):
                mock.apply(plan)
            self.assertEqual(mock.write_count, 0)

    def test_forged_plan_cannot_update_review_notes(self):
        plan = plan_sync([self.row(candidate_value=200)], snapshot([self.row(review_notes='human')]))
        values = list(plan.actions[0].values)
        values[16] = 'machine erased human note'
        forged = replace(plan, actions=(replace(plan.actions[0], values=tuple(values)),))
        with self.assertRaises(ValidationError):
            write_request(forged)

    def test_google_adapter_default_blocks_writes(self):
        fake = FakeSheets([list(COLUMNS)])
        adapter = GoogleSheetsStaging(fake, 'fake-sheet-id')
        plan = plan_sync([self.row()], adapter.read_staging())
        with self.assertRaises(LiveWritesDisabled):
            adapter.apply(plan)
        self.assertEqual(fake.writes, [])

    def test_google_adapter_rechecks_status_in_fake_edit_window(self):
        fake = FakeSheets([list(COLUMNS), encode(tuple(self.row()[c] for c in COLUMNS))])
        adapter = GoogleSheetsStaging(fake, 'fake-sheet-id', exclusive_edit_window=fake_exclusive_window)
        plan = plan_sync([self.row(candidate_value=200)], adapter.read_staging())
        fake.grid[1][15] = 'approved'
        with self.assertRaises(ConflictError):
            adapter.apply(plan)
        self.assertEqual(fake.writes, [])

    def test_write_ranges_only_staging_and_exclude_human_columns(self):
        old = self.row(review_notes='Human note')
        grid = [list(COLUMNS), [], encode(tuple(old[c] for c in COLUMNS))]
        fake = FakeSheets(grid)
        adapter = GoogleSheetsStaging(fake, 'fake-sheet-id', exclusive_edit_window=fake_exclusive_window)
        plan = plan_sync([self.row(candidate_value=200), self.row(school_id='bu')], adapter.read_staging())
        adapter.apply(plan)
        self.assertEqual(len(fake.writes), 1)
        body = fake.writes[0]['body']
        self.assertEqual(body['valueInputOption'], 'RAW')
        self.assertEqual([d['range'] for d in body['data']], ["'Staging'!A3:O3", "'Staging'!R3", "'Staging'!A4:R4"])
        self.assertEqual(len(body['data'][2]['values'][0]), 18)
        self.assertTrue(all(r['range'] == "'Staging'" for r in fake.reads))

    def test_header_extra_columns_and_duplicate_sheet_keys_rejected(self):
        row = encode(tuple(self.row()[c] for c in COLUMNS))
        for grid in [[], [list(COLUMNS[:-1])], [list(COLUMNS) + ['extra']],
                     [list(reversed(COLUMNS))], [list(COLUMNS), row + ['extra']],
                     [list(COLUMNS), row, row]]:
            with self.assertRaises(ValidationError):
                decode_grid(grid)

    def test_literal_formula_text_sent_raw(self):
        plan = plan_sync([self.row(evidence='=NOT_A_FORMULA()')], snapshot([]))
        request = write_request(plan)
        self.assertEqual(request['valueInputOption'], 'RAW')
        self.assertEqual(request['data'][0]['values'][0][7], '=NOT_A_FORMULA()')

    def test_input_key_order_canonicalized_without_changing_values(self):
        row = self.row()
        reordered = dict(reversed(list(row.items())))
        self.assertEqual(plan_sync([reordered], snapshot([])).actions[0].values,
                         tuple(row[c] for c in COLUMNS))

    def test_dry_run_zero_writes_and_audit(self):
        self.save('incoming.json', [self.row()])
        with patch.object(MemoryStaging, 'apply', side_effect=AssertionError('No writes allowed')):
            plan, audit = dry_run(self.root / 'incoming.json')
        self.assertEqual(len(audit['inserts']), 1)
        self.assertEqual(audit['validation_errors'], [])
        self.assertIn('timestamp', audit)
        self.assertEqual(audit['input_file'], str(self.root / 'incoming.json'))
        self.assertEqual(audit['mode'], 'dry_run')

    def test_dry_run_validates_existing_and_reports_errors(self):
        self.save('incoming.json', [self.row()])
        self.save('existing.json', [self.row(), self.row()])
        plan, audit = dry_run(self.root / 'incoming.json', self.root / 'existing.json')
        self.assertIsNone(plan)
        self.assertEqual(len(audit['validation_errors']), 1)
        self.assertEqual(audit['inserts'], [])

    def test_dry_run_sanitizes_json_parser_errors(self):
        (self.root / 'bad.json').write_text('{"secret-test-sentinel":1,"secret-test-sentinel":2}')
        _, audit = dry_run(self.root / 'bad.json')
        self.assertNotIn('secret-test-sentinel', json.dumps(audit))

    def test_new_pipeline_review_notes_allowed_and_existing_null_preserved(self):
        new = self.row(review_notes='Machine comparison explanation from pipeline')
        insert = plan_sync([new], snapshot([])).actions[0]
        self.assertEqual(insert.values[16], new['review_notes'])
        update = plan_sync([new], snapshot([self.row(candidate_value=50, review_notes=None)])).actions[0]
        self.assertIsNone(update.values[16])

    def test_cli_writes_audit_only_and_rejects_output_elsewhere(self):
        app = self.root / 'research'
        app.mkdir()
        for name in ['sources.py', 'staging.py', 'staging_sync.py', 'staging_transport.py', 'upload_staging.py']:
            shutil.copyfile(Path(__file__).parent / name, app / name)
        self.save('incoming.json', [self.row()])
        command = [sys.executable, '-B', str(app / 'upload_staging.py'), '--dry-run',
                   '--input', str(self.root / 'incoming.json'), '--report', str(app / 'output' / 'audit.json')]
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('INSERT nyu tuition 2026-27', result.stdout)
        self.assertEqual(len(load_json(app / 'output' / 'audit.json')['inserts']), 1)
        self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
        command[-1] = str(self.root / 'school.csv')
        self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
        self.assertFalse((self.root / 'school.csv').exists())
        command[-1] = str(app / 'output' / 'invalid.json')
        self.save('incoming.json', [self.row(extra=True)])
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(load_json(app / 'output' / 'invalid.json')['validation_errors']), 1)


PILOT = Path(__file__).parent / 'output' / 'pilot-01-staging.json'


@unittest.skipUnless(PILOT.exists(), 'Private pilot output not installed')
class PilotSyncTests(unittest.TestCase):
    def test_all_nine_pilot_rows_insert_without_loss(self):
        rows = load_json(PILOT)
        mock = MemoryStaging()
        plan = plan_sync(rows, mock.read_staging())
        self.assertEqual(len(plan.actions), 9)
        self.assertTrue(all(a.kind == 'INSERT' for a in plan.actions))
        mock.apply(plan)
        self.assertEqual(mock.read_staging().records(), rows)
        self.assertTrue(all(r['checked_date'] is None for r in mock.read_staging().records()))
        second = plan_sync(rows, mock.read_staging())
        self.assertTrue(all(a.kind == 'NOOP' for a in second.actions))

    def test_mixed_pilot_actions(self):
        rows = load_json(PILOT)
        existing = deepcopy(rows[:4])
        existing[0]['candidate_value'] = 1
        existing[0]['review_notes'] = 'Human note'
        existing[1]['status'] = 'approved'
        existing[2]['status'] = 'rejected'
        plan = plan_sync(rows, snapshot(existing))
        self.assertEqual([a.kind for a in plan.actions[:4]], ['UPDATE', 'SKIP_APPROVED', 'SKIP_REJECTED', 'NOOP'])
        self.assertEqual(plan.actions[0].values[16], 'Human note')


if __name__ == '__main__':
    unittest.main()
