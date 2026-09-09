begin;

-- Keep private OUT of Supabase Data API Exposed schemas.
-- Only the restricted public RPC is exposed; no browser execution is allowed.
create schema if not exists private;

revoke all on schema private from public, anon, authenticated, service_role;

create table private.schools (
  -- Only these four fields may appear in a future public directory response.
  -- The underlying table remains private, including these columns.
  school_id text primary key
    check (school_id ~ '^[a-z0-9][a-z0-9_-]*$'),
  school_name text not null
    check (btrim(school_name) <> ''),
  school_name_cn text,
  short_name text,

  school_type text,
  city text,
  city_cn text,
  state text,
  location_cn text,
  region text,

  -- Store original USD amounts only. NULL means unknown; zero is known.
  -- RMB is display-only at 1 USD = 7 RMB; do not store converted amounts.
  tuition numeric(12,2)
    check (tuition between 0 and 9999999999.99),
  tuition_year text
    check (tuition_year ~ '^[0-9]{4}-[0-9]{2}$'),
  coa numeric(12,2)
    check (coa between 0 and 9999999999.99),
  coa_year text
    check (coa_year ~ '^[0-9]{4}-[0-9]{2}$'),

  -- Default NULL unless explicitly verified. Do not auto-import undergraduate counts.
  -- NYU can be verified/imported separately; BU/Berkeley dummy values must not copy.
  first_year_enrollment integer
    check (first_year_enrollment >= 0),
  -- Percentage points: 15.5 means 15.5%, not 0.155.
  international_pct numeric(5,2)
    check (international_pct between 0 and 100),

  campus_type text,
  campus_description text,
  campus_description_cn text,
  famous_majors text[],
  famous_majors_cn text[],
  career_model text,
  career_model_cn text,
  notable_alumni text[]
);

-- Trusted migration owner also owns the SECURITY DEFINER function below.
alter table private.schools owner to postgres;
alter table private.schools enable row level security;
revoke all on table private.schools
  from public, anon, authenticated, service_role;

-- public is the exposed RPC schema; private must remain unexposed.
-- Exactly two required arguments, no defaults, no dynamic SQL, no SELECT *.
create function public.get_school_comparison(
  p_school_id_a text,
  p_school_id_b text
)
returns table (
  school_id text,
  school_name text,
  school_name_cn text,
  short_name text,
  school_type text,
  city text,
  city_cn text,
  state text,
  location_cn text,
  region text,
  tuition numeric,
  tuition_year text,
  coa numeric,
  coa_year text,
  first_year_enrollment integer,
  international_pct numeric,
  campus_type text,
  campus_description text,
  campus_description_cn text,
  famous_majors text[],
  famous_majors_cn text[],
  career_model text,
  career_model_cn text,
  notable_alumni text[]
)
language plpgsql
security definer
set search_path = ''
as $function$
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
      s.tuition,
      s.tuition_year,
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
$function$;

alter function public.get_school_comparison(text, text) owner to postgres;
revoke all on function public.get_school_comparison(text, text)
  from public, anon, authenticated, service_role;
grant usage on schema public to service_role;
grant execute on function public.get_school_comparison(text, text)
  to service_role;

-- Credentials remain exclusively in Edge Function secrets/environment variables.
-- No Edge Function, data import, or Supabase API configuration is created here.
commit;
