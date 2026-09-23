"""Synthetic fixtures only: no researched or approved production values."""
import copy
from contextlib import contextmanager
from decimal import Decimal
import unittest
import subprocess
import sys
import tempfile
import json
from pathlib import Path
from unittest.mock import Mock

from sources import ValidationError
from school_publish import (COLUMNS, FIELDS, SELECT_SQL, UPDATE_SQL, PostgresSchools,
                            master_snapshot, plan_publish, read_school, records)


def row(sid, value=10):
    return dict(zip(COLUMNS, (sid, value, '2026-27' if value is not None else None,
                             value, '2026-27' if value is not None else None, value)))


def fixtures():
    master = {'source_tab': 'School', 'spreadsheet_id': 'synthetic-sheet',
              'rows': [row(sid) for sid in ('nyu', 'bu', 'ucb')]}
    database = {'target': 'private.schools', 'database_id': 'synthetic-project',
                'rows': [row(sid, None) for sid in ('nyu', 'bu', 'ucb')]}
    return master, database


class Database:
    autocommit = True

    def __init__(self, rows):
        self.rows = copy.deepcopy(rows)
        self.calls = []
        self.fail_update = False
        self.rowcount = 0
        self.unrelated = {'school_name': 'preserved', 'city': 'preserved'}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    @contextmanager
    def transaction(self):
        before = copy.deepcopy(self.rows)
        try:
            yield
        except Exception:
            self.rows = before
            raise

    def cursor(self):
        return self

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        if sql.startswith(SELECT_SQL):
            self.selected = [r for r in self.rows if r['school_id'] in params[0]]
        elif sql == UPDATE_SQL:
            if self.fail_update and params[-1] == 'bu':
                raise RuntimeError('synthetic failure')
            self.rowcount = 0
            for r in self.rows:
                if r['school_id'] == params[-1]:
                    r.update(dict(zip(FIELDS, params[:-1])))
                    self.rowcount += 1

    def fetchall(self):
        return [tuple(r[c] for c in COLUMNS) for r in self.selected]


class PublisherTests(unittest.TestCase):
    def setUp(self):
        self.master, self.database = fixtures()
        self.db = Database(self.database['rows'])
        self.connect = Mock(return_value=self.db)
        self.transport = PostgresSchools(self.connect, 'synthetic-project')

    def plan(self):
        return plan_publish(self.master, self.database)

    def apply(self, plan=None, **kwargs):
        plan = plan or self.plan()
        return self.transport.apply(plan, approved_digest=kwargs.get('digest', plan.report()['approval_digest']),
                                    current_master=kwargs.get('master', self.master))

    def test_exact_diff(self):
        report = self.plan().report()
        self.assertEqual([r['school_id'] for r in report['changes']], ['nyu', 'bu', 'ucb'])
        self.assertEqual(report['changes'][0]['changes']['tuition'], {'before': None, 'after': 10})
        self.assertEqual(set(report['changes'][0]['changes']), set(FIELDS))
        self.connect.assert_not_called()

    def test_unchanged(self):
        self.database['rows'] = copy.deepcopy(self.master['rows'])
        report = self.plan().report()
        self.assertEqual(report['changes'], [])
        self.assertEqual(report['unchanged'], ['nyu', 'bu', 'ucb'])

    def test_null_clears_and_zero_survives(self):
        self.master['rows'][0] = row('nyu', None)
        self.database['rows'][0] = row('nyu', 0)
        self.assertEqual(self.plan().report()['changes'][0]['changes']['tuition'],
                         {'before': 0, 'after': None})
        self.master['rows'][0] = row('nyu', 0)
        self.database['rows'][0] = row('nyu', None)
        self.assertEqual(self.plan().report()['changes'][0]['changes']['tuition']['after'], 0)

    def test_invalid_values(self):
        for value in (True, '10', '', -1, float('nan'), float('inf'), 1.001, 10000000000):
            with self.subTest(value=value):
                self.master, self.database = fixtures()
                self.master['rows'][0]['tuition'] = value
                with self.assertRaises(ValidationError):
                    self.plan()

    def test_invalid_enrollment(self):
        for value in (1.5, 1.0, True, '1', 2147483648):
            self.master['rows'][0]['first_year_enrollment'] = value
            with self.assertRaises(ValidationError):
                self.plan()

    def test_missing_and_unknown_fields(self):
        for field in ('school_name', 'undergrad_enrollment', 'status', 'tuition;DROP TABLE schools'):
            self.master, self.database = fixtures()
            self.master['rows'][0][field] = 'forbidden'
            with self.assertRaises(ValidationError):
                self.plan()
        self.master, self.database = fixtures()
        del self.master['rows'][0]['coa']
        with self.assertRaises(ValidationError):
            self.plan()

    def test_unknown_duplicate_blank_school(self):
        for sid in ('other', '', ' nyu ', None, ['nyu'], 'bu'):
            self.master, self.database = fixtures()
            self.master['rows'][0]['school_id'] = sid
            with self.assertRaises(ValidationError):
                self.plan()

    def test_staging_forbidden(self):
        self.master['source_tab'] = 'Staging'
        with self.assertRaises(ValidationError):
            self.plan()

    def test_year_validation(self):
        for value in ('2026', '2026-28', '', None):
            self.master['rows'][0]['tuition_year'] = value
            with self.assertRaises(ValidationError):
                self.plan()

    def test_null_amount_with_year_rejected(self):
        self.master['rows'][0]['tuition'] = None
        with self.assertRaises(ValidationError):
            self.plan()

    def test_missing_target_no_insert(self):
        self.database['rows'].pop()
        with self.assertRaises(ValidationError):
            self.plan()

    def test_input_order_does_not_change_plan(self):
        expected = self.plan()
        self.master['rows'].reverse()
        self.database['rows'].reverse()
        self.assertEqual(self.plan(), expected)

    def test_fixed_parameterized_updates_preserve_unrelated(self):
        self.assertEqual(self.apply(), 3)
        self.assertEqual(self.db.rows, self.master['rows'])
        self.assertEqual(self.db.unrelated, {'school_name': 'preserved', 'city': 'preserved'})
        updates = [call for call in self.db.calls if call[0].startswith('UPDATE')]
        self.assertEqual(len(updates), 3)
        self.assertTrue(all(sql == UPDATE_SQL and len(params) == 6 for sql, params in updates))
        self.assertTrue(any(sql.endswith('FOR UPDATE') for sql, _ in self.db.calls))

    def test_idempotent_noop_has_no_updates(self):
        self.apply()
        self.database['rows'] = copy.deepcopy(self.db.rows)
        self.db.calls.clear()
        self.assertEqual(self.apply(), 0)
        self.assertFalse(any(sql.startswith('UPDATE') for sql, _ in self.db.calls))

    def test_approval_required_before_connection(self):
        with self.assertRaises(ValidationError):
            self.apply(digest='')
        self.connect.assert_not_called()

    def test_stale_database_aborts_before_updates(self):
        self.db.rows[1]['first_year_enrollment'] = 99
        with self.assertRaises(ValidationError):
            self.apply()
        self.assertFalse(any(sql.startswith('UPDATE') for sql, _ in self.db.calls))

    def test_changed_master_aborts_before_connection(self):
        master = copy.deepcopy(self.master)
        master['rows'][0]['first_year_enrollment'] = 99
        with self.assertRaises(ValidationError):
            self.apply(master=master)
        self.connect.assert_not_called()

    def test_wrong_target_aborts(self):
        self.transport.database_id = 'different-project'
        with self.assertRaises(ValidationError):
            self.apply()
        self.connect.assert_not_called()

    def test_transaction_rolls_back_partial_batch(self):
        before = copy.deepcopy(self.db.rows)
        self.db.fail_update = True
        with self.assertRaises(RuntimeError):
            self.apply()
        self.assertEqual(self.db.rows, before)

    def test_read_is_read_only_and_decimal_supported(self):
        self.db.rows[0]['tuition'] = Decimal('10.25')
        snapshot = self.transport.read(['nyu', 'bu', 'ucb'])
        self.assertEqual(snapshot['rows'][0]['tuition'], 10.25)
        self.assertEqual(self.db.calls[0][0], 'SET TRANSACTION READ ONLY')
        self.assertFalse(any(sql.startswith('UPDATE') for sql, _ in self.db.calls))

    def test_subset_does_not_touch_other_schools(self):
        self.master['rows'] = self.master['rows'][:1]
        self.assertEqual(self.apply(), 1)
        self.assertEqual(self.db.rows[1], self.database['rows'][1])

    def test_sheet_reader_projects_only_school(self):
        service = Mock()
        grid = [list(COLUMNS) + ['unrelated'],
                ['nyu', 0, '2026-27', '', '', '', 'preserved']]
        service.spreadsheets().values().get().execute.return_value = {'values': grid}
        result = read_school(service, 'synthetic-sheet')
        self.assertEqual(result['rows'][0]['tuition'], 0)
        self.assertIsNone(result['rows'][0]['coa'])
        self.assertEqual(set(result['rows'][0]), set(COLUMNS))
        self.assertEqual(service.spreadsheets().values().get.call_args.kwargs['range'], "'School'")
        service.spreadsheets().values().batchUpdate.assert_not_called()

    def test_sheet_reader_rejects_missing_header(self):
        service = Mock()
        service.spreadsheets().values().get().execute.return_value = {'values': [['school_id'], ['nyu']]}
        with self.assertRaises(ValidationError):
            read_school(service, 'synthetic-sheet')

    def test_sheet_unknown_school_rejected(self):
        service = Mock()
        service.spreadsheets().values().get().execute.return_value = {
            'values': [list(COLUMNS), ['unknown', 10, '2026-27', 10, '2026-27', 10]]}
        with self.assertRaises(ValidationError):
            read_school(service, 'synthetic-sheet')

    def test_cli_dry_run(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'master.json').write_text(json.dumps(self.master))
            (root / 'database.json').write_text(json.dumps(self.database))
            result = subprocess.run([sys.executable, '-B',
                str(Path(__file__).with_name('publish_school.py')),
                '--master', str(root / 'master.json'), '--database', str(root / 'database.json'),
                '--dry-run'], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), self.plan().report())
            self.assertEqual(json.loads((root / 'master.json').read_text()), self.master)
            self.assertEqual(json.loads((root / 'database.json').read_text()), self.database)


if __name__ == '__main__':
    unittest.main()
