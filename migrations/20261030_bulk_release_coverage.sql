-- M3 Bulk supply follow-up: a maker's Bulk run cannot be released while another store's live
-- scheduled request for that run is left uncovered. Each requested item must be in the run
-- (not omitted) and planned at no less than the amount requested; a to-par task always is,
-- because the request is added to its need. A fixed-quantity override must cover it too.
BEGIN;
SET LOCAL lock_timeout = '5s';

CREATE FUNCTION prep_inventory.guard_bulk_release() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE identity prep_inventory.day_lists; missing text;
BEGIN
 IF NEW.action <> 'release' THEN RETURN NEW; END IF;
 SELECT * INTO identity FROM prep_inventory.day_lists WHERE id = NEW.list_id;
 IF identity.track <> 'bulk' THEN RETURN NEW; END IF;
 SELECT string_agg(l.maker_product_id::text, ', ') INTO missing FROM (
   SELECT l.maker_product_id, sum(l.requested_base_quantity) AS asked FROM prep_inventory.bulk_request_lines l
    JOIN prep_inventory.bulk_requests r ON r.id = l.request_id
    WHERE r.maker_store_id = identity.store_id AND r.run_date = identity.prep_date AND r.kind = 'scheduled'
     AND NOT EXISTS (SELECT 1 FROM prep_inventory.bulk_events e WHERE e.request_id = r.id AND e.action = 'cancel')
    GROUP BY l.maker_product_id) l
  WHERE l.asked > 0 AND NOT EXISTS (SELECT 1 FROM prep_inventory.day_tasks t WHERE t.version_id = NEW.draft_version_id
   AND t.product_id = l.maker_product_id AND t.included AND t.planned_base_quantity >= l.asked);
 IF missing IS NOT NULL THEN RAISE EXCEPTION 'Another store''s Bulk request is not covered by this run'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER guard_bulk_release BEFORE INSERT ON prep_inventory.execution_events
 FOR EACH ROW EXECUTE FUNCTION prep_inventory.guard_bulk_release();
REVOKE ALL ON FUNCTION prep_inventory.guard_bulk_release() FROM PUBLIC;
COMMIT;
