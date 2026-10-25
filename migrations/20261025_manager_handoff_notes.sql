-- Additive receiving journal. No operational data, timezone configuration or role grants.
BEGIN;
CREATE SCHEMA operations;
REVOKE ALL ON SCHEMA operations FROM PUBLIC;

CREATE TABLE operations.store_settings (
 store_id text PRIMARY KEY REFERENCES public.stores(id),
 timezone_name text NOT NULL CHECK (length(timezone_name) BETWEEN 1 AND 100),
 revision integer NOT NULL CHECK (revision > 0)
);
CREATE TABLE operations.handoff_notes (
 id uuid PRIMARY KEY,
 store_id text NOT NULL REFERENCES operations.store_settings(store_id),
 business_date date NOT NULL,
 prep_track text NOT NULL CHECK (prep_track IN ('daily','bulk')),
 creator_id text NOT NULL CHECK (length(creator_id) BETWEEN 1 AND 160),
 timezone_name text NOT NULL,
 settings_revision integer NOT NULL CHECK (settings_revision > 0),
 revision integer NOT NULL CHECK (revision > 0),
 status text NOT NULL CHECK (status IN ('draft','submitted')),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 first_submitted_at timestamptz,
 UNIQUE (store_id,id),
 UNIQUE (store_id,business_date,prep_track),
 CHECK ((status='draft' AND first_submitted_at IS NULL) OR (status='submitted' AND first_submitted_at IS NOT NULL))
);
CREATE TABLE operations.handoff_note_revisions (
 store_id text NOT NULL,
 note_id uuid NOT NULL,
 revision integer NOT NULL CHECK (revision > 0),
 action text NOT NULL CHECK (action IN ('create_draft','save_draft','submit','correct')),
 actor_id text NOT NULL CHECK (length(actor_id) BETWEEN 1 AND 160),
 recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 status text NOT NULL CHECK (status IN ('draft','submitted')),
 summary text NOT NULL CHECK (length(btrim(summary)) BETWEEN 1 AND 6000),
 next_shift_note text NOT NULL CHECK (length(next_shift_note) <= 4000),
 reported_readiness text NOT NULL CHECK (reported_readiness IN ('not_assessed','ready','action_needed')),
 correction_reason text NOT NULL DEFAULT '' CHECK (length(correction_reason) <= 2000),
 PRIMARY KEY (store_id,note_id,revision),
 FOREIGN KEY (store_id,note_id) REFERENCES operations.handoff_notes(store_id,id),
 CHECK ((action='correct' AND length(btrim(correction_reason))>0) OR (action<>'correct' AND correction_reason=''))
);
ALTER TABLE operations.handoff_notes ADD CONSTRAINT handoff_current_revision_fk
 FOREIGN KEY (store_id,id,revision) REFERENCES operations.handoff_note_revisions(store_id,note_id,revision)
 DEFERRABLE INITIALLY DEFERRED;

CREATE TABLE operations.handoff_command_receipts (
 store_id text NOT NULL,
 actor_id text NOT NULL CHECK (length(actor_id) BETWEEN 1 AND 160),
 request_key uuid NOT NULL,
 request_fingerprint text NOT NULL CHECK (request_fingerprint ~ '^[a-f0-9]{64}$'),
 note_id uuid NOT NULL,
 accepted_revision integer NOT NULL,
 recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY (store_id,actor_id,request_key),
 FOREIGN KEY (store_id,note_id,accepted_revision) REFERENCES operations.handoff_note_revisions(store_id,note_id,revision)
);

CREATE FUNCTION operations.guard_handoff_header() RETURNS trigger LANGUAGE plpgsql
SET search_path=pg_catalog AS $$
BEGIN
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Handoff history cannot be deleted'; END IF;
 IF TG_OP='INSERT' THEN
  IF NEW.revision<>1 OR NEW.status<>'draft' OR NEW.first_submitted_at IS NOT NULL THEN
   RAISE EXCEPTION 'Create a first draft revision'; END IF;
 ELSE
  IF ROW(NEW.id,NEW.store_id,NEW.business_date,NEW.prep_track,NEW.creator_id,NEW.timezone_name,NEW.settings_revision,NEW.created_at)
   IS DISTINCT FROM ROW(OLD.id,OLD.store_id,OLD.business_date,OLD.prep_track,OLD.creator_id,OLD.timezone_name,OLD.settings_revision,OLD.created_at)
   OR NEW.revision<>OLD.revision+1 OR (OLD.status='submitted' AND NEW.status<>'submitted')
   OR (OLD.first_submitted_at IS NOT NULL AND NEW.first_submitted_at IS DISTINCT FROM OLD.first_submitted_at)
   THEN RAISE EXCEPTION 'Handoff context and revision history are immutable'; END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER handoff_header_guard BEFORE INSERT OR UPDATE OR DELETE ON operations.handoff_notes
 FOR EACH ROW EXECUTE FUNCTION operations.guard_handoff_header();

CREATE FUNCTION operations.guard_handoff_history() RETURNS trigger LANGUAGE plpgsql
SET search_path=pg_catalog AS $$
DECLARE h operations.handoff_notes%ROWTYPE; previous_status text;
BEGIN
 IF TG_OP<>'INSERT' THEN RAISE EXCEPTION 'Handoff evidence is append-only'; END IF;
 IF TG_TABLE_NAME='handoff_note_revisions' THEN
  SELECT * INTO h FROM operations.handoff_notes WHERE store_id=NEW.store_id AND id=NEW.note_id;
  IF NOT FOUND OR h.revision<>NEW.revision OR h.status<>NEW.status THEN
   RAISE EXCEPTION 'Revision must match the current scoped header'; END IF;
  IF NEW.revision=1 THEN
   IF NEW.action<>'create_draft' OR NEW.status<>'draft' THEN RAISE EXCEPTION 'Invalid first draft'; END IF;
  ELSE
   SELECT status INTO previous_status FROM operations.handoff_note_revisions
    WHERE store_id=NEW.store_id AND note_id=NEW.note_id AND revision=NEW.revision-1;
   IF NOT FOUND OR NOT ((previous_status='draft' AND NEW.action='save_draft' AND NEW.status='draft')
    OR (previous_status='draft' AND NEW.action='submit' AND NEW.status='submitted')
    OR (previous_status='submitted' AND NEW.action='correct' AND NEW.status='submitted'))
    THEN RAISE EXCEPTION 'Invalid handoff transition'; END IF;
  END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER handoff_revision_guard BEFORE INSERT OR UPDATE OR DELETE ON operations.handoff_note_revisions
 FOR EACH ROW EXECUTE FUNCTION operations.guard_handoff_history();
CREATE TRIGGER handoff_receipt_guard BEFORE UPDATE OR DELETE ON operations.handoff_command_receipts
 FOR EACH ROW EXECUTE FUNCTION operations.guard_handoff_history();

CREATE FUNCTION operations.refuse_handoff_truncate() RETURNS trigger LANGUAGE plpgsql
SET search_path=pg_catalog AS $$
BEGIN
 RAISE EXCEPTION 'Handoff history cannot be truncated';
END $$;
CREATE TRIGGER handoff_notes_no_truncate BEFORE TRUNCATE ON operations.handoff_notes
 FOR EACH STATEMENT EXECUTE FUNCTION operations.refuse_handoff_truncate();
CREATE TRIGGER handoff_revisions_no_truncate BEFORE TRUNCATE ON operations.handoff_note_revisions
 FOR EACH STATEMENT EXECUTE FUNCTION operations.refuse_handoff_truncate();
CREATE TRIGGER handoff_receipts_no_truncate BEFORE TRUNCATE ON operations.handoff_command_receipts
 FOR EACH STATEMENT EXECUTE FUNCTION operations.refuse_handoff_truncate();

ALTER TABLE operations.store_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE operations.handoff_notes ENABLE ROW LEVEL SECURITY;
ALTER TABLE operations.handoff_note_revisions ENABLE ROW LEVEL SECURITY;
ALTER TABLE operations.handoff_command_receipts ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON ALL TABLES IN SCHEMA operations FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA operations FROM PUBLIC;
-- Existing client-role default ACLs must not expose a new private namespace.
DO $clients$
DECLARE client_role text;
BEGIN
 FOR client_role IN SELECT rolname FROM pg_catalog.pg_roles WHERE rolname IN ('anon','authenticated','service_role') LOOP
  EXECUTE format('REVOKE ALL ON SCHEMA operations FROM %I',client_role);
  EXECUTE format('REVOKE ALL ON ALL TABLES IN SCHEMA operations FROM %I',client_role);
  EXECUTE format('REVOKE ALL ON ALL FUNCTIONS IN SCHEMA operations FROM %I',client_role);
 END LOOP;
END $clients$;
COMMIT;
