-- Standalone waste explanations and complete physical prep observations.
-- Counts do not create stock movements. No Track 1 writes.
BEGIN;
CREATE TABLE prep_inventory.observations (
 id uuid PRIMARY KEY, store_id text NOT NULL, purpose text NOT NULL CHECK(purpose IN ('waste','count')),
 root_id uuid NOT NULL, predecessor_id uuid UNIQUE, revision integer NOT NULL CHECK(revision>0),
 kind text NOT NULL CHECK(kind IN ('initial','replacement','void')), performed_at timestamptz NOT NULL,
 business_date date NOT NULL, timezone_name text NOT NULL, day_basis text NOT NULL DEFAULT 'calendar_day',
 raw_item_code text, product_id uuid, base_unit text, source_batch_id uuid,
 reason text NOT NULL CHECK(length(btrim(reason))>0), review_snapshot jsonb NOT NULL CHECK(jsonb_typeof(review_snapshot)='object'),
 review_hash bytea NOT NULL CHECK(octet_length(review_hash)=32), recorded_by text NOT NULL,
 recorded_at timestamptz NOT NULL DEFAULT now(), created_xid xid8 NOT NULL DEFAULT pg_current_xact_id(),
 request_key uuid NOT NULL UNIQUE, request_fingerprint bytea NOT NULL CHECK(octet_length(request_fingerprint)=32),
 UNIQUE(id,store_id), UNIQUE(id,store_id,purpose), UNIQUE(root_id,revision),
 FOREIGN KEY(store_id,timezone_name,day_basis) REFERENCES prep_inventory.batch_policies(store_id,timezone_name,day_basis),
 FOREIGN KEY(root_id,store_id,purpose) REFERENCES prep_inventory.observations(id,store_id,purpose),
 FOREIGN KEY(predecessor_id,store_id,purpose) REFERENCES prep_inventory.observations(id,store_id,purpose),
 FOREIGN KEY(store_id,raw_item_code,base_unit) REFERENCES purchasing.item_bases(store_id,item_code,base_unit),
 FOREIGN KEY(product_id,store_id,base_unit) REFERENCES prep_inventory.products(id,store_id,base_unit),
 FOREIGN KEY(source_batch_id,store_id,product_id,base_unit) REFERENCES prep_inventory.batch_events(id,store_id,product_id,base_unit),
 CHECK((purpose='count' AND raw_item_code IS NULL AND product_id IS NULL AND base_unit IS NULL AND source_batch_id IS NULL)
 OR (purpose='waste' AND base_unit IS NOT NULL AND ((raw_item_code IS NOT NULL AND product_id IS NULL AND source_batch_id IS NULL)
 OR (raw_item_code IS NULL AND product_id IS NOT NULL AND source_batch_id IS NOT NULL)))),
 CHECK((kind='initial' AND predecessor_id IS NULL AND root_id=id AND revision=1)
 OR (kind IN ('replacement','void') AND predecessor_id IS NOT NULL AND revision>1)),
 CHECK(business_date=(performed_at AT TIME ZONE timezone_name)::date)
);
CREATE UNIQUE INDEX one_prep_count_instant ON prep_inventory.observations(store_id,performed_at) WHERE purpose='count' AND kind='initial';
CREATE TABLE prep_inventory.waste_movements (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), event_id uuid NOT NULL, store_id text NOT NULL,
 ordinal integer NOT NULL CHECK(ordinal>0), side text NOT NULL CHECK(side IN ('apply','reverse')),
 raw_item_code text, product_id uuid, base_unit text NOT NULL, source_batch_id uuid,
 quantity numeric NOT NULL CHECK(quantity<>0 AND quantity NOT IN ('NaN'::numeric,'Infinity'::numeric,'-Infinity'::numeric)),
 reverses_movement_id uuid UNIQUE REFERENCES prep_inventory.waste_movements(id), UNIQUE(event_id,ordinal),
 FOREIGN KEY(event_id,store_id) REFERENCES prep_inventory.observations(id,store_id),
 FOREIGN KEY(store_id,raw_item_code,base_unit) REFERENCES purchasing.item_bases(store_id,item_code,base_unit),
 FOREIGN KEY(product_id,store_id,base_unit) REFERENCES prep_inventory.products(id,store_id,base_unit),
 FOREIGN KEY(source_batch_id,store_id,product_id,base_unit) REFERENCES prep_inventory.batch_events(id,store_id,product_id,base_unit),
 CHECK((raw_item_code IS NOT NULL AND product_id IS NULL AND source_batch_id IS NULL)
 OR (raw_item_code IS NULL AND product_id IS NOT NULL AND source_batch_id IS NOT NULL)),
 CHECK((side='apply' AND quantity<0 AND reverses_movement_id IS NULL) OR (side='reverse' AND quantity>0 AND reverses_movement_id IS NOT NULL))
);
CREATE INDEX waste_source_allocations ON prep_inventory.waste_movements(source_batch_id);
CREATE TABLE prep_inventory.count_observations (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), event_id uuid NOT NULL, store_id text NOT NULL,
 line_number integer NOT NULL CHECK(line_number>0), product_id uuid NOT NULL, product_version_id uuid NOT NULL,
 profile_id uuid NOT NULL, base_unit text NOT NULL, quantity numeric NOT NULL CHECK(quantity>=0 AND quantity NOT IN ('NaN'::numeric,'Infinity'::numeric,'-Infinity'::numeric)),
 factor numeric NOT NULL CHECK(factor>0 AND factor NOT IN ('NaN'::numeric,'Infinity'::numeric,'-Infinity'::numeric)),
 base_quantity numeric NOT NULL CHECK(base_quantity=quantity*factor), evidence text NOT NULL CHECK(length(btrim(evidence))>0),
 UNIQUE(event_id,line_number), UNIQUE(event_id,product_id),
 FOREIGN KEY(event_id,store_id) REFERENCES prep_inventory.observations(id,store_id),
 FOREIGN KEY(product_id,store_id,base_unit) REFERENCES prep_inventory.products(id,store_id,base_unit),
 FOREIGN KEY(product_version_id,product_id,store_id) REFERENCES prep_inventory.product_versions(id,product_id,store_id),
 FOREIGN KEY(profile_id,product_version_id,store_id) REFERENCES prep_inventory.unit_profiles(id,product_version_id,store_id)
);
-- Both batches and waste use this projection, regardless of UI/feature flags.
CREATE OR REPLACE FUNCTION prep_inventory.lot_used(source_id uuid) RETURNS numeric LANGUAGE sql STABLE AS $$
 SELECT -(coalesce((SELECT sum(quantity) FROM prep_inventory.batch_movements WHERE source_batch_id=source_id),0)
   +coalesce((SELECT sum(quantity) FROM prep_inventory.waste_movements WHERE source_batch_id=source_id),0))
$$;
CREATE FUNCTION prep_inventory.guard_observation() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE prior prep_inventory.observations;
BEGIN
 PERFORM 1 FROM public.store_state WHERE store_id=NEW.store_id FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Observation requires store coordination'; END IF;
 IF NEW.predecessor_id IS NOT NULL THEN
  SELECT * INTO prior FROM prep_inventory.observations WHERE id=NEW.predecessor_id;
  IF prior.kind='void' OR NEW.root_id IS DISTINCT FROM prior.root_id OR NEW.revision<>prior.revision+1
   OR (NEW.performed_at,NEW.business_date,NEW.timezone_name,NEW.raw_item_code,NEW.product_id,NEW.base_unit)
    IS DISTINCT FROM (prior.performed_at,prior.business_date,prior.timezone_name,prior.raw_item_code,prior.product_id,prior.base_unit)
  THEN RAISE EXCEPTION 'Correction must extend the same observation identity and date'; END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER observation_guard BEFORE INSERT ON prep_inventory.observations FOR EACH ROW EXECUTE FUNCTION prep_inventory.guard_observation();
CREATE FUNCTION prep_inventory.guard_observation_child() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE parent prep_inventory.observations;
BEGIN
 SELECT * INTO parent FROM prep_inventory.observations WHERE id=NEW.event_id;
 IF parent.created_xid IS DISTINCT FROM pg_current_xact_id() OR parent.recorded_at IS DISTINCT FROM transaction_timestamp()
 THEN RAISE EXCEPTION 'Observation is sealed; append a correction'; END IF;
 IF (TG_TABLE_NAME='waste_movements' AND parent.purpose<>'waste') OR (TG_TABLE_NAME='count_observations' AND parent.purpose<>'count')
 THEN RAISE EXCEPTION 'Observation child purpose mismatch'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER waste_child_guard BEFORE INSERT ON prep_inventory.waste_movements FOR EACH ROW EXECUTE FUNCTION prep_inventory.guard_observation_child();
CREATE TRIGGER count_child_guard BEFORE INSERT ON prep_inventory.count_observations FOR EACH ROW EXECUTE FUNCTION prep_inventory.guard_observation_child();
CREATE FUNCTION prep_inventory.seal_observation() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE actual jsonb; line jsonb; n integer; source prep_inventory.batch_events; scope jsonb;
BEGIN
 IF NEW.review_snapshot->>'purpose' IS DISTINCT FROM NEW.purpose OR NEW.review_snapshot->>'kind' IS DISTINCT FROM NEW.kind
 OR (NEW.review_snapshot->>'revision')::integer IS DISTINCT FROM NEW.revision
 OR (NEW.review_snapshot->>'predecessor_id')::uuid IS DISTINCT FROM NEW.predecessor_id
 OR (NEW.kind<>'initial' AND (NEW.review_snapshot->>'root_id')::uuid IS DISTINCT FROM NEW.root_id)
 OR (NEW.review_snapshot->>'performed_at')::timestamptz IS DISTINCT FROM NEW.performed_at
 OR (NEW.review_snapshot->>'business_date')::date IS DISTINCT FROM NEW.business_date
 OR NEW.review_snapshot->>'timezone_name' IS DISTINCT FROM NEW.timezone_name
 OR NEW.review_snapshot->>'reason' IS DISTINCT FROM NEW.reason
 OR NEW.review_snapshot->'cost' IS DISTINCT FROM '{"status":"not_calculated","amount":null}'::jsonb
 THEN RAISE EXCEPTION 'Observation header differs from its reviewed facts'; END IF;
 IF NEW.purpose='waste' THEN
  SELECT coalesce(jsonb_agg(jsonb_build_object('side',side,'raw_item_code',raw_item_code,'product_id',product_id,'base_unit',base_unit,
    'source_batch_id',source_batch_id,'quantity',quantity::text,'reverses_movement_id',reverses_movement_id) ORDER BY ordinal),'[]'::jsonb)
   INTO actual FROM prep_inventory.waste_movements WHERE event_id=NEW.id;
  IF actual IS DISTINCT FROM NEW.review_snapshot->'movements' THEN RAISE EXCEPTION 'Waste movements differ from reviewed quantities'; END IF;
  IF NEW.kind='void' THEN
   IF EXISTS(SELECT 1 FROM prep_inventory.waste_movements WHERE event_id=NEW.id AND side='apply') THEN RAISE EXCEPTION 'Void cannot apply waste'; END IF;
  ELSE
   IF NEW.review_snapshot->'body'->'already_included_in_batch' IS DISTINCT FROM 'false'::jsonb
    OR NEW.review_snapshot->'body'->>'measurement_basis' IS DISTINCT FROM 'measured'
    OR (NEW.review_snapshot->>'baseQuantity')::numeric IS DISTINCT FROM (NEW.review_snapshot->'body'->>'quantity')::numeric*(NEW.review_snapshot->>'factor')::numeric
   THEN RAISE EXCEPTION 'Waste must be separate measured loss with a verified conversion'; END IF;
   SELECT count(*) INTO n FROM prep_inventory.waste_movements WHERE event_id=NEW.id AND side='apply'
    AND (raw_item_code,product_id,base_unit,source_batch_id) IS NOT DISTINCT FROM (NEW.raw_item_code,NEW.product_id,NEW.base_unit,NEW.source_batch_id)
    AND quantity=-(NEW.review_snapshot->>'baseQuantity')::numeric;
   IF n<>1 OR (SELECT count(*) FROM prep_inventory.waste_movements WHERE event_id=NEW.id AND side='apply')<>1 THEN RAISE EXCEPTION 'Waste requires one exact withdrawal'; END IF;
   IF NEW.product_id IS NOT NULL THEN
    SELECT * INTO source FROM prep_inventory.batch_events WHERE id=NEW.source_batch_id;
    IF source.kind='void' OR source.performed_at>NEW.performed_at THEN RAISE EXCEPTION 'Waste source must be produced before waste'; END IF;
    IF (NEW.review_snapshot->>'factor')::numeric IS DISTINCT FROM (SELECT u.base_units_per_source_unit FROM prep_inventory.unit_profiles u
       JOIN prep_inventory.product_versions v ON v.id=u.product_version_id
       WHERE u.id=(NEW.review_snapshot->'body'->>'profile_id')::uuid AND u.product_version_id=(NEW.review_snapshot->'body'->>'product_version_id')::uuid
        AND u.store_id=NEW.store_id AND v.product_id=NEW.product_id AND v.base_unit=NEW.base_unit)
    THEN RAISE EXCEPTION 'Waste unit must match the frozen prepared profile'; END IF;
   END IF;
  END IF;
  IF (SELECT count(*) FROM prep_inventory.waste_movements WHERE event_id=NEW.id AND side='reverse')<>
   (SELECT count(*) FROM prep_inventory.waste_movements WHERE event_id=NEW.predecessor_id AND side='apply')
   OR EXISTS(SELECT 1 FROM prep_inventory.waste_movements m LEFT JOIN prep_inventory.waste_movements prior_m ON prior_m.id=m.reverses_movement_id
    WHERE m.event_id=NEW.id AND m.side='reverse' AND (prior_m.id IS NULL OR prior_m.event_id IS DISTINCT FROM NEW.predecessor_id OR prior_m.side<>'apply'
    OR (m.raw_item_code,m.product_id,m.base_unit,m.source_batch_id,m.quantity) IS DISTINCT FROM
       (prior_m.raw_item_code,prior_m.product_id,prior_m.base_unit,prior_m.source_batch_id,-prior_m.quantity)))
   THEN RAISE EXCEPTION 'Waste correction must exactly reverse its predecessor'; END IF;
  PERFORM prep_inventory.assert_lot_allocations(NEW.store_id);
 ELSE
  SELECT coalesce(jsonb_agg(jsonb_build_object('line_number',line_number,'product_id',product_id,'product_version_id',product_version_id,
    'profile_id',profile_id,'base_unit',base_unit,'quantity',quantity::text,'factor',factor::text,'base_quantity',base_quantity::text,'evidence',evidence) ORDER BY line_number),'[]'::jsonb)
    INTO actual FROM prep_inventory.count_observations WHERE event_id=NEW.id;
  IF actual IS DISTINCT FROM NEW.review_snapshot->'lines' THEN RAISE EXCEPTION 'Physical prep observations differ from reviewed quantities'; END IF;
  IF NEW.kind='void' THEN
   IF jsonb_array_length(actual)<>0 THEN RAISE EXCEPTION 'Void cannot add physical counts'; END IF;
  ELSE
   IF NEW.review_snapshot->'body'->'complete_scope_confirmed' IS DISTINCT FROM 'true'::jsonb
    THEN RAISE EXCEPTION 'Physical prep scope must be explicitly confirmed'; END IF;
   SELECT coalesce(jsonb_agg(product_id::text ORDER BY product_id::text),'[]'::jsonb) INTO scope FROM prep_inventory.count_observations WHERE event_id=NEW.id;
   IF scope IS DISTINCT FROM NEW.review_snapshot->'scope' OR jsonb_array_length(scope)=0 THEN RAISE EXCEPTION 'Count scope must be complete and nonempty'; END IF;
   IF EXISTS(SELECT 1 FROM prep_inventory.count_observations c JOIN prep_inventory.unit_profiles u ON u.id=c.profile_id
    WHERE c.event_id=NEW.id AND c.factor IS DISTINCT FROM u.base_units_per_source_unit) THEN RAISE EXCEPTION 'Count factor differs from frozen profile'; END IF;
  END IF;
  IF NEW.predecessor_id IS NOT NULL AND NEW.review_snapshot->'scope' IS DISTINCT FROM
   (SELECT review_snapshot->'scope' FROM prep_inventory.observations WHERE id=NEW.predecessor_id)
  THEN RAISE EXCEPTION 'Count correction must retain original scope'; END IF;
 END IF;
 RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER observation_seal AFTER INSERT ON prep_inventory.observations DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION prep_inventory.seal_observation();
CREATE TRIGGER observation_immutable BEFORE UPDATE OR DELETE ON prep_inventory.observations FOR EACH ROW EXECUTE FUNCTION purchasing.reject_fact_change();
CREATE TRIGGER waste_movement_immutable BEFORE UPDATE OR DELETE ON prep_inventory.waste_movements FOR EACH ROW EXECUTE FUNCTION purchasing.reject_fact_change();
CREATE TRIGGER physical_prep_count_immutable BEFORE UPDATE OR DELETE ON prep_inventory.count_observations FOR EACH ROW EXECUTE FUNCTION purchasing.reject_fact_change();
REVOKE ALL ON ALL TABLES IN SCHEMA prep_inventory FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA prep_inventory FROM PUBLIC;
DO $$ DECLARE role_name text; BEGIN
 FOREACH role_name IN ARRAY ARRAY['anon','authenticated'] LOOP
  IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=role_name) THEN
   EXECUTE format('REVOKE ALL ON ALL TABLES IN SCHEMA prep_inventory FROM %I',role_name);
   EXECUTE format('REVOKE ALL ON ALL FUNCTIONS IN SCHEMA prep_inventory FROM %I',role_name);
  END IF;
 END LOOP;
END $$;
COMMIT;
