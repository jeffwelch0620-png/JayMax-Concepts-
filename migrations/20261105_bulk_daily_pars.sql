-- M2 Bulk daily pars (Jeff 2026-11-04). Each store chooses how its Bulk pars work:
--   window (the default): the Monday run uses the weekday par, the Thursday run the weekend par;
--   daily: each Bulk item has seven daily pars (Monday first), and a run's target is the sum of
--          the days it covers (Monday: Monday to Wednesday; Thursday: Thursday to Sunday).
-- Large Bulk runs stay twice a week in both modes. The choice is versioned per store and only
-- switches to daily once every active Bulk item there has daily pars. Each plan records where its
-- pars came from (par_source) so a future par agent's proposals, once a manager accepts them, are
-- told apart from pars entered by hand; the agent never writes pars itself. Applies to new drafts
-- and requests only; nothing recorded is changed. No stock, purchase or accounting writes.
BEGIN;
SET LOCAL lock_timeout = '5s';

ALTER TABLE prep_inventory.planning_versions
 ADD COLUMN daily_pars numeric[],
 ADD COLUMN par_source text NOT NULL DEFAULT 'manual' CHECK (par_source IN ('manual', 'agent')),
 ADD CONSTRAINT planning_daily_pars_check CHECK (daily_pars IS NULL OR (
  track = 'bulk' AND schedule = 'daily'
  AND array_ndims(daily_pars) = 1 AND array_lower(daily_pars, 1) = 1 AND cardinality(daily_pars) = 7
  AND array_position(daily_pars, NULL) IS NULL AND 0 <= ALL(daily_pars)
  AND NOT ('NaN'::numeric = ANY(daily_pars)) AND NOT ('Infinity'::numeric = ANY(daily_pars))));

CREATE TABLE prep_inventory.bulk_par_modes (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 store_id text NOT NULL REFERENCES public.stores(id),
 revision integer NOT NULL CHECK (revision > 0),
 predecessor_id uuid UNIQUE,
 mode text NOT NULL CHECK (mode IN ('window', 'daily')),
 note text NOT NULL CHECK (length(btrim(note)) > 0),
 actor text NOT NULL CHECK (length(btrim(actor)) > 0),
 request_key uuid NOT NULL UNIQUE,
 request_fingerprint bytea NOT NULL CHECK (octet_length(request_fingerprint) = 32),
 recorded_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE (store_id, revision), UNIQUE (id, store_id),
 FOREIGN KEY (predecessor_id, store_id) REFERENCES prep_inventory.bulk_par_modes(id, store_id),
 CHECK ((revision = 1) = (predecessor_id IS NULL))
);

-- The store's current Bulk par mode; window until a store chooses otherwise.
CREATE FUNCTION prep_inventory.bulk_par_mode(store text) RETURNS text LANGUAGE sql STABLE AS $$
 SELECT coalesce((SELECT mode FROM prep_inventory.bulk_par_modes WHERE store_id = store ORDER BY revision DESC LIMIT 1), 'window')
$$;

-- A Bulk run's target par in the plan's own unit, or NULL when Bulk does not run that day or the
-- item has no daily pars in daily mode. backend/prep_day_tasks.py bulk_run_target mirrors this.
CREATE FUNCTION prep_inventory.bulk_run_target(plan prep_inventory.planning_versions, run date, mode text) RETURNS numeric LANGUAGE sql IMMUTABLE AS $$
 SELECT CASE
  WHEN prep_inventory.bulk_run_day_group(run) IS NULL THEN NULL
  WHEN mode = 'daily' THEN (SELECT sum(plan.daily_pars[d]) FROM unnest(CASE prep_inventory.bulk_run_day_group(run)
    WHEN 'weekday' THEN ARRAY[1, 2, 3] ELSE ARRAY[4, 5, 6, 7] END) d HAVING count(plan.daily_pars[d]) = count(*))
  WHEN prep_inventory.bulk_run_day_group(run) = 'weekend' THEN plan.weekend_par
  ELSE plan.weekday_par END
$$;

-- Each switch follows the store's latest one, and daily mode needs daily pars on every active
-- to-par Bulk item at the store.
CREATE FUNCTION prep_inventory.guard_bulk_par_mode() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE prior prep_inventory.bulk_par_modes;
BEGIN
 SELECT * INTO prior FROM prep_inventory.bulk_par_modes WHERE store_id = NEW.store_id ORDER BY revision DESC LIMIT 1;
 IF NEW.revision IS DISTINCT FROM coalesce(prior.revision, 0) + 1 OR NEW.predecessor_id IS DISTINCT FROM prior.id
 THEN RAISE EXCEPTION 'Bulk par mode changed; refresh before switching'; END IF;
 IF NEW.mode = 'daily' AND EXISTS (SELECT 1 FROM prep_inventory.planning_versions p WHERE p.store_id = NEW.store_id
    AND p.active AND p.track = 'bulk' AND p.schedule = 'daily' AND p.daily_pars IS NULL
    AND NOT EXISTS (SELECT 1 FROM prep_inventory.planning_versions q WHERE q.product_id = p.product_id AND q.revision > p.revision))
 THEN RAISE EXCEPTION 'Enter daily pars for every active Bulk item before switching to daily pars'; END IF;
 INSERT INTO public.store_state(store_id, revision) VALUES (NEW.store_id, 1)
 ON CONFLICT (store_id) DO UPDATE SET revision = store_state.revision + 1, updated_at = now();
 RETURN NEW;
END $$;
CREATE TRIGGER guard_bulk_par_mode BEFORE INSERT ON prep_inventory.bulk_par_modes
 FOR EACH ROW EXECUTE FUNCTION prep_inventory.guard_bulk_par_mode();
CREATE TRIGGER immutable_fact BEFORE UPDATE OR DELETE ON prep_inventory.bulk_par_modes
 FOR EACH ROW EXECUTE FUNCTION purchasing.reject_fact_change();

-- From migrations/20261007_prep_planning.sql, plus: a retirement keeps the daily pars, and a store
-- in daily mode cannot save an active to-par Bulk item without them.
CREATE OR REPLACE FUNCTION prep_inventory.guard_planning_version() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE recipe prep_inventory.recipe_versions; profile prep_inventory.unit_profiles; prior prep_inventory.planning_versions;
BEGIN
 SELECT * INTO recipe FROM prep_inventory.recipe_versions WHERE id=NEW.recipe_version_id;
 SELECT * INTO profile FROM prep_inventory.unit_profiles WHERE id=NEW.unit_profile_id;
 IF profile.product_version_id IS DISTINCT FROM recipe.product_version_id THEN RAISE EXCEPTION 'Planning unit must belong to the recipe output definition'; END IF;
 IF cardinality(NEW.recur_days)<>(SELECT count(DISTINCT d) FROM unnest(NEW.recur_days) d) THEN RAISE EXCEPTION 'Planning weekdays cannot repeat'; END IF;
 IF NOT NEW.active THEN
  SELECT * INTO prior FROM prep_inventory.planning_versions WHERE id=NEW.predecessor_id;
  IF NOT FOUND OR NOT prior.active OR
    (NEW.recipe_version_id,NEW.unit_profile_id,NEW.track,NEW.schedule,NEW.weekday_par,NEW.weekend_par,NEW.recur_days,NEW.fixed_quantity,NEW.daily_pars)
    IS DISTINCT FROM (prior.recipe_version_id,prior.unit_profile_id,prior.track,prior.schedule,prior.weekday_par,prior.weekend_par,prior.recur_days,prior.fixed_quantity,prior.daily_pars)
    THEN RAISE EXCEPTION 'Retirement must preserve an active predecessor planning definition'; END IF;
 ELSIF NEW.track='bulk' AND NEW.schedule='daily' AND NEW.daily_pars IS NULL AND prep_inventory.bulk_par_mode(NEW.store_id)='daily' THEN
  RAISE EXCEPTION 'This store uses daily Bulk pars; enter a par for each day';
 END IF;
 INSERT INTO public.store_state(store_id,revision) VALUES(NEW.store_id,1)
 ON CONFLICT(store_id) DO UPDATE SET revision=store_state.revision+1,updated_at=now();
 RETURN NEW;
END $$;

-- From migrations/20261030_bulk_supply.sql; the target is now the requester's Bulk run target.
CREATE OR REPLACE FUNCTION prep_inventory.guard_bulk_request_line() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE parent prep_inventory.bulk_requests; plan prep_inventory.planning_versions; counted numeric; factor numeric; target numeric;
BEGIN
 SELECT * INTO parent FROM prep_inventory.bulk_requests WHERE id = NEW.request_id;
 IF parent.created_xid <> pg_current_xact_id() THEN RAISE EXCEPTION 'A sent Bulk request cannot gain lines'; END IF;
 IF (SELECT identity_key FROM prep_inventory.products WHERE id = NEW.product_id)
    IS DISTINCT FROM (SELECT identity_key FROM prep_inventory.products WHERE id = NEW.maker_product_id)
 THEN RAISE EXCEPTION 'The maker''s item must be the same prepared item'; END IF;
 IF NOT EXISTS (SELECT 1 FROM prep_inventory.planning_versions p WHERE p.store_id = NEW.maker_store_id AND p.product_id = NEW.maker_product_id
    AND p.active AND p.track = 'bulk' AND p.schedule = 'daily' AND NOT EXISTS (SELECT 1 FROM prep_inventory.planning_versions q WHERE q.product_id = p.product_id AND q.revision > p.revision))
 THEN RAISE EXCEPTION 'The maker has no active to-par Bulk plan for this item'; END IF;
 IF parent.kind = 'spot' THEN
  IF NEW.planning_version_id IS NOT NULL OR NEW.factor IS NOT NULL OR NEW.target_par IS NOT NULL OR NEW.counted_base_quantity IS NOT NULL
     OR NEW.requested_base_quantity <= 0 OR coalesce(length(btrim(NEW.reason)), 0) = 0
  THEN RAISE EXCEPTION 'A spot request line is a positive amount with a reason'; END IF;
  RETURN NEW;
 END IF;
 SELECT * INTO plan FROM prep_inventory.planning_versions WHERE id = NEW.planning_version_id;
 IF plan.id IS NULL OR plan.store_id <> NEW.store_id OR plan.product_id <> NEW.product_id OR NOT plan.active OR plan.track <> 'bulk'
    OR plan.schedule <> 'daily'
    OR EXISTS (SELECT 1 FROM prep_inventory.planning_versions q WHERE q.product_id = plan.product_id AND q.revision > plan.revision)
 THEN RAISE EXCEPTION 'A scheduled request line needs the item''s current Bulk par'; END IF;
 SELECT base_units_per_source_unit INTO factor FROM prep_inventory.unit_profiles WHERE id = plan.unit_profile_id;
 target := prep_inventory.bulk_run_target(plan, parent.run_date, prep_inventory.bulk_par_mode(parent.store_id));
 IF target IS NULL THEN RAISE EXCEPTION 'Enter daily pars for this Bulk item before requesting it'; END IF;
 SELECT base_quantity INTO counted FROM prep_inventory.count_observations WHERE event_id = parent.count_event_id AND product_id = NEW.product_id;
 IF NOT FOUND THEN RAISE EXCEPTION 'Count this item before requesting it; a missing count is not zero'; END IF;
 IF NEW.factor IS DISTINCT FROM factor OR NEW.target_par IS DISTINCT FROM target OR NEW.counted_base_quantity IS DISTINCT FROM counted
    OR NEW.requested_base_quantity IS DISTINCT FROM greatest(target * factor - counted, 0) OR NEW.reason IS NOT NULL
 THEN RAISE EXCEPTION 'A scheduled request is par minus counted on hand'; END IF;
 RETURN NEW;
END $$;

-- From migrations/20261030_bulk_supply.sql; a Bulk task's target is now the store's Bulk run target,
-- and a Bulk item with no target (no daily pars in daily mode) cannot be planned to par.
CREATE OR REPLACE FUNCTION prep_inventory.guard_day_task() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE parent prep_inventory.day_list_versions; plan prep_inventory.planning_versions; profile prep_inventory.unit_profiles;
 identity prep_inventory.day_lists; override jsonb; included boolean; mode text; target numeric; counted numeric; needed numeric; qty numeric;
 batch numeric; batches numeric; incoming numeric; requested numeric; shown_count numeric;
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
  target:=CASE WHEN override IS NOT NULL THEN (override->>'quantity')::numeric
   WHEN identity.track='bulk' THEN prep_inventory.bulk_run_target(plan,identity.prep_date,prep_inventory.bulk_par_mode(identity.store_id))
   WHEN parent.day_group='weekend' THEN plan.weekend_par ELSE plan.weekday_par END;
  IF target IS NULL AND NEW.planned_quantity IS NOT NULL THEN RAISE EXCEPTION 'A Bulk item without daily pars cannot be planned to par'; END IF;
  SELECT base_quantity INTO counted FROM prep_inventory.count_observations WHERE event_id=parent.count_event_id AND product_id=NEW.product_id;
  IF FOUND AND target IS NOT NULL THEN
   -- Draft 0.7: N = max(0, T - H - I), planned as whole recipe batches covering N (Q = r x ceil(N/r)).
   -- Incoming supply (I) is recorded by store transfers (M3); until then it must be zero.
   incoming:=coalesce((NEW.task_snapshot->>'incoming_base_quantity')::numeric,0);
   IF incoming<>0 THEN RAISE EXCEPTION 'Incoming supply needs a recorded transfer'; END IF;
   -- Bulk: plus what other stores requested from this run (R).
   requested:=CASE WHEN identity.track='bulk' THEN prep_inventory.bulk_requested_base(identity.store_id,identity.prep_date,NEW.product_id) END;
   IF (NEW.task_snapshot->>'requested_base_quantity')::numeric IS DISTINCT FROM requested THEN RAISE EXCEPTION 'Other stores'' Bulk requests changed; review a fresh preview'; END IF;
   needed:=greatest(target*NEW.factor-counted-incoming,0)+coalesce(requested,0);
   SELECT usable_base_yield INTO batch FROM prep_inventory.recipe_versions WHERE id=NEW.recipe_version_id;
   batches:=(NEW.task_snapshot->>'batches')::numeric;
   IF NEW.planned_quantity IS NOT NULL AND (batch IS NULL OR batches IS NULL OR batches<0 OR batches<>trunc(batches)
    OR (NEW.task_snapshot->>'batch_base_yield')::numeric IS DISTINCT FROM batch
    OR NEW.planned_base_quantity IS DISTINCT FROM batches*batch
    OR batches*batch<needed OR (batches>0 AND (batches-1)*batch>=needed))
   THEN RAISE EXCEPTION 'To-par task must plan the fewest whole recipe batches covering its measured deficit'; END IF;
  ELSIF NEW.planned_quantity IS NOT NULL THEN RAISE EXCEPTION 'Missing physical count cannot be treated as zero stock'; END IF;
 END IF;
 -- A to-par item with no target shows no count; computed here because PL/pgSQL ends an IF test at its first THEN.
 shown_count:=CASE WHEN target IS NOT NULL OR mode<>'target_par' THEN counted END;
 IF (mode IN ('fixed_quantity','omit') AND NEW.planned_quantity IS DISTINCT FROM qty)
 OR (NEW.task_snapshot->>'target_par')::numeric IS DISTINCT FROM target
 OR (NEW.task_snapshot->>'counted_base_quantity')::numeric IS DISTINCT FROM shown_count
 OR (NEW.task_snapshot->>'needed_base_quantity')::numeric IS DISTINCT FROM needed
 OR (NEW.planned_quantity IS NULL AND coalesce(length(btrim(NEW.task_snapshot->>'issue')),0)=0)
 THEN RAISE EXCEPTION 'Task calculation needs matching measured or explicitly overridden evidence'; END IF;
 RETURN NEW;
END $$;

REVOKE ALL ON prep_inventory.bulk_par_modes FROM PUBLIC;
DO $$ BEGIN
 IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN REVOKE ALL ON prep_inventory.bulk_par_modes FROM anon; END IF;
 IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN REVOKE ALL ON prep_inventory.bulk_par_modes FROM authenticated; END IF;
END $$;
REVOKE ALL ON FUNCTION prep_inventory.bulk_par_mode(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION prep_inventory.bulk_run_target(prep_inventory.planning_versions, date, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION prep_inventory.guard_bulk_par_mode() FROM PUBLIC;
COMMIT;
