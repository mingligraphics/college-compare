"""Explicit School-to-Supabase T1 publication; no network or writes on import.

Private source snapshots and approval evidence stay outside the public repository.
The original pilot and ten-school publishers keep their existing contracts.
"""
import copy
import hashlib
import json
import math
from pathlib import Path
from school_publish import COLUMNS, validate_rows
from school_cli_transport import json_sql
from sources import require

IDS = ('duke','northwestern','jhu','cornell','brown','dartmouth','caltech','cmu',
       'michigan','georgetown','vanderbilt','rice','emory','washu','ucsd','ucsb',
       'uci','ucdavis','unc','uva')
EXTRA = ('gpa_unweighted_25','gpa_unweighted_75','gpa_scale_definition',
         'gpa_population','gpa_year','signature_programs')
PUBLISH_COLUMNS = (*COLUMNS, *EXTRA)

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     allow_nan=False).encode()).hexdigest()

def selected_rows(rows, *, approval=None):
    if approval is not None:
        from incremental_publish import selected_rows as select_incremental
        return select_incremental(rows, approval)
    require(len({r['school_id'] for r in rows}) == len(rows), 'Duplicate School IDs')
    selected = {r['school_id']:r for r in rows if r['school_id'] in IDS}
    require(set(selected) == set(IDS), 'All 20 T1 schools required')
    result = []
    for sid in IDS:
        original = selected[sid]
        require(set(PUBLISH_COLUMNS) <= set(original), 'Missing School columns')
        r = {k:copy.deepcopy(original[k]) for k in PUBLISH_COLUMNS}
        for f in ('english_tests_accepted','signature_programs'):
            if isinstance(r[f],str): r[f] = json.loads(r[f])
        if isinstance(r['ranking_year'],str):
            require(r['ranking_year'].isascii() and r['ranking_year'].isdigit(), 'Invalid rank year')
            r['ranking_year'] = int(r['ranking_year'])
        validate_rows([{k:r[k] for k in COLUMNS}], master=True, allowed_ids=IDS)
        for f in EXTRA[:2]:
            v = r[f]
            require(v is None or (type(v) in (int,float) and math.isfinite(v) and 0 <= v <= 4), 'Invalid GPA')
        lo,hi = (r[f] for f in EXTRA[:2])
        require(lo is None or hi is None or lo <= hi, 'Reversed GPA range')
        for f in EXTRA[2:5]: require(r[f] is None or isinstance(r[f],str), 'Invalid GPA metadata')
        programs = r['signature_programs']
        require(isinstance(programs,list) and programs, 'Missing approved signature list')
        require(len({p['program_key'] for p in programs}) == len(programs), 'Duplicate program')
        for p in programs:
            require(set(p)=={'program_key','name_en','name_cn','selection_basis'}, 'Unexpected public program fields')
            require(all(isinstance(v,str) and v.strip() for v in p.values()), 'Empty program metadata')
            require(p['selection_basis'] in ('renowned','relative_strength','popular'), 'Invalid program basis')
        result.append(r)
    return result

def build_sql(rows, before, migration=None, *, rollback=False, approval=None, master=None, provenance=None, approved_digest=None):
    """One transaction guards the full before-image, adds schema and inserts T1.

    Full-row verification prevents changes to any of the pre-existing schools.
    A failed or uncertain request must be investigated, never blindly replayed.
    """
    if approval is not None:
        from incremental_publish import publication_plan, build_sql as incremental_sql, selected_rows as select_incremental, master_projection
        require(migration is None, 'Incremental publication never changes schema')
        require(master is not None and provenance is not None, 'Fresh master and approved provenance required')
        require(select_incremental(rows, approval) == master_projection(master, approval), 'Master/payload mismatch')
        plan = publication_plan(master, before, approval, provenance)
        return incremental_sql(plan, approved_digest, rollback=rollback)
    require(isinstance(migration, str), 'Legacy T1 migration required')
    rows = selected_rows(rows)
    require(not (set(IDS) & {r['school_id'] for r in before['rows']}), 'T1 already present; inspect instead of replay')
    require(not before['triggers'], 'Unexpected triggers')
    require(not (set(EXTRA) & {c['column_name'] for c in before['columns']}), 'Schema already extended')
    require(set(COLUMNS) <= {c['column_name'] for c in before['columns']}, 'Missing Basic schema')
    names = [c['column_name'] for c in before['columns']] + list(EXTRA)
    expected = [{**r, **dict.fromkeys(EXTRA)} for r in before['rows']]
    expected += [{**dict.fromkeys(names), **r} for r in rows]
    expected.sort(key=lambda r:r['school_id'])
    baseline = sorted(before['rows'],key=lambda r:r['school_id'])
    sql = "BEGIN; SET LOCAL lock_timeout='5s'; SET LOCAL statement_timeout='45s';\n"
    sql += 'LOCK TABLE private.schools IN ACCESS EXCLUSIVE MODE;\n'
    sql += 'CREATE TEMP TABLE t1_payload ON COMMIT DROP AS SELECT '+json_sql(baseline)+' AS before_rows, '+json_sql(expected)+' AS after_rows, '+json_sql(rows)+' AS inserts, '+json_sql(before['columns'])+' AS columns;\n'
    sql += "DO $guard$ BEGIN IF (SELECT jsonb_agg(to_jsonb(s) ORDER BY school_id) FROM private.schools s) IS DISTINCT FROM (SELECT before_rows FROM t1_payload) THEN RAISE EXCEPTION 'Database changed'; END IF; IF (SELECT jsonb_agg(to_jsonb(c) ORDER BY ordinal_position) FROM information_schema.columns c WHERE table_schema='private' AND table_name='schools') IS DISTINCT FROM (SELECT columns FROM t1_payload) THEN RAISE EXCEPTION 'Schema changed'; END IF; END $guard$;\n"
    sql += migration.replace('BEGIN;','').replace('COMMIT;','') + '\n'
    cols = ','.join(PUBLISH_COLUMNS)
    sql += 'INSERT INTO private.schools ('+cols+') SELECT '+cols+' FROM jsonb_populate_recordset(NULL::private.schools,(SELECT inserts FROM t1_payload));\n'
    sql += "DO $verify$ BEGIN IF (SELECT jsonb_agg(to_jsonb(s) ORDER BY school_id) FROM private.schools s) IS DISTINCT FROM (SELECT after_rows FROM t1_payload) THEN RAISE EXCEPTION 'Full readback mismatch'; END IF; END $verify$;\n"
    sql += "SELECT jsonb_build_object('verified',true,'inserted',20,'existing_unchanged',true) AS result;\n"
    return sql + ('ROLLBACK;' if rollback else 'COMMIT;')
