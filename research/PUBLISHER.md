# Basic v1 School → Supabase publisher

The authoritative source is the master **School** tab, spreadsheet
`1gMcmRGVxWgw4olbax2Vwxf4ZDJroBaHShH8A1qAjkrw`. No Staging, CSV, seed, or September 23
snapshot is a publication source. Scope remains `nyu`, `bu`, `ucb`; no inserts.

`school_publish.COLUMNS` is the exact 40-field Basic v1 contract. The publisher
updates 39 non-key fields and never writes Deep/GPA fields or derived values.
`private.schools_basic_v1` computes region, location_cn, and ranking_tier.

## Read, plan, review, apply, verify

1. `read_school(service, spreadsheet_id)` uses an injected read-only Sheets v4
   client to read the bounded pilot area `'School'!A1:BA4`. All 40 Basic headers
   must exist exactly once. Extra Deep/GPA columns are ignored. Pilot rows must
   remain inside that area; the production command requires all three IDs.
2. Read the same fields with `PostgresSchools.read` (psycopg) or
   `SupabaseSchools.read` (the existing authenticated Supabase CLI).
3. `plan_publish(master, database)` creates an immutable before/after plan and
   digest. The source and database identities are part of that digest. Arrays
   are frozen inside the plan. Planning never writes.
4. Review the exact diff, including NULL clears. Re-read School immediately
   before applying. Freeze relevant Sheet edits until verification completes;
   a Sheet read and database commit cannot form one atomic transaction.
5. Apply with the reviewed digest and fresh source snapshot. Both transports
   lock selected rows, compare the before-image, update only changed rows,
   and verify all Basic fields before committing. Re-read after commit. Stale
   database/source values abort; re-plan instead of automatically retrying.

Snapshots use these existing envelopes:

- Master: `{"source_tab":"School","spreadsheet_id":"...","rows":[...]}`
- Database: `{"target":"private.schools","database_id":"...","rows":[...]}`

Every row must have exactly the 40 Basic keys. A snapshot envelope is operator
attestation, not cryptographic evidence of provenance. Use the live read adapter
or connected Sheets read; never relabel research data as School.

## NULL and type rules

Empty Sheet cells map to null; missing columns fail. Null means clear the
corresponding database field. Zero stays zero. Empty test arrays mean a confirmed
empty list, distinct from unknown/null. The Sheet's JSON test list is parsed to a
native array without sorting or filling values. JSON snapshot lists must already
be arrays. Unknown policy cycles stay null.

Money is USD with <=2 decimals, percentages are 0–100 percentage points with
<=2 decimals, counts are nonnegative PostgreSQL integers, and numerical ranks and
ranking years are positive integers. Booleans, numeric strings, nonfinite numbers,
textual nulls, invalid enums, duplicate tests, and reversed test percentiles fail.
Cost years retain the consecutive `YYYY-YY` check. Other periods/cycles are text;
they are not forced into cost-year syntax. Official reported acceptance rates
are preserved rather than recomputed from counts. No missing value is inferred.

## Commands

Offline diff:

```sh
python3 -B research/publish_school.py --master PATH/approved-school.json \
  --database PATH/current-private-schools.json --dry-run
```

After review, place a **newly read** School snapshot at `PATH/current-school.json`.
The execution command requires an explicit folder and the reviewed plan digest:

```sh
python3 -B research/publish_approved.py --execute --snapshots PATH \
  --approved-digest REVIEWED_SHA256 --transport supabase-cli
```

The Supabase CLI transport is pinned to project `hmnoqybdcfwqbjhorwzd` and uses its
existing operator login. It runs bounded SQL through the Management API, with
no secrets in command arguments. SQL identifiers are fixed, payloads are safely
quoted JSON outside PL/pgSQL bodies, and temporary query files are private and
removed. It does not expose an RPC or grant permissions to publish.

Alternatively use `--transport postgres` (default), a preconfigured local
`DATABASE_URL`, and the existing `requirements-publish.txt`. The connection must
match the pinned Supabase project, use TLS, and possess owner/operator access.
Neither browser keys nor comparison RPCs can publish.

The old hard-coded approval/directory defaults were removed. Running the former
`--execute` command alone now fails argument validation, rather than replaying
obsolete costs. The command verifies the pinned master/project, all three IDs,
the fresh School snapshot, database readback, and all Basic fields on all three
pairs through `compare-schools-basic-v1`.

Exit codes: 0 verified; 1 pre-commit validation failure; 2 transaction/commit
outcome uncertain; 3 committed but post-commit verification failed. A CLI query
error is treated conservatively as uncertain once apply begins. Do not retry
codes 2/3 blindly. No automatic repairs or migrations are performed.

## API and frontend compatibility

`get_school_comparison_basic_v1` returns 40 Basic + 3 calculated + 8 existing Deep
fields, exactly two schools in request order. It is service-role-only, has an
empty search_path, and never includes GPA/editorial/provenance fields. The new
`compare-schools-basic-v1` Edge Function exposes the same request shape as the old
endpoint and enforces the 51-field response allowlist. Existing request limits,
CORS, timeouts, secret handling, and sanitized errors are reused.

The legacy RPC/endpoint remain available during frontend rollout. The local
page uses the new endpoint, canonical tuition names, and Chinese display labels
for institution_control/region. Its layout is unchanged. It displays the same
set of comparison sections, not every newly exposed Basic field. Publishing the
local frontend to GitHub Pages is a separate release action.

Tests:

```sh
python3 -B -m unittest discover -s research -p 'test_*.py'
node --test supabase/functions/compare-schools/handler.test.mjs \
  supabase/functions/compare-schools-basic-v1/handler.test.mjs tests/frontend.test.mjs
```
