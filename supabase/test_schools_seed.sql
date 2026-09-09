-- Local test fixture only. Run manually as an authorized database administrator.
-- BU/Berkeley prototype costs and their years are excluded; use NULL until verified.
-- No automatic undergraduate-to-first-year enrollment migration:
-- NYU 5723 is a separately verified override; BU/Berkeley remain NULL.
-- Amounts are original USD; percentage points use 15.5 = 15.5%.
-- Blank scalar and list fields become NULL: not yet researched / unknown.
-- Plain INSERT intentionally fails on duplicate IDs; no existing records are overwritten.
begin;

insert into private.schools (
  school_id, school_name, school_name_cn, short_name,
  school_type, city, city_cn, state, location_cn, region,
  tuition, tuition_year, coa, coa_year,
  first_year_enrollment, international_pct, campus_type, campus_description, campus_description_cn,
  famous_majors, famous_majors_cn, career_model, career_model_cn, notable_alumni
) values
  (
    'nyu', 'New York University', '纽约大学', 'NYU',
    '私立大学', 'New York', '纽约', 'New York', '纽约州纽约', '美国东北部',
    68576, '2026-27', 100998, '2026-27',
    5723, NULL, NULL, NULL, NULL,
    NULL, NULL, NULL, NULL, NULL
  ),
  (
    'bu', 'Boston University', '波士顿大学', 'BU',
    '私立大学', 'Boston', '波士顿', 'MA', '马萨诸塞州波士顿', '美国东北部',
    NULL, NULL, NULL, NULL,
    NULL, NULL, NULL, NULL, NULL,
    NULL, NULL, NULL, NULL, NULL
  ),
  (
    'ucb', 'University of California, Berkeley', '加州大学伯克利分校', 'UCB',
    '公立大学', 'Berkeley', '伯克利', 'CA', '加州伯克利', '美国西海岸',
    NULL, NULL, NULL, NULL,
    NULL, NULL, NULL, NULL, NULL,
    NULL, NULL, NULL, NULL, NULL
  );

commit;
