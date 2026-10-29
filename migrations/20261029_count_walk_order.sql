-- Walk-order count lists for Track 1 physical counts. A store's count layout lists its
-- storage locations in physical walk order and places each counted item in one or more of
-- them. Counts may record a quantity per location; the item's existing count line stays the
-- authoritative total, so Food Cost, closures, recounts and scope handoffs are unchanged.
-- Layouts are versioned and append-only, separate from the count scope, so moving a shelf
-- does not need a new scope version.
BEGIN;
SET LOCAL lock_timeout = '5s';

CREATE TABLE actual_inventory.count_layouts (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 store_id text NOT NULL REFERENCES public.stores(id),
 revision integer NOT NULL CHECK (revision > 0),
 scope_id uuid NOT NULL,
 note text NOT NULL CHECK (length(btrim(note)) > 0),
 request_key uuid NOT NULL UNIQUE,
 request_fingerprint bytea NOT NULL CHECK (octet_length(request_fingerprint) = 32),
 confirmed_by text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE (store_id, revision), UNIQUE (id, scope_id, store_id),
 FOREIGN KEY (scope_id, store_id) REFERENCES actual_inventory.scopes(id, store_id)
);
CREATE TABLE actual_inventory.layout_locations (
 layout_id uuid NOT NULL REFERENCES actual_inventory.count_layouts(id),
 location_code text NOT NULL CHECK (location_code ~ '^[a-z0-9]+(-[a-z0-9]+)*$' AND length(location_code) <= 60),
 name text NOT NULL CHECK (length(btrim(name)) > 0 AND length(name) <= 120),
 walk_position integer NOT NULL CHECK (walk_position > 0),
 PRIMARY KEY (layout_id, location_code), UNIQUE (layout_id, walk_position)
);
CREATE TABLE actual_inventory.layout_placements (
 layout_id uuid NOT NULL,
 scope_id uuid NOT NULL,
 store_id text NOT NULL,
 location_code text NOT NULL,
 item_code text NOT NULL,
 item_position integer NOT NULL CHECK (item_position > 0),
 PRIMARY KEY (layout_id, location_code, item_code), UNIQUE (layout_id, location_code, item_position),
 FOREIGN KEY (layout_id, location_code) REFERENCES actual_inventory.layout_locations(layout_id, location_code),
 FOREIGN KEY (layout_id, scope_id, store_id) REFERENCES actual_inventory.count_layouts(id, scope_id, store_id),
 FOREIGN KEY (scope_id, item_code) REFERENCES actual_inventory.scope_items(scope_id, item_code)
);

-- A count may follow one layout of its own scope; older counts stay NULL (no breakdown).
ALTER TABLE actual_inventory.count_snapshots ADD COLUMN layout_id uuid;
ALTER TABLE actual_inventory.count_snapshots ADD CONSTRAINT count_snapshot_layout_scope
 FOREIGN KEY (layout_id, scope_id, store_id) REFERENCES actual_inventory.count_layouts(id, scope_id, store_id);

CREATE TABLE actual_inventory.count_line_locations (
 snapshot_id uuid NOT NULL,
 item_code text NOT NULL,
 layout_id uuid NOT NULL,
 location_code text NOT NULL,
 counted_quantity numeric(28,10) CHECK (counted_quantity IS NULL OR (counted_quantity >= 0 AND counted_quantity < 'Infinity')),
 PRIMARY KEY (snapshot_id, item_code, location_code),
 FOREIGN KEY (snapshot_id, item_code) REFERENCES actual_inventory.count_lines(snapshot_id, item_code),
 FOREIGN KEY (layout_id, location_code, item_code) REFERENCES actual_inventory.layout_placements(layout_id, location_code, item_code)
);

-- Location quantities must add up to the item's count line exactly; any blank location
-- leaves the line uncounted. Checked at commit, after all of a count's rows exist.
CREATE FUNCTION actual_inventory.check_location_total() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE line_qty numeric; total numeric; blanks integer; snapshot_layout uuid;
BEGIN
 SELECT l.counted_quantity, s.layout_id INTO line_qty, snapshot_layout
  FROM actual_inventory.count_lines l JOIN actual_inventory.count_snapshots s ON s.id = l.snapshot_id
  WHERE l.snapshot_id = NEW.snapshot_id AND l.item_code = NEW.item_code;
 IF snapshot_layout IS DISTINCT FROM NEW.layout_id THEN
  RAISE EXCEPTION 'Location quantities must follow the count''s own layout';
 END IF;
 SELECT sum(counted_quantity), count(*) FILTER (WHERE counted_quantity IS NULL) INTO total, blanks
  FROM actual_inventory.count_line_locations WHERE snapshot_id = NEW.snapshot_id AND item_code = NEW.item_code;
 IF (blanks > 0 AND line_qty IS NOT NULL) OR (blanks = 0 AND line_qty IS DISTINCT FROM total) THEN
  RAISE EXCEPTION 'Location quantities do not add up to the counted total for %', NEW.item_code;
 END IF;
 RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER count_location_total AFTER INSERT ON actual_inventory.count_line_locations
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION actual_inventory.check_location_total();

DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['count_layouts','layout_locations','layout_placements','count_line_locations'] LOOP
  EXECUTE format('CREATE TRIGGER immutable_fact BEFORE UPDATE OR DELETE ON actual_inventory.%I
      FOR EACH ROW EXECUTE FUNCTION purchasing.reject_fact_change()', t);
  EXECUTE format('REVOKE ALL ON actual_inventory.%I FROM PUBLIC', t);
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN EXECUTE format('REVOKE ALL ON actual_inventory.%I FROM anon', t); END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN EXECUTE format('REVOKE ALL ON actual_inventory.%I FROM authenticated', t); END IF;
 END LOOP;
END $$;
REVOKE ALL ON FUNCTION actual_inventory.check_location_total() FROM PUBLIC;
COMMIT;
