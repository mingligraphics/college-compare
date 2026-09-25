# Basic v1 pilot database migration — 2026-09-25

Source: authoritative School!A1:AN4 in spreadsheet 1gMcmRGVxWgw4olbax2Vwxf4ZDJroBaHShH8A1qAjkrw, read twice before execution. Target: hmnoqybdcfwqbjhorwzd, private.schools. Scope: nyu, bu, ucb only.

## Schema

Rename tuition → tuition_fees and tuition_year → tuition_fees_year in place, preserving existing values and constraints. Add the following nullable columns without defaults or backfills:

- `institution_control`: `text`
- `state_cn`: `text`
- `undergrad_enrollment`: `integer`
- `undergrad_enrollment_year`: `text`
- `applicants`: `integer`
- `admitted`: `integer`
- `acceptance_rate`: `numeric(5,2)`
- `admissions_year`: `text`
- `sat_25`: `integer`
- `sat_75`: `integer`
- `act_25`: `integer`
- `act_75`: `integer`
- `test_policy`: `text`
- `test_policy_cycle`: `text`
- `international_pct_year`: `text`
- `international_pct_scope`: `text`
- `graduation_rate_4yr`: `numeric(5,2)`
- `graduation_rate_4yr_year`: `text`
- `international_need_aid`: `text`
- `international_merit_aid`: `text`
- `english_proficiency_policy`: `text`
- `english_tests_accepted`: `text[]`
- `english_policy_cycle`: `text`
- `ranking_usnews`: `integer`
- `ranking_category`: `text`
- `ranking_year`: `integer`

Existing eight Deep columns are untouched. The live pre-migration database has no GPA columns; all five GPA columns in School remain untouched. No columns/tables are dropped. Existing RLS, grants, and private-schema exposure remain unchanged.

## Derived values

`private.schools_basic_v1` is a security-invoker view containing the 40 Basic fields and three calculated fields. Region uses the approved state mapping in Basic_v1_migration. location_cn uses city_cn || state_cn, in the source's stated order, returning NULL if either input is NULL. ranking_tier uses the approved 30/50/100/200 boundaries; absent numerical rank yields unranked per the approved rule. Unknown state maps to NULL. No new derived values are stored.

The pre-existing manual `private.schools.region` and `location_cn` columns are retained unchanged for old RPC compatibility; they are legacy values, not the canonical Basic v1 projection. The next API phase should consume the view's calculated values.

## Minimal compatibility change

The migration changes only `s.tuition` and `s.tuition_year` references inside the existing get_school_comparison RPC to the renamed columns. Its signature, output field names, permissions, security settings, and pair-only behavior remain unchanged. No Edge Function, frontend, CSV, or publisher code is changed.

The legacy five-field publisher is not Basic v1 compatible after the rename. Do not run publish_approved.py: its September 23 snapshot contains obsolete costs. This phase uses a separate guarded SQL sync, rather than expanding the publisher early. Updating that publisher remains the next phase.

## Sync and safety

`sync_pilot_basic_v1.sql` is a one-time update-only script built from the live School values. It requires an exact before-image of all existing database records, takes a table write lock, updates only the 39 non-key Basic columns on each pilot, asserts all 120 Basic fields, and asserts every other column and row identity unchanged before commit. If its before-image no longer matches, re-inspect; do not bypass the guard. Blank cells become SQL NULL; JSON text containing accepted English-test lists becomes text[] without changing values or ordering. Percentages remain percentage points. Berkeley costs are 58484 and 93944.

The deployed operation combines schema migration, guarded sync, and migration-history insertion in one transaction, following a successful rollback rehearsal. No automatic retry on uncertain commit. Re-read database state before any recovery. The schema file alone contains no school data changes. Avoid a blind down-migration; use the saved before snapshot for a separately reviewed recovery.

## Validation

Rollback rehearsal: all 120 Basic fields; all non-Basic fields; RPC pairs and legacy tuition alias; derived pilot values; NULL propagation; zero preservation; all ranking tier boundaries; percentage constraint; RLS and view/RPC grants. Existing suites: 115 Python tests and 27 API tests passed. Production readback results are in the accompanying report.

## Subsequent publisher/API phase

The phase-one statements above describe the migration checkpoint. The publisher
has now been upgraded to the 40-field contract and the old production approval
removed. See PUBLISHER.md. A separate Basic v1 RPC/Edge endpoint serves canonical
and derived values while leaving the original endpoint available for rollout.
