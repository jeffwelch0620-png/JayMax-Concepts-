-- Track 1: purchased items only, explicit physical count values.
-- Requires 20261004_native_purchase_import.sql. Apply to disposable PG first.
BEGIN;
CREATE SCHEMA actual_inventory;

CREATE TABLE actual_inventory.scopes (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 store_id text NOT NULL REFERENCES public.stores(id),
 revision integer NOT NULL CHECK(revision>0),
 scope_kind text NOT NULL CHECK(scope_kind='purchased_items_only'),
 valuation_method text NOT NULL CHECK(valuation_method='explicit_count_values'),
 note text NOT NULL CHECK(length(btrim(note))>0),
 request_key uuid NOT NULL UNIQUE,
 request_fingerprint bytea NOT NULL CHECK(octet_length(request_fingerprint)=32),
 confirmed_by text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(store_id,revision), UNIQUE(id,store_id)
);
CREATE TABLE actual_inventory.scope_items (
 scope_id uuid NOT NULL,
 store_id text NOT NULL,
 item_code text NOT NULL,
 base_unit text NOT NULL,
 name_snapshot text NOT NULL,
 location_notes text NOT NULL CHECK(length(btrim(location_notes))>0),
 PRIMARY KEY(scope_id,item_code),
 UNIQUE(scope_id,store_id,item_code,base_unit),
 FOREIGN KEY(scope_id,store_id) REFERENCES actual_inventory.scopes(id,store_id),
 FOREIGN KEY(store_id,item_code,base_unit) REFERENCES purchasing.item_bases(store_id,item_code,base_unit)
);
CREATE TABLE actual_inventory.count_snapshots (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 store_id text NOT NULL,
 scope_id uuid NOT NULL,
 count_date date NOT NULL,
 timing text NOT NULL CHECK(timing IN ('before_receipts','after_receipts')),
 boundary_date date GENERATED ALWAYS AS
   (count_date + CASE WHEN timing='after_receipts' THEN 1 ELSE 0 END) STORED,
 status text NOT NULL CHECK(status IN ('complete','incomplete')),
 note text NOT NULL CHECK(length(btrim(note))>0),
 corrects_snapshot_id uuid,
 request_key uuid NOT NULL UNIQUE,
 request_fingerprint bytea NOT NULL CHECK(octet_length(request_fingerprint)=32),
 counted_by text NOT NULL,
 recorded_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(scope_id,store_id) REFERENCES actual_inventory.scopes(id,store_id),
 UNIQUE(id,store_id), UNIQUE(id,scope_id,store_id),
 FOREIGN KEY(corrects_snapshot_id,store_id) REFERENCES actual_inventory.count_snapshots(id,store_id)
);
CREATE TABLE actual_inventory.count_lines (
 snapshot_id uuid NOT NULL,
 scope_id uuid NOT NULL,
 store_id text NOT NULL,
 item_code text NOT NULL,
 base_unit text NOT NULL,
 counted_quantity numeric CHECK(counted_quantity>=0),
 counted_unit text NOT NULL CHECK(length(btrim(counted_unit))>0),
 base_units_per_counted_unit numeric CHECK(base_units_per_counted_unit>0),
 base_quantity numeric GENERATED ALWAYS AS(counted_quantity*base_units_per_counted_unit) STORED,
 inventory_value numeric(20,2) CHECK(inventory_value>=0),
 confirmed boolean NOT NULL,
 note text NOT NULL,
 PRIMARY KEY(snapshot_id,item_code),
 FOREIGN KEY(snapshot_id,scope_id,store_id) REFERENCES actual_inventory.count_snapshots(id,scope_id,store_id),
 FOREIGN KEY(scope_id,store_id,item_code,base_unit) REFERENCES actual_inventory.scope_items(scope_id,store_id,item_code,base_unit),
 CHECK(counted_quantity IS NULL OR counted_quantity NOT IN ('NaN'::numeric,'Infinity'::numeric,'-Infinity'::numeric)),
 CHECK(base_units_per_counted_unit IS NULL OR base_units_per_counted_unit NOT IN ('NaN'::numeric,'Infinity'::numeric,'-Infinity'::numeric)),
 CHECK(inventory_value IS NULL OR inventory_value NOT IN ('NaN'::numeric,'Infinity'::numeric,'-Infinity'::numeric)),
 CHECK(counted_quantity IS NULL OR base_units_per_counted_unit IS NOT NULL),
 CHECK(inventory_value IS NULL OR counted_quantity IS NOT NULL),
 CHECK(counted_quantity IS DISTINCT FROM 0 OR coalesce(inventory_value,0)=0),
 CHECK(NOT confirmed OR (counted_quantity IS NOT NULL AND inventory_value IS NOT NULL
    AND base_units_per_counted_unit IS NOT NULL AND length(btrim(note))>0))
);
CREATE TABLE actual_inventory.period_closures (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 store_id text NOT NULL,
 opening_snapshot_id uuid NOT NULL,
 closing_snapshot_id uuid NOT NULL,
 period_start date NOT NULL,
 period_end_exclusive date NOT NULL CHECK(period_end_exclusive>period_start),
 report_snapshot jsonb NOT NULL CHECK(jsonb_typeof(report_snapshot)='object'),
 request_key uuid NOT NULL UNIQUE,
 request_fingerprint bytea NOT NULL CHECK(octet_length(request_fingerprint)=32),
 closed_by text NOT NULL,
 closed_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(opening_snapshot_id,store_id) REFERENCES actual_inventory.count_snapshots(id,store_id),
 FOREIGN KEY(closing_snapshot_id,store_id) REFERENCES actual_inventory.count_snapshots(id,store_id),
 UNIQUE(store_id,opening_snapshot_id,closing_snapshot_id)
);

-- Row locks match purchase posting and application state writes. Late purchases
-- cannot rewrite a closed Track 1 period, even through the native SQL function.
CREATE FUNCTION actual_inventory.guard_closed_purchase_date() RETURNS trigger
LANGUAGE plpgsql AS $$ BEGIN
 IF NEW.classification='food' AND NEW.movement_kind<>'no_inventory' THEN
  INSERT INTO public.store_state(store_id) VALUES(NEW.store_id) ON CONFLICT(store_id) DO NOTHING;
  PERFORM 1 FROM public.store_state WHERE store_id=NEW.store_id FOR UPDATE;
  IF EXISTS(SELECT 1 FROM actual_inventory.period_closures
      WHERE store_id=NEW.store_id AND NEW.inventory_record_date>=period_start
        AND NEW.inventory_record_date<period_end_exclusive)
  THEN RAISE EXCEPTION 'Closed actual-inventory period requires linked correction review'; END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER closed_actual_period_guard BEFORE INSERT ON purchasing.mapping_decisions
FOR EACH ROW EXECUTE FUNCTION actual_inventory.guard_closed_purchase_date();

-- Also cover mappings recorded before the period was closed and posted later.
CREATE FUNCTION actual_inventory.guard_purchase_batch() RETURNS trigger
LANGUAGE plpgsql AS $$ DECLARE sid text; BEGIN
 SELECT store_id INTO STRICT sid FROM purchasing.document_identities WHERE id=NEW.document_id;
 INSERT INTO public.store_state(store_id) VALUES(sid) ON CONFLICT(store_id) DO NOTHING;
 PERFORM 1 FROM public.store_state WHERE store_id=sid FOR UPDATE;
 IF EXISTS(SELECT 1 FROM purchasing.document_lines l
     JOIN LATERAL (SELECT * FROM purchasing.mapping_decisions WHERE line_id=l.id ORDER BY revision DESC LIMIT 1) m ON true
     JOIN actual_inventory.period_closures p ON p.store_id=sid
       AND m.inventory_record_date>=p.period_start AND m.inventory_record_date<p.period_end_exclusive
     WHERE l.document_version_id=NEW.document_version_id AND m.classification='food' AND m.movement_kind<>'no_inventory')
 THEN RAISE EXCEPTION 'Late purchase posting would change a closed actual-inventory period'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER closed_actual_batch_guard BEFORE INSERT ON purchasing.posting_batches
FOR EACH ROW EXECUTE FUNCTION actual_inventory.guard_purchase_batch();

CREATE FUNCTION actual_inventory.guard_closure() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE opening actual_inventory.count_snapshots; closing actual_inventory.count_snapshots;
 prior_period actual_inventory.period_closures; next_period actual_inventory.period_closures;
BEGIN
 INSERT INTO public.store_state(store_id) VALUES(NEW.store_id) ON CONFLICT(store_id) DO NOTHING;
 PERFORM 1 FROM public.store_state WHERE store_id=NEW.store_id FOR UPDATE;
 SELECT * INTO STRICT opening FROM actual_inventory.count_snapshots WHERE id=NEW.opening_snapshot_id AND store_id=NEW.store_id;
 SELECT * INTO STRICT closing FROM actual_inventory.count_snapshots WHERE id=NEW.closing_snapshot_id AND store_id=NEW.store_id;
 IF opening.status<>'complete' OR closing.status<>'complete' OR opening.scope_id<>closing.scope_id
    OR opening.boundary_date<>NEW.period_start OR closing.boundary_date<>NEW.period_end_exclusive
 THEN RAISE EXCEPTION 'Period boundaries require complete counts in the same scope'; END IF;
 IF EXISTS(SELECT 1 FROM actual_inventory.period_closures p WHERE p.store_id=NEW.store_id
    AND NEW.period_start<p.period_end_exclusive AND NEW.period_end_exclusive>p.period_start)
 THEN RAISE EXCEPTION 'Closed actual-inventory periods cannot overlap'; END IF;
 SELECT * INTO prior_period FROM actual_inventory.period_closures p WHERE p.store_id=NEW.store_id
    AND p.period_end_exclusive<=NEW.period_start ORDER BY p.period_end_exclusive DESC LIMIT 1;
 IF FOUND AND (prior_period.period_end_exclusive<>NEW.period_start OR prior_period.closing_snapshot_id<>NEW.opening_snapshot_id)
 THEN RAISE EXCEPTION 'Continue from the previous closing count; do not skip count intervals'; END IF;
 SELECT * INTO next_period FROM actual_inventory.period_closures p WHERE p.store_id=NEW.store_id
    AND p.period_start>=NEW.period_end_exclusive ORDER BY p.period_start LIMIT 1;
 IF FOUND AND (next_period.period_start<>NEW.period_end_exclusive OR next_period.opening_snapshot_id<>NEW.closing_snapshot_id)
 THEN RAISE EXCEPTION 'Closing count must match the next closed period opening without a gap'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER closure_boundary_guard BEFORE INSERT ON actual_inventory.period_closures
FOR EACH ROW EXECUTE FUNCTION actual_inventory.guard_closure();

CREATE FUNCTION actual_inventory.seal_count_child() RETURNS trigger
LANGUAGE plpgsql AS $$ BEGIN
 PERFORM 1 FROM actual_inventory.count_snapshots WHERE id=NEW.snapshot_id FOR UPDATE;
 IF EXISTS(SELECT 1 FROM actual_inventory.period_closures
     WHERE opening_snapshot_id=NEW.snapshot_id OR closing_snapshot_id=NEW.snapshot_id)
 THEN RAISE EXCEPTION 'Closed period count is sealed'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER seal_count_lines BEFORE INSERT ON actual_inventory.count_lines
FOR EACH ROW EXECUTE FUNCTION actual_inventory.seal_count_child();
CREATE FUNCTION actual_inventory.seal_scope_child() RETURNS trigger
LANGUAGE plpgsql AS $$ BEGIN
 PERFORM 1 FROM actual_inventory.scopes WHERE id=NEW.scope_id FOR UPDATE;
 IF EXISTS(SELECT 1 FROM actual_inventory.count_snapshots WHERE scope_id=NEW.scope_id)
 THEN RAISE EXCEPTION 'Count scope is sealed; append a scope version'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER seal_scope_items BEFORE INSERT ON actual_inventory.scope_items
FOR EACH ROW EXECUTE FUNCTION actual_inventory.seal_scope_child();

DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['scopes','scope_items','count_snapshots','count_lines','period_closures'] LOOP
  EXECUTE format('CREATE TRIGGER immutable_fact BEFORE UPDATE OR DELETE ON actual_inventory.%I
      FOR EACH ROW EXECUTE FUNCTION purchasing.reject_fact_change()',t);
 END LOOP;
END $$;
CREATE INDEX count_snapshot_store_date ON actual_inventory.count_snapshots(store_id,boundary_date DESC);
CREATE INDEX closure_store_dates ON actual_inventory.period_closures(store_id,period_start,period_end_exclusive);
REVOKE ALL ON SCHEMA actual_inventory FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA actual_inventory FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA actual_inventory FROM PUBLIC;
COMMIT;
