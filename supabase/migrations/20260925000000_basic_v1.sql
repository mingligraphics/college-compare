-- Basic v1: preserve Deep columns and legacy derived columns; never backfill unapproved values.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';
ALTER TABLE private.schools RENAME COLUMN tuition TO tuition_fees;
ALTER TABLE private.schools RENAME COLUMN tuition_year TO tuition_fees_year;
ALTER TABLE private.schools
 ADD COLUMN institution_control text,
 ADD COLUMN state_cn text,
 ADD COLUMN undergrad_enrollment integer CHECK (undergrad_enrollment >= 0),
 ADD COLUMN undergrad_enrollment_year text,
 ADD COLUMN applicants integer CHECK (applicants >= 0),
 ADD COLUMN admitted integer CHECK (admitted >= 0),
 ADD COLUMN acceptance_rate numeric(5,2) CHECK (acceptance_rate BETWEEN 0 AND 100),
 ADD COLUMN admissions_year text,
 ADD COLUMN sat_25 integer CHECK (sat_25 >= 0),
 ADD COLUMN sat_75 integer CHECK (sat_75 >= 0),
 ADD COLUMN act_25 integer CHECK (act_25 >= 0),
 ADD COLUMN act_75 integer CHECK (act_75 >= 0),
 ADD COLUMN test_policy text,
 ADD COLUMN test_policy_cycle text,
 ADD COLUMN international_pct_year text,
 ADD COLUMN international_pct_scope text,
 ADD COLUMN graduation_rate_4yr numeric(5,2) CHECK (graduation_rate_4yr BETWEEN 0 AND 100),
 ADD COLUMN graduation_rate_4yr_year text,
 ADD COLUMN international_need_aid text,
 ADD COLUMN international_merit_aid text,
 ADD COLUMN english_proficiency_policy text,
 ADD COLUMN english_tests_accepted text[],
 ADD COLUMN english_policy_cycle text,
 ADD COLUMN ranking_usnews integer CHECK (ranking_usnews >= 1),
 ADD COLUMN ranking_category text,
 ADD COLUMN ranking_year integer CHECK (ranking_year >= 1);

-- Keep the old RPC response names/signature; only its two source references change.
CREATE OR REPLACE FUNCTION public.get_school_comparison(p_school_id_a text, p_school_id_b text)
 RETURNS TABLE(school_id text, school_name text, school_name_cn text, short_name text, school_type text, city text, city_cn text, state text, location_cn text, region text, tuition numeric, tuition_year text, coa numeric, coa_year text, first_year_enrollment integer, international_pct numeric, campus_type text, campus_description text, campus_description_cn text, famous_majors text[], famous_majors_cn text[], career_model text, career_model_cn text, notable_alumni text[])
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
  matched_count integer;
begin
  if p_school_id_a is null or p_school_id_b is null
     or p_school_id_a !~ '[^[:space:]]'
     or p_school_id_b !~ '[^[:space:]]' then
    raise exception 'Two nonblank school IDs are required'
      using errcode = '22023';
  end if;

  if p_school_id_a = p_school_id_b then
    raise exception 'School IDs must be distinct'
      using errcode = '22023';
  end if;

  return query
    select
      s.school_id,
      s.school_name,
      s.school_name_cn,
      s.short_name,
      s.school_type,
      s.city,
      s.city_cn,
      s.state,
      s.location_cn,
      s.region,
      s.tuition_fees,
      s.tuition_fees_year,
      s.coa,
      s.coa_year,
      s.first_year_enrollment,
      s.international_pct,
      s.campus_type,
      s.campus_description,
      s.campus_description_cn,
      s.famous_majors,
      s.famous_majors_cn,
      s.career_model,
      s.career_model_cn,
      s.notable_alumni
    from private.schools as s
    where s.school_id in (p_school_id_a, p_school_id_b)
    order by case when s.school_id = p_school_id_a then 0 else 1 end;

  -- Fail the whole call rather than return a partial comparison.
  get diagnostics matched_count = row_count;
  if matched_count <> 2 then
    raise exception 'Both school IDs must exist'
      using errcode = 'P0002';
  end if;
end;
$function$
;

-- Canonical product projection. No new stored derived values and no API exposure.
-- Unknown state/location inputs stay NULL. Approved rule: absent numerical rank => unranked.
CREATE VIEW private.schools_basic_v1 WITH (security_invoker = true) AS
SELECT
 s.school_id,
 s.school_name,
 s.school_name_cn,
 s.short_name,
 s.institution_control,
 s.school_type,
 s.city,
 s.city_cn,
 s.state,
 s.state_cn,
 s.tuition_fees,
 s.tuition_fees_year,
 s.coa,
 s.coa_year,
 s.undergrad_enrollment,
 s.undergrad_enrollment_year,
 s.applicants,
 s.admitted,
 s.first_year_enrollment,
 s.acceptance_rate,
 s.admissions_year,
 s.sat_25,
 s.sat_75,
 s.act_25,
 s.act_75,
 s.test_policy,
 s.test_policy_cycle,
 s.international_pct,
 s.international_pct_year,
 s.international_pct_scope,
 s.graduation_rate_4yr,
 s.graduation_rate_4yr_year,
 s.international_need_aid,
 s.international_merit_aid,
 s.english_proficiency_policy,
 s.english_tests_accepted,
 s.english_policy_cycle,
 s.ranking_usnews,
 s.ranking_category,
 s.ranking_year,
 CASE
 WHEN s.state IN ('ME', 'NH', 'VT', 'MA', 'RI', 'CT', 'NY', 'NJ', 'PA', 'DE', 'MD', 'DC') THEN 'east_coast'
 WHEN s.state IN ('VA', 'WV', 'NC', 'SC', 'GA', 'FL', 'KY', 'TN', 'AL', 'MS', 'AR', 'LA', 'TX', 'OK') THEN 'south'
 WHEN s.state IN ('OH', 'MI', 'IN', 'IL', 'WI', 'MN', 'IA', 'MO', 'ND', 'SD', 'NE', 'KS') THEN 'midwest'
 WHEN s.state IN ('CA', 'OR', 'WA') THEN 'west_coast'
 WHEN s.state IN ('MT', 'ID', 'WY', 'CO', 'NM', 'AZ', 'UT', 'NV') THEN 'mountain_west'
 WHEN s.state IN ('AK', 'HI') THEN 'other'
 ELSE NULL END AS region,
 s.city_cn || s.state_cn AS location_cn,
 CASE WHEN s.ranking_usnews IS NULL THEN 'unranked'
      WHEN s.ranking_usnews <= 30 THEN 'top_30'
      WHEN s.ranking_usnews <= 50 THEN 'top_50'
      WHEN s.ranking_usnews <= 100 THEN 'top_100'
      WHEN s.ranking_usnews <= 200 THEN 'top_200'
      ELSE 'outside_200' END AS ranking_tier
FROM private.schools s;
ALTER VIEW private.schools_basic_v1 OWNER TO postgres;
REVOKE ALL ON private.schools_basic_v1 FROM PUBLIC, anon, authenticated, service_role;
COMMENT ON VIEW private.schools_basic_v1 IS 'Basic v1 canonical projection; derived rules from master Basic_v1_migration. Legacy schools.region/location_cn retained solely for old RPC compatibility.';
COMMIT;
