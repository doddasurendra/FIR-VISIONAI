-- FIR VisionAI: Knowledge Base / hybrid RAG upgrade, part 1 of 2.
-- Run as the project administrator role (postgres), e.g. from the Supabase SQL editor.
-- Additive and re-runnable.

-- Vector search extension, kept out of the public schema
create extension if not exists vector with schema extensions;

-- The application role owns the application tables and must be able to use the vector type
do $$
declare app_owner name;
begin
  select tableowner into app_owner from pg_tables where schemaname = 'public' and tablename = 'documents';
  if app_owner is not null and app_owner <> current_user then
    execute format('grant usage on schema extensions to %I', app_owner);
  end if;
end $$;

-- The RLS helper is an event-trigger function; it should not be callable through the public API
do $$
begin
  if exists (select 1 from pg_proc p join pg_namespace n on n.oid = p.pronamespace
             where n.nspname = 'public' and p.proname = 'rls_auto_enable') then
    revoke execute on function public.rls_auto_enable() from anon, authenticated, public;
  end if;
exception when insufficient_privilege then
  raise notice 'rls_auto_enable is owned by another role; revoke EXECUTE from the Supabase dashboard.';
end $$;
