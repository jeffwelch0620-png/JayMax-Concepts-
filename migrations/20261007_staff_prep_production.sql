-- Staff measurements remain drafts; only paired manager acceptance records production.
BEGIN;
ALTER TABLE prep_inventory.task_assignments ADD UNIQUE(id,store_id);
ALTER TABLE prep_inventory.execution_events ADD COLUMN created_xid xid8;
-- Existing rows retain NULL; only new rows use the current transaction marker.
ALTER TABLE prep_inventory.execution_events ALTER COLUMN created_xid SET DEFAULT pg_current_xact_id();
ALTER TABLE prep_inventory.execution_events ADD UNIQUE(id,store_id);
CREATE TABLE prep_inventory.staff_production_submissions (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),store_id text NOT NULL,root_id uuid NOT NULL,revision integer NOT NULL CHECK(revision>0),
 predecessor_id uuid UNIQUE,task_id uuid NOT NULL,staff_member_id uuid NOT NULL,assignment_id uuid NOT NULL,
 kind text NOT NULL CHECK(kind IN ('submit','withdraw')),note text NOT NULL CHECK(length(btrim(note))>0),
 submitted_by text NOT NULL CHECK(length(btrim(submitted_by))>0),credential_kind text NOT NULL CHECK(credential_kind IN ('shared_pin','bearer')),
 review_snapshot jsonb NOT NULL,review_hash bytea NOT NULL CHECK(octet_length(review_hash)=32),
 request_key uuid NOT NULL UNIQUE,request_fingerprint bytea NOT NULL CHECK(octet_length(request_fingerprint)=32),
 recorded_at timestamptz NOT NULL DEFAULT now(),created_xid xid8 NOT NULL DEFAULT pg_current_xact_id(),
 UNIQUE(id,store_id),UNIQUE(root_id,revision),
 FOREIGN KEY(root_id,store_id) REFERENCES prep_inventory.staff_production_submissions(id,store_id),
 FOREIGN KEY(predecessor_id,store_id) REFERENCES prep_inventory.staff_production_submissions(id,store_id),
 FOREIGN KEY(task_id,store_id) REFERENCES prep_inventory.day_tasks(id,store_id),
 FOREIGN KEY(staff_member_id,store_id) REFERENCES public.staff_members(id,store_id),
 FOREIGN KEY(assignment_id,store_id) REFERENCES prep_inventory.task_assignments(id,store_id),
 CHECK((revision=1)=(predecessor_id IS NULL)),CHECK((revision=1)=(root_id=id)),CHECK(kind='submit' OR revision>1)
);
CREATE TABLE prep_inventory.staff_production_decisions (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),store_id text NOT NULL,submission_id uuid NOT NULL UNIQUE,
 decision text NOT NULL CHECK(decision IN ('accepted','rejected')),task_complete boolean NOT NULL,note text NOT NULL CHECK(length(btrim(note))>0),
 recorded_by text NOT NULL CHECK(length(btrim(recorded_by))>0),review_snapshot jsonb NOT NULL,review_hash bytea NOT NULL CHECK(octet_length(review_hash)=32),
 batch_event_id uuid UNIQUE,execution_event_id uuid UNIQUE,finish_event_id uuid UNIQUE,
 request_key uuid NOT NULL UNIQUE,request_fingerprint bytea NOT NULL CHECK(octet_length(request_fingerprint)=32),
 recorded_at timestamptz NOT NULL DEFAULT now(),created_xid xid8 NOT NULL DEFAULT pg_current_xact_id(),
 FOREIGN KEY(submission_id,store_id) REFERENCES prep_inventory.staff_production_submissions(id,store_id),
 FOREIGN KEY(batch_event_id,store_id) REFERENCES prep_inventory.batch_events(id,store_id),
 FOREIGN KEY(execution_event_id,store_id) REFERENCES prep_inventory.execution_events(id,store_id),
 FOREIGN KEY(finish_event_id,store_id) REFERENCES prep_inventory.execution_events(id,store_id),
 CHECK((decision='accepted' AND batch_event_id IS NOT NULL AND execution_event_id IS NOT NULL AND (task_complete=(finish_event_id IS NOT NULL)))
 OR (decision='rejected' AND NOT task_complete AND batch_event_id IS NULL AND execution_event_id IS NULL AND finish_event_id IS NULL))
);
CREATE FUNCTION prep_inventory.guard_staff_production_submission() RETURNS trigger LANGUAGE plpgsql AS $$
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
 OR p->>'credential_kind' IS DISTINCT FROM NEW.credential_kind OR p->'identity_verified' IS DISTINCT FROM 'false'::jsonb
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
CREATE TRIGGER staff_production_submission_guard BEFORE INSERT ON prep_inventory.staff_production_submissions FOR EACH ROW EXECUTE FUNCTION prep_inventory.guard_staff_production_submission();
CREATE TRIGGER staff_production_submission_immutable BEFORE UPDATE OR DELETE ON prep_inventory.staff_production_submissions FOR EACH ROW EXECUTE FUNCTION purchasing.reject_fact_change();
CREATE TRIGGER staff_production_decision_immutable BEFORE UPDATE OR DELETE ON prep_inventory.staff_production_decisions FOR EACH ROW EXECUTE FUNCTION purchasing.reject_fact_change();
CREATE FUNCTION prep_inventory.guard_staff_production_decision() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE s prep_inventory.staff_production_submissions;b prep_inventory.batch_events;e prep_inventory.execution_events;f prep_inventory.execution_events;
 a prep_inventory.task_assignments;member jsonb;p jsonb:=NEW.review_snapshot;d jsonb:=p->'decision';
BEGIN
 PERFORM 1 FROM store_state WHERE store_id=NEW.store_id FOR UPDATE;
 SELECT * INTO STRICT s FROM prep_inventory.staff_production_submissions WHERE id=NEW.submission_id AND store_id=NEW.store_id;
 IF NEW.created_xid IS DISTINCT FROM pg_current_xact_id() OR NEW.recorded_at IS DISTINCT FROM transaction_timestamp()
 OR s.kind<>'submit' OR EXISTS(SELECT 1 FROM prep_inventory.staff_production_submissions WHERE predecessor_id=s.id)
 OR p->>'store_id' IS DISTINCT FROM NEW.store_id OR p->>'day' IS DISTINCT FROM s.review_snapshot->>'day' OR p->>'track' IS DISTINCT FROM s.review_snapshot->>'track'
 OR (d->>'submission_id')::uuid IS DISTINCT FROM s.id OR d->>'decision' IS DISTINCT FROM NEW.decision
 OR (d->>'task_complete')::boolean IS DISTINCT FROM NEW.task_complete OR d->>'note' IS DISTINCT FROM NEW.note
 OR (p->'submission'->>'id')::uuid IS DISTINCT FROM s.id OR p->'submission'->>'review_hash' IS DISTINCT FROM encode(s.review_hash,'hex')
 OR p->'submission'->'review_snapshot' IS DISTINCT FROM s.review_snapshot OR p->>'accountingEffect' IS DISTINCT FROM 'none'
 THEN RAISE EXCEPTION 'Decision differs from current immutable submission'; END IF;
 IF NEW.decision='rejected' THEN
  IF p->'batch' IS DISTINCT FROM 'null'::jsonb OR p->'sources' IS DISTINCT FROM 'null'::jsonb OR p->>'productionEffect' IS DISTINCT FROM 'none'
  THEN RAISE EXCEPTION 'Rejection cannot produce food'; END IF;
 ELSE
  SELECT * INTO STRICT b FROM prep_inventory.batch_events WHERE id=NEW.batch_event_id;
  SELECT * INTO STRICT e FROM prep_inventory.execution_events WHERE id=NEW.execution_event_id;
  SELECT * INTO a FROM prep_inventory.task_assignments WHERE task_id=s.task_id ORDER BY revision DESC LIMIT 1;
  SELECT jsonb_build_object('id',id,'store_id',store_id,'name',name,'role',role,'active',active) INTO member FROM staff_members WHERE id=s.staff_member_id AND store_id=s.store_id AND active FOR SHARE;
  IF a.id IS DISTINCT FROM s.assignment_id OR a.staff_member_id IS DISTINCT FROM s.staff_member_id OR member IS NULL OR a.review_snapshot->'member' IS DISTINCT FROM member
   OR p->>'productionEffect' IS DISTINCT FROM 'record_once'
   OR b.created_xid IS DISTINCT FROM NEW.created_xid OR e.created_xid IS DISTINCT FROM NEW.created_xid
   OR b.recorded_at IS DISTINCT FROM NEW.recorded_at OR e.recorded_at IS DISTINCT FROM NEW.recorded_at
   OR b.kind<>'initial' OR b.source_kind<>'production' OR b.store_id IS DISTINCT FROM NEW.store_id
   OR b.recorded_by IS DISTINCT FROM NEW.recorded_by OR b.request_key IS DISTINCT FROM NEW.request_key OR b.request_fingerprint IS DISTINCT FROM NEW.request_fingerprint
   OR b.review_snapshot IS DISTINCT FROM p->'batch'->'review' OR encode(b.review_hash,'hex') IS DISTINCT FROM p->'batch'->>'reviewHash'
   OR (b.review_snapshot->>'staff_submission_id')::uuid IS DISTINCT FROM s.id OR (e.review_snapshot->>'staff_submission_id')::uuid IS DISTINCT FROM s.id
   OR b.review_snapshot->'batch' IS DISTINCT FROM s.review_snapshot->'submission'->'batch'
   OR e.store_id IS DISTINCT FROM NEW.store_id OR e.action<>'link' OR e.task_id IS DISTINCT FROM s.task_id OR e.batch_event_id IS DISTINCT FROM b.id
   OR e.actor IS DISTINCT FROM NEW.recorded_by OR e.reason IS DISTINCT FROM NEW.note OR e.request_key IS DISTINCT FROM NEW.request_key OR e.request_fingerprint IS DISTINCT FROM NEW.request_fingerprint
   OR e.revision IS DISTINCT FROM (p->'sources'->>'execution_revision')::integer+1
   OR e.review_snapshot->'progress_before' IS DISTINCT FROM p->'sources'->'progress'
   OR e.review_snapshot->'task' IS DISTINCT FROM p->'sources'->'task'
   OR (p->'sources'->'assignment'->>'id')::uuid IS DISTINCT FROM a.id
   OR (p->'sources'->>'release_event_id')::uuid IS DISTINCT FROM e.release_event_id
  THEN RAISE EXCEPTION 'Acceptance must create its exact measured batch and task link together'; END IF;
  IF NEW.task_complete THEN
   SELECT * INTO STRICT f FROM prep_inventory.execution_events WHERE id=NEW.finish_event_id;
   IF f.created_xid IS DISTINCT FROM NEW.created_xid OR f.recorded_at IS DISTINCT FROM NEW.recorded_at OR f.store_id IS DISTINCT FROM NEW.store_id
    OR f.action<>'finish' OR f.task_id IS DISTINCT FROM s.task_id OR f.predecessor_id IS DISTINCT FROM e.id OR f.revision<>e.revision+1
    OR f.actor IS DISTINCT FROM NEW.recorded_by OR f.reason IS DISTINCT FROM NEW.note OR f.request_fingerprint IS DISTINCT FROM NEW.request_fingerprint
    OR (f.review_snapshot->>'staff_submission_id')::uuid IS DISTINCT FROM s.id
   THEN RAISE EXCEPTION 'Explicit finish must follow paired acceptance in the same transaction'; END IF;
  END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER staff_production_decision_guard BEFORE INSERT ON prep_inventory.staff_production_decisions FOR EACH ROW EXECUTE FUNCTION prep_inventory.guard_staff_production_decision();
CREATE FUNCTION prep_inventory.seal_staff_production_effect() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.review_snapshot ? 'staff_submission_id' THEN
  IF NOT EXISTS(SELECT 1 FROM prep_inventory.staff_production_decisions d WHERE d.submission_id=(NEW.review_snapshot->>'staff_submission_id')::uuid
   AND d.decision='accepted' AND d.created_xid=NEW.created_xid AND d.store_id=NEW.store_id
   AND ((TG_TABLE_NAME='batch_events' AND d.batch_event_id=NEW.id)
    OR (TG_TABLE_NAME='execution_events' AND NEW.id IN (d.execution_event_id,d.finish_event_id))))
  THEN RAISE EXCEPTION 'Staff production effects require their paired atomic acceptance'; END IF;
 END IF;
 RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER staff_batch_acceptance_seal AFTER INSERT ON prep_inventory.batch_events DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION prep_inventory.seal_staff_production_effect();
CREATE CONSTRAINT TRIGGER staff_execution_acceptance_seal AFTER INSERT ON prep_inventory.execution_events DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION prep_inventory.seal_staff_production_effect();
REVOKE ALL ON prep_inventory.staff_production_submissions,prep_inventory.staff_production_decisions FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA prep_inventory FROM PUBLIC;
DO $$ DECLARE r text;BEGIN FOREACH r IN ARRAY ARRAY['anon','authenticated'] LOOP
 IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=r) THEN
  EXECUTE format('REVOKE ALL ON prep_inventory.staff_production_submissions,prep_inventory.staff_production_decisions FROM %I',r);
  EXECUTE format('REVOKE ALL ON ALL FUNCTIONS IN SCHEMA prep_inventory FROM %I',r);
 END IF;
END LOOP;END $$;
COMMIT;
