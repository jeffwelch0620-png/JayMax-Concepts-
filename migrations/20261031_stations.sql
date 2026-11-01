-- Stations and station time (Jeff 2026-10-30). Line Cook tasks belong to a station; a cook's
-- queue for a shift is their station's unassigned tasks plus anything assigned to them by name.
-- Every stint on a station is recorded with its start, and its end separately, so station
-- metrics and each employee's metrics per station (hours, task completion, and later clock
-- in/out from Toast) survive even though Toast and labor costing only say "Cook".
-- Stints and defaults are append-only; a station's name or active flag may change.
BEGIN;
SET LOCAL lock_timeout = '5s';

-- In the existing prep_inventory schema so the hosted backup and restore profiles cover it.

CREATE TABLE prep_inventory.stations (
 store_id text NOT NULL REFERENCES public.stores(id),
 code text NOT NULL CHECK (code ~ '^[A-Z][A-Z-]{1,19}$'),
 name text NOT NULL CHECK (length(btrim(name)) > 0),
 department text NOT NULL CHECK (department IN ('BOH', 'FOH', 'Bulk')),
 position_code text,                       -- the org-chart position that normally works it (LC-GRL, ...)
 active boolean NOT NULL DEFAULT true,
 created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY (store_id, code)
);

-- Starting stations from the org hierarchy (Bert's and Rudd's); Papa Leoni's comes later.
INSERT INTO prep_inventory.stations (store_id, code, name, department, position_code)
SELECT s.store_id, s.code, s.name, s.department, s.position_code FROM (VALUES
 ('berts', 'GRILL', 'Grill', 'BOH', 'LC-GRL'), ('berts', 'PIZZA', 'Pizza', 'BOH', 'LC-PZA'),
 ('berts', 'EXPO', 'Expo', 'BOH', 'LC-EXP'), ('berts', 'SALAD-PASTA', 'Salad/Pasta', 'BOH', 'LC-SLP'),
 ('berts', 'FRY', 'Fry', 'BOH', 'LC-FRY'), ('berts', 'PREP', 'Prep', 'BOH', 'LC-PRP'),
 ('berts', 'SALAD-BAR', 'Salad Bar', 'BOH', 'LC-SBA'),
 ('rudds', 'PIZZA', 'Pizza', 'BOH', 'LC-PZA'), ('rudds', 'ASST-PIZZA', 'Assistant Pizza', 'BOH', 'LC-APZ'),
 ('rudds', 'GRILL', 'Grill', 'BOH', 'LC-GRL'), ('rudds', 'FRY', 'Fry', 'BOH', 'LC-FRY'),
 ('rudds', 'EXPO', 'Expo', 'BOH', 'LC-EXP'), ('rudds', 'PREP', 'Prep', 'BOH', 'LC-PRP'),
 ('rudds', 'BULK', 'Bulk Prep', 'Bulk', 'BPC')
) AS s(store_id, code, name, department, position_code)
WHERE EXISTS (SELECT 1 FROM public.stores WHERE id = s.store_id);

-- Which station normally makes each prepared item; the newest revision wins.
CREATE TABLE prep_inventory.product_stations (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 store_id text NOT NULL,
 product_id uuid NOT NULL,
 station_code text,                        -- NULL = no default station (assigned by name only)
 revision integer NOT NULL CHECK (revision > 0),
 note text NOT NULL CHECK (length(btrim(note)) > 0),
 set_by text NOT NULL,
 set_at timestamptz NOT NULL DEFAULT now(),
 request_key uuid NOT NULL UNIQUE,
 request_fingerprint bytea NOT NULL CHECK (octet_length(request_fingerprint) = 32),
 UNIQUE (product_id, revision),
 FOREIGN KEY (product_id, store_id) REFERENCES prep_inventory.products(id, store_id),
 FOREIGN KEY (store_id, station_code) REFERENCES prep_inventory.stations(store_id, code)
);

-- A stint: one person on one station, from a start time until its end is recorded.
CREATE TABLE prep_inventory.station_stints (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 store_id text NOT NULL,
 staff_member_id uuid NOT NULL,
 station_code text NOT NULL,
 business_date date NOT NULL,
 started_at timestamptz NOT NULL DEFAULT now(),
 source text NOT NULL CHECK (source IN ('board', 'self', 'schedule')),
 assigned_by text NOT NULL,
 note text,
 request_key uuid NOT NULL UNIQUE,
 request_fingerprint bytea NOT NULL CHECK (octet_length(request_fingerprint) = 32),
 FOREIGN KEY (staff_member_id, store_id) REFERENCES public.staff_members(id, store_id),
 FOREIGN KEY (store_id, station_code) REFERENCES prep_inventory.stations(store_id, code)
);
CREATE INDEX station_stints_day ON prep_inventory.station_stints(store_id, business_date);
CREATE INDEX station_stints_member ON prep_inventory.station_stints(staff_member_id, started_at);

CREATE TABLE prep_inventory.stint_ends (
 stint_id uuid PRIMARY KEY REFERENCES prep_inventory.station_stints(id),
 ended_at timestamptz NOT NULL DEFAULT now(),
 ended_by text NOT NULL,
 reason text NOT NULL CHECK (reason IN ('moved', 'off_station', 'shift_end')),
 -- Set when the end was its own request (off station / end of shift), so a retry replays it.
 request_key uuid UNIQUE,
 request_fingerprint bytea CHECK (octet_length(request_fingerprint) = 32),
 CHECK ((request_key IS NULL) = (request_fingerprint IS NULL))
);

-- One open stint per person: a move ends the current one first, in the same transaction.
CREATE FUNCTION prep_inventory.guard_station_stint() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 PERFORM 1 FROM public.staff_members WHERE id = NEW.staff_member_id FOR UPDATE;
 IF NOT (SELECT active FROM public.staff_members WHERE id = NEW.staff_member_id) THEN RAISE EXCEPTION 'Only active staff can work a station'; END IF;
 IF NOT (SELECT active FROM prep_inventory.stations WHERE store_id = NEW.store_id AND code = NEW.station_code) THEN RAISE EXCEPTION 'That station is not active'; END IF;
 IF EXISTS (SELECT 1 FROM prep_inventory.station_stints s WHERE s.staff_member_id = NEW.staff_member_id
     AND NOT EXISTS (SELECT 1 FROM prep_inventory.stint_ends e WHERE e.stint_id = s.id))
 THEN RAISE EXCEPTION 'This person is already on a station; end or move that stint first'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER guard_stint BEFORE INSERT ON prep_inventory.station_stints FOR EACH ROW EXECUTE FUNCTION prep_inventory.guard_station_stint();

CREATE FUNCTION prep_inventory.guard_station_stint_end() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.ended_at < (SELECT started_at FROM prep_inventory.station_stints WHERE id = NEW.stint_id) THEN RAISE EXCEPTION 'A stint cannot end before it started'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER guard_stint_end BEFORE INSERT ON prep_inventory.stint_ends FOR EACH ROW EXECUTE FUNCTION prep_inventory.guard_station_stint_end();

-- Station time for metrics: each stint with its end (open stints have no end yet).
CREATE VIEW prep_inventory.station_time AS
 SELECT s.id AS stint_id, s.store_id, s.staff_member_id, m.name AS staff_name, s.station_code, st.name AS station_name, st.department,
  s.business_date, s.started_at, e.ended_at, e.reason AS end_reason, s.source,
  CASE WHEN e.ended_at IS NULL THEN NULL ELSE e.ended_at - s.started_at END AS duration
 FROM prep_inventory.station_stints s
 JOIN public.staff_members m ON m.id = s.staff_member_id
 JOIN prep_inventory.stations st ON st.store_id = s.store_id AND st.code = s.station_code
 LEFT JOIN prep_inventory.stint_ends e ON e.stint_id = s.id;

-- Stations may be renamed or switched off, never deleted or re-coded.
CREATE FUNCTION prep_inventory.guard_station_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'Stations are switched off, not deleted'; END IF;
 IF (NEW.store_id, NEW.code, NEW.department, NEW.created_at) IS DISTINCT FROM (OLD.store_id, OLD.code, OLD.department, OLD.created_at)
 THEN RAISE EXCEPTION 'Only a station''s name, position or active flag can change'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER guard_station_change BEFORE UPDATE OR DELETE ON prep_inventory.stations FOR EACH ROW EXECUTE FUNCTION prep_inventory.guard_station_change();

DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['product_stations','station_stints','stint_ends'] LOOP
  EXECUTE format('CREATE TRIGGER immutable_fact BEFORE UPDATE OR DELETE ON prep_inventory.%I
      FOR EACH ROW EXECUTE FUNCTION purchasing.reject_fact_change()', t);
 END LOOP;
 FOREACH t IN ARRAY ARRAY['stations','product_stations','station_stints','stint_ends'] LOOP
  EXECUTE format('REVOKE ALL ON prep_inventory.%I FROM PUBLIC', t);
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN EXECUTE format('REVOKE ALL ON prep_inventory.%I FROM anon', t); END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN EXECUTE format('REVOKE ALL ON prep_inventory.%I FROM authenticated', t); END IF;
 END LOOP;
END $$;
REVOKE ALL ON prep_inventory.station_time FROM PUBLIC;
REVOKE ALL ON FUNCTION prep_inventory.guard_station_stint(), prep_inventory.guard_station_stint_end(), prep_inventory.guard_station_change() FROM PUBLIC;
COMMIT;
