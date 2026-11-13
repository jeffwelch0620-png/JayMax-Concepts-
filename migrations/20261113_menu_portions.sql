-- M6 prep against sales (Jeff 2026-11-13): which prep items one sold Toast menu item or modifier uses,
-- and how much, per store. Analytics multiplies Toast's sold quantities by these portions to show how
-- much of each prep item sales imply was used, next to what was made, wasted and counted.
-- A portion is a planning reference only: it never changes stock, food or accounting records and
-- nothing is deducted automatically (Inventory stays the only writer of food records).
--
-- Append-only. Each row sets one line from its date onward: for a business date, the line's value is
-- the most recently recorded row whose effective_from is on or before that date (NULL = from the start
-- of the sales history). A change or correction is a new row; nothing is updated or deleted.
-- A row with no prep item is the "uses no tracked prep" marker (base_quantity 1 = on, 0 = off), so
-- drinks and sides that need no prep don't show as missing portions.
-- Requires the native prep foundation (20261005_prep_mapping_foundation.sql). Seeds nothing.
BEGIN;
CREATE TABLE prep_inventory.menu_portions (
 id uuid PRIMARY KEY,
 store_id text NOT NULL REFERENCES public.stores(id),
 sold_kind text NOT NULL CHECK (sold_kind IN ('item','modifier')),
 sold_guid uuid NOT NULL,
 sold_name text NOT NULL CHECK (length(btrim(sold_name)) BETWEEN 1 AND 200),
 product_id uuid,
 base_unit text,
 base_quantity numeric NOT NULL CHECK (base_quantity >= 0 AND base_quantity < 1000000
   AND base_quantity NOT IN ('NaN'::numeric,'Infinity'::numeric,'-Infinity'::numeric)),
 effective_from date,
 reason text NOT NULL DEFAULT '' CHECK (length(reason) <= 500),
 recorded_by text NOT NULL CHECK (length(recorded_by) BETWEEN 1 AND 160),
 recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 request_key uuid NOT NULL,
 request_fingerprint text NOT NULL CHECK (request_fingerprint ~ '^[a-f0-9]{64}$'),
 FOREIGN KEY (product_id,store_id,base_unit) REFERENCES prep_inventory.products(id,store_id,base_unit),
 CHECK ((product_id IS NULL AND base_unit IS NULL AND base_quantity IN (0,1))
     OR (product_id IS NOT NULL AND base_unit IS NOT NULL))
);
-- One row per line in each saved change; a retried change finds its rows by the key.
CREATE UNIQUE INDEX menu_portions_request_line ON prep_inventory.menu_portions
 (request_key, coalesce(product_id,'00000000-0000-0000-0000-000000000000'::uuid));
CREATE INDEX menu_portions_sold ON prep_inventory.menu_portions(store_id,sold_kind,sold_guid,recorded_at);

CREATE FUNCTION prep_inventory.refuse_menu_portion_change() RETURNS trigger LANGUAGE plpgsql
SET search_path=pg_catalog AS $$
BEGIN
 RAISE EXCEPTION 'Menu portions are append-only: record a new portion instead';
END $$;
CREATE TRIGGER menu_portions_append_only BEFORE UPDATE OR DELETE ON prep_inventory.menu_portions
 FOR EACH ROW EXECUTE FUNCTION prep_inventory.refuse_menu_portion_change();
CREATE TRIGGER menu_portions_no_truncate BEFORE TRUNCATE ON prep_inventory.menu_portions
 FOR EACH STATEMENT EXECUTE FUNCTION prep_inventory.refuse_menu_portion_change();

ALTER TABLE prep_inventory.menu_portions ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON prep_inventory.menu_portions FROM PUBLIC;
REVOKE ALL ON FUNCTION prep_inventory.refuse_menu_portion_change() FROM PUBLIC;
DO $clients$
DECLARE client_role text;
BEGIN
 FOR client_role IN SELECT rolname FROM pg_catalog.pg_roles WHERE rolname IN ('anon','authenticated','service_role') LOOP
  EXECUTE format('REVOKE ALL ON prep_inventory.menu_portions FROM %I',client_role);
 END LOOP;
END $clients$;
COMMIT;
