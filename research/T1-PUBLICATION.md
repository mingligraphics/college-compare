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
