-- Order schedule changes (Jeff 2026-11-01): only an owner or the Ops Lead changes a store's order
-- schedule. A weekly order day is set or removed in purchasing.order_calendar; one cycle can be
-- skipped, moved to another date (with its delivery date) or restored to its usual day. Every
-- change is kept here, append-only, with who made it and why. Nothing here changes stock, orders
-- or accounting.

BEGIN;
SET LOCAL lock_timeout = '5s';

CREATE TABLE purchasing.order_schedule_changes (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 store_id text NOT NULL,
 kind text NOT NULL CHECK (kind IN ('set_day', 'remove_day', 'skip', 'move', 'restore')),
 order_weekday smallint CHECK (order_weekday BETWEEN 0 AND 6),     -- weekly day changes (0 Monday ... 6 Sunday)
 cycle_date date,                                                   -- one cycle: skip, move or restore
 moved_to date,
 delivery_date date,
 day_before jsonb,
 day_after jsonb,
 reason text NOT NULL CHECK (length(btrim(reason)) > 0),
 changed_by text NOT NULL CHECK (length(btrim(changed_by)) > 0),
 changed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 request_key uuid NOT NULL UNIQUE,
 request_fingerprint bytea NOT NULL CHECK (octet_length(request_fingerprint) = 32),
 CHECK ((kind IN ('set_day', 'remove_day')) = (order_weekday IS NOT NULL AND cycle_date IS NULL)),
 CHECK ((kind IN ('skip', 'move', 'restore')) = (cycle_date IS NOT NULL AND order_weekday IS NULL)),
 CHECK ((kind = 'move') = (moved_to IS NOT NULL AND delivery_date IS NOT NULL)),
 CHECK (delivery_date IS NULL OR delivery_date >= moved_to),
 CHECK ((kind = 'set_day') = (day_after IS NOT NULL)),
 CHECK (kind <> 'remove_day' OR day_before IS NOT NULL)
);
CREATE INDEX order_schedule_changes_cycle ON purchasing.order_schedule_changes(store_id, cycle_date, changed_at);
CREATE INDEX order_schedule_changes_moved ON purchasing.order_schedule_changes(store_id, moved_to) WHERE moved_to IS NOT NULL;

CREATE TRIGGER immutable_fact BEFORE UPDATE OR DELETE ON purchasing.order_schedule_changes
 FOR EACH ROW EXECUTE FUNCTION purchasing.reject_fact_change();
REVOKE ALL ON purchasing.order_schedule_changes FROM PUBLIC;
DO $$ BEGIN
 IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN REVOKE ALL ON purchasing.order_schedule_changes FROM anon; END IF;
 IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN REVOKE ALL ON purchasing.order_schedule_changes FROM authenticated; END IF;
END $$;

COMMIT;
