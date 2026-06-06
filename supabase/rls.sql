-- RLS (Row Level Security) policies for Script Workshop on Supabase Postgres.
--
-- Run this entire script in the Supabase SQL editor against your project.
-- The app already enforces user scoping at the application layer (every
-- query goes through `get_project_or_404(user_id=...)` and writes set
-- `owner_id` / `user_id` from the authed principal). RLS is the second
-- line of defense: even if a future code path forgets the filter, the
-- database will reject cross-user access.
--
-- Schema facts this script relies on:
--   * `projects.owner_id`  (String) — the user who owns the project
--   * `user_model_keys.user_id` (String) — the user who owns the API key
--   * `edit_events.actor_id` (String) — who performed the edit
--   * `chapters`, `generation_runs`, `script_versions`, `agent_runs`
--     all link to `projects.id` (no direct user column) — they inherit
--     the project's owner through `projects.owner_id`
--
-- Auth facts:
--   * The Supabase GoTrue server sets `auth.uid()` to the authenticated
--     user's UUID for every request that carries a Bearer access token.
--   * The backend talks to Postgres with `service_role`, so its queries
--     BYPASS RLS by default. We use `SET LOCAL request.jwt.claim.sub`
--     to simulate a user when we need RLS to apply during admin work.
--   * The frontend / Supabase JS client uses the user's anon JWT, so
--     their direct Postgres calls (e.g. via supabase-js) are filtered
--     by these policies.
--
-- We match `projects.owner_id = auth.uid()::text` because the app stores
-- user ids as opaque strings (Supabase UUIDs render as `text` here).
-- If you ever migrate to native UUID columns, change the cast.

-- ============= 1. Enable RLS on every table =============
ALTER TABLE projects         ENABLE ROW LEVEL SECURITY;
ALTER TABLE chapters         ENABLE ROW LEVEL SECURITY;
ALTER TABLE generation_runs  ENABLE ROW LEVEL SECURITY;
ALTER TABLE script_versions  ENABLE ROW LEVEL SECURITY;
ALTER TABLE edit_events      ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_runs       ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_model_keys  ENABLE ROW LEVEL SECURITY;

-- Force RLS even for table owners. Without this, the service role key
-- (and any direct role grant) would still bypass the policies.
ALTER TABLE projects         FORCE ROW LEVEL SECURITY;
ALTER TABLE chapters         FORCE ROW LEVEL SECURITY;
ALTER TABLE generation_runs  FORCE ROW LEVEL SECURITY;
ALTER TABLE script_versions  FORCE ROW LEVEL SECURITY;
ALTER TABLE edit_events      FORCE ROW LEVEL SECURITY;
ALTER TABLE agent_runs       FORCE ROW LEVEL SECURITY;
ALTER TABLE user_model_keys  FORCE ROW LEVEL SECURITY;

-- ============= 2. Helper: read the project owner =============
-- Wrapped as SECURITY DEFINER so it can read `projects` even when the
-- caller is a row-scoped user. Returns NULL if the project doesn't exist.
CREATE OR REPLACE FUNCTION public.project_owner_id(p_project_id TEXT)
RETURNS TEXT
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT owner_id FROM projects WHERE id = p_project_id LIMIT 1;
$$;

-- Allow the function to be called by anon / authenticated roles.
GRANT EXECUTE ON FUNCTION public.project_owner_id(TEXT) TO anon, authenticated;

-- ============= 3. Policies: projects =============
DROP POLICY IF EXISTS projects_select_own ON projects;
DROP POLICY IF EXISTS projects_insert_own ON projects;
DROP POLICY IF EXISTS projects_update_own ON projects;
DROP POLICY IF EXISTS projects_delete_own ON projects;

CREATE POLICY projects_select_own ON projects
  FOR SELECT TO anon, authenticated
  USING (owner_id = auth.uid()::text);

CREATE POLICY projects_insert_own ON projects
  FOR INSERT TO anon, authenticated
  WITH CHECK (owner_id = auth.uid()::text);

CREATE POLICY projects_update_own ON projects
  FOR UPDATE TO anon, authenticated
  USING (owner_id = auth.uid()::text)
  WITH CHECK (owner_id = auth.uid()::text);

CREATE POLICY projects_delete_own ON projects
  FOR DELETE TO anon, authenticated
  USING (owner_id = auth.uid()::text);

-- ============= 4. Policies: chapters / generation_runs / script_versions / agent_runs =============
-- These tables are joined to projects via project_id. A user can only see
-- rows whose project is theirs.
DO $$
DECLARE
  tbl TEXT;
BEGIN
  FOR tbl IN SELECT unnest(ARRAY['chapters', 'generation_runs', 'script_versions', 'agent_runs']) LOOP
    EXECUTE format('DROP POLICY IF EXISTS %I_select_own ON %I', tbl, tbl);
    EXECUTE format('DROP POLICY IF EXISTS %I_insert_own ON %I', tbl, tbl);
    EXECUTE format('DROP POLICY IF EXISTS %I_update_own ON %I', tbl, tbl);
    EXECUTE format('DROP POLICY IF EXISTS %I_delete_own ON %I', tbl, tbl);

    EXECUTE format($f$
      CREATE POLICY %I_select_own ON %I
        FOR SELECT TO anon, authenticated
        USING (public.project_owner_id(project_id) = auth.uid()::text);
    $f$, tbl, tbl);

    EXECUTE format($f$
      CREATE POLICY %I_insert_own ON %I
        FOR INSERT TO anon, authenticated
        WITH CHECK (public.project_owner_id(project_id) = auth.uid()::text);
    $f$, tbl, tbl);

    EXECUTE format($f$
      CREATE POLICY %I_update_own ON %I
        FOR UPDATE TO anon, authenticated
        USING (public.project_owner_id(project_id) = auth.uid()::text)
        WITH CHECK (public.project_owner_id(project_id) = auth.uid()::text);
    $f$, tbl, tbl);

    EXECUTE format($f$
      CREATE POLICY %I_delete_own ON %I
        FOR DELETE TO anon, authenticated
        USING (public.project_owner_id(project_id) = auth.uid()::text);
    $f$, tbl, tbl);
  END LOOP;
END $$;

-- ============= 5. Policies: edit_events =============
-- `edit_events` has both a project_id and an actor_id. Visibility is
-- scoped to the project's owner (so you can read edits made by AI on
-- your project, not just your own).
DROP POLICY IF EXISTS edit_events_select_own ON edit_events;
DROP POLICY IF EXISTS edit_events_insert_own ON edit_events;
DROP POLICY IF EXISTS edit_events_update_own ON edit_events;
DROP POLICY IF EXISTS edit_events_delete_own ON edit_events;

CREATE POLICY edit_events_select_own ON edit_events
  FOR SELECT TO anon, authenticated
  USING (public.project_owner_id(project_id) = auth.uid()::text);

CREATE POLICY edit_events_insert_own ON edit_events
  FOR INSERT TO anon, authenticated
  WITH CHECK (public.project_owner_id(project_id) = auth.uid()::text);

CREATE POLICY edit_events_update_own ON edit_events
  FOR UPDATE TO anon, authenticated
  USING (public.project_owner_id(project_id) = auth.uid()::text)
  WITH CHECK (public.project_owner_id(project_id) = auth.uid()::text);

CREATE POLICY edit_events_delete_own ON edit_events
  FOR DELETE TO anon, authenticated
  USING (public.project_owner_id(project_id) = auth.uid()::text);

-- ============= 6. Policies: user_model_keys =============
-- Each user only sees / mutates their own saved model keys.
DROP POLICY IF EXISTS user_model_keys_select_own ON user_model_keys;
DROP POLICY IF EXISTS user_model_keys_insert_own ON user_model_keys;
DROP POLICY IF EXISTS user_model_keys_update_own ON user_model_keys;
DROP POLICY IF EXISTS user_model_keys_delete_own ON user_model_keys;

CREATE POLICY user_model_keys_select_own ON user_model_keys
  FOR SELECT TO anon, authenticated
  USING (user_id = auth.uid()::text);

CREATE POLICY user_model_keys_insert_own ON user_model_keys
  FOR INSERT TO anon, authenticated
  WITH CHECK (user_id = auth.uid()::text);

CREATE POLICY user_model_keys_update_own ON user_model_keys
  FOR UPDATE TO anon, authenticated
  USING (user_id = auth.uid()::text)
  WITH CHECK (user_id = auth.uid()::text);

CREATE POLICY user_model_keys_delete_own ON user_model_keys
  FOR DELETE TO anon, authenticated
  USING (user_id = auth.uid()::text);

-- ============= 7. alembic_version (system table) =============
-- Don't lock down alembic's own bookkeeping table.
-- (No changes needed — it isn't in the public schema's RLS scope.)

-- ============= 8. Done =============
-- Verify:
--   SELECT tablename, rowsecurity FROM pg_tables WHERE schemaname='public';
-- Expect: every table in the project shows `rowsecurity = t`.
