-- Count zones for the evening prep count. A store's zone layout lists where prepared food is
-- kept (for Bert's Salad Bar: Walk-in, Cooler, Below bar, Salad station) in walk order and
-- places each prepared item in one or more zones. A full prep count may record a quantity per
-- zone; the item's count line stays the one total, so moving a pan between zones creates no
-- food. Layouts are versioned and append-only.
BEGIN;
SET LOCAL lock_timeout = '5s';

CREATE TABLE prep_inventory.zone_layouts (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 store_id text NOT NULL REFERENCES public.stores(id),
 revision integer NOT NULL CHECK (revision > 0),
 note text NOT NULL CHECK (length(btrim(note)) > 0),
 request_key uuid NOT NULL UNIQUE,
 request_fingerprint bytea NOT NULL CHECK (octet_length(request_fingerprint) = 32),
 confirmed_by text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE (store_id, revision), UNIQUE (id, store_id)
);
CREATE TABLE prep_inventory.zone_layout_zones (
 layout_id uuid NOT NULL REFERENCES prep_inventory.zone_layouts(id),
 zone_code text NOT NULL CHECK (zone_code ~ '^[a-z0-9]+(-[a-z0-9]+)*$' AND length(zone_code) <= 60),
 name text NOT NULL CHECK (length(btrim(name)) > 0 AND length(name) <= 120),
 walk_position integer NOT NULL CHECK (walk_position > 0),
 PRIMARY KEY (layout_id, zone_code), UNIQUE (layout_id, walk_position)
);
CREATE TABLE prep_inventory.zone_layout_placements (
 layout_id uuid NOT NULL,
 store_id text NOT NULL,
 zone_code text NOT NULL,
 product_id uuid NOT NULL,
 item_position integer NOT NULL CHECK (item_position > 0),
 PRIMARY KEY (layout_id, zone_code, product_id), UNIQUE (layout_id, zone_code, item_position),
 FOREIGN KEY (layout_id, zone_code) REFERENCES prep_inventory.zone_layout_zones(layout_id, zone_code),
 FOREIGN KEY (layout_id, store_id) REFERENCES prep_inventory.zone_layouts(id, store_id),
 FOREIGN KEY (product_id, store_id) REFERENCES prep_inventory.products(id, store_id)
);

CREATE TABLE prep_inventory.count_zone_quantities (
 event_id uuid NOT NULL,
 store_id text NOT NULL,
 product_id uuid NOT NULL,
 layout_id uuid NOT NULL,
 zone_code text NOT NULL,
 quantity numeric NOT NULL CHECK (quantity >= 0 AND quantity NOT IN ('NaN'::numeric, 'Infinity'::numeric)),
 PRIMARY KEY (event_id, product_id, zone_code),
 FOREIGN KEY (event_id, product_id) REFERENCES prep_inventory.count_observations(event_id, product_id),
 FOREIGN KEY (event_id, store_id) REFERENCES prep_inventory.observations(id, store_id),
 FOREIGN KEY (layout_id, zone_code, product_id) REFERENCES prep_inventory.zone_layout_placements(layout_id, zone_code, product_id)
);

-- Zone quantities must cover every zone the item is placed in, follow one layout per count,
-- and add up to the item's count line exactly. Checked at commit, after all rows exist.
CREATE FUNCTION prep_inventory.check_zone_total() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE line_qty numeric; total numeric; given integer; placed integer; layouts integer;
BEGIN
 SELECT quantity INTO line_qty FROM prep_inventory.count_observations WHERE event_id = NEW.event_id AND product_id = NEW.product_id;
 SELECT count(DISTINCT layout_id) INTO layouts FROM prep_inventory.count_zone_quantities WHERE event_id = NEW.event_id;
 IF layouts <> 1 THEN RAISE EXCEPTION 'A prep count follows one zone layout'; END IF;
 SELECT sum(quantity), count(*) INTO total, given FROM prep_inventory.count_zone_quantities
  WHERE event_id = NEW.event_id AND product_id = NEW.product_id;
 SELECT count(*) INTO placed FROM prep_inventory.zone_layout_placements WHERE layout_id = NEW.layout_id AND product_id = NEW.product_id;
 IF given <> placed THEN RAISE EXCEPTION 'Count every zone of the prepared item'; END IF;
 IF total IS DISTINCT FROM line_qty THEN RAISE EXCEPTION 'Zone quantities do not add up to the counted total'; END IF;
 RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER count_zone_total AFTER INSERT ON prep_inventory.count_zone_quantities
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION prep_inventory.check_zone_total();

DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['zone_layouts','zone_layout_zones','zone_layout_placements','count_zone_quantities'] LOOP
  EXECUTE format('CREATE TRIGGER immutable_fact BEFORE UPDATE OR DELETE ON prep_inventory.%I
      FOR EACH ROW EXECUTE FUNCTION purchasing.reject_fact_change()', t);
  EXECUTE format('REVOKE ALL ON prep_inventory.%I FROM PUBLIC', t);
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN EXECUTE format('REVOKE ALL ON prep_inventory.%I FROM anon', t); END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN EXECUTE format('REVOKE ALL ON prep_inventory.%I FROM authenticated', t); END IF;
 END LOOP;
END $$;
REVOKE ALL ON FUNCTION prep_inventory.check_zone_total() FROM PUBLIC;
COMMIT;
