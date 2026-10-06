-- Append-only reopening and replacement reports. Requires both prior migrations.
BEGIN;
ALTER TABLE actual_inventory.period_closures ADD CONSTRAINT closure_id_store_unique UNIQUE(id,store_id);
ALTER TABLE actual_inventory.period_closures ADD COLUMN supersedes_closure_id uuid;
ALTER TABLE actual_inventory.period_closures ADD CONSTRAINT replacement_same_store
 FOREIGN KEY(supersedes_closure_id,store_id) REFERENCES actual_inventory.period_closures(id,store_id);
CREATE UNIQUE INDEX one_closure_replacement ON actual_inventory.period_closures(supersedes_closure_id)
 WHERE supersedes_closure_id IS NOT NULL;
-- Reclosing unchanged counts after a late receipt must retain the original row.
DO $$ DECLARE c record; BEGIN
 FOR c IN SELECT conname FROM pg_constraint WHERE conrelid='actual_inventory.period_closures'::regclass
   AND contype='u' AND pg_get_constraintdef(oid)='UNIQUE (store_id, opening_snapshot_id, closing_snapshot_id)' LOOP
  EXECUTE format('ALTER TABLE actual_inventory.period_closures DROP CONSTRAINT %I',c.conname);
 END LOOP;
END $$;
CREATE TABLE actual_inventory.reopen_events (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 store_id text NOT NULL,
 first_closure_id uuid NOT NULL,
 closure_ids uuid[] NOT NULL CHECK(cardinality(closure_ids)>0),
 reason text NOT NULL CHECK(length(btrim(reason))>0),
 plan_snapshot jsonb NOT NULL CHECK(jsonb_typeof(plan_snapshot)='object'),
 request_key uuid NOT NULL UNIQUE,
 request_fingerprint bytea NOT NULL CHECK(octet_length(request_fingerprint)=32),
 reopened_by text NOT NULL,
 reopened_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(first_closure_id,store_id) REFERENCES actual_inventory.period_closures(id,store_id)
);
CREATE VIEW actual_inventory.active_period_closures AS
 SELECT c.* FROM actual_inventory.period_closures c WHERE NOT EXISTS
  (SELECT 1 FROM actual_inventory.reopen_events e WHERE e.store_id=c.store_id AND c.id=ANY(e.closure_ids));
CREATE VIEW actual_inventory.pending_reclosures AS
 SELECT c.* FROM actual_inventory.period_closures c WHERE EXISTS
  (SELECT 1 FROM actual_inventory.reopen_events e WHERE e.store_id=c.store_id AND c.id=ANY(e.closure_ids))
 AND NOT EXISTS(SELECT 1 FROM actual_inventory.period_closures replacement WHERE replacement.supersedes_closure_id=c.id);

CREATE FUNCTION actual_inventory.guard_reopen() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE first_period actual_inventory.period_closures; expected_ids uuid[]; BEGIN
 INSERT INTO public.store_state(store_id) VALUES(NEW.store_id) ON CONFLICT(store_id) DO NOTHING;
 PERFORM 1 FROM public.store_state WHERE store_id=NEW.store_id FOR UPDATE;
 SELECT * INTO STRICT first_period FROM actual_inventory.active_period_closures
  WHERE id=NEW.first_closure_id AND store_id=NEW.store_id;
 SELECT array_agg(id ORDER BY period_start,id) INTO expected_ids FROM actual_inventory.active_period_closures
  WHERE store_id=NEW.store_id AND period_start>=first_period.period_start;
 IF NEW.closure_ids IS DISTINCT FROM expected_ids THEN
  RAISE EXCEPTION 'Reopen the entire active suffix at this location, without omitted or foreign periods'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER reopen_suffix_guard BEFORE INSERT ON actual_inventory.reopen_events
 FOR EACH ROW EXECUTE FUNCTION actual_inventory.guard_reopen();
CREATE TRIGGER immutable_fact BEFORE UPDATE OR DELETE ON actual_inventory.reopen_events
 FOR EACH ROW EXECUTE FUNCTION purchasing.reject_fact_change();

CREATE UNIQUE INDEX one_count_recount ON actual_inventory.count_snapshots(corrects_snapshot_id)
 WHERE corrects_snapshot_id IS NOT NULL;
CREATE FUNCTION actual_inventory.guard_recount() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE prior actual_inventory.count_snapshots; BEGIN
 IF NEW.corrects_snapshot_id IS NULL THEN RETURN NEW; END IF;
 INSERT INTO public.store_state(store_id) VALUES(NEW.store_id) ON CONFLICT(store_id) DO NOTHING;
 PERFORM 1 FROM public.store_state WHERE store_id=NEW.store_id FOR UPDATE;
 SELECT * INTO STRICT prior FROM actual_inventory.count_snapshots
  WHERE id=NEW.corrects_snapshot_id AND store_id=NEW.store_id;
 IF prior.scope_id<>NEW.scope_id OR prior.count_date<>NEW.count_date OR prior.timing<>NEW.timing THEN
  RAISE EXCEPTION 'A recount must keep its scope, physical date and receipt boundary'; END IF;
 IF EXISTS(SELECT 1 FROM actual_inventory.active_period_closures
  WHERE opening_snapshot_id=prior.id OR closing_snapshot_id=prior.id) THEN
  RAISE EXCEPTION 'Reopen every active period that uses this count before correcting it'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER recount_boundary_guard BEFORE INSERT ON actual_inventory.count_snapshots
 FOR EACH ROW EXECUTE FUNCTION actual_inventory.guard_recount();
CREATE FUNCTION actual_inventory.count_descends_from(candidate uuid, original uuid) RETURNS boolean
 LANGUAGE sql STABLE AS $$
 WITH RECURSIVE ancestry AS (
  SELECT id,corrects_snapshot_id FROM actual_inventory.count_snapshots WHERE id=candidate
  UNION ALL SELECT parent.id,parent.corrects_snapshot_id FROM actual_inventory.count_snapshots parent
   JOIN ancestry child ON parent.id=child.corrects_snapshot_id
 ) SELECT EXISTS(SELECT 1 FROM ancestry WHERE id=original)
$$;

CREATE OR REPLACE FUNCTION actual_inventory.guard_closed_purchase_date() RETURNS trigger
LANGUAGE plpgsql AS $$ BEGIN
 IF NEW.classification='food' AND NEW.movement_kind<>'no_inventory' THEN
  INSERT INTO public.store_state(store_id) VALUES(NEW.store_id) ON CONFLICT(store_id) DO NOTHING;
  PERFORM 1 FROM public.store_state WHERE store_id=NEW.store_id FOR UPDATE;
  IF EXISTS(SELECT 1 FROM actual_inventory.active_period_closures
    WHERE store_id=NEW.store_id AND NEW.inventory_record_date>=period_start AND NEW.inventory_record_date<period_end_exclusive)
  THEN RAISE EXCEPTION 'Reopen affected actual-inventory periods before posting a late purchase'; END IF;
 END IF; RETURN NEW;
END $$;
CREATE OR REPLACE FUNCTION actual_inventory.guard_purchase_batch() RETURNS trigger
LANGUAGE plpgsql AS $$ DECLARE sid text; BEGIN
 SELECT store_id INTO STRICT sid FROM purchasing.document_identities WHERE id=NEW.document_id;
 INSERT INTO public.store_state(store_id) VALUES(sid) ON CONFLICT(store_id) DO NOTHING;
 PERFORM 1 FROM public.store_state WHERE store_id=sid FOR UPDATE;
 IF EXISTS(SELECT 1 FROM purchasing.document_lines l
  JOIN LATERAL(SELECT * FROM purchasing.mapping_decisions WHERE line_id=l.id ORDER BY revision DESC LIMIT 1) m ON true
  JOIN actual_inventory.active_period_closures p ON p.store_id=sid
   AND m.inventory_record_date>=p.period_start AND m.inventory_record_date<p.period_end_exclusive
  WHERE l.document_version_id=NEW.document_version_id AND m.classification='food' AND m.movement_kind<>'no_inventory')
 THEN RAISE EXCEPTION 'Late purchase would change an active closed period'; END IF;
 RETURN NEW;
END $$;
CREATE OR REPLACE FUNCTION actual_inventory.guard_closure() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE opening actual_inventory.count_snapshots; closing actual_inventory.count_snapshots;
 prior_period actual_inventory.period_closures; next_period actual_inventory.period_closures;
 pending actual_inventory.period_closures;
BEGIN
 INSERT INTO public.store_state(store_id) VALUES(NEW.store_id) ON CONFLICT(store_id) DO NOTHING;
 PERFORM 1 FROM public.store_state WHERE store_id=NEW.store_id FOR UPDATE;
 SELECT * INTO STRICT opening FROM actual_inventory.count_snapshots WHERE id=NEW.opening_snapshot_id AND store_id=NEW.store_id;
 SELECT * INTO STRICT closing FROM actual_inventory.count_snapshots WHERE id=NEW.closing_snapshot_id AND store_id=NEW.store_id;
 IF opening.status<>'complete' OR closing.status<>'complete' OR opening.scope_id<>closing.scope_id
  OR opening.boundary_date<>NEW.period_start OR closing.boundary_date<>NEW.period_end_exclusive THEN
  RAISE EXCEPTION 'Period boundaries require complete counts in the same scope'; END IF;
 SELECT * INTO pending FROM actual_inventory.pending_reclosures WHERE store_id=NEW.store_id ORDER BY period_start,id LIMIT 1;
 IF FOUND THEN
  IF NEW.supersedes_closure_id IS DISTINCT FROM pending.id
   OR NEW.period_start<>pending.period_start OR NEW.period_end_exclusive<>pending.period_end_exclusive
   OR NOT actual_inventory.count_descends_from(NEW.opening_snapshot_id,pending.opening_snapshot_id)
   OR NOT actual_inventory.count_descends_from(NEW.closing_snapshot_id,pending.closing_snapshot_id) THEN
   RAISE EXCEPTION 'Replace the oldest reopened period using its original or linked corrected counts'; END IF;
 ELSIF NEW.supersedes_closure_id IS NOT NULL THEN
  RAISE EXCEPTION 'Replacement must reference an unresolved reopened period';
 END IF;
 IF EXISTS(SELECT 1 FROM actual_inventory.active_period_closures p WHERE p.store_id=NEW.store_id
  AND NEW.period_start<p.period_end_exclusive AND NEW.period_end_exclusive>p.period_start) THEN
  RAISE EXCEPTION 'Active actual-inventory periods cannot overlap'; END IF;
 SELECT * INTO prior_period FROM actual_inventory.active_period_closures WHERE store_id=NEW.store_id
  AND period_end_exclusive<=NEW.period_start ORDER BY period_end_exclusive DESC LIMIT 1;
 IF FOUND AND (prior_period.period_end_exclusive<>NEW.period_start OR prior_period.closing_snapshot_id<>NEW.opening_snapshot_id) THEN
  RAISE EXCEPTION 'Continue from the previous closing count without a gap'; END IF;
 SELECT * INTO next_period FROM actual_inventory.active_period_closures WHERE store_id=NEW.store_id
  AND period_start>=NEW.period_end_exclusive ORDER BY period_start LIMIT 1;
 IF FOUND AND (next_period.period_start<>NEW.period_end_exclusive OR next_period.opening_snapshot_id<>NEW.closing_snapshot_id) THEN
  RAISE EXCEPTION 'Closing count must match the next opening without a gap'; END IF;
 RETURN NEW;
END $$;
CREATE INDEX reopen_event_store ON actual_inventory.reopen_events(store_id,reopened_at);
REVOKE ALL ON ALL TABLES IN SCHEMA actual_inventory FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA actual_inventory FROM PUBLIC;
COMMIT;
