-- M2 (Draft 0.7 §3): to-par day tasks are planned as the fewest whole recipe batches covering the
-- measured deficit, instead of the exact deficit. Replaces prep_inventory.guard_day_task(); every
-- other check is unchanged. Checked without division, so it agrees exactly with the backend.
BEGIN;
SET LOCAL lock_timeout = '5s';
CREATE OR REPLACE FUNCTION prep_inventory.guard_day_task() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE parent prep_inventory.day_list_versions; plan prep_inventory.planning_versions; profile prep_inventory.unit_profiles;
 identity prep_inventory.day_lists; override jsonb; included boolean; mode text; target numeric; counted numeric; needed numeric; qty numeric;
 batch numeric; batches numeric; incoming numeric;
BEGIN
 SELECT * INTO parent FROM prep_inventory.day_list_versions WHERE id=NEW.version_id;
 IF parent.created_xid<>pg_current_xact_id() THEN RAISE EXCEPTION 'Committed dated draft cannot acquire new tasks'; END IF;
 SELECT * INTO plan FROM prep_inventory.planning_versions WHERE id=NEW.planning_version_id;
 SELECT * INTO profile FROM prep_inventory.unit_profiles WHERE id=NEW.unit_profile_id;
 SELECT * INTO identity FROM prep_inventory.day_lists WHERE id=parent.list_id;
 IF NOT plan.active OR plan.track IS DISTINCT FROM identity.track
 OR EXISTS(SELECT 1 FROM prep_inventory.planning_versions p WHERE p.product_id=plan.product_id AND p.revision>plan.revision)
 OR (plan.recipe_version_id,plan.unit_profile_id) IS DISTINCT FROM (NEW.recipe_version_id,NEW.unit_profile_id)
 OR profile.base_units_per_source_unit IS DISTINCT FROM NEW.factor
 OR (NEW.task_snapshot->>'ordinal')::integer IS DISTINCT FROM NEW.ordinal
 OR (NEW.task_snapshot->>'product_id')::uuid IS DISTINCT FROM NEW.product_id
 OR (NEW.task_snapshot->>'planning_version_id')::uuid IS DISTINCT FROM NEW.planning_version_id
 OR (NEW.task_snapshot->>'recipe_version_id')::uuid IS DISTINCT FROM NEW.recipe_version_id
 OR (NEW.task_snapshot->>'unit_profile_id')::uuid IS DISTINCT FROM NEW.unit_profile_id
 OR (NEW.task_snapshot->>'included')::boolean IS DISTINCT FROM NEW.included
 OR (NEW.task_snapshot->>'planned_quantity')::numeric IS DISTINCT FROM NEW.planned_quantity
 OR (NEW.task_snapshot->>'factor')::numeric IS DISTINCT FROM NEW.factor
 OR (NEW.task_snapshot->>'planned_base_quantity')::numeric IS DISTINCT FROM NEW.planned_base_quantity
 THEN RAISE EXCEPTION 'Dated task identity, quantity or unit differs from its planning evidence'; END IF;
 IF parent.review_snapshot->'tasks'->(NEW.ordinal-1) IS DISTINCT FROM NEW.task_snapshot THEN RAISE EXCEPTION 'Dated task was not included in the reviewed draft'; END IF;
 SELECT value INTO override FROM jsonb_array_elements(parent.review_snapshot->'inputs'->'overrides')
  WHERE (value->>'planning_version_id')::uuid=plan.id;
 included:=CASE WHEN override IS NOT NULL THEN override->>'kind'<>'omit'
  ELSE plan.schedule='daily' OR (plan.schedule='recurring' AND (extract(isodow FROM identity.prep_date)::integer-1)=ANY(plan.recur_days)) END;
 mode:=CASE WHEN NOT included THEN 'omit' WHEN override IS NOT NULL THEN override->>'kind'
  WHEN plan.schedule='recurring' THEN 'fixed_quantity' ELSE 'target_par' END;
 IF NEW.included IS DISTINCT FROM included OR NEW.task_snapshot->>'mode' IS DISTINCT FROM mode
 OR NEW.task_snapshot->>'override_reason' IS DISTINCT FROM override->>'reason' THEN RAISE EXCEPTION 'Task schedule or override differs from the reviewed day inputs'; END IF;
 IF NOT included THEN needed:=0;qty:=0;
 ELSIF mode='fixed_quantity' THEN qty:=CASE WHEN override IS NOT NULL THEN (override->>'quantity')::numeric ELSE plan.fixed_quantity END;needed:=qty*NEW.factor;
 ELSE
  target:=CASE WHEN override IS NOT NULL THEN (override->>'quantity')::numeric WHEN parent.day_group='weekend' THEN plan.weekend_par ELSE plan.weekday_par END;
  SELECT base_quantity INTO counted FROM prep_inventory.count_observations WHERE event_id=parent.count_event_id AND product_id=NEW.product_id;
  IF FOUND THEN
   -- Draft 0.7: N = max(0, T - H - I), planned as whole recipe batches covering N (Q = r x ceil(N/r)).
   -- Incoming supply (I) is recorded by store transfers (M3); until then it must be zero.
   incoming:=coalesce((NEW.task_snapshot->>'incoming_base_quantity')::numeric,0);
   IF incoming<>0 THEN RAISE EXCEPTION 'Incoming supply needs a recorded transfer'; END IF;
   needed:=greatest(target*NEW.factor-counted-incoming,0);
   SELECT usable_base_yield INTO batch FROM prep_inventory.recipe_versions WHERE id=NEW.recipe_version_id;
   batches:=(NEW.task_snapshot->>'batches')::numeric;
   IF NEW.planned_quantity IS NOT NULL AND (batch IS NULL OR batches IS NULL OR batches<0 OR batches<>trunc(batches)
    OR (NEW.task_snapshot->>'batch_base_yield')::numeric IS DISTINCT FROM batch
    OR NEW.planned_base_quantity IS DISTINCT FROM batches*batch
    OR batches*batch<needed OR (batches>0 AND (batches-1)*batch>=needed))
   THEN RAISE EXCEPTION 'To-par task must plan the fewest whole recipe batches covering its measured deficit'; END IF;
  ELSIF NEW.planned_quantity IS NOT NULL THEN RAISE EXCEPTION 'Missing physical count cannot be treated as zero stock'; END IF;
 END IF;
 IF (mode IN ('fixed_quantity','omit') AND NEW.planned_quantity IS DISTINCT FROM qty)
 OR (NEW.task_snapshot->>'target_par')::numeric IS DISTINCT FROM target
 OR (NEW.task_snapshot->>'counted_base_quantity')::numeric IS DISTINCT FROM counted
 OR (NEW.task_snapshot->>'needed_base_quantity')::numeric IS DISTINCT FROM needed
 OR (NEW.planned_quantity IS NULL AND coalesce(length(btrim(NEW.task_snapshot->>'issue')),0)=0)
 THEN RAISE EXCEPTION 'Task calculation needs matching measured or explicitly overridden evidence'; END IF;
 RETURN NEW;
END $$;
COMMIT;
