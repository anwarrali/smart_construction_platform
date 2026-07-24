\set ON_ERROR_STOP on
\if :{?admin_password_hash}
\else
  \echo 'admin_password_hash psql variable is required'
  \quit
\endif

BEGIN;

DO $$
BEGIN
    IF (SELECT count(*) FROM projects WHERE name = 'Residential Complex C') <> 1 THEN
        RAISE EXCEPTION 'Expected exactly one project named Residential Complex C';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM users WHERE role = 'ADMIN') THEN
        RAISE EXCEPTION 'An existing administrator row is required for safe credential rotation';
    END IF;
END $$;

CREATE TEMP TABLE core_project AS
SELECT id FROM projects WHERE name = 'Residential Complex C';

CREATE TEMP TABLE core_admin AS
SELECT id
FROM users
WHERE role = 'ADMIN'
ORDER BY created_at
LIMIT 1;

-- Notifications are transient delivery records. Start the polished core with
-- an empty center so every future row comes from a real post-cleanup event.
DELETE FROM notifications;
DELETE FROM password_reset_tokens;
DELETE FROM revoked_tokens;

-- Preserve only audit history belonging to the retained project.
DELETE FROM audit_logs
WHERE project_id IS NULL
   OR project_id <> (SELECT id FROM core_project);

-- Project-owned tables use cascading foreign keys, preserving every
-- relationship under Residential Complex C while removing other projects.
DELETE FROM projects
WHERE id <> (SELECT id FROM core_project);

CREATE TEMP TABLE core_users (id uuid PRIMARY KEY);

INSERT INTO core_users
SELECT id FROM core_admin
ON CONFLICT DO NOTHING;

INSERT INTO core_users
SELECT owner_id FROM projects WHERE owner_id IS NOT NULL
UNION SELECT project_manager_id FROM projects WHERE project_manager_id IS NOT NULL
ON CONFLICT DO NOTHING;

INSERT INTO core_users
SELECT user_id FROM project_members
UNION SELECT assigned_by_id FROM project_members WHERE assigned_by_id IS NOT NULL
ON CONFLICT DO NOTHING;

INSERT INTO core_users
SELECT created_by_id FROM tasks
UNION SELECT reviewed_by_id FROM tasks WHERE reviewed_by_id IS NOT NULL
UNION SELECT ta.user_id FROM task_assignees ta JOIN tasks t ON t.id = ta.task_id
UNION SELECT tc.author_id FROM task_comments tc JOIN tasks t ON t.id = tc.task_id
UNION SELECT tr.submitted_by_id FROM task_reviews tr JOIN tasks t ON t.id = tr.task_id WHERE tr.submitted_by_id IS NOT NULL
UNION SELECT tr.reviewed_by_id FROM task_reviews tr JOIN tasks t ON t.id = tr.task_id WHERE tr.reviewed_by_id IS NOT NULL
UNION SELECT rl.triggered_by_user_id FROM task_reschedule_logs rl JOIN tasks t ON t.id = rl.task_id WHERE rl.triggered_by_user_id IS NOT NULL
ON CONFLICT DO NOTHING;

INSERT INTO core_users
SELECT raised_by_id FROM issues
UNION SELECT assigned_to_id FROM issues WHERE assigned_to_id IS NOT NULL
UNION SELECT proposed_by_id FROM design_changes
UNION SELECT approved_by_id FROM design_changes WHERE approved_by_id IS NOT NULL
UNION SELECT ad.acknowledged_by_id
  FROM design_change_affected_disciplines ad
  WHERE ad.acknowledged_by_id IS NOT NULL
ON CONFLICT DO NOTHING;

INSERT INTO core_users
SELECT uploaded_by_id FROM documents
UNION SELECT uploaded_by_id FROM media_assets
UNION SELECT uploaded_by_id FROM attachments
UNION SELECT submitted_by_id FROM site_reports
UNION SELECT reviewed_by_id FROM site_reports WHERE reviewed_by_id IS NOT NULL
UNION SELECT recorded_by_id FROM voice_recordings
UNION SELECT created_by_id FROM milestones WHERE created_by_id IS NOT NULL
ON CONFLICT DO NOTHING;

INSERT INTO core_users
SELECT sender_id FROM messages
UNION SELECT receiver_id FROM messages
UNION SELECT requested_by_id FROM cost_validations
UNION SELECT reviewed_by_id FROM cost_validations WHERE reviewed_by_id IS NOT NULL
UNION SELECT actor_id FROM audit_logs WHERE actor_id IS NOT NULL
ON CONFLICT DO NOTHING;

-- Rotate the retained administrator into the single development account.
UPDATE users
SET email = 'admin@local.dev',
    full_name = 'Platform Administrator',
    hashed_password = :'admin_password_hash',
    role = 'ADMIN',
    status = 'active',
    is_email_verified = true,
    is_superuser = true,
    must_change_password = false,
    invitation_accepted = true,
    engineer_affiliation = NULL,
    updated_at = now()
WHERE id = (SELECT id FROM core_admin);

-- Remove users unrelated to the retained project. Referenced participants are
-- kept so assignments, authorship, reviews, messages, and audit history remain valid.
DELETE FROM users
WHERE id NOT IN (SELECT id FROM core_users);

-- Guarantee that only the rotated account retains global administrator access.
UPDATE users
SET role = 'PROJECT_MANAGER',
    status = 'inactive',
    is_superuser = false,
    updated_at = now()
WHERE role = 'ADMIN'
  AND id <> (SELECT id FROM core_admin);

UPDATE users
SET full_name = 'Civil Consultant',
    updated_at = now()
WHERE full_name ILIKE '%demo%';

COMMIT;

SELECT id, name, status FROM projects ORDER BY name;
SELECT email, full_name, role, status FROM users ORDER BY role, email;
SELECT count(*) AS notifications FROM notifications;
