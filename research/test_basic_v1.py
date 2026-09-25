import copy
import unittest
from unittest.mock import Mock
from test_school_publish import fixtures, Database
from school_publish import COLUMNS, FIELDS, plan_publish, PostgresSchools, read_school
from school_cli_transport import SupabaseSchools, PROJECT
from sources import ValidationError

class BasicTests(unittest.TestCase):
    def setUp(self):
        self.master,self.baseline=fixtures()
        self.baseline['database_id']=PROJECT

    def test_40_fields_no_derived_or_deep(self):
        self.assertEqual(len(COLUMNS),40)
        self.assertFalse(set(COLUMNS)&{'region','location_cn','ranking_tier','campus_type','gpa_year'})

    def test_arrays_frozen_and_null_not_empty(self):
        self.master['rows'][0]['english_tests_accepted']=['IELTS']
        plan=plan_publish(self.master,self.baseline)
        self.master['rows'][0]['english_tests_accepted'].append('TOEFL')
        self.assertEqual(plan.report()['after'][0]['english_tests_accepted'],['IELTS'])
        self.master['rows'][0]['english_tests_accepted']=[]
        self.assertEqual(plan_publish(self.master,self.baseline).report()['changes'][0]['changes']['english_tests_accepted'],{'before':None,'after':[]})

    def test_invalid_classification_percent_array(self):
        for field,value in [('school_type','私立大学'),('international_pct',True),('international_pct',100.01),('acceptance_rate','9'),('graduation_rate_4yr',0.001),('english_tests_accepted','[]'),('english_tests_accepted',['IELTS','IELTS']),('english_tests_accepted',[None]),('ranking_usnews',0)]:
            with self.subTest(field=field,value=value):
                master=copy.deepcopy(self.master);master['rows'][0][field]=value
                with self.assertRaises(ValidationError):plan_publish(master,self.baseline)

    def test_metadata_and_official_rate_not_recomputed(self):
        self.master['rows'][0].update(applicants=114125,admitted=10340,acceptance_rate=9,admissions_year='Fall 2025',english_policy_cycle=None)
        row=plan_publish(self.master,self.baseline).report()['after'][0]
        self.assertEqual(row['acceptance_rate'],9)
        self.assertIsNone(row['english_policy_cycle'])

    def test_sheet_array_and_reordered_headers(self):
        service=Mock();headers=list(reversed(COLUMNS))+['gpa_year']
        r=self.master['rows'][0];r['english_tests_accepted']='["IELTS","TOEFL"]'
        service.spreadsheets().values().get().execute.return_value={'values':[headers,[r[f] for f in reversed(COLUMNS)]+['preserved']]}
        result=read_school(service,'sheet')
        self.assertEqual(result['rows'][0]['english_tests_accepted'],['IELTS','TOEFL'])
        self.assertNotIn('gpa_year',result['rows'][0])

    def test_all_new_fields_are_published_and_verified(self):
        self.master['rows'][0].update(institution_control='public',sat_25=None,international_merit_aid='yes',english_tests_accepted=['IELTS'])
        db=Database(self.baseline['rows']);transport=PostgresSchools(lambda:db,PROJECT)
        plan=plan_publish(self.master,self.baseline)
        transport.apply(plan,approved_digest=plan.report()['approval_digest'],current_master=self.master)
        self.assertEqual(db.rows,self.master['rows'])

    def test_cli_plan_guards_before_query(self):
        query=Mock();transport=SupabaseSchools(query)
        plan=plan_publish(self.master,self.baseline)
        with self.assertRaises(ValidationError):transport.apply(plan,approved_digest='',current_master=self.master)
        changed=copy.deepcopy(self.master);changed['rows'][0]['city']='Different'
        with self.assertRaises(ValidationError):transport.apply(plan,approved_digest=plan.report()['approval_digest'],current_master=changed)
        query.assert_not_called()

    def test_cli_payload_kept_outside_sql_body(self):
        self.master['rows'][0]['city']="City ' $guard$ ; --"
        plan=plan_publish(self.master,self.baseline);query=Mock(return_value=[{'result':{'updated':3}}])
        self.assertEqual(SupabaseSchools(query).apply(plan,approved_digest=plan.report()['approval_digest'],current_master=self.master),3)
        sql=query.call_args.args[0]
        self.assertIn("City '' $guard$ ; --",sql)
        self.assertIn('FOR UPDATE',sql)
        self.assertIn('IS DISTINCT FROM',sql)
        self.assertNotIn('gpa_',sql)
        self.assertNotIn('DELETE ',sql)

    def test_cli_read_only_and_scope(self):
        q=Mock(return_value=[{'record':r} for r in self.master['rows']]);t=SupabaseSchools(q)
        t.read(['nyu','bu','ucb']);self.assertTrue(q.call_args.args[0].startswith('BEGIN READ ONLY'))
        with self.assertRaises(ValidationError):t.read(['other'])
