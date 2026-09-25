-- Versioned Basic v1 comparison; legacy RPC remains available during rollout.
BEGIN;
CREATE FUNCTION public.get_school_comparison_basic_v1(p_school_id_a text, p_school_id_b text)
RETURNS TABLE (
  school_id text,
  school_name text,
  school_name_cn text,
  short_name text,
  institution_control text,
  school_type text,
  city text,
  city_cn text,
  state text,
  state_cn text,
  tuition_fees numeric,
  tuition_fees_year text,
  coa numeric,
  coa_year text,
  undergrad_enrollment integer,
  undergrad_enrollment_year text,
  applicants integer,
  admitted integer,
  first_year_enrollment integer,
  acceptance_rate numeric,
  admissions_year text,
  sat_25 integer,
  sat_75 integer,
  act_25 integer,
  act_75 integer,
  test_policy text,
  test_policy_cycle text,
  international_pct numeric,
  international_pct_year text,
  international_pct_scope text,
  graduation_rate_4yr numeric,
  graduation_rate_4yr_year text,
  international_need_aid text,
  international_merit_aid text,
  english_proficiency_policy text,
  english_tests_accepted text[],
  english_policy_cycle text,
  ranking_usnews integer,
  ranking_category text,
  ranking_year integer,
  region text,
  location_cn text,
  ranking_tier text,
  campus_type text,
  campus_description text,
  campus_description_cn text,
  famous_majors text[],
  famous_majors_cn text[],
  career_model text,
  career_model_cn text,
  notable_alumni text[]
)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $function$
DECLARE matched_count integer;
BEGIN
 IF p_school_id_a IS NULL OR p_school_id_b IS NULL
    OR p_school_id_a !~ '^[a-z0-9][a-z0-9_-]*$' OR p_school_id_b !~ '^[a-z0-9][a-z0-9_-]*$'
    OR length(p_school_id_a)>100 OR length(p_school_id_b)>100 OR p_school_id_a=p_school_id_b THEN
  RAISE EXCEPTION 'Two distinct canonical school IDs required' USING ERRCODE='22023';
 END IF;
 RETURN QUERY SELECT
  v.school_id,
  v.school_name,
  v.school_name_cn,
  v.short_name,
  v.institution_control,
  v.school_type,
  v.city,
  v.city_cn,
  v.state,
  v.state_cn,
  v.tuition_fees,
  v.tuition_fees_year,
  v.coa,
  v.coa_year,
  v.undergrad_enrollment,
  v.undergrad_enrollment_year,
  v.applicants,
  v.admitted,
  v.first_year_enrollment,
  v.acceptance_rate,
  v.admissions_year,
  v.sat_25,
  v.sat_75,
  v.act_25,
  v.act_75,
  v.test_policy,
  v.test_policy_cycle,
  v.international_pct,
  v.international_pct_year,
  v.international_pct_scope,
  v.graduation_rate_4yr,
  v.graduation_rate_4yr_year,
  v.international_need_aid,
  v.international_merit_aid,
  v.english_proficiency_policy,
  v.english_tests_accepted,
  v.english_policy_cycle,
  v.ranking_usnews,
  v.ranking_category,
  v.ranking_year,
  v.region,
  v.location_cn,
  v.ranking_tier,
  s.campus_type,
  s.campus_description,
  s.campus_description_cn,
  s.famous_majors,
  s.famous_majors_cn,
  s.career_model,
  s.career_model_cn,
  s.notable_alumni
 FROM private.schools_basic_v1 v JOIN private.schools s USING (school_id)
 WHERE v.school_id IN (p_school_id_a,p_school_id_b)
 ORDER BY CASE WHEN v.school_id=p_school_id_a THEN 0 ELSE 1 END;
 GET DIAGNOSTICS matched_count = ROW_COUNT;
 IF matched_count <> 2 THEN RAISE EXCEPTION 'Both school IDs must exist' USING ERRCODE='P0002'; END IF;
END;
$function$;
ALTER FUNCTION public.get_school_comparison_basic_v1(text,text) OWNER TO postgres;
REVOKE ALL ON FUNCTION public.get_school_comparison_basic_v1(text,text) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.get_school_comparison_basic_v1(text,text) TO service_role;
COMMIT;
