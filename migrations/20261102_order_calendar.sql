-- Order calendar (Jeff 2026-11-01, M4): Bert's and Rudd's order Sunday, Wednesday and Thursday;
-- counts are due at noon and orders at 3 PM, Eastern time. Deliveries: Monday PFG and US Foods,
-- Thursday PFG and US Foods, Friday US Foods only. Papa's has no calendar in V1.1.
-- A late count or order is allowed with a short reason, kept as an append-only note. Nothing here
-- changes stock, orders or accounting.

BEGIN;
SET LOCAL lock_timeout = '5s';

CREATE TABLE purchasing.order_calendar (
 store_id text NOT NULL,
 order_weekday smallint NOT NULL CHECK (order_weekday BETWEEN 0 AND 6),      -- 0 Monday ... 6 Sunday
 count_due time NOT NULL,
 order_due time NOT NULL CHECK (count_due <= order_due),
 delivery_weekday smallint NOT NULL CHECK (delivery_weekday BETWEEN 0 AND 6),
 vendor_ids text[] NOT NULL CHECK (cardinality(vendor_ids) > 0),
 timezone_name text NOT NULL DEFAULT 'America/New_York',
 PRIMARY KEY (store_id, order_weekday)
);

INSERT INTO purchasing.order_calendar(store_id, order_weekday, count_due, order_due, delivery_weekday, vendor_ids)
SELECT s, d.order_weekday, '12:00', '15:00', d.delivery_weekday, d.vendor_ids
FROM unnest(ARRAY['berts', 'rudds']) s,
     (VALUES (6, 0, ARRAY['pfg', 'us_foods']), (2, 3, ARRAY['pfg', 'us_foods']), (3, 4, ARRAY['us_foods'])) d(order_weekday, delivery_weekday, vendor_ids);

-- Why a count or an order was late. One note per late order; a count may gather more than one.
CREATE TABLE purchasing.order_cycle_notes (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 store_id text NOT NULL,
 cycle_date date NOT NULL,
 kind text NOT NULL CHECK (kind IN ('count_late', 'order_late')),
 vendor_id text,
 po_id uuid REFERENCES public.purchase_orders(id),
 reason text NOT NULL CHECK (length(btrim(reason)) > 0),
 recorded_by text NOT NULL CHECK (length(btrim(recorded_by)) > 0),
 recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 request_key uuid NOT NULL UNIQUE,
 CHECK ((kind = 'order_late') = (po_id IS NOT NULL AND vendor_id IS NOT NULL))
);
CREATE INDEX order_cycle_notes_day ON purchasing.order_cycle_notes(store_id, cycle_date);

CREATE TRIGGER immutable_fact BEFORE UPDATE OR DELETE ON purchasing.order_cycle_notes
 FOR EACH ROW EXECUTE FUNCTION purchasing.reject_fact_change();
REVOKE ALL ON purchasing.order_calendar, purchasing.order_cycle_notes FROM PUBLIC;
DO $$ BEGIN
 IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN REVOKE ALL ON purchasing.order_calendar, purchasing.order_cycle_notes FROM anon; END IF;
 IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN REVOKE ALL ON purchasing.order_calendar, purchasing.order_cycle_notes FROM authenticated; END IF;
END $$;

COMMIT;
