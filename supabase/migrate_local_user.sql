-- Data migration: remap legacy `local_user` rows to a real Supabase user.
--
-- The Supabase SQL editor does not understand psql meta-commands (e.g.
-- \set), so the target UUID is inlined into each statement. The script is
-- idempotent: rerunning it on already-migrated data is a no-op.
--
-- Target UUID (find yours with: select id, email from auth.users):
--   9d928dc2-c744-4a5f-802e-f59a42bc254b  (1938707132@qq.com)

-- 1. projects: remap owner_id
UPDATE projects
   SET owner_id = '9d928dc2-c744-4a5f-802e-f59a42bc254b'
 WHERE owner_id = 'local_user';

-- 2. user_model_keys: remap user_id (only active keys migrate; revoked
--    stay so we don't accidentally resurrect them).
UPDATE user_model_keys
   SET user_id = '9d928dc2-c744-4a5f-802e-f59a42bc254b'
 WHERE user_id = 'local_user'
   AND status = 'active';

-- 3. edit_events: remap actor_id (only edits made by the local user
--    under the legacy mode). AI/system actors (`actor_type != 'user'`)
--    stay with their original tag.
UPDATE edit_events
   SET actor_id = '9d928dc2-c744-4a5f-802e-f59a42bc254b'
 WHERE actor_id = 'local_user'
   AND actor_type = 'user';

-- 4. generation_runs / chapters / script_versions / agent_runs:
--    No direct user column. They follow `projects.owner_id` because
--    we updated projects above, and RLS's `project_owner_id()` helper
--    reads the new owner. No row updates needed.

-- 5. Sanity check: nothing should still be tagged local_user.
SELECT
  (SELECT count(*) FROM projects        WHERE owner_id = 'local_user')        AS projects_leftover,
  (SELECT count(*) FROM user_model_keys WHERE user_id  = 'local_user' AND status = 'active') AS keys_leftover,
  (SELECT count(*) FROM edit_events     WHERE actor_id = 'local_user' AND actor_type = 'user') AS edits_leftover;
