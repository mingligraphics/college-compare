import copy,json,tempfile,unittest
from pathlib import Path
from incremental_publish import *
from t1_publish import selected_rows as entry_select, build_sql as entry_sql

class IncrementalTests(unittest.TestCase):
 def setUp(self):
  self.ids=['notre_dame','penn_state'];self.temp=tempfile.TemporaryDirectory();self.file=Path(self.temp.name)/'evidence.txt';self.file.write_text('synthetic authoritative fixture');sha=__import__('hashlib').sha256(self.file.read_bytes()).hexdigest()
  self.rows=[{**dict.fromkeys(PUBLISH_COLUMNS),'school_id':s,'school_name':s,'tuition_fees':100,'tuition_fees_year':'2026-27','coa':200,'coa_year':'2026-27'} for s in self.ids]
  self.pairs=[]
  for row in self.rows:
   for f in PUBLISH_COLUMNS:
    rid=f"{row['school_id']}-{f}";base={'production_id':row['school_id'],'research_id':'US-152080' if row['school_id']=='notre_dame' else 'US-214777','field':f,'value':row[f],'definition_version':('signature_programs_v1' if f=='signature_programs' else 'basic_v1'),'scope':'synthetic undergraduate scope','method':'direct','checked_date':'2026-10-02','locator':'fixture'}
    self.pairs.append({'staging':{**base,'record_id':rid+'s','related_record_id':rid+'r'},'source':{**base,'record_id':rid+'r','related_record_id':rid+'s'},'decision':{'outcome':'supported_value' if row[f] is not None else 'approved_intentional_blank' if f in CORE else 'authorized_nonblocking_null','reason':'explicit approved fixture blank'},'attachments':[{'path':str(self.file),'sha256':sha}]})
  self.approval={'rule':RULE,'actor':'Human fixture','instruction':'Explicit fixture subset approval','execution_authorized':True,'school_ids':self.ids,'identities':{s:{'school_name':s,'research_id':'US-152080' if s=='notre_dame' else 'US-214777'} for s in self.ids},'operations':dict.fromkeys(self.ids,'insert'),'spreadsheet_id':SPREADSHEET,'database_id':PROJECT,'payload_digest':digest(self.rows),'evidence_digest':digest(self.pairs),'deferred_fields':{s:[f for f in PUBLISH_COLUMNS if f not in CORE] for s in self.ids}}
  self.schema=json.loads((Path(__file__).parent/'testdata/incremental-schema.json').read_text());names=[c['column_name'] for c in self.schema['columns']]
  self.before={'rows':[{**dict.fromkeys(names),'school_id':'unrelated','school_name':"O'Brien $guard$"}],'schema':self.schema}
  self.master={'source_tab':'School','spreadsheet_id':SPREADSHEET,'allocated_row_count':1000,'read_row_count':1000,'rows':copy.deepcopy(self.rows)}
 def tearDown(self):self.temp.cleanup()
 def plan(self):return publication_plan(self.master,self.before,self.approval,self.pairs)
 def test_two_school_entry_point_without_T1_batch(self):
  self.assertEqual(entry_select(self.rows,approval=self.approval),self.rows)
  p=self.plan();sql=entry_sql(self.rows,self.before,approval=self.approval,master=self.master,provenance=self.pairs,approved_digest=p['plan_digest'],rollback=True)
  self.assertIn("'inserted',2",sql);self.assertTrue(sql.endswith('ROLLBACK;'));self.assertNotIn('ALTER TABLE',sql);self.assertNotIn('ON CONFLICT',sql)
 def test_no_approval_does_not_enable_incremental(self):
  with self.assertRaises(ValueError):entry_select(self.rows)
 def test_empty_duplicate_extra_or_missing_scope(self):
  for ids in ([],['notre_dame','notre_dame'],['notre_dame']):
   a=copy.deepcopy(self.approval);a['school_ids']=ids
   with self.assertRaises(ValueError):selected_rows(self.rows,a)
  for rows in (self.rows[:1],self.rows+[copy.deepcopy(self.rows[0])],self.rows+[dict(self.rows[0],school_id='wisconsin')]):
   with self.assertRaises(ValueError):selected_rows(rows,self.approval)
 def test_approval_value_and_name_drift(self):
  for f,v in [('coa',300),('school_name','different institution')]:
   r=copy.deepcopy(self.rows);r[0][f]=v
   with self.assertRaises(ValueError):selected_rows(r,self.approval)
 def test_schema_type_and_existing_constraints_preserved(self):
  for mutate in (lambda s:s['columns'].pop(),lambda s:s['triggers'].append({'name':'unexpected'}),lambda s:s['constraints'].__setitem__(slice(None),[c for c in s['constraints'] if c['name']!='gpa_bounds_v2'])):
   s=copy.deepcopy(self.schema);mutate(s)
   with self.assertRaises(ValueError):validate_schema(s)
 def test_invalid_scalar_enum_pair_and_gpa(self):
  for changes in ({'international_need_aid':'maybe'},{'coa_year':None},{'sat_25':1400,'sat_75':1300},{'acceptance_rate':True},{'gpa_unweighted_25':4.1},{'gpa_unweighted_25':4,'gpa_unweighted_75':3}):
   r=copy.deepcopy(self.rows);r[0].update(changes);a=copy.deepcopy(self.approval);a['payload_digest']=digest(r)
   with self.assertRaises(ValueError):selected_rows(r,a)
 def test_signature_deferral_must_be_explicit_and_nonnull_still_validated(self):
  a=copy.deepcopy(self.approval);a['deferred_fields'][self.ids[0]].remove('signature_programs')
  with self.assertRaises(ValueError):selected_rows(self.rows,a)
  r=copy.deepcopy(self.rows);r[0]['signature_programs']=[];a=copy.deepcopy(self.approval);a['payload_digest']=digest(r)
  with self.assertRaises(ValueError):selected_rows(r,a)
 def test_nonreciprocal_ID_mapping(self):
  a=copy.deepcopy(self.approval);a['identities']['penn_state']['research_id']='US-152080'
  with self.assertRaises(ValueError):approved_ids(a)
 def test_missing_master_promotion_or_complete_scan(self):
  for m in ({**self.master,'rows':self.rows[:1]},{**self.master,'read_row_count':100}):
   with self.assertRaises(ValueError):publication_plan(m,self.before,self.approval,self.pairs)
 def test_collision_and_replay_do_not_upsert(self):
  b=copy.deepcopy(self.before);b['rows'].append({**dict.fromkeys(b['rows'][0]),**self.rows[0]})
  with self.assertRaises(ValueError):publication_plan(self.master,b,self.approval,self.pairs)
 def test_mismatched_provenance_or_stale_approval(self):
  for mutate in (lambda p:p[0]['source'].update(scope='wrong'),lambda p:p.pop(),lambda p:p[0]['staging'].update(value='forged'),lambda p:p[0]['decision'].update(outcome='pending')):
   pairs=copy.deepcopy(self.pairs);mutate(pairs);a=copy.deepcopy(self.approval);a['evidence_digest']=digest(pairs)
   with self.assertRaises(ValueError):verify_provenance(self.rows,pairs,a)
 def test_artifact_tampering_fails(self):
  self.file.write_text('changed')
  with self.assertRaises(ValueError):self.plan()
 def test_unresolved_visible_null_is_not_approved_blank(self):
  p=copy.deepcopy(self.pairs);v=next(v for v in p if v['staging']['field']=='test_policy');v['decision']['outcome']='authorized_nonblocking_null';a=copy.deepcopy(self.approval);a['evidence_digest']=digest(p)
  with self.assertRaises(ValueError):verify_provenance(self.rows,p,a)
 def test_unrelated_school_full_image_preserved(self):
  p=self.plan();self.assertEqual(p['expected_rows'][2],self.before['rows'][0]);s=build_sql(p,p['plan_digest']);self.assertIn('Schema changed',s);self.assertIn('Database changed',s);self.assertIn('Full readback mismatch',s);self.assertIn("O''Brien $guard$",s)
 def test_plan_digest_and_unrelated_mutations_rejected(self):
  p=self.plan()
  with self.assertRaises(ValueError):build_sql(p,'0'*64)
  p['expected_rows'][-1]['school_name']='forged';p['plan_digest']=digest({k:v for k,v in p.items() if k!='plan_digest'})
  with self.assertRaises(ValueError):build_sql(p,p['plan_digest'])
 def test_explicit_update_preserves_unselected_extra_columns(self):
  p=self.plan();b={'schema':self.schema,'rows':p['expected_rows']};a=copy.deepcopy(self.approval);a['operations']=dict.fromkeys(self.ids,'update');b['rows'][0]['campus_description']='untouched editorial column'
  new=publication_plan(self.master,b,a,self.pairs);self.assertEqual(new['expected_rows'][0]['campus_description'],'untouched editorial column');self.assertEqual(len(new['updates']),2)
 def test_explicit_noop_is_idempotent(self):
  p=self.plan();a=copy.deepcopy(self.approval);a['operations']=dict.fromkeys(self.ids,'noop');new=publication_plan(self.master,{'schema':self.schema,'rows':p['expected_rows']},a,self.pairs);self.assertEqual(new['inserts'],[]);self.assertEqual(new['updates'],[]);self.assertIn("'inserted',0",build_sql(new,new['plan_digest']))

if __name__=='__main__':unittest.main()
