-- M2 Bulk daily pars, phase B (Jeff 2026-11-04 and 2026-11-05): a quick daily Bulk count.
-- A manager counts only the store's active to-par Bulk items at night (Bert's includes its Bulk
-- held at Rudd's: one par, met wherever it is kept). In daily par mode the server compares it with
-- the daily pars for the days left before the next Monday or Thursday run and shows when a spot
-- prep is needed; it only suggests, and a manager still sends any spot request. This count is
-- separate from the full prep count, so the Sunday and Wednesday night counts that drive the runs
-- are unchanged. A correction is a new revision for the same night; nothing is overwritten.
-- No stock, purchase or accounting writes.
BEGIN;
SET LOCAL lock_timeout = '5s';

CREATE TABLE prep_inventory.bulk_quick_counts (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 store_id text NOT NULL REFERENCES public.stores(id),
 business_date date NOT NULL,
 revision integer NOT NULL CHECK (revision > 0),
 predecessor_id uuid UNIQUE,
 performed_at timestamptz NOT NULL,
 timezone_name text NOT NULL CHECK (length(btrim(timezone_name)) > 0),
 note text NOT NULL CHECK (length(btrim(note)) > 0),
 actor text NOT NULL CHECK (length(btrim(actor)) > 0),
 review_snapshot jsonb NOT NULL CHECK (jsonb_typeof(review_snapshot) = 'object'),
 request_key uuid NOT NULL UNIQUE,
 request_fingerprint bytea NOT NULL CHECK (octet_length(request_fingerprint) = 32),
 created_xid xid8 NOT NULL DEFAULT pg_current_xact_id(),
 recorded_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE (store_id, business_date, revision), UNIQUE (id, store_id),
 FOREIGN KEY (predecessor_id, store_id) REFERENCES prep_inventory.bulk_quick_counts(id, store_id),
 CHECK ((revision = 1) = (predecessor_id IS NULL))
);

CREATE TABLE prep_inventory.bulk_quick_count_lines (
 count_id uuid NOT NULL,
 store_id text NOT NULL,
 line_number integer NOT NULL CHECK (line_number > 0),
 product_id uuid NOT NULL,
 product_version_id uuid NOT NULL,
 profile_id uuid NOT NULL,
 base_unit text NOT NULL,
 quantity numeric NOT NULL CHECK (quantity >= 0 AND quantity NOT IN ('NaN'::numeric, 'Infinity'::numeric)),
 factor numeric NOT NULL CHECK (factor > 0 AND factor NOT IN ('NaN'::numeric, 'Infinity'::numeric)),
 base_quantity numeric NOT NULL CHECK (base_quantity = quantity * factor),
 PRIMARY KEY (count_id, line_number),
 UNIQUE (count_id, product_id),
 FOREIGN KEY (count_id, store_id) REFERENCES prep_inventory.bulk_quick_counts(id, store_id),
 FOREIGN KEY (product_id, store_id, base_unit) REFERENCES prep_inventory.products(id, store_id, base_unit),
 FOREIGN KEY (product_version_id, product_id, store_id) REFERENCES prep_inventory.product_versions(id, product_id, store_id),
 FOREIGN KEY (profile_id, product_version_id, store_id) REFERENCES prep_inventory.unit_profiles(id, product_version_id, store_id)
);

-- The store's active to-par Bulk items: the ones a quick count must cover.
CREATE FUNCTION prep_inventory.bulk_quick_count_scope(store text) RETURNS SETOF uuid LANGUAGE sql STABLE AS $$
 SELECT p.product_id FROM prep_inventory.planning_versions p WHERE p.store_id = store
  AND p.active AND p.track = 'bulk' AND p.schedule = 'daily'
  AND NOT EXISTS (SELECT 1 FROM prep_inventory.planning_versions q WHERE q.product_id = p.product_id AND q.revision > p.revision)
$$;

-- Each count follows the latest one for the same store and night; the count is for that night
-- (taken that evening or after midnight, in the store's time zone).
CREATE FUNCTION prep_inventory.guard_bulk_quick_count() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE prior prep_inventory.bulk_quick_counts; local_day date;
BEGIN
 SELECT * INTO prior FROM prep_inventory.bulk_quick_counts WHERE store_id = NEW.store_id AND business_date = NEW.business_date
  ORDER BY revision DESC LIMIT 1;
 IF NEW.revision IS DISTINCT FROM coalesce(prior.revision, 0) + 1 OR NEW.predecessor_id IS DISTINCT FROM prior.id
 THEN RAISE EXCEPTION 'Quick Bulk count changed; refresh before correcting'; END IF;
 local_day := (NEW.performed_at AT TIME ZONE NEW.timezone_name)::date;
 IF local_day NOT IN (NEW.business_date, NEW.business_date + 1) THEN RAISE EXCEPTION 'A quick Bulk count is taken that night or before the next morning'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER guard_bulk_quick_count BEFORE INSERT ON prep_inventory.bulk_quick_counts
 FOR EACH ROW EXECUTE FUNCTION prep_inventory.guard_bulk_quick_count();

-- Lines are written with their count, use the item's verified unit conversion, and only count
-- the store's active to-par Bulk items.
CREATE FUNCTION prep_inventory.guard_bulk_quick_count_line() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE parent prep_inventory.bulk_quick_counts;
BEGIN
 SELECT * INTO parent FROM prep_inventory.bulk_quick_counts WHERE id = NEW.count_id;
 IF parent.created_xid <> pg_current_xact_id() THEN RAISE EXCEPTION 'A recorded quick Bulk count cannot gain lines'; END IF;
 IF NEW.factor IS DISTINCT FROM (SELECT base_units_per_source_unit FROM prep_inventory.unit_profiles WHERE id = NEW.profile_id)
 THEN RAISE EXCEPTION 'Quick Bulk count uses the verified unit conversion'; END IF;
 IF NEW.product_id NOT IN (SELECT prep_inventory.bulk_quick_count_scope(NEW.store_id))
 THEN RAISE EXCEPTION 'A quick Bulk count only counts active to-par Bulk items'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER guard_bulk_quick_count_line BEFORE INSERT ON prep_inventory.bulk_quick_count_lines
 FOR EACH ROW EXECUTE FUNCTION prep_inventory.guard_bulk_quick_count_line();

-- At commit: every reviewed line is recorded and every active to-par Bulk item is counted once
-- (a missing count is not zero).
CREATE FUNCTION prep_inventory.check_bulk_quick_count_lines() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF (SELECT count(*) FROM prep_inventory.bulk_quick_count_lines WHERE count_id = NEW.id)
    IS DISTINCT FROM jsonb_array_length(NEW.review_snapshot->'lines')
    OR EXISTS (SELECT 1 FROM prep_inventory.bulk_quick_count_scope(NEW.store_id) s(product_id)
     WHERE NOT EXISTS (SELECT 1 FROM prep_inventory.bulk_quick_count_lines l WHERE l.count_id = NEW.id AND l.product_id = s.product_id))
    OR NOT EXISTS (SELECT 1 FROM prep_inventory.bulk_quick_count_lines WHERE count_id = NEW.id)
 THEN RAISE EXCEPTION 'Count every active Bulk item once; a missing count is not zero'; END IF;
 RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER bulk_quick_count_lines_complete AFTER INSERT ON prep_inventory.bulk_quick_counts
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION prep_inventory.check_bulk_quick_count_lines();

DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['bulk_quick_counts','bulk_quick_count_lines'] LOOP
  EXECUTE format('CREATE TRIGGER immutable_fact BEFORE UPDATE OR DELETE ON prep_inventory.%I
      FOR EACH ROW EXECUTE FUNCTION purchasing.reject_fact_change()', t);
  EXECUTE format('REVOKE ALL ON prep_inventory.%I FROM PUBLIC', t);
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN EXECUTE format('REVOKE ALL ON prep_inventory.%I FROM anon', t); END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN EXECUTE format('REVOKE ALL ON prep_inventory.%I FROM authenticated', t); END IF;
 END LOOP;
END $$;
REVOKE ALL ON FUNCTION prep_inventory.bulk_quick_count_scope(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION prep_inventory.guard_bulk_quick_count() FROM PUBLIC;
REVOKE ALL ON FUNCTION prep_inventory.guard_bulk_quick_count_line() FROM PUBLIC;
REVOKE ALL ON FUNCTION prep_inventory.check_bulk_quick_count_lines() FROM PUBLIC;
COMMIT;
