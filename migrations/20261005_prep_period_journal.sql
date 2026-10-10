-- Quantity-only analytical snapshots. Physical counts and lot balances unchanged.
BEGIN;
CREATE TABLE prep_inventory.period_closures (
 id uuid PRIMARY KEY,store_id text NOT NULL REFERENCES public.stores(id),ordinal bigint NOT NULL CHECK(ordinal>0),previous_id uuid,
 opening_count_id uuid NOT NULL,closing_count_id uuid NOT NULL,
 opening_cutoff text NOT NULL CHECK(opening_cutoff IN ('before_all','after_all')),
 closing_cutoff text NOT NULL CHECK(closing_cutoff IN ('before_all','after_all')),
 reason text NOT NULL CHECK(length(btrim(reason))>0),review_snapshot jsonb NOT NULL,
 review_hash bytea NOT NULL CHECK(octet_length(review_hash)=32),source_digest bytea NOT NULL CHECK(octet_length(source_digest)=32),
 recorded_by text NOT NULL,recorded_at timestamptz NOT NULL DEFAULT now(),request_key uuid NOT NULL UNIQUE,
 request_fingerprint bytea NOT NULL CHECK(octet_length(request_fingerprint)=32),UNIQUE(store_id,ordinal),UNIQUE(id,store_id),
 FOREIGN KEY(previous_id,store_id) REFERENCES prep_inventory.period_closures(id,store_id),
 FOREIGN KEY(opening_count_id,store_id) REFERENCES prep_inventory.observations(id,store_id),
 FOREIGN KEY(closing_count_id,store_id) REFERENCES prep_inventory.observations(id,store_id)
);
CREATE TABLE prep_inventory.period_reopenings (
 id uuid PRIMARY KEY,store_id text NOT NULL REFERENCES public.stores(id),closure_ids uuid[] NOT NULL CHECK(cardinality(closure_ids)>0),
 reason text NOT NULL CHECK(length(btrim(reason))>0),review_snapshot jsonb NOT NULL,
 review_hash bytea NOT NULL CHECK(octet_length(review_hash)=32),recorded_by text NOT NULL,recorded_at timestamptz NOT NULL DEFAULT now(),
 request_key uuid NOT NULL UNIQUE,request_fingerprint bytea NOT NULL CHECK(octet_length(request_fingerprint)=32)
);
CREATE FUNCTION prep_inventory.period_sources_current(c prep_inventory.period_closures) RETURNS boolean LANGUAGE plpgsql STABLE AS $$
DECLARE a prep_inventory.observations; b prep_inventory.observations; expected jsonb; supplied jsonb; z jsonb;
BEGIN
 SELECT * INTO a FROM prep_inventory.observations WHERE id=c.opening_count_id;
 SELECT * INTO b FROM prep_inventory.observations WHERE id=c.closing_count_id;
 IF a.purpose IS DISTINCT FROM 'count' OR b.purpose IS DISTINCT FROM 'count' OR a.kind='void' OR b.kind='void'
 OR EXISTS(SELECT 1 FROM prep_inventory.observations WHERE predecessor_id IN (a.id,b.id))
 OR c.review_snapshot->'report'->'opening'->>'review_hash' IS DISTINCT FROM encode(a.review_hash,'hex')
 OR c.review_snapshot->'report'->'closing'->>'review_hash' IS DISTINCT FROM encode(b.review_hash,'hex') THEN RETURN false; END IF;
 SELECT coalesce(jsonb_agg(jsonb_build_object('id',id,'hash',encode(review_hash,'hex'),'journal',journal) ORDER BY journal,id::text),'[]'::jsonb) INTO expected
 FROM (SELECT id,review_hash,'batch_events' AS journal FROM prep_inventory.batch_events WHERE store_id=c.store_id AND source_kind='production' AND performed_at BETWEEN a.performed_at AND b.performed_at
 UNION ALL SELECT id,review_hash,'observations' FROM prep_inventory.observations WHERE store_id=c.store_id AND purpose='waste' AND performed_at BETWEEN a.performed_at AND b.performed_at) h;
 SELECT coalesce(jsonb_agg(jsonb_build_object('id',x->>'id','hash',x->>'review_hash','journal',x->>'journal') ORDER BY x->>'journal',x->>'id'),'[]'::jsonb)
 INTO supplied FROM jsonb_array_elements(c.review_snapshot->'sourceHistory') x;
 IF expected IS DISTINCT FROM supplied THEN RETURN false; END IF;
 FOR z IN SELECT x FROM jsonb_array_elements(c.review_snapshot->'submission'->'zero_additions') x LOOP
  IF EXISTS(SELECT 1 FROM prep_inventory.batch_movements m JOIN prep_inventory.batch_events e ON e.id=m.event_id WHERE e.store_id=c.store_id
   AND m.product_id=(z->>'product_id')::uuid AND (e.performed_at<a.performed_at OR (e.performed_at=a.performed_at AND c.opening_cutoff='after_all')))
  OR EXISTS(SELECT 1 FROM prep_inventory.waste_movements m JOIN prep_inventory.observations e ON e.id=m.event_id WHERE e.store_id=c.store_id
   AND m.product_id=(z->>'product_id')::uuid AND (e.performed_at<a.performed_at OR (e.performed_at=a.performed_at AND c.opening_cutoff='after_all')))
  OR EXISTS(SELECT 1 FROM prep_inventory.count_observations m JOIN prep_inventory.observations e ON e.id=m.event_id WHERE e.store_id=c.store_id
   AND m.product_id=(z->>'product_id')::uuid AND m.base_quantity<>0 AND e.performed_at<a.performed_at) THEN RETURN false; END IF;
 END LOOP;
 RETURN true;
END $$;
CREATE FUNCTION prep_inventory.period_movements(c prep_inventory.period_closures)
RETURNS TABLE(product_id uuid,raw_item_code text,base_unit text,kind text,basis text,quantity numeric,included_trim numeric) LANGUAGE sql STABLE AS $$
 WITH bounds AS (SELECT a.performed_at AS start_at,b.performed_at AS end_at FROM prep_inventory.observations a,prep_inventory.observations b WHERE a.id=c.opening_count_id AND b.id=c.closing_count_id),
 selected AS (SELECT e.* FROM prep_inventory.batch_events e,bounds WHERE e.store_id=c.store_id AND e.source_kind='production' AND e.kind<>'void'
 AND NOT EXISTS(SELECT 1 FROM prep_inventory.batch_events n WHERE n.predecessor_id=e.id)
 AND (e.performed_at>start_at OR (e.performed_at=start_at AND c.opening_cutoff='before_all'))
 AND (e.performed_at<end_at OR (e.performed_at=end_at AND c.closing_cutoff='after_all')))
 SELECT m.product_id,m.raw_item_code,m.base_unit,m.kind,i.x->>'measurement_basis',m.quantity,(i.x->>'includedLossBaseQuantity')::numeric
 FROM selected e JOIN prep_inventory.batch_movements m ON m.event_id=e.id AND m.side='apply'
 LEFT JOIN LATERAL (SELECT x FROM jsonb_array_elements(e.review_snapshot->'inputs') x WHERE (x->>'recipe_line_id')::uuid=m.recipe_line_id) i ON true
 UNION ALL SELECT m.product_id,m.raw_item_code,m.base_unit,'waste','measured',m.quantity,NULL::numeric
 FROM prep_inventory.observations e JOIN prep_inventory.waste_movements m ON m.event_id=e.id AND m.side='apply',bounds
 WHERE e.store_id=c.store_id AND e.purpose='waste' AND e.kind<>'void' AND NOT EXISTS(SELECT 1 FROM prep_inventory.observations n WHERE n.predecessor_id=e.id)
 AND (e.performed_at>start_at OR (e.performed_at=start_at AND c.opening_cutoff='before_all'))
 AND (e.performed_at<end_at OR (e.performed_at=end_at AND c.closing_cutoff='after_all'))
$$;
CREATE FUNCTION prep_inventory.guard_period_closure() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE last_row prep_inventory.period_closures; a prep_inventory.observations; b prep_inventory.observations;
 p jsonb; l jsonb; old_line jsonb; added jsonb; expected_scope jsonb; produced numeric; measured numeric; estimated numeric; wasted numeric; trimmed numeric;
BEGIN
 PERFORM 1 FROM public.store_state WHERE store_id=NEW.store_id FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Analytical period requires store coordination'; END IF;
 SELECT * INTO last_row FROM prep_inventory.period_closures c WHERE c.store_id=NEW.store_id AND NOT EXISTS(
 SELECT 1 FROM prep_inventory.period_reopenings r WHERE r.store_id=c.store_id AND c.id=ANY(r.closure_ids)) ORDER BY ordinal DESC LIMIT 1;
 IF NEW.previous_id IS DISTINCT FROM last_row.id OR (last_row.id IS NOT NULL AND (NEW.opening_count_id,NEW.opening_cutoff) IS DISTINCT FROM (last_row.closing_count_id,last_row.closing_cutoff))
 OR NEW.ordinal<>(SELECT coalesce(max(ordinal),0)+1 FROM prep_inventory.period_closures WHERE store_id=NEW.store_id)
 THEN RAISE EXCEPTION 'Analytical chain changed or boundary is discontinuous'; END IF;
 IF EXISTS(SELECT 1 FROM prep_inventory.period_closures c WHERE c.store_id=NEW.store_id AND NOT EXISTS(
 SELECT 1 FROM prep_inventory.period_reopenings r WHERE r.store_id=c.store_id AND c.id=ANY(r.closure_ids)) AND NOT prep_inventory.period_sources_current(c))
 THEN RAISE EXCEPTION 'Reopen stale analytical periods first'; END IF;
 SELECT * INTO a FROM prep_inventory.observations WHERE id=NEW.opening_count_id;
 SELECT * INTO b FROM prep_inventory.observations WHERE id=NEW.closing_count_id;
 IF a.performed_at>=b.performed_at OR a.timezone_name<>b.timezone_name OR NOT prep_inventory.period_sources_current(NEW)
 THEN RAISE EXCEPTION 'Analytical sources changed or invalid boundaries'; END IF;
 p=NEW.review_snapshot;
 IF p->>'store_id' IS DISTINCT FROM NEW.store_id OR (p->>'ordinal')::bigint IS DISTINCT FROM NEW.ordinal
 OR (p->>'previous_id')::uuid IS DISTINCT FROM NEW.previous_id OR p->'submission'->>'reason' IS DISTINCT FROM NEW.reason
 OR p->'submission'->'period'->>'opening_count_id' IS DISTINCT FROM NEW.opening_count_id::text
 OR p->'submission'->'period'->>'closing_count_id' IS DISTINCT FROM NEW.closing_count_id::text
 OR p->'submission'->'period'->>'opening_cutoff' IS DISTINCT FROM NEW.opening_cutoff
 OR p->'submission'->'period'->>'closing_cutoff' IS DISTINCT FROM NEW.closing_cutoff
 OR p->'submission'->'period'->'cutoffs_confirmed' IS DISTINCT FROM 'true'::jsonb
 OR p->>'sourceDigest' IS DISTINCT FROM encode(NEW.source_digest,'hex')
 OR p->'report'->'track1Writeback' IS DISTINCT FROM 'false'::jsonb
 OR p->'report'->'coverage'->'finalVarianceAvailable' IS DISTINCT FROM 'false'::jsonb
 OR p->'report'->'cost' IS DISTINCT FROM '{"status":"not_calculated","amount":null}'::jsonb
 OR p->'report'->'opening'->>'id' IS DISTINCT FROM a.id::text OR p->'report'->'closing'->>'id' IS DISTINCT FROM b.id::text
 OR p->'report'->'request' IS DISTINCT FROM p->'submission'->'period'
 OR p->'report'->'scopeHandoff'->'physicalOpeningScope' IS DISTINCT FROM a.review_snapshot->'scope'
 OR p->'report'->'scopeHandoff'->'periodScope' IS DISTINCT FROM b.review_snapshot->'scope'
 OR p->'report'->'scopeHandoff'->'createsStockSources' IS DISTINCT FROM 'false'::jsonb
 THEN RAISE EXCEPTION 'Analytical snapshot differs from reviewed sources'; END IF;
 IF EXISTS(SELECT 1 FROM jsonb_array_elements_text(a.review_snapshot->'scope') x WHERE NOT (b.review_snapshot->'scope' ? x))
 THEN RAISE EXCEPTION 'Scope removals need retirement workflow'; END IF;
 SELECT coalesce(jsonb_agg(x ORDER BY x),'[]'::jsonb) INTO expected_scope FROM jsonb_array_elements_text(b.review_snapshot->'scope') x WHERE NOT (a.review_snapshot->'scope' ? x);
 SELECT coalesce(jsonb_agg(x->>'product_id' ORDER BY x->>'product_id'),'[]'::jsonb) INTO added FROM jsonb_array_elements(p->'submission'->'zero_additions') x
 WHERE x->'zero_at_opening_confirmed'='true'::jsonb AND length(btrim(x->>'evidence'))>0;
 IF added IS DISTINCT FROM expected_scope OR jsonb_array_length(p->'submission'->'zero_additions')<>jsonb_array_length(expected_scope)
 OR jsonb_array_length(p->'report'->'prepared')<>jsonb_array_length(b.review_snapshot->'lines') THEN RAISE EXCEPTION 'Missing or duplicate zero additions/count rows'; END IF;
 FOR l IN SELECT x FROM jsonb_array_elements(b.review_snapshot->'lines') x LOOP
  SELECT x INTO old_line FROM jsonb_array_elements(a.review_snapshot->'lines') x WHERE x->>'product_id'=l->>'product_id';
  SELECT x INTO added FROM jsonb_array_elements(p->'report'->'prepared') x WHERE x->>'product_id'=l->>'product_id';
  IF added IS NULL OR added->>'base_unit' IS DISTINCT FROM l->>'base_unit'
  OR (added->>'closingQuantity')::numeric IS DISTINCT FROM (l->>'base_quantity')::numeric
  OR (added->>'openingQuantity')::numeric IS DISTINCT FROM coalesce((old_line->>'base_quantity')::numeric,0)
  OR (old_line IS NOT NULL AND old_line->>'base_unit' IS DISTINCT FROM l->>'base_unit')
  OR added->'expectedClosingQuantity' IS DISTINCT FROM 'null'::jsonb OR added->'unexplainedVariance' IS DISTINCT FROM 'null'::jsonb
  THEN RAISE EXCEPTION 'Analytical quantities differ from physical anchors/zero handoff'; END IF;
  SELECT coalesce(sum(quantity) FILTER(WHERE kind='output'),0),-coalesce(sum(quantity) FILTER(WHERE kind='prepared_input' AND basis='measured'),0),
   -coalesce(sum(quantity) FILTER(WHERE kind='prepared_input' AND basis='recipe_estimate'),0),-coalesce(sum(quantity) FILTER(WHERE kind='waste'),0)
   INTO produced,measured,estimated,wasted FROM prep_inventory.period_movements(NEW) WHERE product_id=(l->>'product_id')::uuid;
  IF (added->>'recordedProduction')::numeric IS DISTINCT FROM produced OR (added->>'recordedNestedUseMeasured')::numeric IS DISTINCT FROM measured
   OR (added->>'recordedNestedUseEstimated')::numeric IS DISTINCT FROM estimated OR (added->>'recordedWaste')::numeric IS DISTINCT FROM wasted
   OR (added->>'observedDepletion')::numeric IS DISTINCT FROM (added->>'openingQuantity')::numeric+produced-(added->>'closingQuantity')::numeric
   OR (added->>'serviceUseOrUnrecordedLoss')::numeric IS DISTINCT FROM (added->>'openingQuantity')::numeric+produced-(added->>'closingQuantity')::numeric-measured-estimated-wasted
   OR (added->>'stockBeforeUnrecordedServiceUse')::numeric IS DISTINCT FROM (added->>'openingQuantity')::numeric+produced-measured-estimated-wasted
   THEN RAISE EXCEPTION 'Analytical preparation totals differ from effective movements'; END IF;
 END LOOP;
 SELECT coalesce(jsonb_agg(jsonb_build_object('raw_item_code',raw_item_code,'base_unit',base_unit) ORDER BY raw_item_code,base_unit),'[]'::jsonb) INTO expected_scope
 FROM (SELECT DISTINCT raw_item_code,base_unit FROM prep_inventory.period_movements(NEW) WHERE raw_item_code IS NOT NULL) q;
 SELECT coalesce(jsonb_agg(jsonb_build_object('raw_item_code',x->>'raw_item_code','base_unit',x->>'base_unit') ORDER BY x->>'raw_item_code',x->>'base_unit'),'[]'::jsonb)
 INTO added FROM jsonb_array_elements(p->'report'->'rawExplanations') x;
 IF expected_scope IS DISTINCT FROM added OR EXISTS(SELECT 1 FROM prep_inventory.period_movements(NEW) m WHERE m.product_id IS NOT NULL AND NOT(b.review_snapshot->'scope' ? m.product_id::text))
 OR jsonb_array_length(p->'report'->'rawExplanations')<>(SELECT count(DISTINCT raw_item_code) FROM prep_inventory.period_movements(NEW) WHERE raw_item_code IS NOT NULL)
 THEN RAISE EXCEPTION 'Analytical activity outside counted scope or missing raw explanation'; END IF;
 FOR l IN SELECT x FROM jsonb_array_elements(p->'report'->'rawExplanations') x LOOP
  SELECT -coalesce(sum(quantity) FILTER(WHERE kind='raw_input' AND basis='measured'),0),-coalesce(sum(quantity) FILTER(WHERE kind='raw_input' AND basis='recipe_estimate'),0),
   -coalesce(sum(quantity) FILTER(WHERE kind='waste'),0),coalesce(sum(included_trim),0) INTO measured,estimated,wasted,trimmed
   FROM prep_inventory.period_movements(NEW) WHERE raw_item_code=l->>'raw_item_code' AND base_unit=l->>'base_unit';
  IF (l->>'recordedGrossPrepUseMeasured')::numeric IS DISTINCT FROM measured OR (l->>'recordedGrossPrepUseEstimated')::numeric IS DISTINCT FROM estimated
   OR (l->>'recordedStandaloneRawWaste')::numeric IS DISTINCT FROM wasted OR (l->>'recordedRawExplanation')::numeric IS DISTINCT FROM measured+estimated+wasted
   OR (l->>'annotatedIncludedTrim')::numeric IS DISTINCT FROM trimmed OR l->'trimIsAlreadyInGrossInput' IS DISTINCT FROM 'true'::jsonb
   OR (l->>'unannotatedInputs')::bigint IS DISTINCT FROM (SELECT count(*) FROM prep_inventory.period_movements(NEW) WHERE raw_item_code=l->>'raw_item_code' AND kind='raw_input' AND included_trim IS NULL)
   THEN RAISE EXCEPTION 'Analytical raw explanation differs from effective gross inputs'; END IF;
 END LOOP;
 -- Zero evidence is retained independently of the physical opening count.
 FOR l IN SELECT x FROM jsonb_array_elements(p->'submission'->'zero_additions') x LOOP
  SELECT x INTO added FROM jsonb_array_elements(p->'report'->'scopeHandoff'->'zeroAdditions') x WHERE x->>'product_id'=l->>'product_id';
  IF added->>'evidence' IS DISTINCT FROM l->>'evidence' OR added->'zero_at_opening_confirmed' IS DISTINCT FROM 'true'::jsonb OR (added->>'base_quantity')::numeric IS DISTINCT FROM 0
  OR EXISTS(SELECT 1 FROM prep_inventory.batch_movements m JOIN prep_inventory.batch_events e ON e.id=m.event_id WHERE e.store_id=NEW.store_id
    AND m.product_id=(l->>'product_id')::uuid AND (e.performed_at<a.performed_at OR (e.performed_at=a.performed_at AND NEW.opening_cutoff='after_all')))
  OR EXISTS(SELECT 1 FROM prep_inventory.waste_movements m JOIN prep_inventory.observations e ON e.id=m.event_id WHERE e.store_id=NEW.store_id
    AND m.product_id=(l->>'product_id')::uuid AND (e.performed_at<a.performed_at OR (e.performed_at=a.performed_at AND NEW.opening_cutoff='after_all')))
  OR EXISTS(SELECT 1 FROM prep_inventory.count_observations m JOIN prep_inventory.observations e ON e.id=m.event_id WHERE e.store_id=NEW.store_id
    AND m.product_id=(l->>'product_id')::uuid AND m.base_quantity<>0 AND e.performed_at<a.performed_at)
  THEN RAISE EXCEPTION 'Zero handoff has conflicting historical stock/activity or evidence'; END IF;
 END LOOP;
 RETURN NEW;
END $$;
CREATE FUNCTION prep_inventory.seal_period_sources() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NOT prep_inventory.period_sources_current(NEW) THEN RAISE EXCEPTION 'Analytical source history changed within save transaction'; END IF;
 RETURN NEW;
END $$;
CREATE FUNCTION prep_inventory.guard_period_reopening() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE start_ordinal bigint; expected uuid[]; supplied jsonb; frozen jsonb;
BEGIN
 PERFORM 1 FROM public.store_state WHERE store_id=NEW.store_id FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Reopening requires store coordination'; END IF;
 SELECT ordinal INTO start_ordinal FROM prep_inventory.period_closures WHERE id=NEW.closure_ids[1] AND store_id=NEW.store_id;
 SELECT array_agg(c.id ORDER BY c.ordinal),jsonb_agg(jsonb_build_object('id',c.id,'hash',encode(c.review_hash,'hex')) ORDER BY c.ordinal) INTO expected,frozen
 FROM prep_inventory.period_closures c WHERE c.store_id=NEW.store_id AND c.ordinal>=start_ordinal AND NOT EXISTS(
 SELECT 1 FROM prep_inventory.period_reopenings r WHERE r.store_id=c.store_id AND c.id=ANY(r.closure_ids));
 SELECT jsonb_agg(jsonb_build_object('id',x->>'id','hash',x->>'review_hash') ORDER BY n) INTO supplied FROM jsonb_array_elements(NEW.review_snapshot->'snapshots') WITH ORDINALITY t(x,n);
 IF expected IS NULL OR NEW.closure_ids IS DISTINCT FROM expected OR frozen IS DISTINCT FROM supplied
 OR NEW.review_snapshot->>'store_id' IS DISTINCT FROM NEW.store_id
 OR NEW.review_snapshot->'submission'->>'reason' IS DISTINCT FROM NEW.reason
 OR NEW.review_snapshot->'submission'->>'from_closure_id' IS DISTINCT FROM NEW.closure_ids[1]::text
 OR NEW.review_snapshot->'closure_ids' IS DISTINCT FROM to_jsonb(NEW.closure_ids)
 OR NEW.review_snapshot->'track1Writeback' IS DISTINCT FROM 'false'::jsonb
 THEN RAISE EXCEPTION 'Reopening must retain exactly the active suffix and its saved hashes'; END IF;
 IF EXISTS(SELECT 1 FROM prep_inventory.period_closures c WHERE c.store_id=NEW.store_id AND c.ordinal<start_ordinal AND NOT EXISTS(
 SELECT 1 FROM prep_inventory.period_reopenings r WHERE r.store_id=c.store_id AND c.id=ANY(r.closure_ids)) AND NOT prep_inventory.period_sources_current(c))
 THEN RAISE EXCEPTION 'Reopen from earlier stale period'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER period_closure_guard BEFORE INSERT ON prep_inventory.period_closures FOR EACH ROW EXECUTE FUNCTION prep_inventory.guard_period_closure();
CREATE CONSTRAINT TRIGGER period_source_seal AFTER INSERT ON prep_inventory.period_closures DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION prep_inventory.seal_period_sources();
CREATE TRIGGER period_reopening_guard BEFORE INSERT ON prep_inventory.period_reopenings FOR EACH ROW EXECUTE FUNCTION prep_inventory.guard_period_reopening();
CREATE TRIGGER period_closure_immutable BEFORE UPDATE OR DELETE ON prep_inventory.period_closures FOR EACH ROW EXECUTE FUNCTION purchasing.reject_fact_change();
CREATE TRIGGER period_reopening_immutable BEFORE UPDATE OR DELETE ON prep_inventory.period_reopenings FOR EACH ROW EXECUTE FUNCTION purchasing.reject_fact_change();
REVOKE ALL ON ALL TABLES IN SCHEMA prep_inventory FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA prep_inventory FROM PUBLIC;
DO $$ DECLARE role_name text; BEGIN
 FOREACH role_name IN ARRAY ARRAY['anon','authenticated'] LOOP
 IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=role_name) THEN
 EXECUTE format('REVOKE ALL ON ALL TABLES IN SCHEMA prep_inventory FROM %I',role_name);
 EXECUTE format('REVOKE ALL ON ALL FUNCTIONS IN SCHEMA prep_inventory FROM %I',role_name);
 END IF; END LOOP;
END $$;
COMMIT;
