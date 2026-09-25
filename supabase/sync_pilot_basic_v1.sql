-- Three-school, update-only sync from School!A1:AN4. Blank cells => SQL NULL.
-- Baseline guard prevents replay over changed records. Never run the legacy approved publisher.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';
LOCK TABLE private.schools IN SHARE ROW EXCLUSIVE MODE;
CREATE TEMP TABLE basic_v1_before ON COMMIT DROP AS SELECT * FROM private.schools;
DO $guard$ BEGIN
 IF (SELECT jsonb_agg(jsonb_build_object('campus_description', s.campus_description, 'campus_description_cn', s.campus_description_cn, 'campus_type', s.campus_type, 'career_model', s.career_model, 'career_model_cn', s.career_model_cn, 'city', s.city, 'city_cn', s.city_cn, 'coa', s.coa, 'coa_year', s.coa_year, 'famous_majors', s.famous_majors, 'famous_majors_cn', s.famous_majors_cn, 'first_year_enrollment', s.first_year_enrollment, 'international_pct', s.international_pct, 'location_cn', s.location_cn, 'notable_alumni', s.notable_alumni, 'region', s.region, 'school_id', s.school_id, 'school_name', s.school_name, 'school_name_cn', s.school_name_cn, 'school_type', s.school_type, 'short_name', s.short_name, 'state', s.state, 'tuition_fees', s.tuition_fees, 'tuition_fees_year', s.tuition_fees_year) ORDER BY s.school_id) FROM private.schools s)
 IS DISTINCT FROM '[{"campus_description":null,"campus_description_cn":null,"campus_type":null,"career_model":null,"career_model_cn":null,"city":"Boston","city_cn":"波士顿","coa":98419,"coa_year":"2026-27","famous_majors":null,"famous_majors_cn":null,"first_year_enrollment":3449,"international_pct":null,"location_cn":"马萨诸塞州波士顿","notable_alumni":null,"region":"美国东北部","school_id":"bu","school_name":"Boston University","school_name_cn":"波士顿大学","school_type":"私立大学","short_name":"BU","state":"MA","tuition_fees":73024,"tuition_fees_year":"2026-27"},{"campus_description":null,"campus_description_cn":null,"campus_type":null,"career_model":null,"career_model_cn":null,"city":"New York","city_cn":"纽约","coa":100998,"coa_year":"2026-27","famous_majors":null,"famous_majors_cn":null,"first_year_enrollment":5662,"international_pct":null,"location_cn":"纽约州纽约","notable_alumni":null,"region":"美国东北部","school_id":"nyu","school_name":"New York University","school_name_cn":"纽约大学","school_type":"私立大学","short_name":"NYU","state":"New York","tuition_fees":68576,"tuition_fees_year":"2026-27"},{"campus_description":null,"campus_description_cn":null,"campus_type":null,"career_model":null,"career_model_cn":null,"city":"Berkeley","city_cn":"伯克利","coa":54674,"coa_year":"2026-27","famous_majors":null,"famous_majors_cn":null,"first_year_enrollment":6724,"international_pct":null,"location_cn":"加州伯克利","notable_alumni":null,"region":"美国西海岸","school_id":"ucb","school_name":"University of California, Berkeley","school_name_cn":"加州大学伯克利分校","school_type":"公立大学","short_name":"UCB","state":"CA","tuition_fees":18214,"tuition_fees_year":"2026-27"}]'::jsonb THEN
  RAISE EXCEPTION 'Database baseline changed; re-inspect before syncing';
 END IF;
END $guard$;
UPDATE private.schools SET
 school_name = 'New York University',
 school_name_cn = '纽约大学',
 short_name = 'NYU',
 institution_control = 'private_nonprofit',
 school_type = 'research_university',
 city = 'New York',
 city_cn = '纽约',
 state = 'NY',
 state_cn = '纽约州',
 tuition_fees = 68576,
 tuition_fees_year = '2026-27',
 coa = 100998,
 coa_year = '2026-27',
 undergrad_enrollment = 29471,
 undergrad_enrollment_year = 'Fall 2025',
 applicants = 114125,
 admitted = 10340,
 first_year_enrollment = 5662,
 acceptance_rate = 9,
 admissions_year = 'Fall 2025',
 sat_25 = 1480,
 sat_75 = 1550,
 act_25 = 34,
 act_75 = 35,
 test_policy = 'test_optional',
 test_policy_cycle = '2026-27 through 2027-28',
 international_pct = 25.55,
 international_pct_year = 'Fall 2025',
 international_pct_scope = 'undergraduate',
 graduation_rate_4yr = 73.7,
 graduation_rate_4yr_year = 'Fall 2019 cohort; completed by Aug 31, 2023',
 international_need_aid = 'yes',
 international_merit_aid = NULL,
 english_proficiency_policy = 'conditional',
 english_tests_accepted = ARRAY['TOEFL', 'IELTS', 'Duolingo', 'PTE', 'Cambridge']::text[],
 english_policy_cycle = NULL,
 ranking_usnews = 31,
 ranking_category = 'national_university',
 ranking_year = 2027
WHERE school_id = 'nyu';
UPDATE private.schools SET
 school_name = 'Boston University',
 school_name_cn = '波士顿大学',
 short_name = 'BU',
 institution_control = 'private_nonprofit',
 school_type = 'research_university',
 city = 'Boston',
 city_cn = '波士顿',
 state = 'MA',
 state_cn = '马萨诸塞州',
 tuition_fees = 74594,
 tuition_fees_year = '2026-27',
 coa = 98419,
 coa_year = '2026-27',
 undergrad_enrollment = 18289,
 undergrad_enrollment_year = 'Fall 2025',
 applicants = 76776,
 admitted = 9853,
 first_year_enrollment = 3449,
 acceptance_rate = 12.83,
 admissions_year = 'Fall 2025',
 sat_25 = 1420,
 sat_75 = 1510,
 act_25 = 33,
 act_75 = 34,
 test_policy = 'test_optional',
 test_policy_cycle = 'Through Fall 2028 and Spring 2029',
 international_pct = 20.1,
 international_pct_year = 'Fall 2025',
 international_pct_scope = 'undergraduate',
 graduation_rate_4yr = 81.62,
 graduation_rate_4yr_year = 'Fall 2019 cohort; four-year cutoff 2023-08-31',
 international_need_aid = 'no',
 international_merit_aid = 'yes',
 english_proficiency_policy = 'conditional',
 english_tests_accepted = ARRAY['TOEFL', 'IELTS', 'Duolingo']::text[],
 english_policy_cycle = NULL,
 ranking_usnews = 34,
 ranking_category = 'national_university',
 ranking_year = 2027
WHERE school_id = 'bu';
UPDATE private.schools SET
 school_name = 'University of California, Berkeley',
 school_name_cn = '加州大学伯克利分校',
 short_name = 'UC Berkeley',
 institution_control = 'public',
 school_type = 'research_university',
 city = 'Berkeley',
 city_cn = '伯克利',
 state = 'CA',
 state_cn = '加州',
 tuition_fees = 58484,
 tuition_fees_year = '2026-27',
 coa = 93944,
 coa_year = '2026-27',
 undergrad_enrollment = 33122,
 undergrad_enrollment_year = 'Fall 2025',
 applicants = 126864,
 admitted = 14524,
 first_year_enrollment = 6687,
 acceptance_rate = 11,
 admissions_year = '2025-26',
 sat_25 = NULL,
 sat_75 = NULL,
 act_25 = NULL,
 act_75 = NULL,
 test_policy = 'test_free',
 test_policy_cycle = 'Fall 2027',
 international_pct = 9.82,
 international_pct_year = 'Fall 2025',
 international_pct_scope = 'undergraduate',
 graduation_rate_4yr = 81.33,
 graduation_rate_4yr_year = 'Fall 2019 cohort; completed by 2023-08-31',
 international_need_aid = 'limited',
 international_merit_aid = 'yes',
 english_proficiency_policy = 'conditional',
 english_tests_accepted = ARRAY['TOEFL', 'IELTS', 'Duolingo']::text[],
 english_policy_cycle = NULL,
 ranking_usnews = 20,
 ranking_category = 'national_university',
 ranking_year = 2027
WHERE school_id = 'ucb';
DO $verify$ BEGIN
 IF (SELECT jsonb_agg(jsonb_build_object('school_id', s.school_id, 'school_name', s.school_name, 'school_name_cn', s.school_name_cn, 'short_name', s.short_name, 'institution_control', s.institution_control, 'school_type', s.school_type, 'city', s.city, 'city_cn', s.city_cn, 'state', s.state, 'state_cn', s.state_cn, 'tuition_fees', s.tuition_fees, 'tuition_fees_year', s.tuition_fees_year, 'coa', s.coa, 'coa_year', s.coa_year, 'undergrad_enrollment', s.undergrad_enrollment, 'undergrad_enrollment_year', s.undergrad_enrollment_year, 'applicants', s.applicants, 'admitted', s.admitted, 'first_year_enrollment', s.first_year_enrollment, 'acceptance_rate', s.acceptance_rate, 'admissions_year', s.admissions_year, 'sat_25', s.sat_25, 'sat_75', s.sat_75, 'act_25', s.act_25, 'act_75', s.act_75, 'test_policy', s.test_policy, 'test_policy_cycle', s.test_policy_cycle, 'international_pct', s.international_pct, 'international_pct_year', s.international_pct_year, 'international_pct_scope', s.international_pct_scope, 'graduation_rate_4yr', s.graduation_rate_4yr, 'graduation_rate_4yr_year', s.graduation_rate_4yr_year, 'international_need_aid', s.international_need_aid, 'international_merit_aid', s.international_merit_aid, 'english_proficiency_policy', s.english_proficiency_policy, 'english_tests_accepted', s.english_tests_accepted, 'english_policy_cycle', s.english_policy_cycle, 'ranking_usnews', s.ranking_usnews, 'ranking_category', s.ranking_category, 'ranking_year', s.ranking_year) ORDER BY s.school_id) FROM private.schools s WHERE school_id IN ('nyu','bu','ucb'))
 IS DISTINCT FROM '[{"school_id":"bu","school_name":"Boston University","school_name_cn":"波士顿大学","short_name":"BU","institution_control":"private_nonprofit","school_type":"research_university","city":"Boston","city_cn":"波士顿","state":"MA","state_cn":"马萨诸塞州","tuition_fees":74594,"tuition_fees_year":"2026-27","coa":98419,"coa_year":"2026-27","undergrad_enrollment":18289,"undergrad_enrollment_year":"Fall 2025","applicants":76776,"admitted":9853,"first_year_enrollment":3449,"acceptance_rate":12.83,"admissions_year":"Fall 2025","sat_25":1420,"sat_75":1510,"act_25":33,"act_75":34,"test_policy":"test_optional","test_policy_cycle":"Through Fall 2028 and Spring 2029","international_pct":20.1,"international_pct_year":"Fall 2025","international_pct_scope":"undergraduate","graduation_rate_4yr":81.62,"graduation_rate_4yr_year":"Fall 2019 cohort; four-year cutoff 2023-08-31","international_need_aid":"no","international_merit_aid":"yes","english_proficiency_policy":"conditional","english_tests_accepted":["TOEFL","IELTS","Duolingo"],"english_policy_cycle":null,"ranking_usnews":34,"ranking_category":"national_university","ranking_year":2027},{"school_id":"nyu","school_name":"New York University","school_name_cn":"纽约大学","short_name":"NYU","institution_control":"private_nonprofit","school_type":"research_university","city":"New York","city_cn":"纽约","state":"NY","state_cn":"纽约州","tuition_fees":68576,"tuition_fees_year":"2026-27","coa":100998,"coa_year":"2026-27","undergrad_enrollment":29471,"undergrad_enrollment_year":"Fall 2025","applicants":114125,"admitted":10340,"first_year_enrollment":5662,"acceptance_rate":9,"admissions_year":"Fall 2025","sat_25":1480,"sat_75":1550,"act_25":34,"act_75":35,"test_policy":"test_optional","test_policy_cycle":"2026-27 through 2027-28","international_pct":25.55,"international_pct_year":"Fall 2025","international_pct_scope":"undergraduate","graduation_rate_4yr":73.7,"graduation_rate_4yr_year":"Fall 2019 cohort; completed by Aug 31, 2023","international_need_aid":"yes","international_merit_aid":null,"english_proficiency_policy":"conditional","english_tests_accepted":["TOEFL","IELTS","Duolingo","PTE","Cambridge"],"english_policy_cycle":null,"ranking_usnews":31,"ranking_category":"national_university","ranking_year":2027},{"school_id":"ucb","school_name":"University of California, Berkeley","school_name_cn":"加州大学伯克利分校","short_name":"UC Berkeley","institution_control":"public","school_type":"research_university","city":"Berkeley","city_cn":"伯克利","state":"CA","state_cn":"加州","tuition_fees":58484,"tuition_fees_year":"2026-27","coa":93944,"coa_year":"2026-27","undergrad_enrollment":33122,"undergrad_enrollment_year":"Fall 2025","applicants":126864,"admitted":14524,"first_year_enrollment":6687,"acceptance_rate":11,"admissions_year":"2025-26","sat_25":null,"sat_75":null,"act_25":null,"act_75":null,"test_policy":"test_free","test_policy_cycle":"Fall 2027","international_pct":9.82,"international_pct_year":"Fall 2025","international_pct_scope":"undergraduate","graduation_rate_4yr":81.33,"graduation_rate_4yr_year":"Fall 2019 cohort; completed by 2023-08-31","international_need_aid":"limited","international_merit_aid":"yes","english_proficiency_policy":"conditional","english_tests_accepted":["TOEFL","IELTS","Duolingo"],"english_policy_cycle":null,"ranking_usnews":20,"ranking_category":"national_university","ranking_year":2027}]'::jsonb THEN RAISE EXCEPTION 'Basic v1 readback mismatch'; END IF;
 IF EXISTS (
  SELECT 1 FROM private.schools s FULL JOIN basic_v1_before b USING (school_id)
  WHERE (to_jsonb(s) - ARRAY['school_name', 'school_name_cn', 'short_name', 'institution_control', 'school_type', 'city', 'city_cn', 'state', 'state_cn', 'tuition_fees', 'tuition_fees_year', 'coa', 'coa_year', 'undergrad_enrollment', 'undergrad_enrollment_year', 'applicants', 'admitted', 'first_year_enrollment', 'acceptance_rate', 'admissions_year', 'sat_25', 'sat_75', 'act_25', 'act_75', 'test_policy', 'test_policy_cycle', 'international_pct', 'international_pct_year', 'international_pct_scope', 'graduation_rate_4yr', 'graduation_rate_4yr_year', 'international_need_aid', 'international_merit_aid', 'english_proficiency_policy', 'english_tests_accepted', 'english_policy_cycle', 'ranking_usnews', 'ranking_category', 'ranking_year']::text[])
  IS DISTINCT FROM (to_jsonb(b) - ARRAY['school_name', 'school_name_cn', 'short_name', 'institution_control', 'school_type', 'city', 'city_cn', 'state', 'state_cn', 'tuition_fees', 'tuition_fees_year', 'coa', 'coa_year', 'undergrad_enrollment', 'undergrad_enrollment_year', 'applicants', 'admitted', 'first_year_enrollment', 'acceptance_rate', 'admissions_year', 'sat_25', 'sat_75', 'act_25', 'act_75', 'test_policy', 'test_policy_cycle', 'international_pct', 'international_pct_year', 'international_pct_scope', 'graduation_rate_4yr', 'graduation_rate_4yr_year', 'international_need_aid', 'international_merit_aid', 'english_proficiency_policy', 'english_tests_accepted', 'english_policy_cycle', 'ranking_usnews', 'ranking_category', 'ranking_year']::text[])
 ) THEN RAISE EXCEPTION 'Unrelated columns or row identities changed'; END IF;
END $verify$;
COMMIT;
