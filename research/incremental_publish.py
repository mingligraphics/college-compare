"""Approved subsets -> fresh School master -> guarded existing-schema publication.

The 40 Basic columns and six already-deployed nullable v2 columns are fixed.
No network, credential reads, DDL, automatic approval, or writes on import.
"""
import copy
import json
import math
import re
from pathlib import Path
from school_publish import COLUMNS, validate_rows
from school_cli_transport import json_sql, PROJECT
from t1_publish import EXTRA, PUBLISH_COLUMNS, digest
from sources import require

SPREADSHEET = '1gMcmRGVxWgw4olbax2Vwxf4ZDJroBaHShH8A1qAjkrw'
RULE = 'INCREMENTAL_EXISTING_SCHEMA_V1'
CORE = frozenset(('school_id','school_name','city','state','institution_control',
 'undergrad_enrollment','international_pct','acceptance_rate','test_policy',
 'sat_25','sat_75','act_25','act_75','gpa_unweighted_25','gpa_unweighted_75',
 'english_proficiency_policy','english_tests_accepted','tuition_fees','coa',
 'international_need_aid','international_merit_aid','graduation_rate_4yr'))
SCHEMA_SQL = """jsonb_build_object(
'columns',(SELECT jsonb_agg(to_jsonb(c) ORDER BY ordinal_position) FROM information_schema.columns c WHERE table_schema='private' AND table_name='schools'),
'constraints',(SELECT jsonb_agg(jsonb_build_object('name',conname,'type',contype,'definition',pg_get_constraintdef(oid)) ORDER BY conname) FROM pg_constraint WHERE conrelid='private.schools'::regclass),
 'triggers',(SELECT coalesce(jsonb_agg(jsonb_build_object('name',tgname,'definition',pg_get_triggerdef(oid)) ORDER BY tgname),'[]'::jsonb) FROM pg_trigger WHERE tgrelid='private.schools'::regclass AND NOT tgisinternal))"""
READ_SQL = "BEGIN READ ONLY; SELECT jsonb_build_object('rows',(SELECT coalesce(jsonb_agg(to_jsonb(s) ORDER BY school_id),'[]'::jsonb) FROM private.schools s),'schema'," + SCHEMA_SQL + ") AS snapshot; COMMIT;"

def approved_ids(approval):
    require(isinstance(approval,dict) and approval.get('rule')==RULE,'Explicit subset approval required')
    require(approval.get('execution_authorized') is True and approval.get('actor') and approval.get('instruction'), 'Explicit execution authorization required')
    require(approval.get('spreadsheet_id')==SPREADSHEET and approval.get('database_id')==PROJECT,'Wrong publication destination')
    ids=approval.get('school_ids')
    require(isinstance(ids,list) and ids and len(ids)==len(set(ids)),'Empty/duplicate manifest')
    require(all(type(s) is str and re.fullmatch(r'[a-z0-9][a-z0-9_-]*',s) for s in ids),'Invalid permanent ID')
    require(set(approval.get('identities',{}))==set(ids),'Identity mapping missing')
    research=[approval['identities'][s]['research_id'] for s in ids]
    require(len(set(research))==len(ids) and all(re.fullmatch(r'US-\d+',s) for s in research),'Nonreciprocal research/production IDs')
    require(set(approval.get('operations',{}))==set(ids) and all(v in ('insert','update','noop') for v in approval['operations'].values()),'Explicit per-school operation required')
    return tuple(ids)

def selected_rows(rows, approval):
    ids=approved_ids(approval)
    require(isinstance(rows,list) and len(rows)==len(ids),'Subset payload count mismatch')
    require(len({r['school_id'] for r in rows})==len(rows) and {r['school_id'] for r in rows}==set(ids),'Extra/missing/duplicate subset school')
    deferred=approval.get('deferred_fields',{})
    require(set(deferred)==set(ids),'Explicit nullable/deferred manifest required')
    result=[]
    for sid in ids:
        original=next(r for r in rows if r['school_id']==sid)
        require(set(PUBLISH_COLUMNS)<=set(original),'Missing fixed publishing columns')
        r={f:copy.deepcopy(original[f]) for f in PUBLISH_COLUMNS}
        require(r['school_name']==approval['identities'][sid]['school_name'],'ID/name collision')
        for f in ('english_tests_accepted','signature_programs'):
            if isinstance(r[f],str): r[f]=json.loads(r[f])
        if isinstance(r['ranking_year'],str):
            require(r['ranking_year'].isascii() and r['ranking_year'].isdigit(),'Invalid rank year');r['ranking_year']=int(r['ranking_year'])
        validate_rows([{f:r[f] for f in COLUMNS}],master=True,allowed_ids=ids)
        for f in EXTRA[:2]:
            v=r[f]; require(v is None or (type(v) in (int,float) and math.isfinite(v) and 0<=v<=4),'Invalid GPA')
        lo,hi=(r[f] for f in EXTRA[:2]);require(lo is None or hi is None or lo<=hi,'Reversed GPA range')
        for f in EXTRA[2:5]:require(r[f] is None or isinstance(r[f],str),'Invalid GPA metadata')
        programs=r['signature_programs']
        if programs is None:
            require('signature_programs' in deferred[sid],'Unapproved deferred signature list')
        else:
            require(isinstance(programs,list) and programs,'Missing approved signature list')
            require(len({p['program_key'] for p in programs})==len(programs),'Duplicate program')
            for p in programs:
                require(set(p)=={'program_key','name_en','name_cn','selection_basis'},'Unexpected public program fields')
                require(all(isinstance(v,str) and v.strip() for v in p.values()),'Empty program metadata')
                require(p['selection_basis'] in ('renowned','relative_strength','popular'),'Invalid program basis')
        result.append(r)
    require(digest(result)==approval.get('payload_digest'),'Approved payload changed')
    return result

def verify_provenance(rows, paired, approval):
    ids=approved_ids(approval)
    require(isinstance(paired,list) and len(paired)==len(ids)*len(PUBLISH_COLUMNS),'Incomplete provenance projection')
    require(digest(paired)==approval.get('evidence_digest'),'Approved evidence changed')
    found=set();record_ids=set()
    for pair in paired:
        s,r=pair['staging'],pair['source'];d=pair['decision']
        key=(s['production_id'],s['field'])
        require(key not in found and key[0] in ids and key[1] in PUBLISH_COLUMNS,'Duplicate/out-of-scope provenance')
        found.add(key)
        require(s['record_id']!=r['record_id'] and s['related_record_id']==r['record_id'] and r['related_record_id']==s['record_id'],'Provenance pair mismatch')
        for rid in (s['record_id'],r['record_id']):require(rid not in record_ids,'Duplicate source/staging record');record_ids.add(rid)
        require({k:v for k,v in s.items() if k not in ('record_id','related_record_id')}=={k:v for k,v in r.items() if k not in ('record_id','related_record_id')},'Provenance metadata mismatch')
        require(s['research_id']==approval['identities'][key[0]]['research_id'] and s['definition_version']==('signature_programs_v1' if key[1]=='signature_programs' else 'basic_v1'),'ID/definition mismatch')
        row=next(row for row in rows if row['school_id']==key[0]);require(s['value']==row[key[1]],'Evidence/value mismatch')
        require(d['outcome'] in ('supported_value','approved_intentional_blank','authorized_nonblocking_null'),'Unapproved candidate')
        if row[key[1]] is None:
            require(d.get('reason'),'Unexplained null')
            if key[1] in CORE:require(d['outcome']=='approved_intentional_blank','Unresolved visible core field')
            else:require(key[1] in approval['deferred_fields'][key[0]] or d['outcome']=='approved_intentional_blank','Unapproved null omission')
        else:
            require(d['outcome']=='supported_value' and s.get('scope') and s.get('method') and s.get('checked_date'),'Incomplete value provenance')
            require(s.get('locator'),'Missing evidence locator')
        for attachment in pair.get('attachments',[]):
            file=Path(attachment['path']);require(file.is_file() and __import__('hashlib').sha256(file.read_bytes()).hexdigest()==attachment['sha256'],'Durable evidence changed/missing')
        require(pair.get('attachments') or d['outcome']=='authorized_nonblocking_null','Evidence attachment missing')
    require(found=={(sid,f) for sid in ids for f in PUBLISH_COLUMNS},'Missing provenance cells')
    return True

def validate_schema(schema):
    from batch_publish import validate_schema as validate_basic_schema
    validate_basic_schema(schema)
    columns={c['column_name']:c for c in schema['columns']}
    require(set(PUBLISH_COLUMNS)<=set(columns),'Existing v2 schema missing; no automatic migration')
    for f in EXTRA:
        require(columns[f]['data_type']==('numeric' if f in EXTRA[:2] else 'jsonb' if f=='signature_programs' else 'text'),'Invalid deployed extra-field type')
    require(any(c['name']=='gpa_bounds_v2' and c['type']=='c' for c in schema['constraints']),'Missing GPA schema safeguard')
    require(any(c['name']=='signature_array_v2' and c['type']=='c' for c in schema['constraints']),'Missing signature schema safeguard')

def master_projection(snapshot, approval):
    ids=approved_ids(approval)
    require(snapshot['source_tab']=='School' and snapshot['spreadsheet_id']==SPREADSHEET,'Fresh School master required')
    require(snapshot['allocated_row_count']==snapshot['read_row_count'],'Incomplete School collision scan')
    require(len({r['school_id'] for r in snapshot['rows']})==len(snapshot['rows']),'Duplicate master IDs')
    require(set(ids)<=set(r['school_id'] for r in snapshot['rows']),'Master promotion/readback required')
    return selected_rows([r for sid in ids for r in snapshot['rows'] if r['school_id']==sid],approval)

def publication_plan(master, before, approval, paired):
    rows=master_projection(master,approval);verify_provenance(rows,paired,approval);validate_schema(before['schema'])
    ids=approved_ids(approval);existing={r['school_id']:r for r in before['rows']}
    require(len(existing)==len(before['rows']),'Duplicate production IDs')
    names={c['column_name'] for c in before['schema']['columns']}
    require(all(set(r)==names for r in before['rows']),'Incomplete full database before-image')
    expected=copy.deepcopy(existing);inserts=[];updates=[]
    for row in rows:
        sid=row['school_id'];op=approval['operations'][sid];old=existing.get(sid)
        if op=='insert':require(old is None,'Production ID collision; never upsert');inserts.append(row)
        else:
            require(old is not None and old['school_name']==approval['identities'][sid]['school_name'],'Existing ID/name collision')
            if op=='noop':require(all(old[f]==row[f] for f in PUBLISH_COLUMNS),'Noop would change data')
            else: updates.append(row)
        expected[sid]={**(old if old else dict.fromkeys(names)),**row}
    p={'rule':RULE,'school_ids':list(ids),'approval':approval,'master_digest':digest(master),'before':before,'expected_rows':sorted(expected.values(),key=lambda r:r['school_id']),'inserts':inserts,'updates':updates}
    return {**p,'plan_digest':digest(p)}

def build_sql(plan, approved_digest, *, rollback=False):
    require(digest({k:v for k,v in plan.items() if k!='plan_digest'})==plan['plan_digest']==approved_digest,'Plan approval drift')
    approved_ids(plan['approval']);validate_schema(plan['before']['schema'])
    rows=selected_rows(plan['inserts']+plan['updates'] if len(plan['inserts']+plan['updates'])==len(plan['school_ids']) else [{f:r[f] for f in PUBLISH_COLUMNS} for sid in plan['school_ids'] for r in plan['expected_rows'] if r['school_id']==sid],plan['approval'])
    require({r['school_id'] for r in plan['inserts']}.isdisjoint(r['school_id'] for r in plan['updates']),'Duplicate operation')
    reconstructed={r['school_id']:copy.deepcopy(r) for r in plan['before']['rows']}
    for row in rows:
        sid=row['school_id'];op=plan['approval']['operations'][sid]
        require((sid not in reconstructed) if op=='insert' else (sid in reconstructed),'Operation/collision drift')
        reconstructed[sid]={**reconstructed.get(sid,dict.fromkeys(c['column_name'] for c in plan['before']['schema']['columns'])),**row}
    require(sorted(reconstructed.values(),key=lambda r:r['school_id'])==plan['expected_rows'],'Unexpected unrelated change')
    sql="BEGIN; SET LOCAL lock_timeout='5s'; SET LOCAL statement_timeout='45s';\nLOCK TABLE private.schools IN SHARE ROW EXCLUSIVE MODE;\n"
    sql+='CREATE TEMP TABLE incremental_payload ON COMMIT DROP AS SELECT '+json_sql(sorted(plan['before']['rows'],key=lambda r:r['school_id']))+' AS before_rows, '+json_sql(plan['expected_rows'])+' AS after_rows, '+json_sql(plan['before']['schema'])+' AS schema, '+json_sql(plan['inserts'])+' AS inserts, '+json_sql(plan['updates'])+' AS updates;\n'
    sql+="DO $guard$ BEGIN IF (SELECT "+SCHEMA_SQL+") IS DISTINCT FROM (SELECT schema FROM incremental_payload) THEN RAISE EXCEPTION 'Schema changed'; END IF; IF (SELECT coalesce(jsonb_agg(to_jsonb(s) ORDER BY school_id),'[]'::jsonb) FROM private.schools s) IS DISTINCT FROM (SELECT before_rows FROM incremental_payload) THEN RAISE EXCEPTION 'Database changed'; END IF; END $guard$;\n"
    cols=','.join(PUBLISH_COLUMNS)
    sql+='INSERT INTO private.schools ('+cols+') SELECT '+cols+' FROM jsonb_populate_recordset(NULL::private.schools,(SELECT inserts FROM incremental_payload));\n'
    sql+='UPDATE private.schools s SET '+','.join(f+'=x.'+f for f in PUBLISH_COLUMNS if f!='school_id')+' FROM jsonb_populate_recordset(NULL::private.schools,(SELECT updates FROM incremental_payload)) x WHERE s.school_id=x.school_id;\n'
    sql+="DO $verify$ BEGIN IF (SELECT coalesce(jsonb_agg(to_jsonb(s) ORDER BY school_id),'[]'::jsonb) FROM private.schools s) IS DISTINCT FROM (SELECT after_rows FROM incremental_payload) THEN RAISE EXCEPTION 'Full readback mismatch'; END IF; END $verify$;\n"
    sql+="SELECT jsonb_build_object('verified',true,'inserted',"+str(len(plan['inserts']))+",'updated',"+str(len(plan['updates']))+",'existing_unchanged',"+('false' if plan['updates'] else 'true')+",'unrelated_unchanged',true) AS result;\n"
    return sql+('ROLLBACK;' if rollback else 'COMMIT;')
