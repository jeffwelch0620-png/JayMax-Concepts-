-- Reviewed commissioning sources: no production, raw withdrawal or Track 1 value.
BEGIN;
CREATE TABLE prep_inventory.opening_decisions (
 id uuid PRIMARY KEY,store_id text NOT NULL REFERENCES public.stores(id),root_id uuid NOT NULL,predecessor_id uuid UNIQUE,
 revision integer NOT NULL CHECK(revision>0),kind text NOT NULL CHECK(kind IN ('initial','void')),count_id uuid NOT NULL,
 reason text NOT NULL CHECK(length(btrim(reason))>0),review_snapshot jsonb NOT NULL,review_hash bytea NOT NULL CHECK(octet_length(review_hash)=32),
 recorded_by text NOT NULL,recorded_at timestamptz NOT NULL DEFAULT now(),created_xid xid8 NOT NULL DEFAULT pg_current_xact_id(),
 request_key uuid NOT NULL UNIQUE,request_fingerprint bytea NOT NULL CHECK(octet_length(request_fingerprint)=32),
 UNIQUE(id,store_id),UNIQUE(root_id,revision),FOREIGN KEY(root_id,store_id) REFERENCES prep_inventory.opening_decisions(id,store_id),
 FOREIGN KEY(predecessor_id,store_id) REFERENCES prep_inventory.opening_decisions(id,store_id),
 FOREIGN KEY(count_id,store_id) REFERENCES prep_inventory.observations(id,store_id),
 CHECK((kind='initial' AND root_id=id AND predecessor_id IS NULL AND revision=1) OR (kind='void' AND predecessor_id IS NOT NULL AND revision=2))
);
ALTER TABLE prep_inventory.batch_events ALTER COLUMN recipe_version_id DROP NOT NULL;
ALTER TABLE prep_inventory.batch_movements ALTER COLUMN recipe_version_id DROP NOT NULL;
ALTER TABLE prep_inventory.batch_events ADD COLUMN source_kind text NOT NULL DEFAULT 'production';
ALTER TABLE prep_inventory.batch_events ADD COLUMN opening_decision_id uuid;
ALTER TABLE prep_inventory.batch_events ADD COLUMN count_line_id uuid REFERENCES prep_inventory.count_observations(id);
ALTER TABLE prep_inventory.batch_events ADD FOREIGN KEY(opening_decision_id,store_id) REFERENCES prep_inventory.opening_decisions(id,store_id);
ALTER TABLE prep_inventory.batch_events ADD CONSTRAINT source_kind_fields CHECK(
 (source_kind='production' AND recipe_version_id IS NOT NULL AND opening_decision_id IS NULL AND count_line_id IS NULL)
 OR (source_kind='opening' AND recipe_version_id IS NULL AND opening_decision_id IS NOT NULL AND count_line_id IS NOT NULL));
CREATE UNIQUE INDEX opening_product_once ON prep_inventory.batch_events(opening_decision_id,product_id) WHERE source_kind='opening';
CREATE FUNCTION prep_inventory.opening_source_valid(decision_id uuid) RETURNS boolean LANGUAGE sql STABLE AS $$
 SELECT EXISTS(SELECT 1 FROM prep_inventory.opening_decisions d JOIN prep_inventory.observations c ON c.id=d.count_id
 WHERE d.id=decision_id AND d.kind='initial' AND c.purpose='count' AND c.kind<>'void'
 AND NOT EXISTS(SELECT 1 FROM prep_inventory.opening_decisions n WHERE n.predecessor_id=d.id)
 AND NOT EXISTS(SELECT 1 FROM prep_inventory.observations n WHERE n.predecessor_id=c.id))
$$;
CREATE FUNCTION prep_inventory.guard_opening_decision() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE counted prep_inventory.observations; prior prep_inventory.opening_decisions;
BEGIN
 PERFORM 1 FROM public.store_state WHERE store_id=NEW.store_id FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Opening requires store coordination'; END IF;
 SELECT * INTO counted FROM prep_inventory.observations WHERE id=NEW.count_id;
 IF counted.purpose IS DISTINCT FROM 'count' OR counted.store_id IS DISTINCT FROM NEW.store_id THEN RAISE EXCEPTION 'Opening requires same-store prep count'; END IF;
 IF NEW.kind='initial' THEN
  IF counted.kind='void' OR EXISTS(SELECT 1 FROM prep_inventory.observations WHERE predecessor_id=counted.id)
   OR EXISTS(SELECT 1 FROM prep_inventory.opening_decisions d WHERE store_id=NEW.store_id AND kind='initial' AND NOT EXISTS(SELECT 1 FROM prep_inventory.opening_decisions n WHERE n.predecessor_id=d.id))
   OR EXISTS(SELECT 1 FROM prep_inventory.batch_events WHERE store_id=NEW.store_id AND source_kind='production')
   OR EXISTS(SELECT 1 FROM prep_inventory.observations WHERE store_id=NEW.store_id AND purpose='waste')
   THEN RAISE EXCEPTION 'Opening must be current and before recorded activity, with no active opening'; END IF;
  IF counted.review_snapshot->'scope' IS DISTINCT FROM (SELECT coalesce(jsonb_agg(id::text ORDER BY id::text),'[]'::jsonb) FROM prep_inventory.products WHERE store_id=NEW.store_id)
   THEN RAISE EXCEPTION 'Opening must cover the current full prepared scope'; END IF;
 ELSE
  SELECT * INTO prior FROM prep_inventory.opening_decisions WHERE id=NEW.predecessor_id;
  IF prior.kind<>'initial' OR NEW.root_id<>prior.root_id OR NEW.count_id<>prior.count_id THEN RAISE EXCEPTION 'Void must extend original opening decision'; END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER opening_decision_guard BEFORE INSERT ON prep_inventory.opening_decisions FOR EACH ROW EXECUTE FUNCTION prep_inventory.guard_opening_decision();
CREATE FUNCTION prep_inventory.seal_opening_decision() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE expected jsonb; actual jsonb; counted prep_inventory.observations;
BEGIN
 SELECT * INTO counted FROM prep_inventory.observations WHERE id=NEW.count_id;
 IF NEW.review_snapshot->>'kind' IS DISTINCT FROM NEW.kind OR (NEW.review_snapshot->>'revision')::integer IS DISTINCT FROM NEW.revision
 OR (NEW.review_snapshot->>'predecessor_id')::uuid IS DISTINCT FROM NEW.predecessor_id
 OR (NEW.kind='void' AND (NEW.review_snapshot->>'root_id')::uuid IS DISTINCT FROM NEW.root_id)
 OR NEW.review_snapshot->>'reason' IS DISTINCT FROM NEW.reason
 OR (NEW.review_snapshot->'count'->>'id')::uuid IS DISTINCT FROM NEW.count_id
 OR NEW.review_snapshot->'count'->'review_snapshot' IS DISTINCT FROM counted.review_snapshot
 OR NEW.review_snapshot->'before_activity_confirmed' IS DISTINCT FROM 'true'::jsonb
 OR NEW.review_snapshot->'cost' IS DISTINCT FROM '{"status":"not_calculated","amount":null}'::jsonb
 THEN RAISE EXCEPTION 'Opening differs from reviewed physical facts'; END IF;
 IF NEW.kind='initial' THEN
  SELECT coalesce(jsonb_agg(jsonb_build_object('product_id',product_id,'product_version_id',product_version_id,'base_unit',base_unit,
   'count_line_id',id,'quantity',base_quantity::text,'predecessor_id',NULL,'root_id',NULL,'revision',1) ORDER BY product_id::text),'[]'::jsonb)
   INTO expected FROM prep_inventory.count_observations WHERE event_id=NEW.count_id AND base_quantity>0;
 ELSE
  SELECT coalesce(jsonb_agg(jsonb_build_object('product_id',product_id,'product_version_id',product_version_id,'base_unit',base_unit,
   'count_line_id',count_line_id,'quantity','0','predecessor_id',id,'root_id',root_id,'revision',revision+1) ORDER BY product_id::text),'[]'::jsonb)
   INTO expected FROM prep_inventory.batch_events WHERE opening_decision_id=NEW.predecessor_id;
 END IF;
 IF NEW.review_snapshot->'lots' IS DISTINCT FROM expected THEN RAISE EXCEPTION 'Opening requires every positive count line exactly'; END IF;
 SELECT coalesce(jsonb_agg(jsonb_build_object('product_id',product_id,'product_version_id',product_version_id,'base_unit',base_unit,
  'count_line_id',count_line_id,'quantity',CASE WHEN kind='void' THEN '0' ELSE review_snapshot->>'usableBaseOutput' END,
  'predecessor_id',predecessor_id,'root_id',CASE WHEN kind='initial' THEN NULL ELSE root_id END,'revision',revision) ORDER BY product_id::text),'[]'::jsonb)
  INTO actual FROM prep_inventory.batch_events WHERE opening_decision_id=NEW.id;
 IF actual IS DISTINCT FROM expected THEN RAISE EXCEPTION 'Opening source lots are incomplete or differ from count'; END IF;
 PERFORM prep_inventory.assert_lot_allocations(NEW.store_id);
 RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER opening_seal AFTER INSERT ON prep_inventory.opening_decisions DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION prep_inventory.seal_opening_decision();
CREATE TRIGGER opening_immutable BEFORE UPDATE OR DELETE ON prep_inventory.opening_decisions FOR EACH ROW EXECUTE FUNCTION purchasing.reject_fact_change();
CREATE OR REPLACE FUNCTION prep_inventory.guard_batch_event() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE prior prep_inventory.batch_events; recipe prep_inventory.recipe_versions; decision prep_inventory.opening_decisions; counted prep_inventory.count_observations;
BEGIN
 -- All trusted writers, including SQL inserts, serialize allocations by store.
 PERFORM 1 FROM public.store_state WHERE store_id=NEW.store_id FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Batch requires a store coordination row'; END IF;
 IF NEW.source_kind='opening' THEN
  SELECT * INTO decision FROM prep_inventory.opening_decisions WHERE id=NEW.opening_decision_id;
  SELECT * INTO counted FROM prep_inventory.count_observations WHERE id=NEW.count_line_id;
  IF decision.created_xid IS DISTINCT FROM pg_current_xact_id() OR decision.recorded_at IS DISTINCT FROM transaction_timestamp()
   OR (counted.event_id,counted.store_id,counted.product_id,counted.product_version_id,counted.base_unit)
     IS DISTINCT FROM (decision.count_id,NEW.store_id,NEW.product_id,NEW.product_version_id,NEW.base_unit)
   OR NEW.kind IS DISTINCT FROM decision.kind
   OR (NEW.performed_at,NEW.business_date,NEW.timezone_name) IS DISTINCT FROM
     (SELECT ROW(performed_at,business_date,timezone_name) FROM prep_inventory.observations WHERE id=decision.count_id)
   THEN RAISE EXCEPTION 'Opening source must match its creating reviewed count decision'; END IF;
 ELSE
 IF EXISTS(SELECT 1 FROM prep_inventory.opening_decisions d JOIN prep_inventory.observations c ON c.id=d.count_id
  WHERE d.store_id=NEW.store_id AND d.kind='initial' AND NOT EXISTS(SELECT 1 FROM prep_inventory.opening_decisions n WHERE n.predecessor_id=d.id)
  AND (NEW.performed_at<c.performed_at OR NOT prep_inventory.opening_source_valid(d.id)))
  THEN RAISE EXCEPTION 'Production must follow a current opening source'; END IF;
 SELECT * INTO recipe FROM prep_inventory.recipe_versions WHERE id=NEW.recipe_version_id;
 IF recipe.product_version_id IS DISTINCT FROM NEW.product_version_id THEN RAISE EXCEPTION 'Batch output does not match its recipe'; END IF;
 END IF;
 IF NEW.predecessor_id IS NOT NULL THEN
  SELECT * INTO prior FROM prep_inventory.batch_events WHERE id=NEW.predecessor_id;
  IF prior.source_kind IS DISTINCT FROM NEW.source_kind OR prior.kind='void' OR NEW.root_id<>prior.root_id OR NEW.revision<>prior.revision+1
    OR (NEW.performed_at,NEW.business_date,NEW.timezone_name,NEW.day_basis)
      IS DISTINCT FROM (prior.performed_at,prior.business_date,prior.timezone_name,prior.day_basis)
  THEN RAISE EXCEPTION 'Correction must extend a current batch at its original date'; END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE OR REPLACE FUNCTION prep_inventory.assert_lot_allocations(location_id text) RETURNS void LANGUAGE plpgsql AS $$
DECLARE source prep_inventory.batch_events; q numeric;
BEGIN
 FOR source IN SELECT * FROM prep_inventory.batch_events WHERE store_id=location_id LOOP
  q:=prep_inventory.lot_used(source.id);
  IF q<0 OR q>coalesce((SELECT sum(quantity) FROM prep_inventory.batch_movements WHERE event_id=source.id AND side='apply' AND kind='output'),0)
    OR (q>0 AND source.source_kind='opening' AND NOT prep_inventory.opening_source_valid(source.opening_decision_id))
    OR (q>0 AND (source.kind='void' OR EXISTS(SELECT 1 FROM prep_inventory.batch_events WHERE predecessor_id=source.id)))
   THEN RAISE EXCEPTION 'Prepared source lot allocation is invalid'; END IF;
 END LOOP;
END $$;
CREATE OR REPLACE FUNCTION prep_inventory.seal_batch_event() RETURNS trigger LANGUAGE plpgsql AS $$
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
 IF NEW.source_kind='opening' THEN
  IF NEW.review_snapshot->>'source_kind' IS DISTINCT FROM 'opening'
   OR (NEW.review_snapshot->>'opening_decision_id')::uuid IS DISTINCT FROM NEW.opening_decision_id
   OR (NEW.review_snapshot->>'count_line_id')::uuid IS DISTINCT FROM NEW.count_line_id
   OR jsonb_array_length(NEW.review_snapshot->'inputs')<>0
   OR EXISTS(SELECT 1 FROM prep_inventory.batch_movements WHERE event_id=NEW.id AND kind<>'output')
   THEN RAISE EXCEPTION 'Opening stock is not production or ingredient use'; END IF;
  IF NEW.kind='initial' THEN
   IF (SELECT count(*) FROM prep_inventory.batch_movements WHERE event_id=NEW.id AND side='apply')<>1
    OR NOT EXISTS(SELECT 1 FROM prep_inventory.batch_movements m JOIN prep_inventory.count_observations c ON c.id=NEW.count_line_id
      WHERE m.event_id=NEW.id AND m.side='apply' AND m.recipe_version_id IS NULL AND m.quantity=c.base_quantity AND m.quantity>0
      AND (m.product_id,m.base_unit)=(NEW.product_id,NEW.base_unit)
      AND m.quantity=(NEW.review_snapshot->>'usableBaseOutput')::numeric)
    THEN RAISE EXCEPTION 'Opening quantity must equal its positive physical count line'; END IF;
  ELSIF NEW.kind='void' THEN
   IF EXISTS(SELECT 1 FROM prep_inventory.batch_movements WHERE event_id=NEW.id AND side='apply')
    THEN RAISE EXCEPTION 'Opening void cannot apply quantities'; END IF;
  ELSE RAISE EXCEPTION 'Opening correction requires reviewed void and unused re-establishment'; END IF;
 ELSIF NEW.kind='void' THEN
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
CREATE FUNCTION prep_inventory.guard_count_opening_dependencies() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.purpose='count' THEN PERFORM prep_inventory.assert_lot_allocations(NEW.store_id); END IF;
 IF NEW.purpose='waste' AND NEW.kind<>'void' AND EXISTS(SELECT 1 FROM prep_inventory.opening_decisions d JOIN prep_inventory.observations c ON c.id=d.count_id
  WHERE d.store_id=NEW.store_id AND d.kind='initial' AND NOT EXISTS(SELECT 1 FROM prep_inventory.opening_decisions n WHERE n.predecessor_id=d.id)
  AND (NEW.performed_at<c.performed_at OR NOT prep_inventory.opening_source_valid(d.id)))
  THEN RAISE EXCEPTION 'Waste must follow a current opening source'; END IF;
 RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER count_opening_dependencies AFTER INSERT ON prep_inventory.observations DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION prep_inventory.guard_count_opening_dependencies();
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
