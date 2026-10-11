# College Compare migration — 2026-10-10

Separate test: https://college-compare-migration-test.stillsnail16.chatgpt.site
Audience: owner-private, ChatGPT login required. No production promotion.
Canonical local branch: discovery-supabase-test (based on b08bbef9295a98921c6eabe3d7660b72a7e9ce31).
Separate Sites source commit: 09532a65cdb8c788550e55cc11c155309a710c98.
Deployment: appgdep_6aca426132d88191b1404a3f9a96aeb7 (succeeded).

## Implemented

`dist/` is the deliberate static deployment boundary for a future GitHub Pages test repository. The original root homepage, school.csv, all historical SQL data files, prototype, and old deployed preview remain untouched. Do not deploy the entire repository root for this migration.

Discovery prototype appearance, Chinese/English/abbreviation search, geographic/size/USD-COA/type filters, missing-data choices, reset, 12-card pagination, detail dialogs, two-school selection, persistence and URL handoff are retained. Both comparison views use compare-schools-basic-v2. The complete comparison tables reuse production normalization/rendering. Each relevant field now shows its year/cycle or a missing-year message. Directory labels show retrieval time instead of a fixed snapshot date.

Both full embedded snapshots are absent from the new pages. No snapshot fallback is used. Directory failure shows retry; comparison failure allows retry. Requests have 15-second client and 10-second endpoint timeouts. Both comparison views reject mismatched pair order. Selection-version checks prevent stale comparison results from showing after selection changes; the discovery dialog also checks request identity. Selection persistence validates and deduplicates stored IDs. Selected-pair responses are cached in memory and only the most recently selected pair is stored in sessionStorage for a maximum five-minute handoff window. Clearing site storage removes these local selections/caches.

New public Edge Function: https://hmnoqybdcfwqbjhorwzd.supabase.co/functions/v1/discover-schools
POST with application/json and `{}`. New RPC: public.get_school_discovery_v1().
Exactly 18 fields, no dialog-driven expansion:
school_id, school_name, school_name_cn, short_name, city, city_cn, state, state_cn, region, school_type, undergrad_enrollment, undergrad_enrollment_year, acceptance_rate, admissions_year, coa, coa_year, tuition_fees, tuition_fees_year.

The RPC reads the existing publication view joined with the school table, using SECURITY DEFINER with an empty search_path. Only service_role and owner may execute it; table and existing RPC grants are unchanged. The new endpoint enforces an empty bounded JSON request, response allowlist, duplicate-ID/schema checks, sanitized errors and no-store. No school rows, existing endpoint authentication/CORS configuration, rate-limit settings, or data classifications were changed. The newly applied migration is recorded in migration history.

GitHub credentials were unavailable. Authenticated Pages publishing settings and a separate GitHub test repository could not be obtained. The canonical migration branch is local and unpushed. The fallback is a genuinely separate owner-private Sites project. Its Worker serves only explicit frontend routes and forwards only the directory and pair endpoints, bounded to 1 KB with a 12-second timeout. It uses no privileged credentials. This avoids changing existing Supabase CORS settings. It is test-hosting code, not required for the future GitHub deployment.

## Verification

- Live database: 299 rows before/after; MD5 of ordered full rows unchanged: c5d08e09584b145dd8adfddaf10ba506. Direct SELECT is denied for anon and authenticated on private.schools and private.schools_basic_v1. All three existing comparison RPCs and the new directory RPC are service-only. The underlying table has RLS; the view does not itself have RLS but has no visitor grants. See verification/database-after.json. The initial fingerprint and grant result were observed before deployment; the retained database-after.json is the post-deployment result.
- Live directory: 299 unique records, exactly 18 fields, correct GitHub CORS origin.
- Live v2: NYU–BU, BU–NYU and Amherst–Babson returned exactly two ordered 57-field records. All 18 overlapping values equal the directory. Same-school request returned 400; unknown ID returned 404; discovery field-expansion request returned 400. This verifies these pairs, not independent freshness of every university field.
- Seven focused tests passed: endpoint allowlist/preflight/invalid requests/upstream failures, actual filter boundaries and missing values, pair caching/order rejection, snapshot/credential scan. Both final HTML scripts passed syntax checks.
- Local browser using live Supabase through the same Worker: abbreviation search, Chinese search, selection, comparison dialog, detail dialog, URL handoff and complete tables, selection persistence on reload/navigation, pagination, missing-enrollment filtering. Mobile comparison at 390 px renders 16 metric rows with document width equal to viewport width (no horizontal overflow).
- Production: current main SHA remains b08bbef9295a98921c6eabe3d7660b72a7e9ce31; delivered homepage bytes equal the untouched baseline. See verification/production-unchanged.json.
- Published archive source matches pushed Worker. The package has only the Worker and hosting metadata (plus macOS AppleDouble metadata). Explicit visitor assets are /, /index.html, /existing-comparison[.html], /api.js, /wechat-qr.jpeg. No 299-profile literals, credential markers, SQL, research, backups or source datasets are present. No arbitrary file serving is implemented; unknown paths return 404. See verification/asset-audit.json.
- Native publishing confirms success. An actual browser visit encountered the owner login gate; no login credentials were available. Hosted page/API asset retrieval, host-injected scripts and a complete live network capture remain unverified. No login bypass token was generated and access settings were not changed. Package audit and local live-data verification must not be described as exhaustive hosted-asset verification.
- Mainland China connectivity has not been tested.

## Anonymous extraction risk and user review

The entire 18-field directory is intentionally downloadable. The existing comparison API remains anonymous. An operator can repeatedly request different pairs to collect all detailed profiles, including hidden GPA methodology and signature-program selection_basis fields. Pair limits, RPC/table grants and CORS do not prevent that collection. The new private test relay preserves the two existing API contracts; it does not add authorization or rate limiting. No exhaustive bulk extraction was performed.

Before production promotion, review whether anonymous access to every v2 field is acceptable, whether authentication/rate limiting or a narrower comparison projection is needed (separate approval/scope), and whether the limited public directory is acceptable. Historical preview snapshots, public SQL artifacts and Git history remain exposed as previously audited and require separate review; this migration does not erase them.

Also review the fallback relay/test-hosting choice, obtain GitHub write/Pages access if a same-origin GitHub test deployment is preferred, complete authenticated hosted-browser verification, and decide whether to make ONLY the separate test site shareable for your sister. Production promotion requires explicit approval.

## Mainland China test instructions

The current test site requires the owner's ChatGPT login. Do not share account credentials. Your sister cannot independently test it until a separate shareable test deployment is available or this test site's audience is intentionally changed. GitHub test hosting is preferable for testing the proposed GitHub-to-Supabase production path; the Sites relay tests a different path and cannot prove direct browser access to Supabase from China.

Once a suitable test URL is available, test without VPN, first on home broadband and then mobile data:
1. Open the homepage; record whether the page itself opens and how long the 299-school directory takes to appear.
2. Search NYU, 纽约大学 and Boston University. Try region, small/medium/large size, each COA range, and 暂无数据; reset and page forward/back.
3. Add NYU and BU, open details, compare, then enter the complete comparison page. Confirm names/order, cost/admissions years and the richer tables. Reload and confirm the shortlist remains.
4. Compare Amherst–Babson or another pair. Confirm neither school is silently replaced and missing fields say 暂无数据.
5. Temporarily disconnect the network, attempt a new uncached pair or reload the directory, restore the network and use retry. Previously cached selected pairs may still display briefly.
6. Record device/browser, network/provider, local date/time, URL, page-load result, directory result, comparison result, delay and exact displayed error. Distinguish a website/login failure from a directory/API failure. Send screenshots with private account details hidden.

For the Sites fallback, failures may occur at ChatGPT login, Sites hosting or the relay. For a GitHub test, the browser connects directly to Supabase. Results from one path must not be assumed to validate the other.

## Operator follow-up

Do not merge/promote. Serve only `dist/` for future static publication. Apply no broad `db push` from an old checkout; inspect migration history first. The rollback for the newly added functionality is to stop using this test frontend, then separately drop the new function/RPC only if explicitly requested; production continues to work with its unchanged existing endpoints.
