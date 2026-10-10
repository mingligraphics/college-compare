BEGIN READ ONLY;
SELECT jsonb_build_object(
 'schools',(SELECT count(*) FROM private.schools),
 'data_hash',(SELECT md5(jsonb_agg(to_jsonb(s) ORDER BY school_id)::text) FROM private.schools s),
 'relations',(SELECT jsonb_agg(jsonb_build_object('schema',n.nspname,'name',c.relname,'rls',c.relrowsecurity,'acl',c.relacl::text)) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='private' AND c.relname IN ('schools','schools_basic_v1')),
 'rpcs',(SELECT jsonb_agg(jsonb_build_object('name',p.proname,'definer',p.prosecdef,'acl',p.proacl::text,'config',p.proconfig)) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' AND p.proname LIKE 'get_school_%'),
 'anon_table',has_table_privilege('anon','private.schools','SELECT'),
 'auth_table',has_table_privilege('authenticated','private.schools','SELECT'),
 'anon_view',has_table_privilege('anon','private.schools_basic_v1','SELECT'),
 'auth_view',has_table_privilege('authenticated','private.schools_basic_v1','SELECT')) AS baseline;
COMMIT;