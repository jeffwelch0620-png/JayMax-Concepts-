-- Reviewed zero-balance scope changes at an active closing-count boundary.
-- Requires the native purchase, physical count, and corrections migrations.
BEGIN;
CREATE TABLE actual_inventory.scope_bridges (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 store_id text NOT NULL,
 anchor_closure_id uuid NOT NULL UNIQUE,
 old_closing_snapshot_id uuid NOT NULL,
 new_opening_snapshot_id uuid NOT NULL,
 note text NOT NULL CHECK(length(btrim(note))>0),
 plan_snapshot jsonb NOT NULL CHECK(jsonb_typeof(plan_snapshot)='object'),
 request_key uuid NOT NULL UNIQUE,
 request_fingerprint bytea NOT NULL CHECK(octet_length(request_fingerprint)=32),
 confirmed_by text NOT NULL,
 confirmed_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(id,store_id),
 FOREIGN KEY(anchor_closure_id,store_id) REFERENCES actual_inventory.period_closures(id,store_id),
 FOREIGN KEY(old_closing_snapshot_id,store_id) REFERENCES actual_inventory.count_snapshots(id,store_id),
 FOREIGN KEY(new_opening_snapshot_id,store_id) REFERENCES actual_inventory.count_snapshots(id,store_id)
);
ALTER TABLE actual_inventory.period_closures ADD COLUMN opening_bridge_id uuid;
ALTER TABLE actual_inventory.period_closures ADD CONSTRAINT opening_bridge_same_store
 FOREIGN KEY(opening_bridge_id,store_id) REFERENCES actual_inventory.scope_bridges(id,store_id);
CREATE VIEW actual_inventory.active_scope_bridges AS
 SELECT b.* FROM actual_inventory.scope_bridges b
 JOIN actual_inventory.active_period_closures anchor ON anchor.id=b.anchor_closure_id;

CREATE FUNCTION actual_inventory.guard_scope_bridge() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE anchor actual_inventory.period_closures; old_count actual_inventory.count_snapshots;
 new_count actual_inventory.count_snapshots; pending actual_inventory.period_closures;
BEGIN
 INSERT INTO public.store_state(store_id) VALUES(NEW.store_id) ON CONFLICT(store_id) DO NOTHING;
 PERFORM 1 FROM public.store_state WHERE store_id=NEW.store_id FOR UPDATE;
 SELECT * INTO STRICT anchor FROM actual_inventory.active_period_closures
  WHERE id=NEW.anchor_closure_id AND store_id=NEW.store_id;
 IF anchor.closing_snapshot_id<>NEW.old_closing_snapshot_id OR EXISTS(
  SELECT 1 FROM actual_inventory.active_period_closures WHERE store_id=NEW.store_id AND period_end_exclusive>anchor.period_end_exclusive)
 THEN RAISE EXCEPTION 'Scope handoff must start from the latest active closing count'; END IF;
 SELECT * INTO STRICT old_count FROM actual_inventory.count_snapshots WHERE id=NEW.old_closing_snapshot_id AND store_id=NEW.store_id;
 SELECT * INTO STRICT new_count FROM actual_inventory.count_snapshots WHERE id=NEW.new_opening_snapshot_id AND store_id=NEW.store_id;
 IF old_count.status<>'complete' OR new_count.status<>'complete' OR old_count.scope_id=new_count.scope_id
  OR old_count.count_date<>new_count.count_date OR old_count.timing<>new_count.timing
  OR (SELECT revision FROM actual_inventory.scopes WHERE id=new_count.scope_id)<=
     (SELECT revision FROM actual_inventory.scopes WHERE id=old_count.scope_id)
  OR EXISTS(SELECT 1 FROM actual_inventory.count_snapshots WHERE corrects_snapshot_id IN(old_count.id,new_count.id))
 THEN RAISE EXCEPTION 'Scope handoff requires current complete counts at the same physical boundary and a newer scope'; END IF;
 IF (SELECT count(*) FROM actual_inventory.count_lines WHERE snapshot_id=old_count.id)<>
    (SELECT count(*) FROM actual_inventory.scope_items WHERE scope_id=old_count.scope_id)
 OR (SELECT count(*) FROM actual_inventory.count_lines WHERE snapshot_id=new_count.id)<>
    (SELECT count(*) FROM actual_inventory.scope_items WHERE scope_id=new_count.scope_id)
 OR EXISTS(SELECT 1 FROM actual_inventory.count_lines WHERE snapshot_id IN(old_count.id,new_count.id) AND NOT confirmed)
 THEN RAISE EXCEPTION 'Every scope item needs a confirmed physical quantity and value'; END IF;
 IF EXISTS(
  SELECT 1 FROM (SELECT * FROM actual_inventory.count_lines WHERE snapshot_id=old_count.id) a
  FULL JOIN (SELECT * FROM actual_inventory.count_lines WHERE snapshot_id=new_count.id) b USING(item_code)
  WHERE (a.item_code IS NOT NULL AND b.item_code IS NOT NULL AND
    (a.base_unit IS DISTINCT FROM b.base_unit OR a.base_quantity IS DISTINCT FROM b.base_quantity OR a.inventory_value IS DISTINCT FROM b.inventory_value))
   OR (a.item_code IS NULL AND (b.base_quantity<>0 OR b.inventory_value<>0))
   OR (b.item_code IS NULL AND (a.base_quantity<>0 OR a.inventory_value<>0))
 ) THEN RAISE EXCEPTION 'Carry shared quantities and values exactly; additions and removals require explicit zero balances'; END IF;
 SELECT * INTO pending FROM actual_inventory.pending_reclosures WHERE store_id=NEW.store_id ORDER BY period_start,id LIMIT 1;
 IF FOUND AND (pending.period_start<>anchor.period_end_exclusive
  OR NOT actual_inventory.count_descends_from(new_count.id,pending.opening_snapshot_id))
 THEN RAISE EXCEPTION 'Finish older reopened periods; rebuild only the handoff needed by the next replacement'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER scope_bridge_guard BEFORE INSERT ON actual_inventory.scope_bridges
 FOR EACH ROW EXECUTE FUNCTION actual_inventory.guard_scope_bridge();
CREATE TRIGGER immutable_fact BEFORE UPDATE OR DELETE ON actual_inventory.scope_bridges
 FOR EACH ROW EXECUTE FUNCTION purchasing.reject_fact_change();

CREATE OR REPLACE FUNCTION actual_inventory.guard_recount() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE prior actual_inventory.count_snapshots; BEGIN
 IF NEW.corrects_snapshot_id IS NULL THEN RETURN NEW; END IF;
 INSERT INTO public.store_state(store_id) VALUES(NEW.store_id) ON CONFLICT(store_id) DO NOTHING;
 PERFORM 1 FROM public.store_state WHERE store_id=NEW.store_id FOR UPDATE;
 SELECT * INTO STRICT prior FROM actual_inventory.count_snapshots WHERE id=NEW.corrects_snapshot_id AND store_id=NEW.store_id;
 IF prior.scope_id<>NEW.scope_id OR prior.count_date<>NEW.count_date OR prior.timing<>NEW.timing THEN
  RAISE EXCEPTION 'A recount must keep its scope, physical date and receipt boundary'; END IF;
 IF EXISTS(SELECT 1 FROM actual_inventory.active_period_closures WHERE opening_snapshot_id=prior.id OR closing_snapshot_id=prior.id)
 OR EXISTS(SELECT 1 FROM actual_inventory.active_scope_bridges WHERE old_closing_snapshot_id=prior.id OR new_opening_snapshot_id=prior.id) THEN
  RAISE EXCEPTION 'Reopen the active period or scope handoff anchor before correcting this count'; END IF;
 RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION actual_inventory.guard_closure() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE opening actual_inventory.count_snapshots; closing actual_inventory.count_snapshots;
 prior_period actual_inventory.period_closures; next_period actual_inventory.period_closures;
 pending actual_inventory.period_closures; bridge actual_inventory.scope_bridges; has_prior boolean;
BEGIN
 INSERT INTO public.store_state(store_id) VALUES(NEW.store_id) ON CONFLICT(store_id) DO NOTHING;
 PERFORM 1 FROM public.store_state WHERE store_id=NEW.store_id FOR UPDATE;
 SELECT * INTO STRICT opening FROM actual_inventory.count_snapshots WHERE id=NEW.opening_snapshot_id AND store_id=NEW.store_id;
 SELECT * INTO STRICT closing FROM actual_inventory.count_snapshots WHERE id=NEW.closing_snapshot_id AND store_id=NEW.store_id;
 IF opening.status<>'complete' OR closing.status<>'complete' OR opening.scope_id<>closing.scope_id
  OR opening.boundary_date<>NEW.period_start OR closing.boundary_date<>NEW.period_end_exclusive THEN
  RAISE EXCEPTION 'Each period still requires complete counts in the same scope'; END IF;
 SELECT * INTO pending FROM actual_inventory.pending_reclosures WHERE store_id=NEW.store_id ORDER BY period_start,id LIMIT 1;
 IF FOUND THEN
  IF NEW.supersedes_closure_id IS DISTINCT FROM pending.id OR NEW.period_start<>pending.period_start
   OR NEW.period_end_exclusive<>pending.period_end_exclusive
   OR NOT actual_inventory.count_descends_from(NEW.opening_snapshot_id,pending.opening_snapshot_id)
   OR NOT actual_inventory.count_descends_from(NEW.closing_snapshot_id,pending.closing_snapshot_id) THEN
   RAISE EXCEPTION 'Replace the oldest reopened period using original or linked corrected counts'; END IF;
 ELSIF NEW.supersedes_closure_id IS NOT NULL THEN RAISE EXCEPTION 'Replacement requires an unresolved reopened period'; END IF;
 IF EXISTS(SELECT 1 FROM actual_inventory.active_period_closures p WHERE p.store_id=NEW.store_id
  AND NEW.period_start<p.period_end_exclusive AND NEW.period_end_exclusive>p.period_start) THEN
  RAISE EXCEPTION 'Active periods cannot overlap'; END IF;
 SELECT * INTO prior_period FROM actual_inventory.active_period_closures WHERE store_id=NEW.store_id
  AND period_end_exclusive<=NEW.period_start ORDER BY period_end_exclusive DESC LIMIT 1;
 has_prior=FOUND;
 IF has_prior THEN
  IF prior_period.period_end_exclusive<>NEW.period_start THEN RAISE EXCEPTION 'Do not skip count intervals'; END IF;
  SELECT * INTO bridge FROM actual_inventory.active_scope_bridges WHERE anchor_closure_id=prior_period.id;
  IF FOUND THEN
   IF NEW.opening_bridge_id IS DISTINCT FROM bridge.id OR NEW.opening_snapshot_id<>bridge.new_opening_snapshot_id THEN
    RAISE EXCEPTION 'Continue from the accepted scope handoff opening count'; END IF;
  ELSIF NEW.opening_bridge_id IS NOT NULL OR prior_period.closing_snapshot_id<>NEW.opening_snapshot_id THEN
   RAISE EXCEPTION 'Use the exact previous closing count or a reviewed scope handoff'; END IF;
 ELSIF NEW.opening_bridge_id IS NOT NULL THEN RAISE EXCEPTION 'A handoff requires its active predecessor'; END IF;
 SELECT * INTO next_period FROM actual_inventory.active_period_closures WHERE store_id=NEW.store_id
  AND period_start>=NEW.period_end_exclusive ORDER BY period_start LIMIT 1;
 IF FOUND AND (next_period.period_start<>NEW.period_end_exclusive OR next_period.opening_snapshot_id<>NEW.closing_snapshot_id) THEN
  RAISE EXCEPTION 'Closing count must match the next opening without a gap'; END IF;
 RETURN NEW;
END $$;
CREATE INDEX bridge_store_date ON actual_inventory.scope_bridges(store_id,confirmed_at);
REVOKE ALL ON ALL TABLES IN SCHEMA actual_inventory FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA actual_inventory FROM PUBLIC;
COMMIT;
