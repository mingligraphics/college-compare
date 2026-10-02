import copy,unittest
from incremental_publish import *
import test_incremental_publish as fixtures
class BundleTests(unittest.TestCase):
 def setUp(self):
  self.fixture=fixtures.IncrementalTests();self.fixture.setUp();self.rows=copy.deepcopy(self.fixture.rows)
  for r in self.rows:r.update(dict.fromkeys(OPTIONAL_COLUMNS));r.update(city='Verified city',state='IN',undergrad_enrollment=100,undergrad_enrollment_year='Fall 2023',international_pct=10,international_pct_year='Fall 2023',international_pct_scope='undergraduate',acceptance_rate=20,admissions_year='Fall 2023',region='midwest')
  self.a=copy.deepcopy(self.fixture.approval);self.a.update(contract_columns=list(FULL_COLUMNS),initial_publication_threshold={'rule':BUNDLE_RULE,'required_fields':list(BUNDLE_FIELDS),'required_metadata':list(BUNDLE_METADATA),'unresearched_nulls_allowed':True,'preserve_other_null_categories':True,'historical_values_allowed':True},null_classifications={r['school_id']:{f:'unresearched' for f in FULL_COLUMNS if r[f] is None} for r in self.rows},deferred_fields={r['school_id']:[f for f in FULL_COLUMNS if r[f] is None] for r in self.rows},payload_digest=digest(self.rows))
  self.pairs=[]
  for r in self.rows:
   for f in FULL_COLUMNS:
    base={'production_id':r['school_id'],'research_id':self.a['identities'][r['school_id']]['research_id'],'field':f,'value':r[f],'definition_version':field_definition(f),'scope':'Fixture scope','method':'official_reported','checked_date':'2026-10-02','locator':'synthetic authoritative fixture','original_null_category':'unresearched_null' if r[f] is None else ''};rid=r['school_id']+'-'+f
    self.pairs.append({'staging':{**base,'record_id':rid+'s','related_record_id':rid+'r'},'source':{**base,'record_id':rid+'r','related_record_id':rid+'s'},'decision':{'outcome':'supported_value' if r[f] is not None else 'tracked_null','null_category':'unresearched' if r[f] is None else '', 'reason':'Explicit fixture bundle approval, no intentional-blank assertion'},'attachments':self.fixture.pairs[0]['attachments']})
  self.a['evidence_digest']=digest(self.pairs);self.master={**self.fixture.master,'rows':self.rows}
 def tearDown(self):self.fixture.tearDown()
 def test_supported_bundle_with_unresearched_policy_and_cost_nulls(self):
  self.assertEqual(selected_rows(self.rows,self.a),self.rows);self.assertTrue(verify_provenance(self.rows,self.pairs,self.a))
  p=publication_plan(self.master,self.fixture.before,self.a,self.pairs);s=build_sql(p,p['plan_digest'],rollback=True);self.assertTrue(s.endswith('ROLLBACK;'));self.assertIn('location_cn,region',s);self.assertEqual(p['expected_rows'][0]['region'],'midwest');self.assertEqual(p['expected_rows'][-1],self.fixture.before['rows'][0])
 def test_missing_bundle_field_or_metadata_is_not_waived(self):
  for f in (*BUNDLE_FIELDS,*BUNDLE_METADATA):
   r=copy.deepcopy(self.rows);r[0][f]=None;a=copy.deepcopy(self.a);a['payload_digest']=digest(r)
   with self.assertRaises(ValueError):selected_rows(r,a)
 def test_no_global_approval_cannot_relax_core_nulls(self):
  a=copy.deepcopy(self.a);del a['initial_publication_threshold'];del a['contract_columns'];a['payload_digest']=digest([{f:r[f] for f in PUBLISH_COLUMNS} for r in self.rows])
  with self.assertRaises(ValueError):verify_provenance(self.rows,self.pairs,a)
 def test_unresearched_cannot_be_relabeled_as_intentional_or_source_absence(self):
  for category in ('approved_intentional_blank','not_reported_in_examined_source','not_applicable_in_examined_source'):
   pairs=copy.deepcopy(self.pairs);p=next(p for p in pairs if p['staging']['field']=='test_policy');p['decision']['null_category']=category;a=copy.deepcopy(self.a);a['null_classifications'][p['staging']['production_id']]['test_policy']=category;a['evidence_digest']=digest(pairs)
   with self.assertRaises(ValueError):verify_provenance(self.rows,pairs,a)
 def test_existing_conflict_null_can_be_preserved(self):
  p=copy.deepcopy(self.pairs);c=next(v for v in p if v['staging']['field']=='coa');c['staging']['original_null_category']=c['source']['original_null_category']='conflict';c['decision']['null_category']='conflict';a=copy.deepcopy(self.a);a['null_classifications'][c['staging']['production_id']]['coa']='conflict';a['evidence_digest']=digest(p);self.assertTrue(verify_provenance(self.rows,p,a))
 def test_threshold_cannot_drop_required_values_or_expand_sql_columns(self):
  for change in ('fields','contract','policy'):
   a=copy.deepcopy(self.a)
   if change=='fields':a['initial_publication_threshold']['required_fields'].pop()
   elif change=='contract':a['contract_columns'].append('unapproved_column')
   else:a['initial_publication_threshold']['preserve_other_null_categories']=False
   with self.assertRaises(ValueError):selected_rows(self.rows,a)
 def test_classification_manifest_must_cover_exact_null_fields(self):
  a=copy.deepcopy(self.a);a['null_classifications']['notre_dame'].pop('test_policy')
  with self.assertRaises(ValueError):selected_rows(self.rows,a)
 def test_additional_existing_schema_values_remain_typed(self):
  for f,v in [('region','unknown_region'),('campus_description',42),('famous_majors','not an array'),('famous_majors',[None])]:
   r=copy.deepcopy(self.rows);r[0][f]=v;a=copy.deepcopy(self.a);a['payload_digest']=digest(r);a['null_classifications']['notre_dame'].pop(f,None)
   with self.assertRaises(ValueError):selected_rows(r,a)
if __name__=='__main__':unittest.main()
