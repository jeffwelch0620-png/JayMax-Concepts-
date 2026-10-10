-- Requires native day tasks, execution and progress. No production or stock writes.
BEGIN;
ALTER TABLE prep_inventory.day_tasks ADD CONSTRAINT day_tasks_assignment_scope UNIQUE(id,store_id);
ALTER TABLE public.staff_members ADD CONSTRAINT staff_assignment_scope UNIQUE(id,store_id);
CREATE TABLE prep_inventory.task_assignments (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), store_id text NOT NULL, task_id uuid NOT NULL,
 revision integer NOT NULL CHECK(revision>0), predecessor_id uuid UNIQUE, staff_member_id uuid,
 note text NOT NULL CHECK(length(btrim(note))>0), recorded_by text NOT NULL CHECK(length(btrim(recorded_by))>0),
 review_snapshot jsonb NOT NULL, review_hash bytea NOT NULL CHECK(octet_length(review_hash)=32),
 request_key uuid NOT NULL UNIQUE, request_fingerprint bytea NOT NULL CHECK(octet_length(request_fingerprint)=32),
 recorded_at timestamptz NOT NULL DEFAULT now(), UNIQUE(task_id,revision), UNIQUE(id,task_id,store_id),
 FOREIGN KEY(task_id,store_id) REFERENCES prep_inventory.day_tasks(id,store_id),
 FOREIGN KEY(staff_member_id,store_id) REFERENCES public.staff_members(id,store_id),
 FOREIGN KEY(predecessor_id,task_id,store_id) REFERENCES prep_inventory.task_assignments(id,task_id,store_id),
 CHECK((revision=1)=(predecessor_id IS NULL)), CHECK(staff_member_id IS NOT NULL OR revision>1)
);
CREATE UNIQUE INDEX assignment_one_root ON prep_inventory.task_assignments(task_id) WHERE predecessor_id IS NULL;
CREATE FUNCTION prep_inventory.guard_task_assignment() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE task prep_inventory.day_tasks; draft prep_inventory.day_list_versions; list prep_inventory.day_lists;
 phase prep_inventory.execution_events; previous prep_inventory.task_assignments; member jsonb;
 p jsonb:=NEW.review_snapshot; a jsonb:=p->'assignment'; progress jsonb; observed_task jsonb;
BEGIN
 PERFORM 1 FROM public.store_state WHERE store_id=NEW.store_id FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Assignment requires location coordination'; END IF;
 SELECT * INTO STRICT task FROM prep_inventory.day_tasks WHERE id=NEW.task_id AND store_id=NEW.store_id;
 SELECT * INTO STRICT draft FROM prep_inventory.day_list_versions WHERE id=task.version_id;
 SELECT * INTO STRICT list FROM prep_inventory.day_lists WHERE id=draft.list_id;
 SELECT * INTO phase FROM prep_inventory.execution_events WHERE list_id=list.id AND action IN ('release','reopen') ORDER BY revision DESC LIMIT 1;
 SELECT * INTO previous FROM prep_inventory.task_assignments WHERE task_id=NEW.task_id ORDER BY revision DESC LIMIT 1;
 progress:=prep_inventory.task_progress(task.id);
 observed_task:=to_jsonb(jsonb_populate_record(NULL::prep_inventory.day_tasks,p->'task'));
 IF phase.action IS DISTINCT FROM 'release' OR phase.draft_version_id IS DISTINCT FROM task.version_id
  OR EXISTS(SELECT 1 FROM prep_inventory.day_list_versions WHERE predecessor_id=task.version_id)
  OR NOT task.included OR task.planned_quantity IS NULL OR task.planned_quantity<=0
  OR (progress->>'closed')::boolean OR (progress->>'needs_review')::boolean
  OR NEW.revision<>coalesce(previous.revision,0)+1 OR NEW.predecessor_id IS DISTINCT FROM previous.id
  OR p->>'store_id' IS DISTINCT FROM NEW.store_id OR (p->>'day')::date IS DISTINCT FROM list.prep_date
  OR p->>'track' IS DISTINCT FROM list.track OR (p->>'draft_version_id')::uuid IS DISTINCT FROM task.version_id
  OR (p->>'release_event_id')::uuid IS DISTINCT FROM phase.id
  OR (p->>'execution_revision')::integer IS DISTINCT FROM (SELECT max(revision) FROM prep_inventory.execution_events WHERE list_id=list.id)
  OR p->'progress' IS DISTINCT FROM progress OR observed_task IS DISTINCT FROM to_jsonb(task)
  OR (a->>'task_id')::uuid IS DISTINCT FROM NEW.task_id OR (a->>'expected_revision')::integer IS DISTINCT FROM NEW.revision-1
  OR (a->>'staff_member_id')::uuid IS DISTINCT FROM NEW.staff_member_id OR a->>'note' IS DISTINCT FROM NEW.note
  OR (p->>'predecessor_id')::uuid IS DISTINCT FROM NEW.predecessor_id
  OR p->>'accountingEffect' IS DISTINCT FROM 'none' OR p->>'productionEffect' IS DISTINCT FROM 'none'
 THEN RAISE EXCEPTION 'Assignment differs from current released task, progress or reviewed command'; END IF;
 IF NEW.staff_member_id IS NOT NULL THEN
  SELECT jsonb_build_object('id',id,'store_id',store_id,'name',name,'role',role,'active',active) INTO member
   FROM public.staff_members WHERE id=NEW.staff_member_id AND store_id=NEW.store_id AND active FOR SHARE;
  IF member IS NULL OR p->'member' IS DISTINCT FROM member THEN RAISE EXCEPTION 'Assignment requires current active roster snapshot'; END IF;
 ELSIF p->'member' IS DISTINCT FROM 'null'::jsonb THEN RAISE EXCEPTION 'Unassignment has no selected member'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER assignment_guard BEFORE INSERT ON prep_inventory.task_assignments FOR EACH ROW EXECUTE FUNCTION prep_inventory.guard_task_assignment();
CREATE TRIGGER assignment_immutable BEFORE UPDATE OR DELETE ON prep_inventory.task_assignments FOR EACH ROW EXECUTE FUNCTION purchasing.reject_fact_change();
-- Historical assignments retain roster identities. Archive assigned staff rather than delete.
REVOKE ALL ON prep_inventory.task_assignments FROM PUBLIC;
REVOKE ALL ON FUNCTION prep_inventory.guard_task_assignment() FROM PUBLIC;
DO $$ DECLARE r text; BEGIN
 FOREACH r IN ARRAY ARRAY['anon','authenticated'] LOOP
  IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=r) THEN
   EXECUTE format('REVOKE ALL ON prep_inventory.task_assignments FROM %I',r);
   EXECUTE format('REVOKE ALL ON FUNCTION prep_inventory.guard_task_assignment() FROM %I',r);
  END IF;
 END LOOP;
END $$;
COMMIT;
