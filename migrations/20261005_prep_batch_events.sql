-- Quantity-only explanation journal. Never updates purchased counts or purchases.
BEGIN;
ALTER TABLE prep_inventory.recipe_lines ADD UNIQUE(id,recipe_version_id,store_id);
CREATE TABLE prep_inventory.batch_policies (
 store_id text PRIMARY KEY REFERENCES public.stores(id), timezone_name text NOT NULL,
 day_basis text NOT NULL CHECK(day_basis='calendar_day'), confirmed_by text NOT NULL,
 confirmed_at timestamptz NOT NULL DEFAULT now(), UNIQUE(store_id,timezone_name,day_basis)
);
CREATE TABLE prep_inventory.batch_events (
 id uuid PRIMARY KEY, store_id text NOT NULL, root_id uuid NOT NULL, predecessor_id uuid UNIQUE,
 revision integer NOT NULL CHECK(revision>0), kind text NOT NULL CHECK(kind IN ('initial','replacement','void')),
 recipe_version_id uuid NOT NULL, product_id uuid NOT NULL, product_version_id uuid NOT NULL,
 base_unit text NOT NULL, performed_at timestamptz NOT NULL, business_date date NOT NULL,
 timezone_name text NOT NULL, day_basis text NOT NULL DEFAULT 'calendar_day',
 reason text NOT NULL CHECK(length(btrim(reason))>0), review_snapshot jsonb NOT NULL,
 review_hash bytea NOT NULL CHECK(octet_length(review_hash)=32), recorded_by text NOT NULL,
 recorded_at timestamptz NOT NULL DEFAULT now(), created_xid xid8 NOT NULL DEFAULT pg_current_xact_id(),
 request_key uuid NOT NULL UNIQUE, request_fingerprint bytea NOT NULL CHECK(octet_length(request_fingerprint)=32),
 UNIQUE(id,store_id), UNIQUE(id,store_id,product_id,base_unit), UNIQUE(root_id,revision),
 FOREIGN KEY(store_id,timezone_name,day_basis) REFERENCES prep_inventory.batch_policies(store_id,timezone_name,day_basis),
 FOREIGN KEY(recipe_version_id,product_id,store_id) REFERENCES prep_inventory.recipe_versions(id,product_id,store_id),
 FOREIGN KEY(product_version_id,product_id,store_id) REFERENCES prep_inventory.product_versions(id,product_id,store_id),
 FOREIGN KEY(product_id,store_id,base_unit) REFERENCES prep_inventory.products(id,store_id,base_unit),
 FOREIGN KEY(root_id,store_id,product_id,base_unit) REFERENCES prep_inventory.batch_events(id,store_id,product_id,base_unit),
 FOREIGN KEY(predecessor_id,store_id,product_id,base_unit) REFERENCES prep_inventory.batch_events(id,store_id,product_id,base_unit),
 CHECK((kind='initial' AND predecessor_id IS NULL AND root_id=id AND revision=1)
    OR (kind IN ('replacement','void') AND predecessor_id IS NOT NULL AND revision>1)),
 CHECK(business_date=(performed_at AT TIME ZONE timezone_name)::date)
);
CREATE TABLE prep_inventory.batch_movements (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), event_id uuid NOT NULL, store_id text NOT NULL,
 ordinal integer NOT NULL CHECK(ordinal>0), side text NOT NULL CHECK(side IN ('apply','reverse')),
 kind text NOT NULL CHECK(kind IN ('raw_input','prepared_input','output')),
 recipe_version_id uuid NOT NULL, recipe_line_id uuid, raw_item_code text,
 product_id uuid, base_unit text NOT NULL, quantity numeric NOT NULL
   CHECK(quantity<>0 AND quantity NOT IN ('NaN'::numeric,'Infinity'::numeric,'-Infinity'::numeric)),
 source_batch_id uuid, reverses_movement_id uuid UNIQUE REFERENCES prep_inventory.batch_movements(id),
 UNIQUE(event_id,ordinal),
 FOREIGN KEY(event_id,store_id) REFERENCES prep_inventory.batch_events(id,store_id),
 FOREIGN KEY(recipe_line_id,recipe_version_id,store_id) REFERENCES prep_inventory.recipe_lines(id,recipe_version_id,store_id),
 FOREIGN KEY(recipe_version_id,store_id) REFERENCES prep_inventory.recipe_versions(id,store_id),
 FOREIGN KEY(store_id,raw_item_code,base_unit) REFERENCES purchasing.item_bases(store_id,item_code,base_unit),
 FOREIGN KEY(product_id,store_id,base_unit) REFERENCES prep_inventory.products(id,store_id,base_unit),
 FOREIGN KEY(source_batch_id,store_id,product_id,base_unit) REFERENCES prep_inventory.batch_events(id,store_id,product_id,base_unit),
 CHECK((kind='raw_input' AND raw_item_code IS NOT NULL AND product_id IS NULL AND source_batch_id IS NULL AND recipe_line_id IS NOT NULL)
 OR (kind='prepared_input' AND raw_item_code IS NULL AND product_id IS NOT NULL AND source_batch_id IS NOT NULL AND recipe_line_id IS NOT NULL)
 OR (kind='output' AND raw_item_code IS NULL AND product_id IS NOT NULL AND source_batch_id IS NULL AND recipe_line_id IS NULL)),
 CHECK((side='apply' AND reverses_movement_id IS NULL AND ((kind='output' AND quantity>0) OR (kind<>'output' AND quantity<0)))
 OR (side='reverse' AND reverses_movement_id IS NOT NULL AND ((kind='output' AND quantity<0) OR (kind<>'output' AND quantity>0))))
);
CREATE INDEX batch_source_allocations ON prep_inventory.batch_movements(source_batch_id);
CREATE FUNCTION prep_inventory.guard_batch_event() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE prior prep_inventory.batch_events; recipe prep_inventory.recipe_versions;
BEGIN
 -- All trusted writers, including SQL inserts, serialize allocations by store.
 PERFORM 1 FROM public.store_state WHERE store_id=NEW.store_id FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Batch requires a store coordination row'; END IF;
 SELECT * INTO recipe FROM prep_inventory.recipe_versions WHERE id=NEW.recipe_version_id;
 IF recipe.product_version_id IS DISTINCT FROM NEW.product_version_id THEN RAISE EXCEPTION 'Batch output does not match its recipe'; END IF;
 IF NEW.predecessor_id IS NOT NULL THEN
  SELECT * INTO prior FROM prep_inventory.batch_events WHERE id=NEW.predecessor_id;
  IF prior.kind='void' OR NEW.root_id<>prior.root_id OR NEW.revision<>prior.revision+1
    OR (NEW.performed_at,NEW.business_date,NEW.timezone_name,NEW.day_basis)
      IS DISTINCT FROM (prior.performed_at,prior.business_date,prior.timezone_name,prior.day_basis)
  THEN RAISE EXCEPTION 'Correction must extend a current batch at its original date'; END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER batch_event_guard BEFORE INSERT ON prep_inventory.batch_events FOR EACH ROW EXECUTE FUNCTION prep_inventory.guard_batch_event();
CREATE FUNCTION prep_inventory.guard_batch_movement() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE parent prep_inventory.batch_events;
BEGIN
 SELECT * INTO parent FROM prep_inventory.batch_events WHERE id=NEW.event_id;
 IF parent.created_xid IS DISTINCT FROM pg_current_xact_id() OR parent.recorded_at IS DISTINCT FROM transaction_timestamp()
 THEN RAISE EXCEPTION 'Batch is sealed; append a correction'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER batch_child_guard BEFORE INSERT ON prep_inventory.batch_movements FOR EACH ROW EXECUTE FUNCTION prep_inventory.guard_batch_movement();
-- Shared lot projection. Later explanation events extend lot_used, not balances.
CREATE FUNCTION prep_inventory.lot_used(source_id uuid) RETURNS numeric LANGUAGE sql STABLE AS $$
 SELECT -coalesce(sum(quantity),0) FROM prep_inventory.batch_movements WHERE source_batch_id=source_id
$$;
CREATE FUNCTION prep_inventory.lot_remaining(source_id uuid) RETURNS numeric LANGUAGE sql STABLE AS $$
 SELECT coalesce((SELECT sum(quantity) FROM prep_inventory.batch_movements WHERE event_id=source_id AND side='apply' AND kind='output'),0)
   -prep_inventory.lot_used(source_id)
$$;
CREATE FUNCTION prep_inventory.assert_lot_allocations(location_id text) RETURNS void LANGUAGE plpgsql AS $$
DECLARE source prep_inventory.batch_events; q numeric;
BEGIN
 FOR source IN SELECT * FROM prep_inventory.batch_events WHERE store_id=location_id LOOP
  q:=prep_inventory.lot_used(source.id);
  IF q<0 OR q>coalesce((SELECT sum(quantity) FROM prep_inventory.batch_movements WHERE event_id=source.id AND side='apply' AND kind='output'),0)
    OR (q>0 AND (source.kind='void' OR EXISTS(SELECT 1 FROM prep_inventory.batch_events WHERE predecessor_id=source.id)))
   THEN RAISE EXCEPTION 'Prepared source lot allocation is invalid'; END IF;
 END LOOP;
END $$;
CREATE FUNCTION prep_inventory.seal_batch_event() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE actual jsonb; line jsonb; definition prep_inventory.recipe_lines; n integer; source prep_inventory.batch_events; q numeric;
BEGIN
 IF NEW.review_snapshot->>'kind' IS DISTINCT FROM NEW.kind
   OR (NEW.review_snapshot->>'revision')::integer IS DISTINCT FROM NEW.revision
   OR (NEW.review_snapshot->>'predecessor_id')::uuid IS DISTINCT FROM NEW.predecessor_id
   OR (NEW.kind<>'initial' AND (NEW.review_snapshot->>'root_id')::uuid IS DISTINCT FROM NEW.root_id)
   OR NEW.review_snapshot->>'reason' IS DISTINCT FROM NEW.reason
   OR (NEW.review_snapshot->>'recipe_version_id')::uuid IS DISTINCT FROM NEW.recipe_version_id
   OR (NEW.review_snapshot->>'product_id')::uuid IS DISTINCT FROM NEW.product_id
   OR (NEW.review_snapshot->>'product_version_id')::uuid IS DISTINCT FROM NEW.product_version_id
   OR NEW.review_snapshot->>'base_unit' IS DISTINCT FROM NEW.base_unit
   OR (NEW.review_snapshot->>'performed_at')::timestamptz IS DISTINCT FROM NEW.performed_at
   OR (NEW.review_snapshot->>'business_date')::date IS DISTINCT FROM NEW.business_date
   OR NEW.review_snapshot->>'timezone_name' IS DISTINCT FROM NEW.timezone_name
   OR NEW.review_snapshot->'cost' IS DISTINCT FROM '{"status":"not_calculated","amount":null}'::jsonb
 THEN RAISE EXCEPTION 'Batch header differs from its reviewed facts'; END IF;
 SELECT coalesce(jsonb_agg(jsonb_build_object('side',side,'kind',kind,'recipe_version_id',recipe_version_id,
  'recipe_line_id',recipe_line_id,'raw_item_code',raw_item_code,'product_id',product_id,'base_unit',base_unit,
  'quantity',quantity::text,'source_batch_id',source_batch_id,'reverses_movement_id',reverses_movement_id) ORDER BY ordinal),'[]'::jsonb)
 INTO actual FROM prep_inventory.batch_movements WHERE event_id=NEW.id;
 IF actual IS DISTINCT FROM NEW.review_snapshot->'movements' THEN RAISE EXCEPTION 'Batch movements differ from reviewed quantities'; END IF;
 IF NEW.kind='void' THEN
  IF EXISTS(SELECT 1 FROM prep_inventory.batch_movements WHERE event_id=NEW.id AND side='apply')
    OR jsonb_array_length(NEW.review_snapshot->'inputs')<>0 THEN RAISE EXCEPTION 'Void cannot apply new quantities'; END IF;
 ELSE
  SELECT count(*) INTO n FROM prep_inventory.batch_movements WHERE event_id=NEW.id AND side='apply' AND kind='output'
    AND product_id=NEW.product_id AND base_unit=NEW.base_unit AND recipe_version_id=NEW.recipe_version_id
    AND quantity=(NEW.review_snapshot->>'usableBaseOutput')::numeric;
  IF n<>1 THEN RAISE EXCEPTION 'Batch requires one measured usable output'; END IF;
  IF jsonb_array_length(NEW.review_snapshot->'inputs')<>(SELECT count(*) FROM prep_inventory.recipe_lines WHERE recipe_version_id=NEW.recipe_version_id)
   THEN RAISE EXCEPTION 'Batch must record every recipe ingredient'; END IF;
  FOR line IN SELECT value FROM jsonb_array_elements(NEW.review_snapshot->'inputs') LOOP
   SELECT * INTO definition FROM prep_inventory.recipe_lines WHERE id=(line->>'recipe_line_id')::uuid AND recipe_version_id=NEW.recipe_version_id;
   IF NOT FOUND OR (line->>'quantity')::numeric<=0 OR (line->>'factor')::numeric<=0
     OR (line->>'base_quantity')::numeric<>(line->>'quantity')::numeric*(line->>'factor')::numeric
     OR coalesce(line->>'measurement_basis','') NOT IN ('measured','recipe_estimate')
     OR length(btrim(coalesce(line->>'evidence','')))=0
     OR (line->>'included_loss_quantity')::numeric<0 OR (line->>'included_loss_quantity')::numeric>(line->>'quantity')::numeric
     OR (line->>'includedLossBaseQuantity')::numeric IS DISTINCT FROM (line->>'included_loss_quantity')::numeric*(line->>'factor')::numeric
     OR (line->>'included_loss_quantity' IS NOT NULL AND length(btrim(coalesce(line->>'loss_evidence','')))=0)
    THEN RAISE EXCEPTION 'Invalid measured ingredient or included loss'; END IF;
   SELECT count(*) INTO n FROM prep_inventory.batch_movements m WHERE m.event_id=NEW.id AND m.side='apply'
    AND m.recipe_line_id=definition.id AND m.recipe_version_id=NEW.recipe_version_id AND m.kind=definition.source_kind||'_input'
    AND m.raw_item_code IS NOT DISTINCT FROM definition.raw_item_code AND m.base_unit=definition.base_unit
    AND m.quantity=-(line->>'base_quantity')::numeric AND m.source_batch_id IS NOT DISTINCT FROM (line->>'source_batch_id')::uuid;
   IF n<>1 THEN RAISE EXCEPTION 'Ingredient withdrawal is missing or mismatched'; END IF;
   IF definition.source_kind='prepared' THEN
    IF line->>'source_unit' IS DISTINCT FROM definition.source_unit OR (line->>'factor')::numeric IS DISTINCT FROM definition.factor
     THEN RAISE EXCEPTION 'Prepared input conversion differs from its recipe'; END IF;
    SELECT * INTO source FROM prep_inventory.batch_events WHERE id=(line->>'source_batch_id')::uuid;
    IF source.kind='void' OR source.performed_at>NEW.performed_at OR source.product_id<>(SELECT product_id FROM prep_inventory.recipe_versions WHERE id=definition.prepared_recipe_id)
     THEN RAISE EXCEPTION 'Prepared source must be the same product produced before use'; END IF;
   END IF;
  END LOOP;
  IF (SELECT count(*) FROM prep_inventory.batch_movements WHERE event_id=NEW.id AND side='apply')<>1+jsonb_array_length(NEW.review_snapshot->'inputs')
   OR (SELECT count(DISTINCT x->>'recipe_line_id') FROM jsonb_array_elements(NEW.review_snapshot->'inputs') x)<>jsonb_array_length(NEW.review_snapshot->'inputs')
   THEN RAISE EXCEPTION 'Unexpected or repeated ingredient withdrawal'; END IF;
 END IF;
 IF (SELECT count(*) FROM prep_inventory.batch_movements WHERE event_id=NEW.id AND side='reverse')<>
    (SELECT count(*) FROM prep_inventory.batch_movements WHERE event_id=NEW.predecessor_id AND side='apply')
    OR EXISTS(SELECT 1 FROM prep_inventory.batch_movements m LEFT JOIN prep_inventory.batch_movements previous_m ON previous_m.id=m.reverses_movement_id
      WHERE m.event_id=NEW.id AND m.side='reverse' AND (previous_m.id IS NULL OR previous_m.event_id IS DISTINCT FROM NEW.predecessor_id OR previous_m.side<>'apply'
       OR (m.kind,m.recipe_version_id,m.recipe_line_id,m.raw_item_code,m.product_id,m.base_unit,m.quantity,m.source_batch_id)
       IS DISTINCT FROM (previous_m.kind,previous_m.recipe_version_id,previous_m.recipe_line_id,previous_m.raw_item_code,previous_m.product_id,previous_m.base_unit,-previous_m.quantity,previous_m.source_batch_id)))
  THEN RAISE EXCEPTION 'Correction must reverse exactly its predecessor applied quantities'; END IF;
 PERFORM prep_inventory.assert_lot_allocations(NEW.store_id);
 RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER batch_seal AFTER INSERT ON prep_inventory.batch_events DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION prep_inventory.seal_batch_event();
CREATE TRIGGER batch_policy_immutable BEFORE UPDATE OR DELETE ON prep_inventory.batch_policies FOR EACH ROW EXECUTE FUNCTION purchasing.reject_fact_change();
CREATE TRIGGER batch_event_immutable BEFORE UPDATE OR DELETE ON prep_inventory.batch_events FOR EACH ROW EXECUTE FUNCTION purchasing.reject_fact_change();
CREATE TRIGGER batch_movement_immutable BEFORE UPDATE OR DELETE ON prep_inventory.batch_movements FOR EACH ROW EXECUTE FUNCTION purchasing.reject_fact_change();
REVOKE ALL ON ALL TABLES IN SCHEMA prep_inventory FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA prep_inventory FROM PUBLIC;
DO $$ DECLARE role_name text; BEGIN
 FOREACH role_name IN ARRAY ARRAY['anon','authenticated'] LOOP
  IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=role_name) THEN
   EXECUTE format('REVOKE ALL ON SCHEMA prep_inventory FROM %I',role_name);
   EXECUTE format('REVOKE ALL ON ALL TABLES IN SCHEMA prep_inventory FROM %I',role_name);
   EXECUTE format('REVOKE ALL ON ALL FUNCTIONS IN SCHEMA prep_inventory FROM %I',role_name);
  END IF;
 END LOOP;
END $$;
COMMIT;
