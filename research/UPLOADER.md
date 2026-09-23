# Staging synchronization — local implementation, no live connection

The executable entry point is **offline dry-run only**. It never authenticates,
constructs a Google client, reads a real Sheet, or invokes a write method.
The transport adapter is implemented and exercised only with a fake Sheets service.
No credential files, service-account keys, tokens or real spreadsheet IDs are included.

## Files and architecture

- `staging_sync.py`: exact row validation, immutable snapshots/actions, pure planner,
  conflict checks and compact audit records. Reuses research `COLUMNS`, pilot identity,
  numeric checks, year validation and `REVIEWED_RULES`.
- `staging_transport.py`: `StagingTransport` interface, atomic in-memory mock and
  injected Google Sheets v4 adapter restricted to the literal tab name `Staging`.
- `upload_staging.py`: local JSON inputs, dry-run report, no live-write CLI switch.
- `test_staging_sync.py`: planner, transport and CLI tests with no Google calls.

Data flow:

```text
validated Staging JSON + mocked existing Staging JSON
  -> validate BOTH entire datasets
  -> canonical 18-column rows and existing snapshot fingerprint
  -> logical-key matching
  -> INSERT / UPDATE / SKIP_APPROVED / SKIP_REJECTED / NOOP
  -> console report + new local JSON audit file
```

An invalid record or duplicate anywhere rejects the entire plan. No partial plan
is applied. Input objects are not mutated. Re-running against unchanged matching
rows produces NOOP, not duplicate inserts or redundant writes.

## Candidate key and ownership

The exact, case-sensitive logical key is:

```text
(school_id, field, academic_year)
```

Source, value and confidence are NOT part of the key. Multiple incoming candidates
for the same key are rejected, even if their sources differ. Resolve those candidates
into one pending record with alternatives/provenance in evidence before uploading.
The uploader never picks an arbitrary source or merges duplicates. A different
academic year is a different key and can be inserted independently.

| Existing state | Result |
|---|---|
| No matching key | INSERT, status must be pending |
| Matching pending row, machine fields changed | UPDATE machine fields only |
| Matching pending row, only incoming notes differ | NOOP |
| Matching approved row | SKIP_APPROVED, no cell changes |
| Matching rejected row | SKIP_REJECTED, no cell changes |

`status` and `review_notes` are human-owned after insertion. An update carries the
existing values unchanged, including null or blank notes. The actual Google update
ranges exclude columns P and Q entirely. Never clear a reviewer's notes.

For new rows, initial machine-generated `review_notes` are permitted because the
existing research contract explicitly produces comparison/provenance notes there.
This is not permission to refresh them later. Future integrations without such
initial pipeline notes should use null or an empty string.

The uploader preserves `checked_date` verbatim and never derives it from upload time.
The audit timestamp is separate. Unknown numeric/year/URL/date fields remain JSON
null; zero is a real number. In Sheets, null is encoded as a blank cell and decoded
back to null in the schema's nullable columns. Blank versus null review_notes is
not distinguishable in Sheets; existing notes are never included in update ranges.

## Schema checks

The input JSON must have exactly the 18 research `COLUMNS` keys. Key ordering in JSON
objects is immaterial; encoding always uses canonical column order. Incoming status
is pending only; existing status may be pending, approved or rejected. Pilot scope,
field/value/year rules, source types, confidence and selection rules are checked.
Numbers are not coerced from strings; dates/years are not guessed. Majority counts,
no-selection flags, source/rule compatibility and nullable unresolved source URLs
are validated. Duplicate keys are rejected in both JSON objects and logical rows.

The Sheet adapter requires row 1 to be exactly those 18 headers in the approved order.
It does not create headers, reorder columns, create tabs, or alter formatting. It
reads only `'Staging'`, rejects extra header/data columns, preserves physical row
positions across blank rows, and treats nonempty partial/malformed rows as errors.
Use plain text for academic years and checked dates; Sheets date serials are rejected
rather than guessed. Extremely long text cells (>50000 UTF-16 units) are rejected,
never truncated. Keep source evidence externally when it cannot fit.

This validates the Staging boundary, not the factual accuracy of research. Review
flags and evidence remain intact; no candidate is automatically approved/promoted.

## Dry-run usage

From the repository root (Python 3.10+, standard library only):

```sh
python3 -B research/upload_staging.py --dry-run \
  --input research/output/pilot-01-staging.json \
  --report research/output/pilot-01-upload-dry-run.json
```

Omitting `--existing` means empty mocked Staging. To test synchronization against a
local snapshot, pass `--existing /absolute/path/to/existing-staging.json` (an array
of exact-schema row objects). This path is never interpreted as a spreadsheet ID.

Use a fresh report filename for every run. Reports must be new `.json` files inside
`research/output/`; they cannot overwrite input files or existing reports. Validations
are completed before an audit is written. On validation errors, a failure report is
written with no actions and the CLI exits nonzero. On invalid report paths or an
unwritable report, it exits without attempting synchronization.

Each report contains UTC timestamp, input-file path, dry-run mode, inserts, updates,
approved skips, rejected skips, no-op rows and validation errors. Action entries
contain only the three key fields, not evidence, credentials, tokens, or whole rows.
Malformed JSON parser diagnostics are suppressed to avoid echoing file content.
Reports and pilot research files remain ignored/private; do not publish them.

## Future Google setup — not configured or performed

A future integration must:

1. Enable Google Sheets API in an appropriate Google Cloud project.
2. Choose service-account authentication for an unattended process, ideally via
   workload identity/application-default credentials; or authorized-user OAuth for
   an interactive tool. Store any necessary credentials outside the repository in
   a secret manager or protected runtime configuration. Never log them.
3. Grant that identity access to the intended spreadsheet. If using a service
   account, share the specific spreadsheet with its service-account email.
4. Supply a Sheets v4 client to `GoogleSheetsStaging(service, spreadsheet_id, ...)`.
   This implementation does not construct the client, discover files, or obtain IDs.
5. Prepare the exact Staging header row and text-formatted year/date columns manually.
6. Arrange an **externally enforced exclusive edit window** before enabling writes.
   Provide its context-manager factory as `exclusive_edit_window`. The context must
   exclude human/UI edits and ALL other writers, not merely this Python process.
7. Preview, review, then apply a freshly read plan through a separately authorized
   integration. There is deliberately no live-write CLI in this version.

OAuth scopes apply to the spreadsheet file, not a single worksheet. For example,
`https://www.googleapis.com/auth/spreadsheets` is broader than Staging. The hard-coded
adapter boundary limits this uploader, but does not limit the credential itself.
Use Sheet protections/identity permissions and operational controls for other tabs;
never regard the local allowlist as Google-enforced per-tab authorization.

The adapter can only read `'Staging'` and emit value writes to `'Staging'!A:R`.
There is no arbitrary worksheet parameter, generic write method, promotion method,
or code path for School, Sources, Editorial, Supabase, frontend or CSV writes.

## Concurrency and failure handling

The pure plan includes a fingerprint of all validated existing rows, their order
and physical positions. Before a write, the adapter re-reads Staging while inside
the externally supplied edit window. Any row/status/note/key/value/position change,
new row, deletion or invalid header aborts the entire batch. Tests explicitly cover
pending -> approved/rejected and human-note edits between planning and applying.
Incoming human columns are never used in pending updates. Plans are checked again
before write requests are constructed to reject forged unsafe actions.

Google Sheets Values API does not provide a row-level compare-and-swap in this
implementation. Re-reading alone leaves a race between that read and the write;
a batch request is not a conditional write. Therefore real writes are disabled by
default. A process-local mutex, a `nullcontext`, or an acknowledgement flag is NOT a
valid real edit-window implementation. Without external exclusion of human edits,
this version must remain dry-run; it cannot promise never to refresh a just-approved
row. Default refusal makes that limitation explicit rather than silently accepting it.

Under the required edit window, one RAW batch writes all inserts/updates. Pending
updates write A:O and R only (never status P or review_notes Q). Inserts start after
the final nonempty row; blank gaps are not reused. RAW keeps leading `=` evidence as
literal text instead of formulas. No automatic retries are performed. If the network
result is uncertain, re-read the sheet and replan; never blindly replay insert ranges.
The mock provides true check-and-write atomicity under one lock, but its guarantees
must not be attributed to Google Sheets.

## Tests

```sh
python3 -B -m unittest discover -s research -p 'test_*.py' -v
node --test supabase/functions/compare-schools/handler.test.mjs
```

References (documentation only, no Sheet access):
- https://developers.google.com/workspace/sheets/api/scopes
- https://developers.google.com/workspace/sheets/api/guides/values
- https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets.values/batchUpdate
