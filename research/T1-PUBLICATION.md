# T1 publication — 2026-09-30

The approved School master now supplies 20 additional schools. The search catalog
contains 33 schools, and comparison v2 carries the existing Basic fields plus five
GPA fields and the separately reviewed signature-program list. Existing v1 clients
retain their prior response contract.

`t1_publish.py` is a deliberately scoped, insert-only publication builder. It
validates the complete 20-school set and typed values, preserves intentional
NULLs, guards the full database before-image and column schema under a table lock,
and verifies every resulting row before committing. It refuses a replay after T1
already exists. This is not an unattended recurring sync or a replacement for the
pilot and previous ten-school approval workflows.

The operator reads School from the connected spreadsheet, retains the read receipt
and approval evidence privately, checks the source again immediately before apply,
and uses `build_sql(..., rollback=True)` for rehearsal. The approved transaction
combines the additive migration and insert; after commit the operator verifies a
fresh database read and registers migration `20260930000000` as applied. Do not run
the migration separately before this one-time builder, or replay an ambiguous
network result. Inspect the database first.

Public source control includes schema, code, tests, and the four-column school
search catalog only. Research records, provenance snapshots, database backups,
review ledgers and executable publication payloads remain outside this repository.

The v2 database function uses the same security-definer boundary as v1, with an
empty search path and execution granted only to `service_role`. The edge handler
retains bounded requests, canonical ID validation, a fixed output allowlist,
sanitized errors and origin handling. The public edge route's JWT setting requires
explicit operator authorization; it does not grant direct access to private tables.

The page displays signature-program names without subject ranking numbers or
selection-basis labels. GPA ranges retain population and year context; unknown or
partial ranges remain unavailable. Legacy famous-majors fields are not substituted.

Validation: Python publisher/regression suite; Node API/frontend suite; database
rollback rehearsal, exact post-commit readback and deployed endpoint smoke tests.

## Incremental publication — 2026-10-02

The original twenty-school migration remains a legacy one-time path. Calling
`t1_publish.build_sql` with an explicit subset `approval`, fresh complete `master`,
paired `provenance`, and sealed `approved_digest` now delegates to
`incremental_publish`. It reuses the forty Basic fields and six already-deployed
nullable v2 fields; it never performs a migration. An approval binds exact IDs,
names, research IDs, per-school insert/update/noop operations, values, evidence,
and explicitly deferred fields. Signature NULLs require explicit deferral; core
NULLs require supported approved-blank decisions. Full schema, constraints,
triggers, existing rows, reciprocal source records and attachment hashes are
guarded. Inserts refuse collisions; updates touch only approved IDs and columns.
There is no implicit upsert or automatic selection of the whole master.

The operator promotes matched Sources/Staging pairs, records existing T1 blank
and policy-cycle exceptions without replacing formula outputs, promotes only
the approved School rows, and verifies fresh readbacks. Publication rehearses
with rollback and commits the sealed before-image once; uncertain outcomes
require readback before retry. The same Python, API/frontend, exact database
readback and live endpoint tests apply. This run approves Notre Dame and Penn
State only; the search catalog contains 35 schools. Private evidence and
publication payloads remain outside public source control.

## Universe v1 Basic-bundle publication — 2026-10-02

Ming explicitly approved location, undergraduate enrollment, undergraduate
international share and acceptance rate as the initial-publication minimum,
with matching year/scope metadata and supported historical values retained.
The incremental publisher accepts this exact threshold only through a sealed
`initial_publication_threshold` approval. It preserves `unresearched` nulls
and all other recorded source-absence/conflict/scope/cost-selection categories;
none is automatically converted to an intentional blank. Required bundle
values and metadata remain mandatory.

The expanded projection is a fixed allowlist of the 56 already-existing
production columns. The original forty Basic fields and their validation are
unchanged. Optional existing fields are type-checked; no DDL or arbitrary
SQL identifiers are allowed. The original two-school/T1 paths retain their
previous approval rules. Value/evidence hashes, exact per-field null manifests,
original null lineage, reciprocal evidence, schema/full-row guards and
insert collision protection remain required. Repeated evidence-file hashes
are cached within one verification call only.

Approved Universe Sources/Staging pairs and publication receipts are retained
in dedicated native evidence tabs, with canonical null classifications also
in new School cell notes. Existing evidence sheets and the prior 35 School
and production records are unchanged. Existing region/location view mappings
are reused during master readback, without adding School columns.

The approved 258 rows were rehearsed with rollback, promoted, committed once
and verified by full readback. Production/search catalog scope is 293 schools.
Boston College, Indiana University Indianapolis, Tufts, Alaska Fairbanks,
Colorado Denver, UIUC and Pittsburgh fail the bundle and remain unpublished.
Private evidence, approvals and payloads are not committed to public Git.
