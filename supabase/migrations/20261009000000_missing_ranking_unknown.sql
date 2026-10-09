-- Missing ranking is unknown; no unranked status is inferred. No stored school data or output columns change.
BEGIN; SET LOCAL lock_timeout='5s'; SET LOCAL statement_timeout='30s';
CREATE TEMP TABLE ranking_guard ON COMMIT DROP AS SELECT jsonb_agg(to_jsonb(s) ORDER BY school_id) AS rows FROM private.schools s;
DO $guard$ BEGIN IF (SELECT count(*) FROM private.schools) <> 299 OR (SELECT count(*) FROM private.schools WHERE ranking_usnews IS NULL) <> 44 THEN RAISE EXCEPTION 'Universe or rank baseline changed'; END IF; END $guard$;
CREATE OR REPLACE VIEW private.schools_basic_v1 WITH (security_invoker=true) AS  SELECT school_id,
    school_name,
    school_name_cn,
    short_name,
    institution_control,
    school_type,
    city,
    city_cn,
    state,
    state_cn,
    tuition_fees,
    tuition_fees_year,
    coa,
    coa_year,
    undergrad_enrollment,
    undergrad_enrollment_year,
    applicants,
    admitted,
    first_year_enrollment,
    acceptance_rate,
    admissions_year,
    sat_25,
    sat_75,
    act_25,
    act_75,
    test_policy,
    test_policy_cycle,
    international_pct,
    international_pct_year,
    international_pct_scope,
    graduation_rate_4yr,
    graduation_rate_4yr_year,
    international_need_aid,
    international_merit_aid,
    english_proficiency_policy,
    english_tests_accepted,
    english_policy_cycle,
    ranking_usnews,
    ranking_category,
    ranking_year,
        CASE
            WHEN state = ANY (ARRAY['ME'::text, 'NH'::text, 'VT'::text, 'MA'::text, 'RI'::text, 'CT'::text, 'NY'::text, 'NJ'::text, 'PA'::text, 'DE'::text, 'MD'::text, 'DC'::text]) THEN 'east_coast'::text
            WHEN state = ANY (ARRAY['VA'::text, 'WV'::text, 'NC'::text, 'SC'::text, 'GA'::text, 'FL'::text, 'KY'::text, 'TN'::text, 'AL'::text, 'MS'::text, 'AR'::text, 'LA'::text, 'TX'::text, 'OK'::text]) THEN 'south'::text
            WHEN state = ANY (ARRAY['OH'::text, 'MI'::text, 'IN'::text, 'IL'::text, 'WI'::text, 'MN'::text, 'IA'::text, 'MO'::text, 'ND'::text, 'SD'::text, 'NE'::text, 'KS'::text]) THEN 'midwest'::text
            WHEN state = ANY (ARRAY['CA'::text, 'OR'::text, 'WA'::text]) THEN 'west_coast'::text
            WHEN state = ANY (ARRAY['MT'::text, 'ID'::text, 'WY'::text, 'CO'::text, 'NM'::text, 'AZ'::text, 'UT'::text, 'NV'::text]) THEN 'mountain_west'::text
            WHEN state = ANY (ARRAY['AK'::text, 'HI'::text]) THEN 'other'::text
            ELSE NULL::text
        END AS region,
    city_cn || state_cn AS location_cn,
        CASE
            WHEN ranking_usnews IS NULL THEN NULL::text
            WHEN ranking_usnews <= 30 THEN 'top_30'::text
            WHEN ranking_usnews <= 50 THEN 'top_50'::text
            WHEN ranking_usnews <= 100 THEN 'top_100'::text
            WHEN ranking_usnews <= 200 THEN 'top_200'::text
            ELSE 'outside_200'::text
        END AS ranking_tier
   FROM private.schools s;
DO $verify$ BEGIN IF (SELECT jsonb_agg(to_jsonb(s) ORDER BY school_id) FROM private.schools s) IS DISTINCT FROM (SELECT rows FROM ranking_guard) THEN RAISE EXCEPTION 'Stored data changed'; END IF; IF EXISTS (SELECT 1 FROM private.schools_basic_v1 WHERE ranking_usnews IS NULL AND ranking_tier IS NOT NULL) THEN RAISE EXCEPTION 'Missing ranking tier is not null'; END IF; END $verify$;
COMMIT;
