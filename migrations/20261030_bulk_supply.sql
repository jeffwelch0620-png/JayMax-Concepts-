-- M3 Bulk supply (Jeff 2026-10-29). Bert's Bulk is made at Rudd's from Bert's own goods:
--   1. Bert's sends its Bulk count as a request: par minus on hand for each Bulk item.
--   2. Rudd's makes it in its Bulk run, then signs off the amounts and packaging: sent to Bert's
--      (delivery or pickup) and held at Rudd's for Bert's. There is one par per item for the
--      owning store, met by its stock wherever it is held (Jeff 2026-10-29): Bert's counts its
--      goods held at Rudd's in its own count (a "Held at Rudd's" count zone).
--   3. Bert's manager accepts what arrived. Anything short stays open (needed, not fulfilled)
--      until a spot prep or the next run makes it up.
-- Scheduled requests (Sunday night count -> Monday, Wednesday night -> Thursday) feed the
-- maker's Bulk day draft; spot requests are made separately. Each store keeps its own
-- prepared items: a request names the requester's item and the maker's item of the same name.
-- Nothing here writes stock, purchases or accounting. Records are append-only.
BEGIN;
SET LOCAL lock_timeout = '5s';

CREATE TABLE prep_inventory.bulk_requests (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 store_id text NOT NULL REFERENCES public.stores(id),
 maker_store_id text NOT NULL REFERENCES public.stores(id) CHECK (maker_store_id <> store_id),
 run_date date NOT NULL,
 kind text NOT NULL CHECK (kind IN ('scheduled', 'spot')),
 day_group text CHECK (day_group IN ('weekday', 'weekend')),
 count_event_id uuid,
 note text NOT NULL CHECK (length(btrim(note)) > 0),
 actor text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 created_xid xid8 NOT NULL DEFAULT pg_current_xact_id(),
 review_snapshot jsonb NOT NULL CHECK (jsonb_typeof(review_snapshot) = 'object'),
 request_key uuid NOT NULL UNIQUE,
 request_fingerprint bytea NOT NULL CHECK (octet_length(request_fingerprint) = 32),
 CHECK ((kind = 'scheduled') = (count_event_id IS NOT NULL) AND (kind = 'scheduled') = (day_group IS NOT NULL)),
 FOREIGN KEY (count_event_id, store_id) REFERENCES prep_inventory.observations(id, store_id),
 UNIQUE (id, store_id), UNIQUE (id, maker_store_id)
);
CREATE INDEX bulk_requests_maker_run ON prep_inventory.bulk_requests(maker_store_id, run_date);
CREATE INDEX bulk_requests_store_run ON prep_inventory.bulk_requests(store_id, run_date);

CREATE TABLE prep_inventory.bulk_request_lines (
 request_id uuid NOT NULL,
 store_id text NOT NULL,
 maker_store_id text NOT NULL,
 ordinal integer NOT NULL CHECK (ordinal > 0),
 product_id uuid NOT NULL,
 maker_product_id uuid NOT NULL,
 base_unit text NOT NULL,
 planning_version_id uuid REFERENCES prep_inventory.planning_versions(id),
 factor numeric,
 target_par numeric,
 counted_base_quantity numeric,
 requested_base_quantity numeric NOT NULL CHECK (requested_base_quantity >= 0 AND requested_base_quantity NOT IN ('NaN'::numeric, 'Infinity'::numeric)),
 reason text,
 PRIMARY KEY (request_id, ordinal),
 UNIQUE (request_id, product_id),
 FOREIGN KEY (request_id, store_id) REFERENCES prep_inventory.bulk_requests(id, store_id),
 FOREIGN KEY (request_id, maker_store_id) REFERENCES prep_inventory.bulk_requests(id, maker_store_id),
 FOREIGN KEY (product_id, store_id, base_unit) REFERENCES prep_inventory.products(id, store_id, base_unit),
 FOREIGN KEY (maker_product_id, maker_store_id, base_unit) REFERENCES prep_inventory.products(id, store_id, base_unit)
);
CREATE INDEX bulk_request_lines_maker_product ON prep_inventory.bulk_request_lines(maker_product_id);

-- One sign-off per step: the maker fulfills once, the requester accepts once; a request with
-- nothing sent yet can be cancelled by the requester.
CREATE TABLE prep_inventory.bulk_events (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 request_id uuid NOT NULL REFERENCES prep_inventory.bulk_requests(id),
 action text NOT NULL CHECK (action IN ('fulfill', 'accept', 'cancel')),
 store_id text NOT NULL REFERENCES public.stores(id),
 handoff text CHECK (handoff IN ('delivery', 'pickup')),
 note text NOT NULL CHECK (length(btrim(note)) > 0),
 actor text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 created_xid xid8 NOT NULL DEFAULT pg_current_xact_id(),
 request_key uuid NOT NULL UNIQUE,
 request_fingerprint bytea NOT NULL CHECK (octet_length(request_fingerprint) = 32),
 CHECK ((action = 'fulfill') = (handoff IS NOT NULL)),
 UNIQUE (request_id, action)
);

CREATE TABLE prep_inventory.bulk_event_lines (
 event_id uuid NOT NULL REFERENCES prep_inventory.bulk_events(id),
 request_id uuid NOT NULL,
 ordinal integer NOT NULL,
 base_quantity numeric NOT NULL CHECK (base_quantity >= 0 AND base_quantity NOT IN ('NaN'::numeric, 'Infinity'::numeric)),
 held_base_quantity numeric NOT NULL DEFAULT 0 CHECK (held_base_quantity >= 0 AND held_base_quantity NOT IN ('NaN'::numeric, 'Infinity'::numeric)),
 packaging text,
 PRIMARY KEY (event_id, ordinal),
 FOREIGN KEY (request_id, ordinal) REFERENCES prep_inventory.bulk_request_lines(request_id, ordinal)
);

-- A scheduled line is exactly par minus counted on hand (never below zero) for the
-- requester's current Bulk plan; a spot line is a positive amount with a reason. The maker's
-- item has the same name and unit and an active Bulk plan at the maker.
CREATE FUNCTION prep_inventory.guard_bulk_request_line() RETURNS trigger LANGUAGE plpgsql AS $$
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
 target := CASE WHEN parent.day_group = 'weekend' THEN plan.weekend_par ELSE plan.weekday_par END;
 SELECT base_quantity INTO counted FROM prep_inventory.count_observations WHERE event_id = parent.count_event_id AND product_id = NEW.product_id;
 IF NOT FOUND THEN RAISE EXCEPTION 'Count this item before requesting it; a missing count is not zero'; END IF;
 IF NEW.factor IS DISTINCT FROM factor OR NEW.target_par IS DISTINCT FROM target OR NEW.counted_base_quantity IS DISTINCT FROM counted
    OR NEW.requested_base_quantity IS DISTINCT FROM greatest(target * factor - counted, 0) OR NEW.reason IS NOT NULL
 THEN RAISE EXCEPTION 'A scheduled request is par minus counted on hand'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER guard_bulk_request_line BEFORE INSERT ON prep_inventory.bulk_request_lines
 FOR EACH ROW EXECUTE FUNCTION prep_inventory.guard_bulk_request_line();

-- A scheduled request uses the requester's latest current count from the night before the run.
CREATE FUNCTION prep_inventory.guard_bulk_request() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE latest uuid;
BEGIN
 IF NEW.kind = 'scheduled' THEN
  SELECT o.id INTO latest FROM prep_inventory.observations o WHERE o.store_id = NEW.store_id AND o.purpose = 'count'
   AND o.business_date = NEW.run_date - 1 AND o.kind <> 'void'
   AND NOT EXISTS (SELECT 1 FROM prep_inventory.observations c WHERE c.predecessor_id = o.id)
   ORDER BY o.performed_at DESC, o.id LIMIT 1;
  IF latest IS DISTINCT FROM NEW.count_event_id THEN RAISE EXCEPTION 'Use the latest prep count from the night before the Bulk run'; END IF;
  IF EXISTS (SELECT 1 FROM prep_inventory.bulk_requests r WHERE r.store_id = NEW.store_id AND r.run_date = NEW.run_date AND r.kind = 'scheduled'
     AND NOT EXISTS (SELECT 1 FROM prep_inventory.bulk_events e WHERE e.request_id = r.id AND e.action = 'cancel'))
  THEN RAISE EXCEPTION 'This Bulk run already has a request from this store; cancel it before sending another'; END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER guard_bulk_request BEFORE INSERT ON prep_inventory.bulk_requests
 FOR EACH ROW EXECUTE FUNCTION prep_inventory.guard_bulk_request();

-- Every line of a request is present at commit.
CREATE FUNCTION prep_inventory.check_bulk_request_lines() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF (SELECT count(*) FROM prep_inventory.bulk_request_lines WHERE request_id = NEW.id)
    IS DISTINCT FROM jsonb_array_length(NEW.review_snapshot->'lines')
    OR jsonb_array_length(NEW.review_snapshot->'lines') = 0
 THEN RAISE EXCEPTION 'A Bulk request records every reviewed line'; END IF;
 RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER bulk_request_lines_complete AFTER INSERT ON prep_inventory.bulk_requests
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION prep_inventory.check_bulk_request_lines();

-- Order and authority: the maker fulfills (once, before any acceptance), the requester accepts
-- after fulfillment, and the requester can cancel only while nothing has been sent.
CREATE FUNCTION prep_inventory.guard_bulk_event() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE parent prep_inventory.bulk_requests; done text[];
BEGIN
 SELECT * INTO parent FROM prep_inventory.bulk_requests WHERE id = NEW.request_id FOR UPDATE;
 SELECT coalesce(array_agg(action), '{}') INTO done FROM prep_inventory.bulk_events WHERE request_id = NEW.request_id;
 IF 'cancel' = ANY(done) THEN RAISE EXCEPTION 'This Bulk request was cancelled'; END IF;
 IF NEW.action = 'fulfill' AND NEW.store_id <> parent.maker_store_id THEN RAISE EXCEPTION 'Only the making store signs off what it sent'; END IF;
 IF NEW.action IN ('accept', 'cancel') AND NEW.store_id <> parent.store_id THEN RAISE EXCEPTION 'Only the requesting store accepts or cancels its request'; END IF;
 IF NEW.action = 'accept' AND NOT 'fulfill' = ANY(done) THEN RAISE EXCEPTION 'Nothing has been sent to accept yet'; END IF;
 IF NEW.action = 'cancel' AND 'fulfill' = ANY(done) THEN RAISE EXCEPTION 'A request that was already sent cannot be cancelled'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER guard_bulk_event BEFORE INSERT ON prep_inventory.bulk_events
 FOR EACH ROW EXECUTE FUNCTION prep_inventory.guard_bulk_event();

-- Made lines carry packaging when anything was sent or held; accepted amounts never exceed what
-- was sent; held amounts are signed off by the maker only.
CREATE FUNCTION prep_inventory.guard_bulk_event_line() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE event prep_inventory.bulk_events; sent numeric;
BEGIN
 SELECT * INTO event FROM prep_inventory.bulk_events WHERE id = NEW.event_id;
 IF event.created_xid <> pg_current_xact_id() OR event.request_id <> NEW.request_id THEN RAISE EXCEPTION 'A signed Bulk step cannot gain lines'; END IF;
 IF event.action = 'cancel' THEN RAISE EXCEPTION 'A cancellation has no lines'; END IF;
 IF event.action = 'fulfill' AND NEW.base_quantity + NEW.held_base_quantity > 0 AND coalesce(length(btrim(NEW.packaging)), 0) = 0 THEN RAISE EXCEPTION 'Sign off the packaging of each item made'; END IF;
 IF event.action = 'accept' THEN
  IF NEW.packaging IS NOT NULL OR NEW.held_base_quantity <> 0 THEN RAISE EXCEPTION 'Packaging and held amounts are signed off by the maker'; END IF;
  SELECT l.base_quantity INTO sent FROM prep_inventory.bulk_event_lines l JOIN prep_inventory.bulk_events e ON e.id = l.event_id
   WHERE e.request_id = NEW.request_id AND e.action = 'fulfill' AND l.ordinal = NEW.ordinal;
  IF NEW.base_quantity > coalesce(sent, 0) THEN RAISE EXCEPTION 'Accepted more than was sent'; END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER guard_bulk_event_line BEFORE INSERT ON prep_inventory.bulk_event_lines
 FOR EACH ROW EXECUTE FUNCTION prep_inventory.guard_bulk_event_line();

CREATE FUNCTION prep_inventory.check_bulk_event_lines() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.action <> 'cancel' AND (SELECT count(*) FROM prep_inventory.bulk_event_lines WHERE event_id = NEW.id)
    IS DISTINCT FROM (SELECT count(*) FROM prep_inventory.bulk_request_lines WHERE request_id = NEW.request_id)
 THEN RAISE EXCEPTION 'Sign off every requested item, entering zero for any not sent or not received'; END IF;
 RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER bulk_event_lines_complete AFTER INSERT ON prep_inventory.bulk_events
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION prep_inventory.check_bulk_event_lines();

-- Amount other stores asked the maker to make in a scheduled Bulk run (live requests only).
CREATE FUNCTION prep_inventory.bulk_requested_base(maker text, run date, product uuid) RETURNS numeric LANGUAGE sql STABLE AS $$
 SELECT coalesce(sum(l.requested_base_quantity), 0) FROM prep_inventory.bulk_request_lines l
  JOIN prep_inventory.bulk_requests r ON r.id = l.request_id
  WHERE r.maker_store_id = maker AND r.run_date = run AND r.kind = 'scheduled' AND l.maker_product_id = product
   AND NOT EXISTS (SELECT 1 FROM prep_inventory.bulk_events e WHERE e.request_id = r.id AND e.action = 'cancel')
$$;

-- Bulk day tasks at the maker add what other stores requested for that run:
-- N = max(0, T - H - I) + R, still planned as the fewest whole batches. Otherwise unchanged
-- from migrations/20261029_prep_batch_rounding.sql.
CREATE OR REPLACE FUNCTION prep_inventory.guard_day_task() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE parent prep_inventory.day_list_versions; plan prep_inventory.planning_versions; profile prep_inventory.unit_profiles;
 identity prep_inventory.day_lists; override jsonb; included boolean; mode text; target numeric; counted numeric; needed numeric; qty numeric;
 batch numeric; batches numeric; incoming numeric; requested numeric;
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
 IF (mode IN ('fixed_quantity','omit') AND NEW.planned_quantity IS DISTINCT FROM qty)
 OR (NEW.task_snapshot->>'target_par')::numeric IS DISTINCT FROM target
 OR (NEW.task_snapshot->>'counted_base_quantity')::numeric IS DISTINCT FROM counted
 OR (NEW.task_snapshot->>'needed_base_quantity')::numeric IS DISTINCT FROM needed
 OR (NEW.planned_quantity IS NULL AND coalesce(length(btrim(NEW.task_snapshot->>'issue')),0)=0)
 THEN RAISE EXCEPTION 'Task calculation needs matching measured or explicitly overridden evidence'; END IF;
 RETURN NEW;
END $$;

DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['bulk_requests','bulk_request_lines','bulk_events','bulk_event_lines'] LOOP
  EXECUTE format('CREATE TRIGGER immutable_fact BEFORE UPDATE OR DELETE ON prep_inventory.%I
      FOR EACH ROW EXECUTE FUNCTION purchasing.reject_fact_change()', t);
  EXECUTE format('REVOKE ALL ON prep_inventory.%I FROM PUBLIC', t);
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN EXECUTE format('REVOKE ALL ON prep_inventory.%I FROM anon', t); END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN EXECUTE format('REVOKE ALL ON prep_inventory.%I FROM authenticated', t); END IF;
 END LOOP;
END $$;
REVOKE ALL ON FUNCTION prep_inventory.guard_bulk_request_line() FROM PUBLIC;
REVOKE ALL ON FUNCTION prep_inventory.guard_bulk_request() FROM PUBLIC;
REVOKE ALL ON FUNCTION prep_inventory.check_bulk_request_lines() FROM PUBLIC;
REVOKE ALL ON FUNCTION prep_inventory.guard_bulk_event() FROM PUBLIC;
REVOKE ALL ON FUNCTION prep_inventory.guard_bulk_event_line() FROM PUBLIC;
REVOKE ALL ON FUNCTION prep_inventory.check_bulk_event_lines() FROM PUBLIC;
REVOKE ALL ON FUNCTION prep_inventory.bulk_requested_base(text, date, uuid) FROM PUBLIC;
COMMIT;
