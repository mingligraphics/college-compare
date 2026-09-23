# School → private.schools publisher

The authoritative source is the human-maintained **School** tab, never Staging,
research candidates, old SQL seeds, or the public directory CSV. Putting a value
in School is the human approval boundary; this tool does not infer approval from
Staging status. The initial scope is `nyu`, `bu`, `ucb`.

## Data flow

1. Read the actual School tab with `school_publish.read_school`, using an injected
   Sheets v4 client authorized for `spreadsheets.readonly`. The range is fixed to
   `'School'`; this adapter cannot write any sheet. It projects only `school_id`,
   `tuition`, `tuition_year`, `coa`, `coa_year`, `first_year_enrollment`.
2. Read these same six columns through `PostgresSchools.read`, using an injected
   trusted PostgreSQL connection. This transaction is explicitly READ ONLY.
3. `plan_publish(master, database)` validates both complete snapshots and creates
   an immutable, deterministic plan. Its JSON report includes complete before/
   after snapshots, exact field changes, unchanged IDs, source/target identifiers,
   and an approval digest. No connection or write occurs in the planner.
4. Human reviews that exact plan. **No production execution is authorized yet.**
5. A future operator may call `PostgresSchools.apply` with that exact approved
   digest and a freshly read School snapshot. It revalidates the plan and source,
   locks all targeted database rows in one transaction, checks all before values,
   and performs parameterized updates only when values differ. A conflict or any
   failed update rolls back the batch. Re-plan and reapprove after a conflict.

The normal CLI is offline and dry-run-only. The separate production entry point below explicitly loads DATABASE_URL and calls
the existing transaction adapter. No schema change, RPC, or automatic promotion is included.

## Validation and NULL policy

- Normalized records require exactly the six named columns. Missing/extra keys,
  duplicate/unknown IDs, blank IDs, and missing database schools fail the batch.
  Subsets of the three pilot schools are supported explicitly; no insert/upsert.
- A full School worksheet can contain unrelated columns, but the read adapter
  projects the six fixed columns. Unknown school IDs fail rather than disappear.
- Explicit JSON `null` means **clear the database value**. Missing columns do not
  mean null. In Sheets, genuinely empty cells in present columns map to null.
  Whitespace, textual `NULL`, numeric strings, booleans, and malformed values fail.
  Zero remains zero. Verify blanks are intentional before approving a plan.
- Money is USD, finite, nonnegative, at most two decimal places, and within
  PostgreSQL numeric(12,2). Enrollment is an integer between 0 and 2147483647.
- Years must be consecutive `YYYY-YY`. In the master, a tuition/COA amount and
  its year must either both be known or both be null. Database snapshots may
  contain incomplete pairs so they can be corrected from a valid master.
- Enrollment has **no year column in the existing schema**. None is invented;
  keep that provenance/year in the master/source records. Never substitute
  total undergraduate enrollment.
- No source, editorial, names, location, percentage, arrays, or other database
  fields can be changed. SQL table/column names are fixed, not generated from
  input. Re-running against already published values produces zero UPDATEs.

## Local input contract and dry-run

Store private exports in ignored `research/inputs/`, not tracked source files.
The JSON master envelope is:

```json
{
  "source_tab": "School",
  "spreadsheet_id": "ACTUAL_SHEET_ID",
  "rows": []
}
```

The target envelope is:

```json
{
  "target": "private.schools",
  "database_id": "ACTUAL_SUPABASE_PROJECT_REF",
  "rows": []
}
```

Each rows array must contain nonempty, exact six-column records. Use actual
exports; the empty arrays above are documentation placeholders and will fail
validation. An envelope alone is an operator attestation, not cryptographic proof
of provenance. Do not relabel a Staging export as School. Prefer the read adapter
for the master and the read-only database adapter for the target.

```sh
python3 -B research/publish_school.py \
  --master research/inputs/approved-school.json \
  --database research/inputs/current-private-schools.json \
  --dry-run > research/output/school-publish-dry-run.json
```

A rejected input exits nonzero and produces no publication report. Keep a report
only after successful exit. The command cannot write to Supabase or Google Sheets.
The actual NYU/BU/UCB diff requires both real snapshots; earlier pilot research
and seeds cannot establish either current approved values or current DB state.

## Manual setup before eventual execution

- Provide the correct Sheet URL/ID and verify its School headers. Supply a fresh
  approved master export or configure a read-only Sheets client outside the repo.
- Use a trusted server/operator PostgreSQL connection whose permissions include
  schema USAGE and SELECT/UPDATE on the five publishable columns (plus school_id
  SELECT), and that can satisfy the existing RLS policy. The current schema has
  no RLS policies: an ordinary new grant alone is insufficient. No role, grant,
  or policy is created here. The existing owner connection can operate, but has
  broad privileges and must remain operator-only.
- The existing service-role secret cannot directly read/write this table; the
  comparison RPC is read-only. This publisher does not change that security
  design or expose a new browser endpoint.
- Install/configure `psycopg` 3 outside application/frontend code if using the
  PostgreSQL adapter. Supply a factory returning a **fresh** connection with
  `autocommit=True`, default tuple rows, a bounded connect timeout, and TLS.
  Verify the connection host/project matches the configured `database_id`;
  this label is operator-provided, not server-attested. Never store/log the DSN,
  password, service-account JSON, tokens, or keys in the repo or plan.
- The dry-run digest binds the selected rows and configured identities; it is
  an operator confirmation mechanism, not user authentication.
- Freeze edits to the relevant School rows during final re-read and publication.
  Pass that fresh snapshot to `apply`. A Google Sheet read and PostgreSQL commit
  cannot be made one atomic transaction: this tool does not lock the Sheet.
  Database concurrency is protected by row locks and before-image comparison;
  a Sheet edit after the final read remains a race without an edit freeze.
- Review NULL clears, source identity, target identity, and the exact plan before
  approval. No database writes, real credentials, or connections were configured
  while implementing this tool. Unit tests use synthetic values and fake clients.

Tests: `python3 -B -m unittest discover -s research -p 'test_*.py'`.


## Approved production entry point

`publish_approved.py --execute` executes only the saved September 23, 2026
approval. Its pinned digest, project reference, and three-school scope must all
match. Default snapshots are in the original Codex task's
`outputs/school-publish-20260923` directory under the operator's home directory;
`--snapshots PATH` can relocate those files but cannot change the approved digest.
It uses the reviewed snapshot, not a fresh Google Sheet read, as explicitly approved.

Run from the repository, using a stable environment outside the repository:

```sh
python3 -m venv "$HOME/.venvs/college-publish"
"$HOME/.venvs/college-publish/bin/python" -m pip install -r research/requirements-publish.txt
export DATABASE_URL
"$HOME/.venvs/college-publish/bin/python" -B research/publish_approved.py --execute
```

DATABASE_URL must already be set locally; never put its value on the command
line or in source. The CLI suppresses connection/exception details. It validates
the direct Supabase hostname or pooler hostname/project username and database
`postgres`, rejects routing overrides, and requires TLS. Custom hosts/proxies
are intentionally unsupported. No database credential is sent to the API.

Exit codes: 0 = committed and verified; 1 = before-commit abort; 2 = transaction
error with uncertain commit outcome; 3 = confirmed commit but verification failed.
Do not automatically retry codes 2 or 3. A baseline mismatch under locks aborts
the entire transaction. All three API pairs are checked even when database
readback or another API verification fails. No automatic repair is implemented.
The full research suite requires Python 3.10+ because the existing Staging module
uses union annotations; the production entry point and publisher tests support
Python 3.9.6. Tests use fake clients; no production execution occurred in development.
