-- Verified production submissions (Jeff 2026-10-30/2026-11-01). A cook signed in with their own name and
-- PIN submits output as themselves, so the review marks the identity verified. The original guard
-- (20261007_staff_prep_production.sql) required every submission to be a claimed identity; this keeps
-- every other check and allows "verified" exactly when the submitter is that staff member's own
-- personal session ('member:<id>'). Shared-PIN and manager submissions stay claimed (false).

BEGIN;
SET LOCAL lock_timeout = '5s';

CREATE OR REPLACE FUNCTION prep_inventory.guard_staff_production_submission() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE previous prep_inventory.staff_production_submissions;task prep_inventory.day_tasks;list prep_inventory.day_lists;
 a prep_inventory.task_assignments;phase prep_inventory.execution_events;progress jsonb;member jsonb;
 p jsonb:=NEW.review_snapshot;b jsonb:=p->'submission';
BEGIN
 PERFORM 1 FROM store_state WHERE store_id=NEW.store_id FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Production submission requires location coordination'; END IF;
 SELECT * INTO previous FROM prep_inventory.staff_production_submissions WHERE root_id=NEW.root_id ORDER BY revision DESC LIMIT 1;
 SELECT * INTO STRICT task FROM prep_inventory.day_tasks WHERE id=NEW.task_id AND store_id=NEW.store_id;
 SELECT l.* INTO STRICT list FROM prep_inventory.day_lists l JOIN prep_inventory.day_list_versions v ON v.list_id=l.id WHERE v.id=task.version_id;
 IF NEW.created_xid IS DISTINCT FROM pg_current_xact_id() OR NEW.recorded_at IS DISTINCT FROM transaction_timestamp()
 OR NEW.revision IS DISTINCT FROM coalesce(previous.revision,0)+1 OR NEW.predecessor_id IS DISTINCT FROM previous.id
 OR (previous.id IS NOT NULL AND (previous.kind='withdraw' OR previous.task_id<>NEW.task_id OR previous.staff_member_id<>NEW.staff_member_id))
 OR EXISTS(SELECT 1 FROM prep_inventory.staff_production_decisions d JOIN prep_inventory.staff_production_submissions s ON s.id=d.submission_id WHERE s.root_id=NEW.root_id AND d.decision='accepted')
 OR p->>'store_id' IS DISTINCT FROM NEW.store_id OR (p->>'day')::date IS DISTINCT FROM list.prep_date OR p->>'track' IS DISTINCT FROM list.track
 OR (b->>'root_id')::uuid IS DISTINCT FROM NEW.root_id OR (b->>'expected_revision')::integer IS DISTINCT FROM NEW.revision-1
 OR (b->>'task_id')::uuid IS DISTINCT FROM NEW.task_id OR (b->>'staff_member_id')::uuid IS DISTINCT FROM NEW.staff_member_id
 OR (b->>'assignment_id')::uuid IS DISTINCT FROM NEW.assignment_id OR b->>'kind' IS DISTINCT FROM NEW.kind OR b->>'note' IS DISTINCT FROM NEW.note
 OR (p->>'predecessor_id')::uuid IS DISTINCT FROM NEW.predecessor_id OR p->>'submitted_by' IS DISTINCT FROM NEW.submitted_by
 OR p->>'credential_kind' IS DISTINCT FROM NEW.credential_kind OR p->'identity_verified' IS DISTINCT FROM to_jsonb(NEW.submitted_by = 'member:' || NEW.staff_member_id::text)
 OR p->>'accountingEffect' IS DISTINCT FROM 'none' OR p->>'productionEffect' IS DISTINCT FROM 'none'
 THEN RAISE EXCEPTION 'Submission differs from its original scope, revision or claimed actor'; END IF;
 SELECT jsonb_build_object('id',id,'store_id',store_id,'name',name,'role',role,'active',active) INTO member FROM staff_members WHERE id=NEW.staff_member_id AND store_id=NEW.store_id AND active FOR SHARE;
 IF member IS NULL THEN RAISE EXCEPTION 'Submission needs active local claimed roster identity'; END IF;
 IF NEW.kind='withdraw' THEN
  IF EXISTS(SELECT 1 FROM prep_inventory.staff_production_decisions WHERE submission_id=previous.id)
   OR NEW.assignment_id IS DISTINCT FROM previous.assignment_id OR b->'batch' IS DISTINCT FROM 'null'::jsonb
   OR p->'batch' IS DISTINCT FROM 'null'::jsonb OR p->'sources' IS DISTINCT FROM previous.review_snapshot->'sources'
  THEN RAISE EXCEPTION 'Withdrawal must retain undecided original history without production'; END IF;
 ELSE
  SELECT * INTO a FROM prep_inventory.task_assignments WHERE task_id=task.id ORDER BY revision DESC LIMIT 1;
  SELECT * INTO phase FROM prep_inventory.execution_events WHERE list_id=list.id AND action IN ('release','reopen') ORDER BY revision DESC LIMIT 1;
  progress:=prep_inventory.task_progress(task.id);
  IF a.id IS DISTINCT FROM NEW.assignment_id OR a.staff_member_id IS DISTINCT FROM NEW.staff_member_id OR a.review_snapshot->'member' IS DISTINCT FROM member
   OR phase.action IS DISTINCT FROM 'release' OR phase.draft_version_id IS DISTINCT FROM task.version_id
   OR EXISTS(SELECT 1 FROM prep_inventory.day_list_versions WHERE predecessor_id=task.version_id)
   OR NOT task.included OR task.planned_quantity IS NULL OR task.planned_quantity<=0 OR (progress->>'closed')::boolean OR (progress->>'needs_review')::boolean
   OR p->'sources'->'progress' IS DISTINCT FROM progress OR p->'sources'->'member' IS DISTINCT FROM member
   OR (p->'sources'->>'execution_revision')::integer IS DISTINCT FROM (SELECT max(revision) FROM prep_inventory.execution_events WHERE list_id=list.id)
   OR (p->'sources'->>'release_event_id')::uuid IS DISTINCT FROM phase.id
   OR (p->'sources'->'assignment'->>'id')::uuid IS DISTINCT FROM a.id
   OR p->'sources'->'assignment'->>'review_hash' IS DISTINCT FROM encode(a.review_hash,'hex')
   OR p->'sources'->'assignment'->'review_snapshot' IS DISTINCT FROM a.review_snapshot
   OR to_jsonb(jsonb_populate_record(NULL::prep_inventory.day_tasks,p->'sources'->'task')) IS DISTINCT FROM to_jsonb(task)
   OR (b->'batch'->>'recipe_version_id')::uuid IS DISTINCT FROM task.recipe_version_id OR (b->'batch'->>'business_date')::date IS DISTINCT FROM list.prep_date
   OR b->'batch'->'calendar_date_confirmed' IS DISTINCT FROM 'true'::jsonb OR b->'batch'->'single_output_confirmed' IS DISTINCT FROM 'true'::jsonb
   OR p->'batch'->'review'->'batch' IS DISTINCT FROM b->'batch' OR (p->'batch'->'review'->>'usableBaseOutput')::numeric IS NULL
   OR (p->'batch'->'review'->>'usableBaseOutput')::numeric<=0
  THEN RAISE EXCEPTION 'Submit requires current assigned open task and pinned measured batch'; END IF;
 END IF;
 RETURN NEW;
END $$;

COMMIT;
