"""Operator-only Supabase CLI transport. No secrets or SQL identifiers from input."""
import json
import subprocess
import tempfile
from pathlib import Path
from school_publish import COLUMNS, FIELDS, ORDER, records, plan_publish, master_snapshot, database_snapshot
from sources import require

PROJECT = 'hmnoqybdcfwqbjhorwzd'


def quote(value):
    return "'" + value.replace("'", "''") + "'"


def json_sql(value):
    return quote(json.dumps(value, ensure_ascii=False, allow_nan=False)) + '::jsonb'


def run_query(sql):
    with tempfile.TemporaryDirectory(prefix='college-publish-') as directory:
        path = Path(directory) / 'query.sql'
        path.write_text(sql, encoding='utf-8')
        path.chmod(0o600)
        result = subprocess.run(['supabase', 'db', 'query', '--linked', '--project-ref', PROJECT,
                                 '--output', 'json', '--file', str(path)],
                                capture_output=True, text=True, timeout=90, check=False)
    # CLI errors may contain server SQL/credentials: never echo stdout/stderr.
    if result.returncode != 0:
        raise RuntimeError('Database query failed; inspect state before retry')
    return json.loads(result.stdout)['rows']


class SupabaseSchools:
    database_id = PROJECT

    def __init__(self, query=run_query):
        self.query = query

    def read(self, school_ids):
        require(isinstance(school_ids,(tuple,list)) and school_ids and
                all(type(s) is str and s in ORDER for s in school_ids) and
                len(set(school_ids)) == len(school_ids), 'Invalid pilot scope')
        sql = ('BEGIN READ ONLY; SELECT to_jsonb(selected) AS record FROM (SELECT ' + ', '.join(COLUMNS) +
               ' FROM private.schools WHERE school_id IN (' + ', '.join(quote(s) for s in school_ids) +
               ') ORDER BY school_id) selected; COMMIT;')
        result = {'target':'private.schools','database_id':PROJECT,'rows':[item['record'] for item in self.query(sql)]}
        database_snapshot(result)
        require({r['school_id'] for r in result['rows']} == set(school_ids), 'Target school missing')
        return result

    def apply(self, plan, *, approved_digest, current_master):
        master = {'source_tab':'School','spreadsheet_id':plan.spreadsheet_id,'rows':records(plan.after)}
        baseline = {'target':'private.schools','database_id':plan.database_id,'rows':records(plan.before)}
        require(plan_publish(master,baseline) == plan, 'Invalid plan')
        require(plan.database_id == PROJECT, 'Wrong project')
        require(plan.report()['approval_digest'] == approved_digest, 'Explicit plan approval required')
        require(current_master['spreadsheet_id'] == plan.spreadsheet_id and
                master_snapshot(current_master) == plan.after, 'School changed; re-plan')
        ids = ', '.join(quote(r[0]) for r in plan.after)
        projection = 'jsonb_build_object(' + ', '.join(quote(f) + ', s.' + f for f in COLUMNS) + ')'
        before = sorted(records(plan.before),key=lambda r:r['school_id'])
        after = sorted(records(plan.after),key=lambda r:r['school_id'])
        # Lock, compare, update, and verify in one transaction. Unselected rows and
        # every non-Basic column are excluded from the fixed UPDATE projection.
        sql = "BEGIN; SET LOCAL lock_timeout='5s'; SET LOCAL statement_timeout='30s';\n"
        sql += 'SELECT school_id FROM private.schools WHERE school_id IN (' + ids + ') ORDER BY school_id FOR UPDATE;\n'
        # Payload is quoted JSON in a temp table, outside the PL/pgSQL dollar-quoted
        # body: arbitrary school text cannot terminate that body or inject SQL.
        sql += 'CREATE TEMP TABLE publish_payload ON COMMIT DROP AS SELECT ' + json_sql(before) + ' AS before_rows, ' + json_sql(after) + ' AS after_rows;\n'
        sql += 'DO $guard$ BEGIN IF (SELECT jsonb_agg(' + projection + ' ORDER BY s.school_id) FROM private.schools s WHERE school_id IN (' + ids + ")) IS DISTINCT FROM (SELECT before_rows FROM publish_payload) THEN RAISE EXCEPTION 'Database changed; re-plan'; END IF; END $guard$;\n"
        assignment = ', '.join(f + '=x.' + f for f in FIELDS)
        old_tuple = 'ROW(' + ', '.join('s.'+f for f in FIELDS) + ')'
        new_tuple = 'ROW(' + ', '.join('x.'+f for f in FIELDS) + ')'
        sql += 'WITH changed AS (UPDATE private.schools s SET ' + assignment + ' FROM jsonb_populate_recordset(NULL::private.schools, (SELECT after_rows FROM publish_payload)) x WHERE s.school_id=x.school_id AND '+old_tuple+' IS DISTINCT FROM '+new_tuple+' RETURNING s.school_id) SELECT count(*) AS updated INTO TEMP publish_count FROM changed;\n'
        sql += 'DO $verify$ BEGIN IF (SELECT jsonb_agg(' + projection + ' ORDER BY s.school_id) FROM private.schools s WHERE school_id IN (' + ids + ")) IS DISTINCT FROM (SELECT after_rows FROM publish_payload) THEN RAISE EXCEPTION 'Readback mismatch'; END IF; END $verify$;\n"
        sql += "SELECT jsonb_build_object('updated',updated) AS result FROM publish_count; DROP TABLE publish_count; COMMIT;"
        result = [item['result'] for item in self.query(sql)]
        if len(result)!=1 or type(result[0].get('updated')) is not int:
            raise RuntimeError('Unexpected write result; inspect state before retry')
        return result[0]['updated']
