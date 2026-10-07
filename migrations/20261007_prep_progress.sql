-- Additive Track 2 progress/reconciliation. Earlier commands and batches are unchanged.
BEGIN;
ALTER TABLE prep_inventory.execution_events ADD COLUMN link_event_id uuid;
ALTER TABLE prep_inventory.execution_events ADD COLUMN task_complete boolean;
ALTER TABLE prep_inventory.execution_events ADD FOREIGN KEY(link_event_id,list_id,store_id)
 REFERENCES prep_inventory.execution_events(id,list_id,store_id);
ALTER TABLE prep_inventory.execution_events DROP CONSTRAINT execution_events_task_id_key;
ALTER TABLE prep_inventory.execution_events DROP CONSTRAINT execution_events_batch_root_id_key;
ALTER TABLE prep_inventory.execution_events DROP CONSTRAINT execution_events_action_check;
DO $$ DECLARE c record; BEGIN
 FOR c IN SELECT conname FROM pg_constraint WHERE conrelid='prep_inventory.execution_events'::regclass AND contype='c'
  AND pg_get_constraintdef(oid) LIKE '%task_id%' AND pg_get_constraintdef(oid) LIKE '%batch_root_id%' LOOP
  EXECUTE format('ALTER TABLE prep_inventory.execution_events DROP CONSTRAINT %I',c.conname);
 END LOOP;
END $$;
ALTER TABLE prep_inventory.execution_events ADD CONSTRAINT execution_actions CHECK(action IN ('release','reopen','complete','link','finish','reconcile'));
ALTER TABLE prep_inventory.execution_events ADD CONSTRAINT execution_evidence_fields CHECK(
 (action IN ('release','reopen') AND task_id IS NULL AND batch_event_id IS NULL AND batch_root_id IS NULL AND link_event_id IS NULL AND task_complete IS NULL)
 OR (action IN ('complete','link') AND release_event_id IS NOT NULL AND task_id IS NOT NULL AND batch_event_id IS NOT NULL AND batch_root_id IS NOT NULL AND link_event_id IS NULL AND task_complete IS NULL)
 OR (action='finish' AND release_event_id IS NOT NULL AND task_id IS NOT NULL AND batch_event_id IS NULL AND batch_root_id IS NULL AND link_event_id IS NULL AND task_complete IS NULL)
 OR (action='reconcile' AND release_event_id IS NOT NULL AND task_id IS NOT NULL AND batch_event_id IS NOT NULL AND batch_root_id IS NOT NULL AND link_event_id IS NOT NULL AND task_complete IS NOT NULL));
CREATE UNIQUE INDEX production_root_link_once ON prep_inventory.execution_events(batch_root_id) WHERE action IN ('complete','link');
CREATE INDEX execution_task_history ON prep_inventory.execution_events(task_id,revision);
CREATE INDEX execution_link_reviews ON prep_inventory.execution_events(link_event_id,revision) WHERE action='reconcile';

CREATE FUNCTION prep_inventory.task_progress(selected_task uuid) RETURNS jsonb LANGUAGE plpgsql STABLE AS $$
DECLARE task prep_inventory.day_tasks; e prep_inventory.execution_events; accepted uuid; effective prep_inventory.batch_events;
 closed boolean:=false; changed boolean; review_needed boolean:=false; links jsonb:='[]'; actual numeric:=0; reviewed numeric:=0; quantity numeric;
BEGIN
 SELECT * INTO STRICT task FROM prep_inventory.day_tasks WHERE id=selected_task;
 FOR e IN SELECT * FROM prep_inventory.execution_events WHERE task_id=selected_task ORDER BY revision LOOP
  IF e.action IN ('complete','finish') THEN closed:=true;
  ELSIF e.action='reconcile' THEN closed:=e.task_complete;
  END IF;
 END LOOP;
 FOR e IN SELECT * FROM prep_inventory.execution_events WHERE task_id=selected_task AND action IN ('complete','link') ORDER BY revision LOOP
  SELECT batch_event_id INTO accepted FROM prep_inventory.execution_events WHERE link_event_id=e.id AND action='reconcile' ORDER BY revision DESC LIMIT 1;
  accepted:=coalesce(accepted,e.batch_event_id);
  SELECT * INTO STRICT effective FROM prep_inventory.batch_events WHERE root_id=e.batch_root_id ORDER BY revision DESC LIMIT 1;
  changed:=effective.id<>accepted; review_needed:=review_needed OR changed;
  quantity:=CASE WHEN effective.kind='void' THEN 0 ELSE (effective.review_snapshot->>'usableBaseOutput')::numeric END;
  actual:=actual+quantity;
  IF NOT changed THEN reviewed:=reviewed+quantity; END IF;
  links:=links||jsonb_build_array(jsonb_build_object('execution_id',e.id,'acknowledged_batch_event_id',accepted,
   'effective_batch_event_id',effective.id,'batch_root_id',e.batch_root_id,'needs_review',changed,'effective_base_quantity',quantity::text));
 END LOOP;
 RETURN jsonb_build_object('task_id',task.id,'closed',closed,'needs_review',review_needed,'links',links,
  'planned_base_quantity',task.planned_base_quantity::text,'effective_base_quantity',actual::text,'reviewed_base_quantity',reviewed::text,
  'status',CASE WHEN review_needed THEN 'needs_review' WHEN closed THEN 'complete' WHEN actual>0 THEN 'in_progress' ELSE 'open' END);
END $$;

CREATE OR REPLACE FUNCTION prep_inventory.guard_execution() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE previous prep_inventory.execution_events; phase prep_inventory.execution_events;
 draft prep_inventory.day_list_versions; identity prep_inventory.day_lists; task prep_inventory.day_tasks;
 batch prep_inventory.batch_events; scope jsonb; progress jsonb; original prep_inventory.execution_events; accepted uuid;
BEGIN
 INSERT INTO public.store_state(store_id) VALUES(NEW.store_id) ON CONFLICT DO NOTHING;
 PERFORM revision FROM public.store_state WHERE store_id=NEW.store_id FOR UPDATE;
 SELECT * INTO previous FROM prep_inventory.execution_events WHERE list_id=NEW.list_id ORDER BY revision DESC LIMIT 1;
 IF NEW.revision IS DISTINCT FROM coalesce(previous.revision,0)+1 OR NEW.predecessor_id IS DISTINCT FROM previous.id
 THEN RAISE EXCEPTION 'Execution revision or predecessor changed'; END IF;
 SELECT * INTO phase FROM prep_inventory.execution_events WHERE list_id=NEW.list_id AND action IN ('release','reopen') ORDER BY revision DESC LIMIT 1;
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
 OR (NEW.review_snapshot->'command'->>'link_event_id')::uuid IS DISTINCT FROM NEW.link_event_id
 OR (NEW.review_snapshot->'command'->>'task_complete')::boolean IS DISTINCT FROM NEW.task_complete
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
   IF EXISTS(SELECT 1 FROM prep_inventory.execution_events WHERE list_id=NEW.list_id AND action IN ('complete','link')) THEN RAISE EXCEPTION 'Linked production prevents reopening'; END IF;
   IF NEW.review_snapshot->>'task' IS NOT NULL OR NEW.review_snapshot->>'batch' IS NOT NULL THEN RAISE EXCEPTION 'Reopen cannot record production'; END IF;
  ELSE
   SELECT * INTO task FROM prep_inventory.day_tasks WHERE id=NEW.task_id;
   IF task.version_id IS DISTINCT FROM NEW.draft_version_id OR task.store_id IS DISTINCT FROM NEW.store_id
   OR NOT task.included OR task.planned_quantity IS NULL OR task.planned_quantity<=0
   OR (NEW.review_snapshot->'task'->>'id')::uuid IS DISTINCT FROM task.id
   OR (NEW.review_snapshot->'task'->>'version_id')::uuid IS DISTINCT FROM task.version_id
   OR (NEW.review_snapshot->'task'->>'planned_quantity')::numeric IS DISTINCT FROM task.planned_quantity
   OR (NEW.review_snapshot->'task'->>'factor')::numeric IS DISTINCT FROM task.factor
   OR (NEW.review_snapshot->'task'->>'planned_base_quantity')::numeric IS DISTINCT FROM task.planned_base_quantity
   OR NEW.review_snapshot->'task'->'task_snapshot' IS DISTINCT FROM task.task_snapshot
   THEN RAISE EXCEPTION 'Completion requires matching current measured production evidence'; END IF;
   progress:=prep_inventory.task_progress(task.id);
   IF NEW.action IN ('link','finish','reconcile') AND NEW.review_snapshot->'progress_before' IS DISTINCT FROM progress
   THEN RAISE EXCEPTION 'Reviewed task progress changed'; END IF;
   IF NEW.action IN ('link','finish') AND ((progress->>'closed')::boolean OR (progress->>'needs_review')::boolean)
   THEN RAISE EXCEPTION 'Finished or changed task requires reconciliation'; END IF;
   IF NEW.action='finish' THEN
    IF (progress->>'reviewed_base_quantity')::numeric<=0 OR NEW.review_snapshot->>'batch' IS NOT NULL
    THEN RAISE EXCEPTION 'Finish requires positive reviewed production without new movements'; END IF;
   ELSE
    SELECT * INTO batch FROM prep_inventory.batch_events WHERE id=NEW.batch_event_id;
    IF batch.store_id IS DISTINCT FROM NEW.store_id OR batch.product_id IS DISTINCT FROM task.product_id
    OR batch.business_date IS DISTINCT FROM identity.prep_date OR batch.source_kind IS DISTINCT FROM 'production'
    OR batch.root_id IS DISTINCT FROM NEW.batch_root_id OR EXISTS(SELECT 1 FROM prep_inventory.batch_events WHERE predecessor_id=batch.id)
    OR (NEW.review_snapshot->'batch'->>'id')::uuid IS DISTINCT FROM batch.id
    OR (NEW.review_snapshot->'batch'->>'root_id')::uuid IS DISTINCT FROM batch.root_id
    OR (NEW.review_snapshot->'batch'->>'review_hash') IS DISTINCT FROM encode(batch.review_hash,'hex')
    OR NEW.review_snapshot->'batch'->'review_snapshot' IS DISTINCT FROM batch.review_snapshot
    THEN RAISE EXCEPTION 'Completion requires matching current measured production evidence'; END IF;
    IF NEW.action='reconcile' THEN
     SELECT * INTO original FROM prep_inventory.execution_events WHERE id=NEW.link_event_id;
     SELECT acknowledged_batch_event_id::uuid INTO accepted FROM jsonb_to_recordset(progress->'links') AS l(execution_id text,acknowledged_batch_event_id text) WHERE execution_id=original.id::text;
     IF original.action NOT IN ('complete','link') OR original.task_id IS DISTINCT FROM NEW.task_id
     OR original.list_id IS DISTINCT FROM NEW.list_id OR original.batch_root_id IS DISTINCT FROM NEW.batch_root_id
     OR NEW.review_snapshot->'original_link'->>'id' IS DISTINCT FROM original.id::text
     OR NEW.review_snapshot->'original_link'->>'review_hash' IS DISTINCT FROM encode(original.review_hash,'hex')
     OR NEW.review_snapshot->'original_link'->'review_snapshot' IS DISTINCT FROM original.review_snapshot
     OR accepted IS NULL OR accepted=batch.id
     THEN RAISE EXCEPTION 'Reconciliation requires a changed original production link'; END IF;
     IF NEW.task_complete AND (batch.kind='void' OR EXISTS(SELECT 1 FROM jsonb_array_elements(progress->'links') l WHERE l->>'execution_id'<>original.id::text AND (l->>'needs_review')::boolean))
     THEN RAISE EXCEPTION 'Void or other changed production prevents closing this task'; END IF;
    ELSE
     IF batch.recipe_version_id IS DISTINCT FROM task.recipe_version_id OR batch.kind='void'
     OR (batch.review_snapshot->>'usableBaseOutput')::numeric IS NULL OR (batch.review_snapshot->>'usableBaseOutput')::numeric<=0
     OR (NEW.action='complete' AND jsonb_array_length(progress->'links')>0)
     THEN RAISE EXCEPTION 'Completion requires matching current measured production evidence'; END IF;
    END IF;
   END IF;
  END IF;
 END IF;
 INSERT INTO public.store_state(store_id,revision) VALUES(NEW.store_id,1)
 ON CONFLICT(store_id) DO UPDATE SET revision=store_state.revision+1,updated_at=now();
 RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION prep_inventory.hold_released_draft() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE phase text;
BEGIN
 INSERT INTO public.store_state(store_id) VALUES(NEW.store_id) ON CONFLICT DO NOTHING;
 PERFORM revision FROM public.store_state WHERE store_id=NEW.store_id FOR UPDATE;
 SELECT action INTO phase FROM prep_inventory.execution_events WHERE list_id=NEW.list_id AND action IN ('release','reopen') ORDER BY revision DESC LIMIT 1;
 IF phase='release' THEN RAISE EXCEPTION 'Reopen the released draft before editing'; END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION prep_inventory.task_progress(uuid) FROM PUBLIC;
COMMIT;
