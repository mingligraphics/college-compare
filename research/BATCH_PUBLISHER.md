# Ten-school Basic v1 batch: reconciliation and dry-run

The separate batch path allowlists exactly `harvard`, `stanford`, `mit`,
`princeton`, `yale`, `columbia`, `penn`, `uchicago`, `ucla`, `usc`.
The original pilot commands retain their three-school, update-only defaults.
The only shared change is an explicit optional identity scope on the existing
40-field type validator. Neither API nor frontend production code is changed.

## Data and decisions

Staging/Sources current records have `-v2` IDs. Their exact original rows,
reviewer identities, contradictory notes and flags remain in the dated
`Staging_history_20260929_v1` and `Sources_history_20260929_v1` tabs and the local
before-image. Every current decision names its superseded pair and digest.
Research IDs are distinct from production IDs; display normalization preserves
the original institutional name. The 40-field contract excludes GPA/Deep data.

Outcomes are `approved_value`, `accepted_intentional_blank`,
`approved_with_limitation`, or `unresolved`. Only the first three can enter a
review package. Exact candidate/evidence digests, known narrow reason codes,
covered raw flags, checked dates, group IDs and human decision references are
required. The evaluator rejects unknown exceptions, stale digests, missing files,
changed attachment bytes, inconsistent pairs, duplicate IDs, malformed or shifted
formulas, unsupported values, and mixed admissions calculation inputs.

The user's current authorization is **reconciliation and dry-run only**.
The ledger records that scope and `execution_authorized=false`; it does not
impersonate Ming as the original automated reviewer or claim execution approval.
All raw gates remain formula-controlled. They are not forcibly set to ready.
Raw cycle/missingness warnings remain visible and are evaluated through the
version-bound exception ledger. All 21 intentional blanks become JSON null;
unknown test lists never become empty arrays. Three source ranking years stored
as text `2027` are explicitly converted to integer 2027 at the Sheet boundary;
the original typed cells remain in provenance. Database numeric strings fail.

Yale's verified 818/1550 four-year total retains the Fall 2019 cohort and
2023-08-31 completion cutoff. Screenshot files are hashed local evidence with
conversation-backed institution identity because their crops omit school names.
Remote screenshot uploads were rejected by automatic approval review; do not
retry or substitute an unsupported publisher URL. Missing/mutated local files
block evaluation. The official Yale PDF also has a durable Drive archive.

## Review package

`publish_batch.py --dry-run` takes six explicit file arguments: `--cells`
(native CellData), `--receipt` (requested bounded ranges), `--formulas` (versioned
formula contract), `--ledger`, `--database`, and `--output` (must not already exist).
It writes both complete before/after plans, exact operations, NULL fields,
fixed-column payloads, preserved extra fields, target identities and digests.
It never connects to a service or writes to School or the database.

The downstream Staging projection is labelled `downstream_preview` and
`executable=false`. It cannot be used for database apply. After an independently
approved School promotion and readback, a fresh School-only database plan must
be created and separately approved. Never relabel the projection as School.

## Future application, only after explicit approval

`batch_sheet.read_live(service)` reads metadata, the complete allocated School
range, selected research rows, full research identity columns, formulas and
rules using an injected read-only Sheets v4 client. Treat file-based read
receipts as operator attestations, not authentication. Use live callbacks for
application and keep an operational edit freeze until School readback finishes.

`apply_promotion` requires the approved promotion digest, edit-freeze reference,
a fresh `read_and_evaluate` callback and an injected bounded batch writer. It
rebuilds the whole plan before writing, writes only Basic columns, and verifies
all 400 fields plus preserved pilot and extra fields. Sheets has no database
compare-and-swap transaction. A failed response is an uncertain outcome: inspect
fresh data before retrying. Insertion requires expected absence; update requires
expected presence. No silent operation switching or partial batch skipping.

`database_plan` accepts a real post-promotion School read for an executable plan.
`BatchSupabase` and `BatchPostgres` share the exact guarded SQL transaction.
The production Supabase transport retains the pinned project and credential
handling. `production_postgres_batch()` reuses the pilot connection validation
and TLS settings. Injected connections are for trusted operators/testing only.

Apply requires the separate approved database digest and a fresh live School
read callback. The transaction locks the table to serialize absent identities,
checks schema and the full database before-image, performs explicit inserts and
updates (never upserts), then checks the entire table before commit. The primary
key is the final concurrent-insert guard. Updates touch only Basic fields;
inserted extra fields must have verified nullable/no-default schema. Unknown
schema changes, triggers and non-null/defaulted extras fail closed. Full-table
verification preserves unrelated schools and Deep fields. Uncertain commit or
failed post-commit readback never causes an automatic retry or repair.

API/frontend verification after a future publication is a separate step and
is not performed by the dry-run. Do not deploy anything as part of this work.

## Validation

Run Python 3.10+ unit tests with `python -B -m unittest discover -s research`.
`test_batch_publish.py` tests the exact MIT/Stanford regressions, all 21 NULLs,
pair/digest/exception/schema/formula failures, mixed calculations, insert drift,
School freeze/readback, transport parity and uncertain commits. Existing pilot,
API and frontend tests remain applicable. The local PostgreSQL WASM rehearsal
additionally exercises real SQL inserts, updates, no-op, unique-key conflicts,
full-table preservation, schema/before-image drift and mid-transaction rollback.
No rehearsal writes to production.
