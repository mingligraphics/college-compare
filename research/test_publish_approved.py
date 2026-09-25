import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

import test_school_publish as fixtures
from school_publish import PostgresSchools, plan_publish
from sources import ValidationError
import publish_approved as cli


class ProductionCLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.master, self.baseline = fixtures.fixtures()
        self.baseline['database_id'] = cli.PROJECT
        self.master['spreadsheet_id'] = cli.SPREADSHEET
        self.db = fixtures.Database(self.baseline['rows'])
        self.transport = PostgresSchools(lambda: self.db, cli.PROJECT)
        self.factory = Mock(return_value=self.transport)
        self.expected = {r['school_id']: r for r in self.master['rows']}
        self.api = Mock(side_effect=lambda a, b: [self.expected[a], self.expected[b]])
        self.output = []
        self.digest = plan_publish(self.master, self.baseline).report()['approval_digest']
        self.save()

    def save(self):
        for name, value in [('approved-school.json', self.master),
                            ('current-private-schools.json', self.baseline), ('current-school.json',self.master)]:
            (self.folder / name).write_text(json.dumps(value))

    def run_cli(self):
        return cli.run(self.folder, self.factory, self.api, self.output.append, self.digest)

    def test_success_uses_existing_atomic_publisher(self):
        self.assertEqual(self.run_cli(), 0)
        self.assertEqual(self.db.rows, self.master['rows'])
        self.assertEqual(self.api.call_args_list, [unittest.mock.call(*p) for p in cli.PAIRS])
        self.assertTrue(any(sql.endswith('FOR UPDATE') for sql, _ in self.db.calls))
        self.assertIn('Database readback: PASS (120/120 fields)', self.output)

    def test_digest_mismatch_never_connects(self):
        self.master['rows'][0]['first_year_enrollment'] = 20
        self.save()
        self.assertEqual(self.run_cli(), 1)
        self.factory.assert_not_called()

    def test_wrong_project(self):
        self.baseline['database_id'] = 'other'
        self.digest = plan_publish(self.master, self.baseline).report()['approval_digest']
        self.save()
        self.assertEqual(self.run_cli(), 1)
        self.factory.assert_not_called()

    def test_subset_rejected(self):
        self.master['rows'].pop()
        self.digest = plan_publish(self.master, self.baseline).report()['approval_digest']
        self.save()
        self.assertEqual(self.run_cli(), 1)
        self.factory.assert_not_called()

    def test_live_baseline_mismatch(self):
        self.db.rows[0]['first_year_enrollment'] = 3
        self.assertEqual(self.run_cli(), 1)
        self.assertFalse(any(sql.startswith('UPDATE') for sql, _ in self.db.calls))

    def test_locked_baseline_mismatch(self):
        original = self.transport.apply
        def race(*args, **kwargs):
            self.db.rows[0]['first_year_enrollment'] = 3
            return original(*args, **kwargs)
        self.transport.apply = race
        self.assertEqual(self.run_cli(), 1)
        self.assertFalse(any(sql.startswith('UPDATE') for sql, _ in self.db.calls))
        self.assertIn('STOP BEFORE COMMIT', self.output[-1])

    def test_transaction_failure_rolls_back_and_reports_uncertainty(self):
        self.db.fail_update = True
        self.assertEqual(self.run_cli(), 2)
        self.assertEqual(self.db.rows, self.baseline['rows'])
        self.assertIn('COMMIT OUTCOME UNKNOWN', self.output[-1])
        self.api.assert_not_called()

    def test_post_commit_read_failure_still_checks_all_api_pairs(self):
        original = self.transport.read
        self.transport.read = Mock(side_effect=[original(list(cli.IDS)), RuntimeError('secret')])
        self.assertEqual(self.run_cli(), 3)
        self.assertEqual(self.api.call_count, 3)
        self.assertEqual(self.db.rows, self.master['rows'])
        self.assertNotIn('secret', str(self.output))
        self.assertIn('STOP AFTER COMMIT', self.output[-1])

    def test_api_mismatch_reports_field_without_repair(self):
        bad = copy.deepcopy(self.expected['nyu'])
        bad['tuition_fees'] = 'secret-response-content'
        self.api.side_effect = lambda a, b: [bad if a == 'nyu' else self.expected[a], self.expected[b]]
        self.assertEqual(self.run_cli(), 3)
        self.assertIn('nyu.tuition_fees', str(self.output))
        self.assertNotIn('secret-response-content', str(self.output))
        self.assertEqual(self.db.rows, self.master['rows'])
        self.assertEqual(self.api.call_count, 3)

    def test_api_failure_sanitized(self):
        self.api.side_effect = RuntimeError('postgresql://secret')
        self.assertEqual(self.run_cli(), 3)
        self.assertNotIn('postgresql://secret', str(self.output))
        self.assertEqual(self.api.call_count, 3)

    def test_connection_failure_sanitized(self):
        self.factory.side_effect = RuntimeError('postgresql://secret')
        self.assertEqual(self.run_cli(), 1)
        self.assertNotIn('postgresql://secret', str(self.output))

    def test_connection_target_validation(self):
        cli.validate_connection({'host': 'db.' + cli.PROJECT + '.supabase.co', 'dbname': 'postgres'})
        cli.validate_connection({'host': 'aws-0-us-east-1.pooler.supabase.com',
                                 'user': 'postgres.' + cli.PROJECT, 'dbname': 'postgres'})
        for params in [
            {'host': 'db.other.supabase.co', 'dbname': 'postgres'},
            {'host': 'aws-0-us-east-1.pooler.supabase.com', 'user': 'postgres.other', 'dbname': 'postgres'},
            {'host': 'db.' + cli.PROJECT + '.supabase.co', 'dbname': 'wrong'},
            {'host': 'db.' + cli.PROJECT + '.supabase.co', 'dbname': 'postgres', 'hostaddr': '127.0.0.1'},
        ]:
            with self.assertRaises(ValidationError):
                cli.validate_connection(params)
