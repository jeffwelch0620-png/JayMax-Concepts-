-- Track 2 execution is an immutable reference to production, not another movement.
BEGIN;
DO $$ BEGIN
 IF to_regclass('prep_inventory.opening_decisions') IS NULL THEN
  RAISE EXCEPTION 'Install the production/opening source boundary before prep execution';
 END IF;
END $$;
CREATE TABLE prep_inventory.execution_events (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), list_id uuid NOT NULL, store_id text NOT NULL,
 revision integer NOT NULL CHECK(revision>0), predecessor_id uuid,
 action text NOT NULL CHECK(action IN ('release','reopen','complete')), draft_version_id uuid NOT NULL,
 release_event_id uuid, task_id uuid UNIQUE REFERENCES prep_inventory.day_tasks(id),
 batch_event_id uuid REFERENCES prep_inventory.batch_events(id), batch_root_id uuid UNIQUE REFERENCES prep_inventory.batch_events(id),
 reason text NOT NULL CHECK(length(btrim(reason))>0), actor text NOT NULL CHECK(length(btrim(actor))>0),
 review_snapshot jsonb NOT NULL CHECK(jsonb_typeof(review_snapshot)='object'),
 review_hash bytea NOT NULL CHECK(octet_length(review_hash)=32), request_key uuid NOT NULL UNIQUE,
 request_fingerprint bytea NOT NULL CHECK(octet_length(request_fingerprint)=32), recorded_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(list_id,store_id) REFERENCES prep_inventory.day_lists(id,store_id),
 FOREIGN KEY(draft_version_id,list_id,store_id) REFERENCES prep_inventory.day_list_versions(id,list_id,store_id),
 UNIQUE(id,list_id,store_id), UNIQUE(list_id,revision),
 FOREIGN KEY(predecessor_id,list_id,store_id) REFERENCES prep_inventory.execution_events(id,list_id,store_id),
 FOREIGN KEY(release_event_id,list_id,store_id) REFERENCES prep_inventory.execution_events(id,list_id,store_id),
 CHECK((revision=1)=(predecessor_id IS NULL)),
 CHECK((action='complete' AND release_event_id IS NOT NULL AND task_id IS NOT NULL AND batch_event_id IS NOT NULL AND batch_root_id IS NOT NULL)
   OR (action<>'complete' AND task_id IS NULL AND batch_event_id IS NULL AND batch_root_id IS NULL))
);
CREATE UNIQUE INDEX execution_root ON prep_inventory.execution_events(list_id) WHERE predecessor_id IS NULL;

CREATE FUNCTION prep_inventory.guard_execution() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE previous prep_inventory.execution_events; phase prep_inventory.execution_events;
 draft prep_inventory.day_list_versions; identity prep_inventory.day_lists; task prep_inventory.day_tasks;
 batch prep_inventory.batch_events; scope jsonb;
BEGIN
 INSERT INTO public.store_state(store_id) VALUES(NEW.store_id) ON CONFLICT DO NOTHING;
 PERFORM revision FROM public.store_state WHERE store_id=NEW.store_id FOR UPDATE;
 SELECT * INTO previous FROM prep_inventory.execution_events WHERE list_id=NEW.list_id ORDER BY revision DESC LIMIT 1;
 IF NEW.revision IS DISTINCT FROM coalesce(previous.revision,0)+1 OR NEW.predecessor_id IS DISTINCT FROM previous.id
 THEN RAISE EXCEPTION 'Execution revision or predecessor changed'; END IF;
 SELECT * INTO phase FROM prep_inventory.execution_events WHERE list_id=NEW.list_id AND action<>'complete' ORDER BY revision DESC LIMIT 1;
 SELECT * INTO draft FROM prep_inventory.day_list_versions WHERE list_id=NEW.list_id ORDER BY revision DESC LIMIT 1;
 SELECT * INTO identity FROM prep_inventory.day_lists WHERE id=NEW.list_id;
 IF draft.id IS DISTINCT FROM NEW.draft_version_id OR draft.store_id IS DISTINCT FROM NEW.store_id
 OR (NEW.review_snapshot->>'store_id') IS DISTINCT FROM NEW.store_id
 OR (NEW.review_snapshot->>'prep_date')::date IS DISTINCT FROM identity.prep_date
 OR (NEW.review_snapshot->>'track') IS DISTINCT FROM identity.track
 OR (NEW.review_snapshot->>'base_revision')::integer IS DISTINCT FROM NEW.revision-1
 OR (NEW.review_snapshot->>'draft_review_hash') IS DISTINCT FROM encode(draft.review_hash,'hex')
 OR (NEW.review_snapshot->>'release_event_id')::uuid IS DISTINCT FROM NEW.release_event_id
 OR (NEW.review_snapshot->'command'->>'action') IS DISTINCT FROM NEW.action
 OR (NEW.review_snapshot->'command'->>'draft_version_id')::uuid IS DISTINCT FROM NEW.draft_version_id
 OR (NEW.review_snapshot->'command'->>'task_id')::uuid IS DISTINCT FROM NEW.task_id
 OR (NEW.review_snapshot->'command'->>'batch_event_id')::uuid IS DISTINCT FROM NEW.batch_event_id
 OR (NEW.review_snapshot->'command'->>'reason') IS DISTINCT FROM NEW.reason
 OR (NEW.review_snapshot->>'status_after') IS DISTINCT FROM (CASE WHEN NEW.action='reopen' THEN 'draft' ELSE 'released' END)
 THEN RAISE EXCEPTION 'Execution command differs from its dated review evidence'; END IF;
 IF NEW.action='release' THEN
  IF phase.action='release' OR NEW.release_event_id IS NOT NULL THEN RAISE EXCEPTION 'Draft is already released'; END IF;
  IF EXISTS(SELECT 1 FROM prep_inventory.day_tasks WHERE version_id=draft.id AND included AND planned_quantity IS NULL)
  THEN RAISE EXCEPTION 'Unresolved dated draft cannot be released'; END IF;
  SELECT coalesce(jsonb_agg(id::text ORDER BY id::text),'[]'::jsonb) INTO scope FROM
   (SELECT DISTINCT ON(product_id) * FROM prep_inventory.planning_versions WHERE store_id=NEW.store_id ORDER BY product_id,revision DESC) p
   WHERE p.active AND p.track=identity.track;
  IF scope IS DISTINCT FROM draft.review_snapshot->'source_scope'
  OR EXISTS(SELECT 1 FROM prep_inventory.day_tasks t JOIN prep_inventory.recipe_versions r ON r.id=t.recipe_version_id
    JOIN prep_inventory.unit_profiles u ON u.id=t.unit_profile_id WHERE t.version_id=draft.id AND t.included AND
      (EXISTS(SELECT 1 FROM prep_inventory.recipe_versions n WHERE n.predecessor_id=r.id)
       OR EXISTS(SELECT 1 FROM prep_inventory.product_versions n WHERE n.predecessor_id=r.product_version_id)
       OR EXISTS(SELECT 1 FROM prep_inventory.unit_profiles n WHERE n.predecessor_id=u.id OR n.predecessor_id=r.output_profile_id)))
  OR (draft.count_event_id IS NOT NULL AND draft.count_event_id IS DISTINCT FROM
      (SELECT o.id FROM prep_inventory.observations o WHERE o.store_id=NEW.store_id AND o.purpose='count' AND o.business_date=identity.prep_date-1
       AND o.kind<>'void' AND NOT EXISTS(SELECT 1 FROM prep_inventory.observations n WHERE n.predecessor_id=o.id) ORDER BY performed_at DESC,id LIMIT 1))
  THEN RAISE EXCEPTION 'Dated draft sources changed before release'; END IF;
  IF NEW.review_snapshot->>'task' IS NOT NULL OR NEW.review_snapshot->>'batch' IS NOT NULL THEN RAISE EXCEPTION 'Release cannot record production'; END IF;
 ELSE
  IF phase.action IS DISTINCT FROM 'release' OR NEW.release_event_id IS DISTINCT FROM phase.id OR phase.draft_version_id IS DISTINCT FROM NEW.draft_version_id
  THEN RAISE EXCEPTION 'Execution requires the current released draft'; END IF;
  IF NEW.action='reopen' THEN
   IF EXISTS(SELECT 1 FROM prep_inventory.execution_events WHERE list_id=NEW.list_id AND action='complete') THEN RAISE EXCEPTION 'Linked production prevents reopening'; END IF;
   IF NEW.review_snapshot->>'task' IS NOT NULL OR NEW.review_snapshot->>'batch' IS NOT NULL THEN RAISE EXCEPTION 'Reopen cannot record production'; END IF;
  ELSE
   SELECT * INTO task FROM prep_inventory.day_tasks WHERE id=NEW.task_id;
   SELECT * INTO batch FROM prep_inventory.batch_events WHERE id=NEW.batch_event_id;
   IF task.version_id IS DISTINCT FROM NEW.draft_version_id OR task.store_id IS DISTINCT FROM NEW.store_id
   OR NOT task.included OR task.planned_quantity IS NULL OR task.planned_quantity<=0
   OR batch.store_id IS DISTINCT FROM NEW.store_id OR batch.recipe_version_id IS DISTINCT FROM task.recipe_version_id
   OR batch.product_id IS DISTINCT FROM task.product_id OR batch.business_date IS DISTINCT FROM identity.prep_date
   OR batch.source_kind IS DISTINCT FROM 'production' OR batch.kind='void' OR batch.root_id IS DISTINCT FROM NEW.batch_root_id
   OR EXISTS(SELECT 1 FROM prep_inventory.batch_events WHERE predecessor_id=batch.id)
   OR (batch.review_snapshot->>'usableBaseOutput')::numeric IS NULL OR (batch.review_snapshot->>'usableBaseOutput')::numeric<=0
   OR (NEW.review_snapshot->'task'->>'id')::uuid IS DISTINCT FROM task.id
   OR (NEW.review_snapshot->'task'->>'version_id')::uuid IS DISTINCT FROM task.version_id
   OR (NEW.review_snapshot->'task'->>'planned_quantity')::numeric IS DISTINCT FROM task.planned_quantity
   OR (NEW.review_snapshot->'task'->>'factor')::numeric IS DISTINCT FROM task.factor
   OR (NEW.review_snapshot->'task'->>'planned_base_quantity')::numeric IS DISTINCT FROM task.planned_base_quantity
   OR NEW.review_snapshot->'task'->'task_snapshot' IS DISTINCT FROM task.task_snapshot
   OR (NEW.review_snapshot->'batch'->>'id')::uuid IS DISTINCT FROM batch.id
   OR (NEW.review_snapshot->'batch'->>'root_id')::uuid IS DISTINCT FROM batch.root_id
   OR (NEW.review_snapshot->'batch'->>'review_hash') IS DISTINCT FROM encode(batch.review_hash,'hex')
   OR NEW.review_snapshot->'batch'->'review_snapshot' IS DISTINCT FROM batch.review_snapshot
   THEN RAISE EXCEPTION 'Completion requires matching current measured production evidence'; END IF;
  END IF;
 END IF;
 INSERT INTO public.store_state(store_id,revision) VALUES(NEW.store_id,1)
 ON CONFLICT(store_id) DO UPDATE SET revision=store_state.revision+1,updated_at=now();
 RETURN NEW;
END $$;

CREATE FUNCTION prep_inventory.hold_released_draft() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE phase text;
BEGIN
 INSERT INTO public.store_state(store_id) VALUES(NEW.store_id) ON CONFLICT DO NOTHING;
 PERFORM revision FROM public.store_state WHERE store_id=NEW.store_id FOR UPDATE;
 SELECT action INTO phase FROM prep_inventory.execution_events WHERE list_id=NEW.list_id AND action<>'complete' ORDER BY revision DESC LIMIT 1;
 IF phase='release' THEN RAISE EXCEPTION 'Reopen the released draft before editing'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER execution_draft_hold BEFORE INSERT ON prep_inventory.day_list_versions FOR EACH ROW EXECUTE FUNCTION prep_inventory.hold_released_draft();
CREATE TRIGGER valid_execution BEFORE INSERT ON prep_inventory.execution_events FOR EACH ROW EXECUTE FUNCTION prep_inventory.guard_execution();
CREATE TRIGGER immutable_execution BEFORE UPDATE OR DELETE ON prep_inventory.execution_events FOR EACH ROW EXECUTE FUNCTION purchasing.reject_fact_change();
REVOKE ALL ON prep_inventory.execution_events FROM PUBLIC;
REVOKE ALL ON FUNCTION prep_inventory.guard_execution(),prep_inventory.hold_released_draft() FROM PUBLIC;
COMMIT;
