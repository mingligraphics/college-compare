BEGIN; INSERT INTO supabase_migrations.schema_migrations(version,statements,name) VALUES ('20261010000000',ARRAY['BEGIN;
CREATE FUNCTION public.get_school_discovery_v1()
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
 tuition_fees_year text)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = ''''
AS $function$
 SELECT v.school_id, v.school_name, v.school_name_cn, v.short_name, v.city, v.city_cn, v.state, v.state_cn, v.region, v.school_type, v.undergrad_enrollment, v.undergrad_enrollment_year, v.acceptance_rate, v.admissions_year, v.coa, v.coa_year, v.tuition_fees, v.tuition_fees_year FROM private.schools_basic_v1 v
 JOIN private.schools s USING (school_id) ORDER BY v.school_id;
$function$;
ALTER FUNCTION public.get_school_discovery_v1() OWNER TO postgres;
REVOKE ALL ON FUNCTION public.get_school_discovery_v1() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.get_school_discovery_v1() TO service_role;
COMMIT;
'],'discovery_v1') ON CONFLICT(version) DO NOTHING; SELECT version,name FROM supabase_migrations.schema_migrations WHERE version='20261010000000'; COMMIT;