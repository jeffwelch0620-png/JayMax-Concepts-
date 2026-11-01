-- Shortage reports (Jeff 2026-11-01): a signed-in cook tells the Shift Leader they are short on one
-- of their prep tasks, how much (optional) and why. A note only: it changes no counts, pars or
-- production. Reports are append-only; a correction is a new report.

BEGIN;
SET LOCAL lock_timeout = '5s';

-- In the existing prep_inventory schema so the hosted backup and restore profiles cover it.

CREATE TABLE prep_inventory.staff_shortage_reports (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 store_id text NOT NULL,
 business_date date NOT NULL,
 track text NOT NULL,
 task_id uuid NOT NULL,                   -- the released prep task (snapshot below keeps its name and unit)
 task_snapshot jsonb NOT NULL,
 staff_member_id uuid NOT NULL,
 short_quantity numeric CHECK (short_quantity IS NULL OR short_quantity > 0),
 reason text NOT NULL CHECK (reason IN ('out_of_ingredient', 'ran_out_of_time', 'equipment', 'other')),
 note text NOT NULL CHECK (length(btrim(note)) > 0),
 reported_by text NOT NULL CHECK (length(btrim(reported_by)) > 0),
 identity_verified boolean NOT NULL,
 reported_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 request_key uuid NOT NULL UNIQUE,
 request_fingerprint bytea NOT NULL CHECK (octet_length(request_fingerprint) = 32),
 FOREIGN KEY (staff_member_id, store_id) REFERENCES public.staff_members(id, store_id)
);
CREATE INDEX staff_shortage_reports_day ON prep_inventory.staff_shortage_reports(store_id, business_date);

CREATE TRIGGER immutable_fact BEFORE UPDATE OR DELETE ON prep_inventory.staff_shortage_reports
 FOR EACH ROW EXECUTE FUNCTION purchasing.reject_fact_change();
REVOKE ALL ON prep_inventory.staff_shortage_reports FROM PUBLIC;
DO $$ BEGIN
 IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN REVOKE ALL ON prep_inventory.staff_shortage_reports FROM anon; END IF;
 IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN REVOKE ALL ON prep_inventory.staff_shortage_reports FROM authenticated; END IF;
END $$;

COMMIT;
