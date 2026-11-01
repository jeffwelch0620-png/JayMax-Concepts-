-- Personal staff sign-in (Jeff 2026-10-30; safeguards confirmed 2026-10-31). An employee signs in
-- with their own name and a 4-5 digit PIN; the shared store PIN is retired at every store when
-- STAFF_PERSONAL_LOGIN_ENABLED is switched on. An owner or the Ops Lead issues a temporary PIN that the
-- employee replaces at first sign-in; 5 wrong PINs lock that person for 15 minutes unless a manager
-- unlocks them; a session ends after 12 hours or 30 minutes idle.
-- PINs and sign-in events are append-only (the newest PIN is current); only a session's
-- last-seen time and end are updated.

BEGIN;
SET LOCAL lock_timeout = '5s';

-- In the existing prep_inventory schema so the hosted backup and restore profiles cover it.

CREATE TABLE prep_inventory.staff_member_pins (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 store_id text NOT NULL,
 staff_member_id uuid NOT NULL,
 pin_hash text NOT NULL CHECK (pin_hash ~ '^pbkdf2\$[A-Za-z0-9_-]+\$[0-9a-f]{64}$'),
 temporary boolean NOT NULL,              -- issued by an owner or the Ops Lead; replaced at first sign-in
 set_by text NOT NULL CHECK (length(btrim(set_by)) > 0),
 set_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 request_key uuid UNIQUE,                 -- set when issued by a manager, so a retry replays it
 request_fingerprint bytea CHECK (octet_length(request_fingerprint) = 32),
 CHECK ((request_key IS NULL) = (request_fingerprint IS NULL)),
 CHECK (temporary = (request_key IS NOT NULL)),
 FOREIGN KEY (staff_member_id, store_id) REFERENCES public.staff_members(id, store_id)
);
CREATE INDEX staff_member_pins_current ON prep_inventory.staff_member_pins(staff_member_id, set_at DESC);

-- Wrong PINs, successful sign-ins and manager unlocks: a person is locked after 5 wrong PINs
-- since their last sign-in, unlock or new PIN, for 15 minutes after the last one.
CREATE TABLE prep_inventory.staff_sign_in_events (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 store_id text NOT NULL,
 staff_member_id uuid NOT NULL,
 kind text NOT NULL CHECK (kind IN ('failed', 'signed_in', 'unlocked')),
 at timestamptz NOT NULL DEFAULT clock_timestamp(),
 actor text NOT NULL CHECK (length(btrim(actor)) > 0),
 FOREIGN KEY (staff_member_id, store_id) REFERENCES public.staff_members(id, store_id)
);
CREATE INDEX staff_sign_in_events_member ON prep_inventory.staff_sign_in_events(staff_member_id, at);

CREATE TABLE prep_inventory.staff_sessions (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 store_id text NOT NULL,
 staff_member_id uuid NOT NULL,
 started_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 expires_at timestamptz NOT NULL,
 last_seen_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 ended_at timestamptz,
 end_reason text CHECK (end_reason IN ('signed_out', 'pin_reset')),
 CHECK ((ended_at IS NULL) = (end_reason IS NULL)),
 CHECK (expires_at > started_at),
 FOREIGN KEY (staff_member_id, store_id) REFERENCES public.staff_members(id, store_id)
);
CREATE INDEX staff_sessions_open ON prep_inventory.staff_sessions(staff_member_id) WHERE ended_at IS NULL;

-- A session keeps its person, store and times; only its last-seen time moves forward and it ends once.
CREATE FUNCTION prep_inventory.guard_staff_session() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'Staff sessions are ended, not deleted'; END IF;
 IF (NEW.id, NEW.store_id, NEW.staff_member_id, NEW.started_at, NEW.expires_at) IS DISTINCT FROM (OLD.id, OLD.store_id, OLD.staff_member_id, OLD.started_at, OLD.expires_at)
 THEN RAISE EXCEPTION 'Only a session''s last-seen time and end can change'; END IF;
 IF OLD.ended_at IS NOT NULL AND (NEW.ended_at, NEW.end_reason) IS DISTINCT FROM (OLD.ended_at, OLD.end_reason)
 THEN RAISE EXCEPTION 'A session ends once'; END IF;
 IF NEW.last_seen_at < OLD.last_seen_at THEN RAISE EXCEPTION 'A session''s last-seen time only moves forward'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER guard_staff_session BEFORE UPDATE OR DELETE ON prep_inventory.staff_sessions FOR EACH ROW EXECUTE FUNCTION prep_inventory.guard_staff_session();

DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['staff_member_pins','staff_sign_in_events'] LOOP
  EXECUTE format('CREATE TRIGGER immutable_fact BEFORE UPDATE OR DELETE ON prep_inventory.%I
      FOR EACH ROW EXECUTE FUNCTION purchasing.reject_fact_change()', t);
 END LOOP;
 FOREACH t IN ARRAY ARRAY['staff_member_pins','staff_sign_in_events','staff_sessions'] LOOP
  EXECUTE format('REVOKE ALL ON prep_inventory.%I FROM PUBLIC', t);
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN EXECUTE format('REVOKE ALL ON prep_inventory.%I FROM anon', t); END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN EXECUTE format('REVOKE ALL ON prep_inventory.%I FROM authenticated', t); END IF;
 END LOOP;
END $$;
REVOKE ALL ON FUNCTION prep_inventory.guard_staff_session() FROM PUBLIC;

COMMIT;
