"""Ten-school read/plan/apply support. No network calls or writes on import.

Preview payloads from Staging are explicitly non-executable. Database apply accepts
only a fresh, post-promotion School read and a separately approved database digest.
"""
import copy,json
from dataclasses import dataclass
from batch_contract import IDS,NAMES,SPREADSHEET,PROJECT,RULE,digest,validate_batch
from school_publish import COLUMNS,FIELDS
from school_cli_transport import json_sql,quote,run_query
from sources import require

# Include types, defaults, constraints and triggers, and compare this exact shape
# again under a table lock. No dynamically supplied SQL identifiers are accepted.
SCHEMA_SQL="""jsonb_build_object(
'columns',(SELECT jsonb_agg(to_jsonb(c) ORDER BY ordinal_position) FROM information_schema.columns c WHERE table_schema='private' AND table_name='schools'),
'constraints',(SELECT jsonb_agg(jsonb_build_object('name',conname,'type',contype,'definition',pg_get_constraintdef(oid)) ORDER BY conname) FROM pg_constraint WHERE conrelid='private.schools'::regclass),
 'triggers',(SELECT coalesce(jsonb_agg(jsonb_build_object('name',tgname,'definition',pg_get_triggerdef(oid)) ORDER BY tgname),'[]'::jsonb) FROM pg_trigger WHERE tgrelid='private.schools'::regclass AND NOT tgisinternal))"""
READ_SQL="BEGIN READ ONLY; SELECT jsonb_build_object('rows',(SELECT coalesce(jsonb_agg(to_jsonb(s) ORDER BY school_id),'[]'::jsonb) FROM private.schools s),'schema',"+SCHEMA_SQL+") AS snapshot; COMMIT;"


def validate_schema(schema):
 cols=schema['columns'];names=[c['column_name'] for c in cols]
 require(len(names)==len(set(names)) and set(COLUMNS)<=set(names),'Schema columns invalid')
 require(any(c['type']=='p' and c['definition']=='PRIMARY KEY (school_id)' for c in schema['constraints']),'Unique school_id primary key required')
 require(not schema['triggers'],'Unreviewed database trigger')
 from school_publish import INTEGER_FIELDS,PERCENT_FIELDS
 for c in cols:
  name=c['column_name']
  if name in COLUMNS:
   expected='integer' if name in INTEGER_FIELDS else 'numeric' if name in PERCENT_FIELDS or name in ('tuition_fees','coa') else 'ARRAY' if name=='english_tests_accepted' else 'text'
   require(c['data_type']==expected,'Schema type mismatch: '+name)
   if expected=='ARRAY':require(c['udt_name']=='_text','Unexpected array element type')
   require(c.get('is_generated','NEVER')=='NEVER','Generated Basic column')
  else:
   require(c['is_nullable']=='YES' and c['column_default'] is None and c.get('is_generated','NEVER')=='NEVER','Unreviewed insert default/non-null extra field')
 require(all(c['column_default'] is None for c in cols),'Unreviewed default')


def validate_database(snapshot):
 require(snapshot['database_id']==PROJECT,'Wrong database')
 validate_schema(snapshot['schema'])
 rows=snapshot['rows'];require(len({r['school_id'] for r in rows})==len(rows),'Duplicate database ID')
 require(all(set(r)=={c['column_name'] for c in snapshot['schema']['columns']} for r in rows),'Incomplete full database before-image')
 return {r['school_id']:r for r in rows}


def verify_school(snapshot):
 require(snapshot['source_tab']=='School' and snapshot['spreadsheet_id']==SPREADSHEET,'Actual School read required')
 header=snapshot['headers'];require(len(header)==len(set(header)) and set(COLUMNS)<=set(header),'Duplicate/missing School headers')
 require(snapshot['read_row_count']==snapshot['allocated_row_count'] and snapshot['allocated_row_count']>=len(snapshot['rows'])+1,'Incomplete School scan')
 require(len({r['school_id'] for r in snapshot['rows']})==len(snapshot['rows']),'Duplicate School ID')
 require(all(set(r)==set(header) for r in snapshot['rows']),'Malformed School row')
 positions=snapshot['row_positions']
 require(set(positions)=={r['school_id'] for r in snapshot['rows']} and len(set(positions.values()))==len(positions),'Invalid School coordinates')
 require(all(type(n) is int and 2<=n<=snapshot['allocated_row_count'] for n in positions.values()),'Invalid School row')
 for r in snapshot['rows']:require(r['school_id'] in (*IDS,'nyu','bu','ucb'),'Unknown/alias School identity')
 return {r['school_id']:r for r in snapshot['rows']}


def operation(before,after):return 'insert' if before is None else 'noop' if before==after else 'update'

def promotion_plan(candidates,school,evidence_digest):
 candidates=validate_batch(candidates);current=verify_school(school)
 changes=[]
 for row in candidates:
  old=current.get(row['school_id']);after=copy.deepcopy(old) if old else dict.fromkeys(school['headers'])
  after.update(row)
  changes.append({'school_id':row['school_id'],'operation':operation(old,after),'before':old,'after':after,'null_fields':[k for k in COLUMNS if row[k] is None]})
 payload={'kind':'Staging_to_School','rule_version':RULE,'spreadsheet_id':SPREADSHEET,'manifest':list(IDS),'source_evidence_digest':evidence_digest,'school_before':school,'changes':changes,'execution_authorized':False}
 return {**payload,'approval_digest':digest(payload)}


def database_plan(school,database,*,preview=False,candidates=None,promotion_digest=None):
 current=validate_database(database)
 if preview:
  require(candidates is not None and promotion_digest,'Promotion preview required');after=validate_batch(candidates)
 else:
  master=verify_school(school)
  require(set(IDS)<=set(master),'Post-promotion School readback required')
  after=validate_batch([{k:master[sid][k] for k in COLUMNS} for sid in IDS])
 changes=[]
 for row in after:
  old=current.get(row['school_id']);new=copy.deepcopy(old) if old else dict.fromkeys(c['column_name'] for c in database['schema']['columns'])
  new.update(row);changes.append({'school_id':row['school_id'],'operation':operation(old,new),'before':old,'after':new,'payload':row})
 p={'kind':'downstream_preview' if preview else 'School_to_database','executable':not preview,'source_tab':'Staging (projected only)' if preview else 'School','spreadsheet_id':SPREADSHEET,'database_id':PROJECT,'manifest':list(IDS),'rule_version':RULE,'schema':database['schema'],'database_before':database['rows'],'school_digest':None if preview else digest(school),'promotion_digest':promotion_digest,'changes':changes}
 return {**p,'approval_digest':digest(p)}


def checked_plan(plan,kind,approved_digest):
 require(plan['kind']==kind and approved_digest==plan['approval_digest'],'Explicit stage-specific approval required')
 require(digest({k:v for k,v in plan.items() if k!='approval_digest'})==approved_digest,'Plan changed')
 require(plan['manifest']==list(IDS) and plan['spreadsheet_id']==SPREADSHEET,'Wrong manifest/target')


def build_sql(plan,*,rollback=False):
 """Shared transaction for both operator transports; no blanket upsert."""
 checked_plan(plan,'School_to_database',plan['approval_digest'])
 require(plan['executable'] and plan['database_id']==PROJECT,'Preview is not executable')
 validate_schema(plan['schema'])
 require([c['school_id'] for c in plan['changes']]==list(IDS),'Incomplete batch')
 ids=','.join(quote(s) for s in IDS)
 expected_before=sorted(plan['database_before'],key=lambda r:r['school_id'])
 expected_after={r['school_id']:copy.deepcopy(r) for r in expected_before}
 validate_batch([c['payload'] for c in plan['changes']])
 for c in plan['changes']:
  old=expected_after.get(c['school_id'])
  require(c['before']==old,'Operation before-image mismatch')
  new=copy.deepcopy(old) if old else dict.fromkeys(x['column_name'] for x in plan['schema']['columns']);new.update(c['payload'])
  require(c['after']==new and c['operation']==operation(old,new),'Operation mismatch')
  expected_after[c['school_id']]=new
 inserts=[c['payload'] for c in plan['changes'] if c['operation']=='insert']
 updates=[c['payload'] for c in plan['changes'] if c['operation']=='update']
 sql="BEGIN; SET LOCAL lock_timeout='5s'; SET LOCAL statement_timeout='30s';\n"
 # SHARE ROW EXCLUSIVE serializes absent identities as well as updates, and the
 # PK is the final insertion guard. Freeze is short; errors roll back all rows.
 sql+='LOCK TABLE private.schools IN SHARE ROW EXCLUSIVE MODE;\n'
 sql+='CREATE TEMP TABLE batch_payload ON COMMIT DROP AS SELECT '+json_sql(expected_before)+' AS before_rows, '+json_sql(sorted(expected_after.values(),key=lambda r:r['school_id']))+' AS after_rows, '+json_sql(plan['schema'])+' AS schema, '+json_sql(inserts)+' AS inserts, '+json_sql(updates)+' AS updates;\n'
 sql+="DO $guard$ BEGIN IF (SELECT "+SCHEMA_SQL+") IS DISTINCT FROM (SELECT schema FROM batch_payload) THEN RAISE EXCEPTION 'Schema changed'; END IF; IF (SELECT coalesce(jsonb_agg(to_jsonb(s) ORDER BY school_id),'[]'::jsonb) FROM private.schools s) IS DISTINCT FROM (SELECT before_rows FROM batch_payload) THEN RAISE EXCEPTION 'Database changed'; END IF; END $guard$;\n"
 # Explicit insert only. Any unexpected presence causes a unique-key error.
 sql+='INSERT INTO private.schools ('+','.join(COLUMNS)+') SELECT '+','.join(COLUMNS)+' FROM jsonb_populate_recordset(NULL::private.schools,(SELECT inserts FROM batch_payload));\n'
 sql+='UPDATE private.schools s SET '+','.join(f+'=x.'+f for f in FIELDS)+' FROM jsonb_populate_recordset(NULL::private.schools,(SELECT updates FROM batch_payload)) x WHERE s.school_id=x.school_id;\n'
 sql+="DO $verify$ BEGIN IF (SELECT coalesce(jsonb_agg(to_jsonb(s) ORDER BY school_id),'[]'::jsonb) FROM private.schools s) IS DISTINCT FROM (SELECT after_rows FROM batch_payload) THEN RAISE EXCEPTION 'Full readback mismatch'; END IF; END $verify$;\n"
 sql+="SELECT jsonb_build_object('verified',true,'inserted',"+str(len(inserts))+",'updated',"+str(len(updates))+") AS result; "+('ROLLBACK;' if rollback else 'COMMIT;')
 return sql


class BatchSupabase:
 def __init__(self,query=run_query):self.query=query
 def read(self):
  raw=self.query(READ_SQL);require(len(raw)==1,'Malformed snapshot')
  s=raw[0]['snapshot'];s['database_id']=PROJECT;validate_database(s);return s
 def apply(self,plan,*,approved_digest,read_school):
  checked_plan(plan,'School_to_database',approved_digest)
  # Callback must be a fresh live read, never a cached approval snapshot.
  fresh=read_school();require(digest(fresh)==plan['school_digest'],'School changed')
  rebuilt=database_plan(fresh,self.read(),promotion_digest=plan['promotion_digest'])
  require(rebuilt==plan,'Database/source plan drift')
  sql=build_sql(plan)
  try:result=self.query(sql)
  except BaseException as e:raise RuntimeError('COMMIT OUTCOME UNKNOWN; investigate readback; never replay automatically') from e
  require(len(result)==1 and result[0].get('result',{}).get('verified') is True,'COMMIT OUTCOME UNKNOWN; investigate')
  expected={r['school_id']:r for r in plan['database_before']}
  for c in plan['changes']:expected[c['school_id']]=c['after']
  try:require(self.read()['rows']==sorted(expected.values(),key=lambda r:r['school_id']),'Readback mismatch')
  except BaseException as e:raise RuntimeError('COMMITTED; post-commit verification failed; no automatic repair') from e
  return result[0]['result']


class BatchPostgres(BatchSupabase):
 """Same validated plan and SQL as CLI; injected owner/operator connection."""
 def __init__(self,connect):
  def query(sql):
   with connect() as conn:
    require(conn.autocommit is True,'Fresh autocommit connection required')
    with conn.cursor() as cur:
     cur.execute(sql,prepare=False);output=[]
     while True:
      if cur.description:
       names=[c.name for c in cur.description];output=[dict(zip(names,r)) for r in cur.fetchall()]
      if not cur.nextset():break
     return output
  super().__init__(query)


def apply_promotion(plan,*,approved_digest,read_and_evaluate,write_batch,edit_freeze_reference):
 """Fresh whole-scope evaluation before the one bounded School write.

 The operator supplies live adapters and an operational edit freeze; Sheets has
 no transactional compare-and-swap. Unexpected errors require investigation.
 """
 checked_plan(plan,'Staging_to_School',approved_digest)
 require(isinstance(edit_freeze_reference,str) and edit_freeze_reference.strip(),'Operational Sheet edit freeze required')
 candidates,current,evidence_digest=read_and_evaluate()
 require(promotion_plan(candidates,current,evidence_digest)==plan,'Sheet/evidence drift; re-plan')
 header=current['headers'];indexes=[header.index(c) for c in COLUMNS]
 existing={r['school_id']:r for r in current['rows']};positions=current['row_positions'];next_row=max([1,*positions.values()])+1
 requests=[]
 for change in plan['changes']:
  if change['operation']=='noop':continue
  sid=change['school_id'];rowno=positions.get(sid)
  if change['operation']=='insert':require(sid not in existing,'Insert already present');rowno=next_row;next_row+=1
  else:require(sid in existing,'Update absent')
  require(rowno<=current['allocated_row_count'],'School capacity exceeded')
  for field,col in zip(COLUMNS,indexes):
   v=change['after'][field]
   if isinstance(v,list):v=json.dumps(v,ensure_ascii=False)
   cell={} if v is None else {'userEnteredValue':{'numberValue':v} if type(v) in (int,float) else {'stringValue':v}}
   requests.append({'updateCells':{'range':{'sheetId':0,'startRowIndex':rowno-1,'endRowIndex':rowno,'startColumnIndex':col,'endColumnIndex':col+1},'rows':[{'values':[cell]}],'fields':'userEnteredValue'}})
 try:write_batch(requests)
 except BaseException as e:raise RuntimeError('SCHOOL WRITE OUTCOME UNKNOWN; re-read before any retry') from e
 _,after,_=read_and_evaluate();observed=verify_school(after)
 for change in plan['changes']:require(observed.get(change['school_id'])==change['after'],'School readback mismatch')
 for sid,row in existing.items():
  if sid not in IDS:require(observed.get(sid)==row,'Pilot changed')
 return after


def production_postgres_batch():
 """Reuse the pilot's project pin, owner configuration, and TLS validation."""
 from publish_approved import production_transport
 pilot=production_transport()
 return BatchPostgres(pilot.connect)
