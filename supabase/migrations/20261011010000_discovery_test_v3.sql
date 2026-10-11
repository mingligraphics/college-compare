BEGIN;
CREATE FUNCTION public.get_school_discovery_test_v3()
RETURNS TABLE (
 school_id text,
 school_name text,
 school_name_cn text,
 short_name text,
 city text,
 city_cn text,
 state text,
 state_cn text,
 region text,
 school_type text,
 undergrad_enrollment integer,
 undergrad_enrollment_year text,
 acceptance_rate numeric,
 admissions_year text,
 coa numeric,
 coa_year text,
 tuition_fees numeric,
 tuition_fees_year text,
 international_pct numeric,
 international_pct_year text,
 international_pct_scope text,
 institution_control text,
 ranking_usnews integer,
 ranking_category text)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = ''
AS $function$
 SELECT v.school_id, v.school_name, v.school_name_cn, v.short_name, v.city, v.city_cn, v.state, v.state_cn, v.region, v.school_type, v.undergrad_enrollment, v.undergrad_enrollment_year, v.acceptance_rate, v.admissions_year, v.coa, v.coa_year, v.tuition_fees, v.tuition_fees_year, v.international_pct, v.international_pct_year, v.international_pct_scope, v.institution_control, v.ranking_usnews, v.ranking_category FROM private.schools_basic_v1 v
 JOIN private.schools s USING (school_id) ORDER BY v.school_id;
$function$;
ALTER FUNCTION public.get_school_discovery_test_v3() OWNER TO postgres;
REVOKE ALL ON FUNCTION public.get_school_discovery_test_v3() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.get_school_discovery_test_v3() TO service_role;
COMMIT;
