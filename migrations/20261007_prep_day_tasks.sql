-- After prep planning, native batch/count observations and shared catalog.
-- Draft tasks only. Does not release tasks or write stock/accounting movements.
BEGIN;
CREATE TABLE prep_inventory.legacy_day_sources (
 kind text NOT NULL CHECK(kind IN ('override','list','line')), source_id uuid NOT NULL,
 store_id text NOT NULL REFERENCES public.stores(id), raw_record jsonb NOT NULL, PRIMARY KEY(kind,source_id)
);
INSERT INTO prep_inventory.legacy_day_sources SELECT 'override',id,store_id,to_jsonb(o) FROM public.prep_overrides o;
INSERT INTO prep_inventory.legacy_day_sources SELECT 'list',id,store_id,to_jsonb(l) FROM public.prep_lists l;
INSERT INTO prep_inventory.legacy_day_sources SELECT 'line',l.id,p.store_id,to_jsonb(l) FROM public.prep_list_lines l JOIN public.prep_lists p ON p.id=l.list_id;
CREATE TABLE prep_inventory.day_lists (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), store_id text NOT NULL REFERENCES public.stores(id),
 prep_date date NOT NULL, track text NOT NULL CHECK(track IN ('daily','bulk')),
 UNIQUE(store_id,prep_date,track), UNIQUE(id,store_id)
);
CREATE TABLE prep_inventory.day_list_versions (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), list_id uuid NOT NULL, store_id text NOT NULL,
 revision integer NOT NULL CHECK(revision>0), predecessor_id uuid UNIQUE,
 count_event_id uuid, day_group text NOT NULL CHECK(day_group IN ('weekday','weekend')),
 status text NOT NULL DEFAULT 'draft' CHECK(status='draft'),
 note text NOT NULL CHECK(length(btrim(note))>0), actor text NOT NULL CHECK(length(btrim(actor))>0),
 review_snapshot jsonb NOT NULL CHECK(jsonb_typeof(review_snapshot)='object'),
 review_hash bytea NOT NULL CHECK(octet_length(review_hash)=32),
 request_key uuid NOT NULL UNIQUE, request_fingerprint bytea NOT NULL CHECK(octet_length(request_fingerprint)=32),
 recorded_at timestamptz NOT NULL DEFAULT now(), created_xid xid8 NOT NULL DEFAULT pg_current_xact_id(),
 FOREIGN KEY(list_id,store_id) REFERENCES prep_inventory.day_lists(id,store_id),
 FOREIGN KEY(count_event_id,store_id) REFERENCES prep_inventory.observations(id,store_id),
 UNIQUE(id,store_id), UNIQUE(id,list_id,store_id), UNIQUE(list_id,revision),
 FOREIGN KEY(predecessor_id,list_id,store_id) REFERENCES prep_inventory.day_list_versions(id,list_id,store_id),
 CHECK((revision=1)=(predecessor_id IS NULL))
);
CREATE UNIQUE INDEX day_list_root ON prep_inventory.day_list_versions(list_id) WHERE predecessor_id IS NULL;
CREATE TABLE prep_inventory.day_tasks (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), version_id uuid NOT NULL, store_id text NOT NULL,
 ordinal integer NOT NULL CHECK(ordinal>0), product_id uuid NOT NULL, planning_version_id uuid NOT NULL,
 recipe_version_id uuid NOT NULL, unit_profile_id uuid NOT NULL, included boolean NOT NULL,
 planned_quantity numeric, factor numeric NOT NULL CHECK(factor>0 AND factor NOT IN ('NaN'::numeric,'Infinity'::numeric,'-Infinity'::numeric)),
 planned_base_quantity numeric, task_snapshot jsonb NOT NULL CHECK(jsonb_typeof(task_snapshot)='object'),
 FOREIGN KEY(version_id,store_id) REFERENCES prep_inventory.day_list_versions(id,store_id),
 FOREIGN KEY(planning_version_id,product_id,store_id) REFERENCES prep_inventory.planning_versions(id,product_id,store_id),
 FOREIGN KEY(recipe_version_id,product_id,store_id) REFERENCES prep_inventory.recipe_versions(id,product_id,store_id),
 FOREIGN KEY(unit_profile_id,store_id) REFERENCES prep_inventory.unit_profiles(id,store_id),
 UNIQUE(version_id,ordinal), UNIQUE(version_id,product_id),
 CHECK((planned_quantity IS NULL AND planned_base_quantity IS NULL AND included) OR
   (planned_quantity IS NOT NULL AND planned_base_quantity IS NOT NULL AND planned_quantity>=0
    AND planned_quantity NOT IN ('NaN'::numeric,'Infinity'::numeric,'-Infinity'::numeric)
    AND planned_base_quantity=planned_quantity*factor)),
 CHECK(included OR planned_quantity=0)
);
CREATE FUNCTION prep_inventory.guard_day_version() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE identity prep_inventory.day_lists; observed prep_inventory.observations;
BEGIN
 SELECT * INTO identity FROM prep_inventory.day_lists WHERE id=NEW.list_id;
 IF NEW.created_xid<>pg_current_xact_id() OR (NEW.review_snapshot->>'store_id') IS DISTINCT FROM NEW.store_id
 OR (NEW.review_snapshot->>'prep_date')::date IS DISTINCT FROM identity.prep_date
 OR (NEW.review_snapshot->>'track') IS DISTINCT FROM identity.track
 OR (NEW.review_snapshot->>'base_revision')::integer IS DISTINCT FROM NEW.revision-1
 OR (NEW.review_snapshot->'inputs'->>'track') IS DISTINCT FROM identity.track
 OR (NEW.review_snapshot->'inputs'->>'day_group') IS DISTINCT FROM NEW.day_group
 OR (NEW.review_snapshot->'inputs'->>'count_event_id')::uuid IS DISTINCT FROM NEW.count_event_id
 OR (NEW.review_snapshot->'inputs'->>'note') IS DISTINCT FROM NEW.note
 OR (NEW.review_snapshot->>'status') IS DISTINCT FROM 'draft'
 OR (NEW.review_snapshot->>'execution_ready')::boolean IS DISTINCT FROM false
 OR jsonb_typeof(NEW.review_snapshot->'tasks') IS DISTINCT FROM 'array'
 OR jsonb_typeof(NEW.review_snapshot->'inputs'->'overrides') IS DISTINCT FROM 'array'
 THEN RAISE EXCEPTION 'Dated draft needs matching sealed review evidence'; END IF;
 IF EXISTS(SELECT 1 FROM jsonb_array_elements(NEW.review_snapshot->'inputs'->'overrides') o
   WHERE coalesce(length(btrim(o->>'reason')),0)=0 OR coalesce(o->>'kind','') NOT IN ('omit','target_par','fixed_quantity')
    OR (o->>'kind'='omit' AND o->>'quantity' IS NOT NULL)
    OR (o->>'kind'<>'omit' AND (o->>'quantity' IS NULL OR (o->>'quantity')::numeric<0
      OR (o->>'quantity')::numeric IN ('NaN'::numeric,'Infinity'::numeric,'-Infinity'::numeric))))
 OR jsonb_array_length(NEW.review_snapshot->'inputs'->'overrides')<>(SELECT count(DISTINCT o->>'planning_version_id') FROM jsonb_array_elements(NEW.review_snapshot->'inputs'->'overrides') o)
 THEN RAISE EXCEPTION 'Day overrides require unique planning identities and reviewed quantities/reasons'; END IF;
 IF NEW.count_event_id IS NOT NULL THEN
  SELECT * INTO observed FROM prep_inventory.observations WHERE id=NEW.count_event_id;
  IF observed.purpose<>'count' OR observed.kind='void' OR observed.business_date<>identity.prep_date-1
  OR EXISTS(SELECT 1 FROM prep_inventory.observations WHERE predecessor_id=observed.id)
  OR observed.id IS DISTINCT FROM (SELECT o.id FROM prep_inventory.observations o WHERE o.store_id=NEW.store_id
     AND o.purpose='count' AND o.business_date=identity.prep_date-1 AND o.kind<>'void'
     AND NOT EXISTS(SELECT 1 FROM prep_inventory.observations c WHERE c.predecessor_id=o.id) ORDER BY o.performed_at DESC,o.id LIMIT 1)
  THEN RAISE EXCEPTION 'Dated draft requires a current prior-day prep count'; END IF;
 END IF;
 INSERT INTO public.store_state(store_id,revision) VALUES(NEW.store_id,1)
 ON CONFLICT(store_id) DO UPDATE SET revision=store_state.revision+1,updated_at=now();
 RETURN NEW;
END $$;
CREATE FUNCTION prep_inventory.guard_day_task() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE parent prep_inventory.day_list_versions; plan prep_inventory.planning_versions; profile prep_inventory.unit_profiles;
 identity prep_inventory.day_lists; override jsonb; included boolean; mode text; target numeric; counted numeric; needed numeric; qty numeric;
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
  IF FOUND THEN needed:=greatest(target*NEW.factor-counted,0);
   IF NEW.planned_quantity IS NOT NULL AND NEW.planned_base_quantity IS DISTINCT FROM needed THEN RAISE EXCEPTION 'To-par task quantity must equal its exact measured deficit'; END IF;
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
CREATE FUNCTION prep_inventory.seal_day_version() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE scope jsonb; actual jsonb; selected_track text;
BEGIN
 IF jsonb_array_length(NEW.review_snapshot->'tasks')<>(SELECT count(*) FROM prep_inventory.day_tasks WHERE version_id=NEW.id)
 THEN RAISE EXCEPTION 'Dated draft task set is incomplete'; END IF;
 SELECT d.track INTO selected_track FROM prep_inventory.day_lists d WHERE d.id=NEW.list_id;
 SELECT coalesce(jsonb_agg(id::text ORDER BY id::text),'[]'::jsonb) INTO scope FROM
  (SELECT DISTINCT ON(product_id) * FROM prep_inventory.planning_versions WHERE store_id=NEW.store_id ORDER BY product_id,revision DESC) p
  WHERE p.active AND p.track=selected_track;
 SELECT coalesce(jsonb_agg(planning_version_id::text ORDER BY planning_version_id::text),'[]'::jsonb) INTO actual FROM prep_inventory.day_tasks WHERE version_id=NEW.id;
 IF scope IS DISTINCT FROM NEW.review_snapshot->'source_scope' OR actual IS DISTINCT FROM scope
 OR EXISTS(SELECT 1 FROM jsonb_array_elements(NEW.review_snapshot->'inputs'->'overrides') o WHERE NOT scope ? (o->>'planning_version_id'))
 OR (NEW.review_snapshot->>'unresolved_tasks')::integer IS DISTINCT FROM (SELECT count(*)::integer FROM prep_inventory.day_tasks WHERE version_id=NEW.id AND included AND planned_quantity IS NULL)
 THEN RAISE EXCEPTION 'Dated draft planning scope or unresolved count is incomplete'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER valid_day_version BEFORE INSERT ON prep_inventory.day_list_versions FOR EACH ROW EXECUTE FUNCTION prep_inventory.guard_day_version();
CREATE TRIGGER continuous_day_version BEFORE INSERT ON prep_inventory.day_list_versions FOR EACH ROW EXECUTE FUNCTION prep_inventory.guard_version_chain();
CREATE TRIGGER valid_day_task BEFORE INSERT ON prep_inventory.day_tasks FOR EACH ROW EXECUTE FUNCTION prep_inventory.guard_day_task();
CREATE CONSTRAINT TRIGGER sealed_day_version AFTER INSERT ON prep_inventory.day_list_versions DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION prep_inventory.seal_day_version();
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['legacy_day_sources','day_lists','day_list_versions','day_tasks'] LOOP
  EXECUTE format('CREATE TRIGGER immutable_day_record BEFORE UPDATE OR DELETE ON prep_inventory.%I FOR EACH ROW EXECUTE FUNCTION purchasing.reject_fact_change()',t);
  EXECUTE format('REVOKE ALL ON prep_inventory.%I FROM PUBLIC',t);
 END LOOP;
 FOREACH t IN ARRAY ARRAY['prep_lists','prep_list_lines','prep_overrides'] LOOP
  EXECUTE format('CREATE TRIGGER retained_day_source BEFORE INSERT OR UPDATE OR DELETE ON public.%I FOR EACH ROW EXECUTE FUNCTION purchasing.reject_fact_change()',t);
 END LOOP;
END $$;
REVOKE ALL ON FUNCTION prep_inventory.guard_day_version(),prep_inventory.guard_day_task(),prep_inventory.seal_day_version() FROM PUBLIC;
COMMIT;
