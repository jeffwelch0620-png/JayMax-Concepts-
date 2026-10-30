-- M3 store transfers (Jeff 2026-10-29): inventory belongs to the store that bought it. A
-- purchased item moves between stores when one store is out and the other has it, or when one
-- store's stock goes into a batch for the other. The sending manager records what was sent;
-- the receiving manager confirms what arrived. It leaves the sender and enters the receiver
-- once, at cost (the sender's latest purchase cost, per the latest-purchase costing decision),
-- on the received date; no purchase or sale is created. Anything lost on the way stays in
-- the sender's usage. Records are append-only and never write stock.
BEGIN;
SET LOCAL lock_timeout = '5s';

CREATE TABLE actual_inventory.store_transfers (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 from_store_id text NOT NULL REFERENCES public.stores(id),
 to_store_id text NOT NULL REFERENCES public.stores(id) CHECK (to_store_id <> from_store_id),
 item_code text NOT NULL REFERENCES public.items(code),
 base_unit text NOT NULL,
 sent_base_quantity numeric NOT NULL CHECK (sent_base_quantity > 0 AND sent_base_quantity NOT IN ('NaN'::numeric, 'Infinity'::numeric)),
 kind text NOT NULL CHECK (kind IN ('lend', 'batch_ingredient')),
 sent_date date NOT NULL,
 -- The sender's latest current purchase of this item on or before the sent date.
 cost_mapping_id uuid NOT NULL,
 cost_base_quantity numeric NOT NULL CHECK (cost_base_quantity > 0),
 cost_amount numeric NOT NULL CHECK (cost_amount >= 0),
 cost_record_date date NOT NULL,
 note text NOT NULL CHECK (length(btrim(note)) > 0),
 actor text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 request_key uuid NOT NULL UNIQUE,
 request_fingerprint bytea NOT NULL CHECK (octet_length(request_fingerprint) = 32)
);
CREATE INDEX store_transfers_from ON actual_inventory.store_transfers(from_store_id, sent_date);
CREATE INDEX store_transfers_to ON actual_inventory.store_transfers(to_store_id, sent_date);

-- One closing step per transfer: the receiver confirms what arrived, or the sender cancels
-- before anything is received.
CREATE TABLE actual_inventory.store_transfer_events (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 transfer_id uuid NOT NULL UNIQUE REFERENCES actual_inventory.store_transfers(id),
 action text NOT NULL CHECK (action IN ('receive', 'cancel')),
 store_id text NOT NULL REFERENCES public.stores(id),
 received_base_quantity numeric CHECK (received_base_quantity >= 0 AND received_base_quantity NOT IN ('NaN'::numeric, 'Infinity'::numeric)),
 record_date date,
 transfer_cost_amount numeric,
 note text NOT NULL CHECK (length(btrim(note)) > 0),
 actor text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 request_key uuid NOT NULL UNIQUE,
 request_fingerprint bytea NOT NULL CHECK (octet_length(request_fingerprint) = 32),
 CHECK ((action = 'receive') = (received_base_quantity IS NOT NULL AND record_date IS NOT NULL AND transfer_cost_amount IS NOT NULL))
);

-- The cost basis is the sender's latest current purchase of the item on or before the sent
-- date, and the item is known at both stores in the same base unit.
CREATE FUNCTION actual_inventory.guard_store_transfer() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE latest record;
BEGIN
 IF (SELECT count(*) FROM public.store_items WHERE item_code = NEW.item_code AND store_id IN (NEW.from_store_id, NEW.to_store_id)) <> 2
 THEN RAISE EXCEPTION 'Both stores must carry this item'; END IF;
 IF EXISTS (SELECT 1 FROM purchasing.item_bases WHERE item_code = NEW.item_code AND store_id IN (NEW.from_store_id, NEW.to_store_id) AND base_unit <> NEW.base_unit)
 THEN RAISE EXCEPTION 'Both stores must count this item in the same base unit'; END IF;
 SELECT f.mapping_id, f.base_quantity, f.inventory_cost_amount, f.inventory_record_date INTO latest FROM purchasing.current_purchase_facts f
  WHERE f.store_id = NEW.from_store_id AND f.item_code = NEW.item_code AND f.base_unit = NEW.base_unit
   AND f.base_quantity > 0 AND f.inventory_record_date <= NEW.sent_date
  ORDER BY f.inventory_record_date DESC, f.goods_received_at DESC NULLS LAST, f.mapping_id DESC LIMIT 1;
 IF latest.mapping_id IS NULL THEN RAISE EXCEPTION 'The sending store has no purchase cost on record for this item'; END IF;
 IF (NEW.cost_mapping_id, NEW.cost_base_quantity, NEW.cost_amount, NEW.cost_record_date)
    IS DISTINCT FROM (latest.mapping_id, latest.base_quantity, latest.inventory_cost_amount, latest.inventory_record_date)
 THEN RAISE EXCEPTION 'A transfer is priced at the sending store''s latest purchase cost'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER guard_store_transfer BEFORE INSERT ON actual_inventory.store_transfers
 FOR EACH ROW EXECUTE FUNCTION actual_inventory.guard_store_transfer();

-- Receiving: only the receiving store, never more than was sent, on or after the sent date,
-- and never into a closed period at either store. The cost is set here, rounded to the cent.
CREATE FUNCTION actual_inventory.guard_store_transfer_event() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE t actual_inventory.store_transfers;
BEGIN
 SELECT * INTO t FROM actual_inventory.store_transfers WHERE id = NEW.transfer_id FOR UPDATE;
 IF NEW.action = 'cancel' THEN
  IF NEW.store_id <> t.from_store_id THEN RAISE EXCEPTION 'Only the sending store cancels a transfer'; END IF;
  NEW.received_base_quantity := NULL; NEW.record_date := NULL; NEW.transfer_cost_amount := NULL;
  RETURN NEW;
 END IF;
 IF NEW.store_id <> t.to_store_id THEN RAISE EXCEPTION 'Only the receiving store confirms what arrived'; END IF;
 IF NEW.received_base_quantity > t.sent_base_quantity THEN RAISE EXCEPTION 'Received more than was sent'; END IF;
 IF NEW.record_date < t.sent_date THEN RAISE EXCEPTION 'A transfer cannot be received before it was sent'; END IF;
 IF EXISTS (SELECT 1 FROM actual_inventory.active_period_closures p WHERE p.store_id IN (t.from_store_id, t.to_store_id)
     AND NEW.record_date >= p.period_start AND NEW.record_date < p.period_end_exclusive)
  OR EXISTS (SELECT 1 FROM public.reporting_periods p WHERE p.store_id IN (t.from_store_id, t.to_store_id) AND p.status = 'closed'
     AND NEW.record_date BETWEEN p.period_start AND p.period_end)
 THEN RAISE EXCEPTION 'The received date is in a closed period at one of the stores'; END IF;
 NEW.transfer_cost_amount := round(NEW.received_base_quantity * t.cost_amount / t.cost_base_quantity, 2);
 RETURN NEW;
END $$;
CREATE TRIGGER guard_store_transfer_event BEFORE INSERT ON actual_inventory.store_transfer_events
 FOR EACH ROW EXECUTE FUNCTION actual_inventory.guard_store_transfer_event();

-- What each store's food-cost period sees: received transfers in (+) and out (-) at cost.
CREATE VIEW actual_inventory.transfer_movements AS
 SELECT t.to_store_id AS store_id, t.id AS transfer_id, 'in'::text AS direction, t.from_store_id AS other_store_id,
  t.item_code, t.base_unit, e.received_base_quantity AS base_quantity, e.transfer_cost_amount AS cost_amount, e.record_date, t.kind
 FROM actual_inventory.store_transfers t JOIN actual_inventory.store_transfer_events e ON e.transfer_id = t.id AND e.action = 'receive'
 UNION ALL
 SELECT t.from_store_id, t.id, 'out', t.to_store_id, t.item_code, t.base_unit, -e.received_base_quantity, -e.transfer_cost_amount, e.record_date, t.kind
 FROM actual_inventory.store_transfers t JOIN actual_inventory.store_transfer_events e ON e.transfer_id = t.id AND e.action = 'receive';

-- Once received, a transfer is fixed like a posted purchase (append-only), so every later
-- period closure at either store includes it unchanged.
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['store_transfers','store_transfer_events'] LOOP
  EXECUTE format('CREATE TRIGGER immutable_fact BEFORE UPDATE OR DELETE ON actual_inventory.%I
      FOR EACH ROW EXECUTE FUNCTION purchasing.reject_fact_change()', t);
  EXECUTE format('REVOKE ALL ON actual_inventory.%I FROM PUBLIC', t);
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN EXECUTE format('REVOKE ALL ON actual_inventory.%I FROM anon', t); END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN EXECUTE format('REVOKE ALL ON actual_inventory.%I FROM authenticated', t); END IF;
 END LOOP;
END $$;
REVOKE ALL ON actual_inventory.transfer_movements FROM PUBLIC;
REVOKE ALL ON FUNCTION actual_inventory.guard_store_transfer() FROM PUBLIC;
REVOKE ALL ON FUNCTION actual_inventory.guard_store_transfer_event() FROM PUBLIC;
COMMIT;
