"""Batch regression tests: fixture values derive from the reconciled review.

No live clients or production writes. Attachments are tested using temporary
synthetic byte fixtures; source authenticity was reviewed in reconciliation.
"""
import copy,json,tempfile,unittest,hashlib
from pathlib import Path
from unittest.mock import Mock
from batch_contract import *
from batch_publish import *
from batch_sheet import decode,normalize
from sources import ValidationError
FIXTURE=Path(__file__).with_name('testdata')/'batch-20260929.json'

class BatchTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.fixture=json.loads(FIXTURE.read_text())
 def setUp(self):
  x=copy.deepcopy(self.fixture);self.staging=x['staging'];self.sources=x['sources'];self.ledger=x['ledger'];self.school=x['school'];self.database=x['database'];self.candidates=x['candidates']
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
  f=Path(self.temp.name)/'synthetic-evidence';f.write_text('test evidence bytes, not a source claim')
  for e in self.ledger:
   if 'attachment' in e:e['attachment'].update(path=str(f),sha256=hashlib.sha256(f.read_bytes()).hexdigest())
 def evaluate(self):return evaluate(self.staging,self.sources,self.ledger,[])
 def publication(self):
  school=copy.deepcopy(self.school)
  for i,r in enumerate(self.candidates,5):
   s=dict.fromkeys(school['headers']);s.update(r);school['rows'].append(s);school['row_positions'][r['school_id']]=i
  return school,database_plan(school,self.database,promotion_digest='synthetic-approved-promotion')
 def test_review_regressions(self):
  rows=self.evaluate();self.assertEqual(rows,self.candidates)
  self.assertEqual(rows[2]['school_id'],'mit');self.assertEqual([rows[1][k] for k in ('ranking_usnews','ranking_category','ranking_year')],[5,'national_university',2027])
  self.assertEqual(sum(v is None for r in rows for v in r.values()),21)
 def test_preserve_cohort_caveat_and_null_test_lists(self):
  r=self.evaluate();self.assertIsNone(r[1]['english_tests_accepted']);self.assertIsNone(r[7]['english_tests_accepted']);self.assertIn('not specified',r[8]['graduation_rate_4yr_year'])
 def test_stale_value(self):
  self.staging[0]['candidate_value']='2027'
  with self.assertRaises(ValueError):self.evaluate()
 def test_stale_evidence(self):
  self.staging[1]['evidence']+=' changed';self.sources[1]['notes']=self.staging[1]['evidence']
  with self.assertRaisesRegex(ValueError,'DIGEST_STALE'):self.evaluate()
 def test_missing_manual_authorization(self):
  self.ledger.pop()
  with self.assertRaises(ValueError):self.evaluate()
 def test_unknown_exception(self):
  self.ledger[0]['reason_codes']=['WAIVE_EVERYTHING']
  with self.assertRaises(ValueError):self.evaluate()
 def test_nonwaivable_flag(self):
  self.staging[0]['provenance_check']='missing_scope';self.ledger[0]['covered_flags']=['missing_scope']
  with self.assertRaises(ValueError):self.evaluate()
 def test_unresolved_value(self):
  self.ledger[0]['outcome']='unresolved'
  with self.assertRaises(ValueError):self.evaluate()
 def test_tampered_formula(self):
  with self.assertRaisesRegex(ValueError,'FORMULA_TAMPERED'):evaluate(self.staging,self.sources,self.ledger,['AG148'])
  with self.assertRaises(ValueError):evaluate(self.staging,self.sources,self.ledger)
 def test_pair_mismatch(self):
  self.sources[0]['value']='other'
  with self.assertRaisesRegex(ValueError,'PAIR_MISMATCH'):self.evaluate()
 def test_missing_attachment(self):
  next(e for e in self.ledger if 'attachment' in e)['attachment']['sha256']='0'*64
  with self.assertRaises(ValueError):self.evaluate()
 def test_invalid_date(self):
  self.staging[0]['checked_date']='approval prose';self.sources[0]['checked_date']='approval prose';self.ledger[0]['candidate_digest']=candidate_digest(self.staging[0],'harvard')
  with self.assertRaisesRegex(ValueError,'INVALID_CHECKED_DATE'):self.evaluate()
 def test_duplicate_record(self):
  self.staging[1]['record_id']=self.staging[0]['record_id']
  with self.assertRaises(ValueError):self.evaluate()
 def test_duplicate_school_headers_and_ids(self):
  self.school['headers'][1]=self.school['headers'][0]
  with self.assertRaises(ValueError):verify_school(self.school)
 def test_incomplete_school_scan(self):
  self.school['read_row_count']=4
  with self.assertRaises(ValueError):verify_school(self.school)
 def test_numeric_strings_and_reversed_scores_rejected_at_publication(self):
  for mutate in (lambda r:r.update(ranking_usnews='5'),lambda r:r.update(sat_25=1600,sat_75=1400),lambda r:r.update(school_id='US-166683')):
   rows=copy.deepcopy(self.candidates);mutate(rows[1])
   with self.assertRaises(ValueError):validate_batch(rows)
 def test_calculation_mismatch(self):
  i=next(i for i,r in enumerate(self.staging) if r['method']=='calculated')
  details=json.loads(self.staging[i]['calculation_details']);details['result']+=1
  self.staging[i]['calculation_details']=json.dumps(details);self.sources[i]['calculation_details']=json.dumps(details)
  self.ledger[i]['candidate_digest']=candidate_digest(self.staging[i],self.ledger[i]['production_id'])
  with self.assertRaisesRegex(ValueError,'Calculation result mismatch'):self.evaluate()
 def native_fixture(self):
  import re
  def cell(v):
   if isinstance(v,list):v=json.dumps(v)
   return {} if v is None or v=='' else {'effectiveValue':{'numberValue':v} if type(v) in (int,float) else {'stringValue':v}}
  tabs=[]
  for title,rows in [('Staging',self.staging),('Sources',self.sources)]:
   headers=list(rows[0]);data=[]
   for i,r in enumerate(rows,146):
    cells=[cell(r[k]) for k in headers]
    for field in ('provenance_check','promotion_gate'):
     f=re.sub(r'(\$[A-Z]+)#',lambda m:m[1]+str(i),self.fixture['formulas'][title][field])
     cells[headers.index(field)]['userEnteredValue']={'formulaValue':f}
    data.append({'values':cells})
   tabs.append({'properties':{'title':title},'data':[{'rowData':[{'values':[cell(h) for h in headers]}]},{'startRow':145,'rowData':data},{'startRow':1,'startColumn':headers.index('record_id'),'rowData':[]},{'startRow':545,'startColumn':headers.index('record_id'),'rowData':[]}]})
  tabs.append({'properties':{'title':'School','gridProperties':{'rowCount':1000}},'data':[{'rowData':[{'values':[cell(h) for h in self.school['headers']]}]+[{'values':[cell(r[h]) for h in self.school['headers']]} for r in self.school['rows']]}]})
  return {'spreadsheetId':SPREADSHEET,'sheets':tabs}
 def test_incorrect_formula_row_reference_rejected(self):
  raw=self.native_fixture();self.assertEqual(decode(raw,self.fixture['formulas'])['formula_errors'],[])
  cells=raw['sheets'][0]['data'][1]['rowData'][2]['values'];col=list(self.staging[0]).index('provenance_check')
  cells[col]['userEnteredValue']['formulaValue']=cells[col]['userEnteredValue']['formulaValue'].replace('$A148','$A147')
  self.assertEqual(decode(raw,self.fixture['formulas'])['formula_errors'],['Staging:148:provenance_check'])
 def test_duplicate_id_outside_batch_rejected(self):
  raw=self.native_fixture();raw['sheets'][0]['data'][2]['rowData']=[{'values':[{'effectiveValue':{'stringValue':self.staging[0]['record_id']}}]}]
  with self.assertRaisesRegex(ValueError,'Duplicate research ID'):decode(raw,self.fixture['formulas'])
 def test_missing_field(self):
  del self.candidates[0]['city']
  with self.assertRaises(ValueError):validate_batch(self.candidates)
 def test_dryrun_exact_insert_and_zero_writes(self):
  p=promotion_plan(self.candidates,self.school,'evidence')
  self.assertEqual([c['operation'] for c in p['changes']],['insert']*10)
  d=database_plan(None,self.database,preview=True,candidates=self.candidates,promotion_digest=p['approval_digest'])
  self.assertFalse(d['executable']);self.assertEqual([c['payload'] for c in d['changes']],self.candidates)
  with self.assertRaises(ValueError):build_sql(d)
 def test_schema_unique_default_type_trigger_guards(self):
  for key,value in [('constraints',[]),('triggers',[{'name':'side-effect'}])]:
   s=copy.deepcopy(self.database['schema']);s[key]=value
   with self.assertRaises(ValueError):validate_schema(s)
  s=copy.deepcopy(self.database['schema']);s['columns'][0]['data_type']='integer'
  with self.assertRaises(ValueError):validate_schema(s)
 def test_sql_has_guarded_insert_update_and_full_readback(self):
  school,p=self.publication();sql=build_sql(p)
  self.assertIn('SHARE ROW EXCLUSIVE',sql);self.assertNotIn('ON CONFLICT',sql);self.assertIn('Schema changed',sql);self.assertIn('Database changed',sql);self.assertIn('Full readback mismatch',sql)
  insert=sql.split('INSERT INTO private.schools (')[1].split(') SELECT')[0];self.assertEqual(insert.split(','),list(COLUMNS))
  assignment=sql.split('UPDATE private.schools s SET ')[1].split(' FROM ')[0];self.assertNotIn('gpa',assignment);self.assertNotIn('campus',assignment)
 def test_insert_present_update_absent_rejected(self):
  _,p=self.publication();p['changes'][0]['operation']='update';p['approval_digest']=digest({k:v for k,v in p.items() if k!='approval_digest'})
  with self.assertRaisesRegex(ValueError,'Operation mismatch'):build_sql(p)
 def test_plan_mutation_rejected(self):
  _,p=self.publication();p['changes'][0]['payload']['city']='changed'
  with self.assertRaises(ValueError):build_sql(p)
 def test_before_image_drift_fails_before_write(self):
  school,p=self.publication();db=BatchSupabase(Mock());db.read=Mock(return_value=copy.deepcopy(self.database));db.read.return_value['rows'][0]['school_name']='changed'
  with self.assertRaises(ValueError):db.apply(p,approved_digest=p['approval_digest'],read_school=lambda:school)
  db.query.assert_not_called()
 def test_concurrent_insert_fails_before_write(self):
  school,p=self.publication();db=BatchSupabase(Mock());db.read=Mock(return_value=copy.deepcopy(self.database));db.read.return_value['rows'].append(p['changes'][0]['after'])
  with self.assertRaises(ValueError):db.apply(p,approved_digest=p['approval_digest'],read_school=lambda:school)
  db.query.assert_not_called()
 def test_uncertain_commit_never_retries(self):
  school,p=self.publication();query=Mock(side_effect=RuntimeError('lost ack'));db=BatchSupabase(query);db.read=Mock(return_value=self.database)
  with self.assertRaisesRegex(RuntimeError,'COMMIT OUTCOME UNKNOWN'):db.apply(p,approved_digest=p['approval_digest'],read_school=lambda:school)
  self.assertEqual(query.call_count,1)
 def test_sheet_drift_aborts_without_write(self):
  p=promotion_plan(self.candidates,self.school,'evidence');write=Mock();fresh=copy.deepcopy(self.school);fresh['rows'][0]['city']='drift'
  with self.assertRaises(ValueError):apply_promotion(p,approved_digest=p['approval_digest'],read_and_evaluate=lambda:(self.candidates,fresh,'evidence'),write_batch=write,edit_freeze_reference='operator freeze')
  write.assert_not_called()
 def test_sheet_apply_preserves_pilot_and_extra_columns(self):
  p=promotion_plan(self.candidates,self.school,'evidence');state=copy.deepcopy(self.school);calls=[]
  def read():return self.candidates,copy.deepcopy(state),'evidence'
  def write(requests):
   calls.append(requests)
   for change in p['changes']:
    state['rows'].append(change['after']);state['row_positions'][change['school_id']]=len(state['rows'])+1
  result=apply_promotion(p,approved_digest=p['approval_digest'],read_and_evaluate=read,write_batch=write,edit_freeze_reference='operator freeze')
  self.assertEqual(len(calls),1);self.assertEqual(result['rows'][:3],self.school['rows']);self.assertEqual(len(calls[0]),400)
 def test_both_transports_identical_plan_sql(self):
  school,p=self.publication();captured=[]
  class Cursor:
   description=None
   def __enter__(self):return self
   def __exit__(self,*a):pass
   def execute(self,sql,prepare=False):captured.append(sql)
   def nextset(self):return False
  class Conn:
   autocommit=True
   def __enter__(self):return self
   def __exit__(self,*a):pass
   def cursor(self):return Cursor()
  pg=BatchPostgres(Conn);pg.query(build_sql(p));cli=BatchSupabase(lambda s:captured.append(s));cli.query(build_sql(p));self.assertEqual(captured[0],captured[1])

if __name__=='__main__':unittest.main()
