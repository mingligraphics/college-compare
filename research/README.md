# Local research-to-Staging collector (pilot)

This framework does not fetch university pages, access Google Sheets, connect to
Supabase, import seed data, or promote anything. Only `nyu`, `bu`, `ucb` and
`tuition`, `coa`, `first_year_enrollment` are accepted. Python 3.10+; standard
library only. No API keys or dependencies are needed.

## Files and data flow

1. **Research/retrieval, outside this implementation:** a researcher or future
   source-specific adapter saves a dated UTF-8 source excerpt/snapshot and its
   source manifest. For a PDF, preserve the original document separately, extract
   a reproducible text snapshot, and include page/table context in the excerpt.
   Do not use a generic page scraper or infer an unknown page layout.
2. **Normalized candidates:** the researcher/adapter supplies typed JSON records,
   citing literal excerpts from those snapshots. No school facts are embedded in
   application code. Current School values arrive as a separate read-only snapshot.
3. **`sources.py`:** validates reviewer approval, metadata, snapshot paths and
   SHA-256 hashes. Candidate evidence must occur verbatim in the snapshot.
4. **`staging.py`:** validates inputs, selects a strict-majority figure when justified,
   compares it with School values for the same field/year, and creates Staging rows.
5. **`collect.py`:** validates the whole batch before writing a new local JSON file
   under `research/output/`. Existing output files are not overwritten. JSON null
   preserves unknown separately from zero. There is no promotion/writer for School,
   Sources, Editorial, Sheets, Supabase, the frontend, or public CSV.
6. **`test_pipeline.py`:** synthetic fixtures and local CLI integration checks in
   temporary directories. Its numbers are fictional test inputs, not pilot data.

## Inputs

All three input files are JSON arrays. Reject unknown/missing keys, duplicate JSON
keys, nonstandard NaN/Infinity, numeric strings, booleans as numbers, invalid dates,
invalid years, and duplicate candidate/current records. Strings are not silently
trimmed or repaired. Academic years must be consecutive `YYYY-YY` (e.g. `2026-27`).

### Source manifest

Example is **synthetic**, not an approved real source. Replace every example with
reviewed evidence; compute the actual hash with `shasum -a 256 evidence.txt`.

```json
[
  {
    "source_id": "synthetic-source",
    "source_name": "Synthetic university document",
    "source_url": "https://example.edu/synthetic",
    "source_type": "university",
    "approved_by": "reviewer-name",
    "checked_date": "2026-01-01",
    "evidence_file": "evidence.txt",
    "sha256": "REPLACE_WITH_64_LOWERCASE_HEX_CHARACTERS"
  }
]
```

`source_type` is exactly `university`, `CDS`, or `nonprofit_research`.
`approved_by` records a human's approval of source eligibility. HTTPS/domain names
and this string do **not** independently prove university ownership, CDS provenance,
nonprofit credibility, or reviewer identity; those are manual setup responsibilities.
`checked_date` is the date the source was checked, never the output-generation date.
Future dates are rejected. `evidence_file` must resolve within the manifest folder.
Keep snapshots immutable and retain them with the manifest/inputs for reproducibility.

Prefer original university/CDS evidence. If both original and nonprofit candidates
exist for the same school/field/year in a batch, the nonprofit row receives an
explicit original-source preference flag. Both remain pending; conflicting original
sources are also retained for human review, never silently merged or promoted.

### Candidate: one unambiguous published value

```json
[
  {
    "school_id": "nyu",
    "field": "tuition",
    "academic_year": "2026-27",
    "source_id": "synthetic-source",
    "evidence": "SYNTHETIC: university-wide undergraduate tuition is 100 USD.",
    "confidence": "high",
    "population": "undergraduate",
    "selection_rule": "direct",
    "candidate_value": 100
  }
]
```

This is a structural example, **not NYU research**. The excerpt must occur verbatim
in the saved snapshot. `direct` means a single unambiguous university-wide cost
schedule (with consistent residency/campus/enrollment/budget assumptions), or an
explicit first-year enrollment count. Do not use it to bypass conflicting costs
among undergraduate schools/programs. A reviewer must verify this interpretation.
`candidate_value: null` produces a flagged no-selection row.

Tuition/COA are raw nonnegative USD numbers with at most two decimal places.
Enrollment must be a nonnegative JSON integer with `population: "first_year"`.
Never relabel total undergraduate enrollment. Cost candidates require
`population: "undergraduate"`. Include definition, residency, campus, fee coverage,
year, and table/page identifiers in the evidence when applicable; never combine
incompatible student categories or assume current tuition applies to another year.

`confidence` must be `high`, `medium`, or `low`, assigned by the researcher to the
extraction/evidence quality. It is not a probability or approval. Legacy `direct`/`majority_gt_50` no-selection rows
are `low`. Named reviewed rules retain the supplied evidence confidence even when
selection is unresolved: certainty that alternatives exist is not certainty in one
selected value. Every output status is always `pending`.

### Candidate: differentiated costs / majority rule

Use the same common fields but replace `candidate_value` with `coverage_basis`,
`coverage_units`, and `observations`; set `selection_rule` to `majority_gt_50`.
For example, the additional fields are:

```json
{
  "selection_rule": "majority_gt_50",
  "coverage_basis": "schools",
  "coverage_units": ["school-A", "school-B", "school-C"],
  "observations": [
    {"candidate_value": 100, "covered_units": ["school-A", "school-B"],
     "evidence": "SYNTHETIC: schools A and B charge 100 USD."},
    {"candidate_value": 200, "covered_units": ["school-C"],
     "evidence": "SYNTHETIC: school C charges 200 USD."}
  ]
}
```

- Choose **one consistent denominator**: undergraduate `schools` or `programs`,
  never student headcount and never mixed/nested units. Evidence must substantiate
  the complete denominator, not just the subset that published prices. Choosing and
  verifying the unit basis is a human research responsibility.
- Each covered unit must belong to the population and appear at most once, including
  observations with unknown amounts. Duplicate/overlapping coverage is rejected.
- Equal published amounts are aggregated by distinct unit count. No averages.
- Select only if `coverage_numerator * 2 > coverage_denominator`. Exactly 50%, ties,
  and insufficient evidence produce null selection and an explanatory flag.
- Missing observations do not reduce the denominator. Null amounts contribute no
  votes; zero is a valid amount. Unknown coverage is represented with
  `covered_units: null`; an unknown universe uses `coverage_units: null` and all
  `covered_units: null`. Such records are valid but always require manual review.
- No-selection output uses `coverage_numerator: null`; the denominator is retained
  if known. Every observed alternative, covered-unit set, basis and evidence excerpt
  is serialized into the Staging `evidence` cell for review.
- Do not mix academic years or source documents within a candidate group. Multiple
  sources produce separate pending candidates. The collector cannot automatically
  verify that an extracted number or coverage claim is semantically supported by
  the excerpt; matching text and hashes prove reproducibility, not factual accuracy.

### Current School snapshot (normalized adapter format)

```json
[
  {"school_id": "nyu", "field": "tuition",
   "current_value": null, "current_year": null}
]
```

This long-form format is an adapter boundary, not a change to the Google Sheet.
There must be at most one record per pilot school/field. A known value may have an
unknown academic year (`null`); that condition is explicitly noted and is never
treated as a like-for-like change. An unknown value can retain a known year or use null. A missing record
is distinguished from an explicitly unknown value in `review_notes`.

Same-year equality/difference, unknown current values, and year mismatches are
reported in review notes. No cross-year numeric comparison is presented as a change.
The source check date is copied unchanged. No current School value is written back.

## Exact output columns (and insertion order)

```text
school_id
field
candidate_value
academic_year
source_name
source_url
source_type
evidence
current_value
current_year
coverage_numerator
coverage_denominator
selection_rule
confidence
flag_reason
status
review_notes
checked_date
```

No extra output columns. `flag_reason`/`review_notes` are strings; no flag is `""`.
Unknown numeric/year/coverage values use JSON null. Evidence also retains snapshot
path, SHA-256, source ID and approver. No automatic timestamps replace checked dates.

## Run locally

Prepare the source manifest/snapshots, candidates, and School snapshot manually in a
private local input directory. Do not put research artifacts in a publicly served
GitHub Pages directory or commit them to a public repository. This framework creates
no input data and no factual seed records.

From the repository root, using Python 3.10+:

```sh
python3 -B research/collect.py \
  --sources /absolute/path/to/private-inputs/sources.json \
  --candidates /absolute/path/to/private-inputs/candidates.json \
  --current /absolute/path/to/private-inputs/current.json \
  --output research/output/staging-review.json

python3 -B -m unittest discover -s research -p 'test_*.py' -v
```

The CLI performs no network requests. It rejects output outside `research/output/`,
non-JSON output, input replacement, and existing output paths. Keep generated output
private too; local `.gitignore` prevents accidental ordinary commits but is not a
hosting access control. No Sheet ID/credentials are needed until a separately
approved integration is implemented.

Before real research: agree on coverage units/cost scope, identify eligible original
sources and human approvers, and export current School values into this input format.
No changes to the Sheet's School, Sources, Editorial or Staging tabs are made here.

## Reviewed pilot findings extension (no new Staging columns)

The original input contract cannot faithfully encode all nine supplied pilot cases:
its two selection rules, mandatory checked dates/URLs, known-current-year requirement,
and named-unit-only majority input would force invented facts or misleading labels.
The following narrowly scoped input extensions avoid that. The exact 18-column
output stays unchanged, including its `pending` status invariant.

### Evidence origin and missing provenance

A manifest may add `evidence_kind: "reviewed_findings"`. Its evidence file is the
saved reviewed research narrative, **not** a downloaded source snapshot. The hash
and verbatim excerpt checks still apply. `approved_by` identifies who supplied the
reviewed input, not a new verification of source eligibility. Outputs explicitly
record this evidence kind and state that no cited URL was fetched in this run.

Only this mode permits a null `checked_date`; it always creates a missing-date flag.
Do not assign today's date when the original source-check date is unknown. Null
`source_url` is allowed only for an `unresolved_source_conflict` candidate with no
selected value. Source identity/eligibility are then flagged. A provisionally
reported `nonprofit_research` classification must be identified as unverified in
source name and notes, rather than inventing an institution/URL. Ordinary
`source_snapshot` manifests still require HTTPS URLs and actual source-check dates.

### Named interpretations

Named rules require reviewed-findings provenance and these additional common fields:

- `source_concept`: explicit source measure, e.g. `tuition_only`, `tuition_and_fees`,
  or `new_first_time_college_entrants`.
- `review`: exactly `{"flag_reason": "...", "review_notes": "..."}`. These are
  carried into the existing Staging fields; they cannot change status.

Accepted named rules:

| Rule | Required interpretation |
|---|---|
| `majority_undergraduate_schools` | Strict >50% of reviewed undergraduate school/program group counts |
| `university_standard` | Reviewed university standard tuition/COA; concept and caveats retained |
| `resident_standard` | Reviewed resident COA; exceptions require explicit flags |
| `cds_reported` | First-year enrollment with CDS provenance |
| `university_reported` | First-year enrollment with university provenance |
| `unresolved_source_conflict` | Null selection; preserve competing observations in evidence |
| `living_arrangement_ambiguous` | COA null selection; preserve living-arrangement alternatives |

Except the majority rule, these records contain `candidate_value`, `alternatives`,
and `components` in addition to the original common fields. Each alternative or
component has exactly `label`, `candidate_value`, and verbatim `evidence`.

- Alternatives preserve amounts and scope without averaging; an exception with an
  unsupplied amount uses null. Alternatives require a nonblank review flag.
- Components are optional (`[]` means none supplied, not a verified absence). When
  supplied, they must be known first-year counts with distinct labels whose sum
  equals the selected total. Do not invent a component breakdown from a total.
- Unresolved rules require null selection, a flag, and at least one alternative.
- A tuition concept other than `tuition_only` requires a semantic-review flag.
- Known values remain candidates, not approvals. Preserve confidence separately from
  the decision to select; an ambiguous COA can have high evidence confidence.

The reported-majority rule instead contains `coverage_denominator` and `observations`.
Each observation has exactly `label`, `candidate_value`, `coverage_count`, `evidence`.
Counts are positive integers; distinct group labels and total count <= denominator
are required. Equal values aggregate; null amounts get no votes; exactly 50% fails.
The collector calculates the winning numerator/value, never trusts an input winner.
It always flags that group counts are reviewed assertions, not a checked unit roster.
Do not fabricate names when only aggregate counts were supplied. Raw unit-based
`majority_gt_50` remains available for independently auditable named-unit coverage.

### Local pilot 01

Private, ignored files live in `research/inputs/pilot-01/`:
`sources.json`, `candidates.json`, `current.json`, `reviewed-findings.txt`, `README.md`.
The narrative is an exact copy of the user-supplied findings, with no web retrieval.
Only the explicitly supplied current School value (NYU first-year count 5723) is in
the current snapshot, with unknown year. Other current records are missing, not
assumed blank or read from a live Sheet. Missing detailed source evidence remains
flagged: NYU group roster and exceptional COA amounts, BU CGS amount and CDS components.

```sh
python3 -B research/collect.py \
  --sources research/inputs/pilot-01/sources.json \
  --candidates research/inputs/pilot-01/candidates.json \
  --current research/inputs/pilot-01/current.json \
  --output research/output/pilot-01-staging.json
```

Choose a new output filename to rerun without overwriting. The real-pilot tests use
these private local files and generated output; they explicitly skip if the private
inputs are absent on another checkout. General contract tests use disposable
synthetic fixtures and always run. No factual values are in application logic.

## Offline Staging uploader

`upload_staging.py` validates the exact 18-column output and plans insert/update/skip
operations against local mocked Staging rows. It never connects to Google Sheets.
See [UPLOADER.md](UPLOADER.md) for candidate keys, human-field protection, audit
reports, the injected Staging-only adapter and the mandatory concurrency guard.
