from pathlib import Path
import subprocess,json
p=Path('supabase/migrations/20261010000000_discovery_v1.sql');sql=p.read_text();quoted="'"+sql.replace("'","''")+"'"
q=Path('verification/record-migration.sql');q.write_text("BEGIN; INSERT INTO supabase_migrations.schema_migrations(version,statements,name) VALUES ('20261010000000',ARRAY["+quoted+"],'discovery_v1') ON CONFLICT(version) DO NOTHING; SELECT version,name FROM supabase_migrations.schema_migrations WHERE version='20261010000000'; COMMIT;")
r=subprocess.run(['supabase','db','query','--linked','--project-ref','hmnoqybdcfwqbjhorwzd','--output','json','--file',str(q)],capture_output=True,text=True)
if r.returncode:print('Migration history registration unavailable');raise SystemExit(1)
d=json.loads(r.stdout);assert d['rows'][0]['version']=='20261010000000';Path('verification/migration-history.json').write_text(json.dumps(d['rows'],indent=2));print('New discovery migration recorded in migration history')
