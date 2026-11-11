-- AM-to-PM manager prep handoff (Jeff 2026-11-11; spec docs/handoffs/jay-rudd/berts-manager-prep-handoff-20261030.md
-- in jmax-workspace). The morning manager carries one unfinished dated prep task to a named evening manager,
-- who accepts responsibility for it. A handoff records responsibility only: it never records production,
-- changes stock, assigns staff or finishes the task. Inventory stays the only writer of food records.
-- Every change is a new revision; nothing is updated in place except the header's current revision and status.
-- Requires 20261025_manager_handoff_notes.sql (operations schema, store_settings) and the native day tasks.
BEGIN;
CREATE TABLE operations.prep_handoffs (
 id uuid PRIMARY KEY,
 store_id text NOT NULL REFERENCES operations.store_settings(store_id),
 task_id uuid NOT NULL,
 business_date date NOT NULL,
 prep_track text NOT NULL CHECK (prep_track IN ('daily','bulk','salad')),
 sender_id text NOT NULL CHECK (length(sender_id) BETWEEN 1 AND 160),
 revision integer NOT NULL CHECK (revision > 0),
 status text NOT NULL CHECK (status IN ('waiting','accepted','withdrawn')),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE (store_id,id),
 FOREIGN KEY (task_id,store_id) REFERENCES prep_inventory.day_tasks(id,store_id),
 CHECK (prep_track <> 'salad' OR store_id = 'berts')
);
-- One open handoff per task; a withdrawn one stays as history and the task can be carried again.
CREATE UNIQUE INDEX prep_handoff_one_open ON operations.prep_handoffs(task_id) WHERE status <> 'withdrawn';
CREATE INDEX prep_handoff_day ON operations.prep_handoffs(store_id,business_date,prep_track);

CREATE TABLE operations.prep_handoff_revisions (
 store_id text NOT NULL,
 handoff_id uuid NOT NULL,
 revision integer NOT NULL CHECK (revision > 0),
 action text NOT NULL CHECK (action IN ('send','correct','accept','take_over','withdraw')),
 actor_id text NOT NULL CHECK (length(actor_id) BETWEEN 1 AND 160),
 recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 status text NOT NULL CHECK (status IN ('waiting','accepted','withdrawn')),
 recipient_id text NOT NULL CHECK (length(recipient_id) BETWEEN 1 AND 160),
 remaining_base_quantity numeric NOT NULL CHECK (remaining_base_quantity >= 0),
 base_unit text NOT NULL CHECK (length(btrim(base_unit)) BETWEEN 1 AND 40),
 ready_by timestamptz NOT NULL,
 note text NOT NULL DEFAULT '' CHECK (length(note) <= 2000),
 reason text NOT NULL DEFAULT '' CHECK (length(reason) <= 1000),
 -- The linked prep facts the actor saw (task, progress, assignee) and their digest. An acceptance is
 -- only saved against the current facts, and a later change shows the handoff as needing acceptance again.
 prep_snapshot jsonb NOT NULL,
 prep_hash text NOT NULL CHECK (prep_hash ~ '^[a-f0-9]{64}$'),
 PRIMARY KEY (store_id,handoff_id,revision),
 FOREIGN KEY (store_id,handoff_id) REFERENCES operations.prep_handoffs(store_id,id),
 CHECK ((action IN ('correct','take_over','withdraw')) = (length(btrim(reason)) > 0)),
 CHECK ((action = 'withdraw') = (status = 'withdrawn')),
 CHECK ((action IN ('accept','take_over')) = (status = 'accepted') OR action = 'withdraw')
);
ALTER TABLE operations.prep_handoffs ADD CONSTRAINT prep_handoff_current_revision_fk
 FOREIGN KEY (store_id,id,revision) REFERENCES operations.prep_handoff_revisions(store_id,handoff_id,revision)
 DEFERRABLE INITIALLY DEFERRED;

CREATE TABLE operations.prep_handoff_receipts (
 store_id text NOT NULL,
 actor_id text NOT NULL CHECK (length(actor_id) BETWEEN 1 AND 160),
 request_key uuid NOT NULL,
 request_fingerprint text NOT NULL CHECK (request_fingerprint ~ '^[a-f0-9]{64}$'),
 handoff_id uuid NOT NULL,
 accepted_revision integer NOT NULL,
 recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY (store_id,actor_id,request_key),
 FOREIGN KEY (store_id,handoff_id,accepted_revision) REFERENCES operations.prep_handoff_revisions(store_id,handoff_id,revision)
);

CREATE FUNCTION operations.guard_prep_handoff() RETURNS trigger LANGUAGE plpgsql
SET search_path=pg_catalog AS $$
BEGIN
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Prep handoffs cannot be deleted'; END IF;
 IF TG_OP='INSERT' THEN
  IF NEW.revision<>1 OR NEW.status<>'waiting' THEN RAISE EXCEPTION 'A handoff starts as a waiting first revision'; END IF;
 ELSIF ROW(NEW.id,NEW.store_id,NEW.task_id,NEW.business_date,NEW.prep_track,NEW.sender_id,NEW.created_at)
   IS DISTINCT FROM ROW(OLD.id,OLD.store_id,OLD.task_id,OLD.business_date,OLD.prep_track,OLD.sender_id,OLD.created_at)
   OR NEW.revision<>OLD.revision+1 OR OLD.status='withdrawn' THEN
  RAISE EXCEPTION 'Handoff context is fixed, revisions advance by one and a withdrawn handoff is closed';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER prep_handoff_guard BEFORE INSERT OR UPDATE OR DELETE ON operations.prep_handoffs
 FOR EACH ROW EXECUTE FUNCTION operations.guard_prep_handoff();

CREATE FUNCTION operations.guard_prep_handoff_history() RETURNS trigger LANGUAGE plpgsql
SET search_path=pg_catalog AS $$
DECLARE h operations.prep_handoffs%ROWTYPE; previous text;
BEGIN
 IF TG_OP<>'INSERT' THEN RAISE EXCEPTION 'Handoff history is append-only'; END IF;
 IF TG_TABLE_NAME='prep_handoff_revisions' THEN
  SELECT * INTO h FROM operations.prep_handoffs WHERE store_id=NEW.store_id AND id=NEW.handoff_id;
  IF NOT FOUND OR h.revision<>NEW.revision OR h.status<>NEW.status THEN
   RAISE EXCEPTION 'Revision must match the current handoff'; END IF;
  IF NEW.revision=1 THEN
   IF NEW.action<>'send' OR NEW.actor_id<>h.sender_id THEN RAISE EXCEPTION 'A handoff starts with its sender'; END IF;
  ELSE
   SELECT status INTO previous FROM operations.prep_handoff_revisions
    WHERE store_id=NEW.store_id AND handoff_id=NEW.handoff_id AND revision=NEW.revision-1;
   -- waiting/accepted -> correct (back to waiting), accept, take over or withdraw; withdrawn is closed.
   IF NOT FOUND OR previous='withdrawn' OR NEW.action='send'
    OR (NEW.action='correct' AND NEW.status<>'waiting')
    OR (NEW.action='take_over' AND NEW.recipient_id<>NEW.actor_id)
    OR (NEW.action='accept' AND NEW.recipient_id<>NEW.actor_id)
    THEN RAISE EXCEPTION 'Invalid handoff transition'; END IF;
  END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER prep_handoff_revision_guard BEFORE INSERT OR UPDATE OR DELETE ON operations.prep_handoff_revisions
 FOR EACH ROW EXECUTE FUNCTION operations.guard_prep_handoff_history();
CREATE TRIGGER prep_handoff_receipt_guard BEFORE UPDATE OR DELETE ON operations.prep_handoff_receipts
 FOR EACH ROW EXECUTE FUNCTION operations.guard_prep_handoff_history();

CREATE FUNCTION operations.refuse_prep_handoff_truncate() RETURNS trigger LANGUAGE plpgsql
SET search_path=pg_catalog AS $$
BEGIN
 RAISE EXCEPTION 'Handoff history cannot be truncated';
END $$;
CREATE TRIGGER prep_handoffs_no_truncate BEFORE TRUNCATE ON operations.prep_handoffs
 FOR EACH STATEMENT EXECUTE FUNCTION operations.refuse_prep_handoff_truncate();
CREATE TRIGGER prep_handoff_revisions_no_truncate BEFORE TRUNCATE ON operations.prep_handoff_revisions
 FOR EACH STATEMENT EXECUTE FUNCTION operations.refuse_prep_handoff_truncate();
CREATE TRIGGER prep_handoff_receipts_no_truncate BEFORE TRUNCATE ON operations.prep_handoff_receipts
 FOR EACH STATEMENT EXECUTE FUNCTION operations.refuse_prep_handoff_truncate();

ALTER TABLE operations.prep_handoffs ENABLE ROW LEVEL SECURITY;
ALTER TABLE operations.prep_handoff_revisions ENABLE ROW LEVEL SECURITY;
ALTER TABLE operations.prep_handoff_receipts ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON operations.prep_handoffs, operations.prep_handoff_revisions, operations.prep_handoff_receipts FROM PUBLIC;
REVOKE ALL ON FUNCTION operations.guard_prep_handoff(), operations.guard_prep_handoff_history(),
 operations.refuse_prep_handoff_truncate() FROM PUBLIC;
DO $clients$
DECLARE client_role text;
BEGIN
 FOR client_role IN SELECT rolname FROM pg_catalog.pg_roles WHERE rolname IN ('anon','authenticated','service_role') LOOP
  EXECUTE format('REVOKE ALL ON operations.prep_handoffs, operations.prep_handoff_revisions, operations.prep_handoff_receipts FROM %I',client_role);
 END LOOP;
END $clients$;
COMMIT;
