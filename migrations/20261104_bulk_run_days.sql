-- M2 Bulk run days (Jeff 2026-11-04): Bulk runs and scheduled Bulk requests happen only on Monday
-- or Thursday, and the par group follows the run day instead of a manager's choice: the Monday run
-- uses the weekday par (it covers Monday to Wednesday), the Thursday run the weekend par (Thursday
-- to Sunday). Spot requests may be any day. Applies to new drafts and requests only; nothing
-- recorded is changed. No stock, purchase or accounting writes.
BEGIN;
SET LOCAL lock_timeout = '5s';

-- The par group for a Bulk run on this date, or NULL when Bulk does not run that day.
CREATE FUNCTION prep_inventory.bulk_run_day_group(run date) RETURNS text LANGUAGE sql IMMUTABLE AS $$
 SELECT CASE extract(isodow FROM run)::integer WHEN 1 THEN 'weekday' WHEN 4 THEN 'weekend' END
$$;

CREATE FUNCTION prep_inventory.guard_bulk_run_day() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE identity prep_inventory.day_lists; expected text;
BEGIN
 SELECT * INTO identity FROM prep_inventory.day_lists WHERE id = NEW.list_id;
 IF identity.track = 'bulk' THEN
  expected := prep_inventory.bulk_run_day_group(identity.prep_date);
  IF expected IS NULL THEN RAISE EXCEPTION 'Bulk runs are on Monday or Thursday'; END IF;
  IF NEW.day_group IS DISTINCT FROM expected THEN
   RAISE EXCEPTION 'A Monday Bulk run uses the weekday par and a Thursday run the weekend par';
  END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER bulk_run_day BEFORE INSERT ON prep_inventory.day_list_versions
 FOR EACH ROW EXECUTE FUNCTION prep_inventory.guard_bulk_run_day();

CREATE FUNCTION prep_inventory.guard_bulk_request_day() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE expected text;
BEGIN
 IF NEW.kind = 'scheduled' THEN
  expected := prep_inventory.bulk_run_day_group(NEW.run_date);
  IF expected IS NULL THEN RAISE EXCEPTION 'Bulk runs are on Monday or Thursday; send a spot request for another day'; END IF;
  IF NEW.day_group IS DISTINCT FROM expected THEN
   RAISE EXCEPTION 'A Monday Bulk run uses the weekday par and a Thursday run the weekend par';
  END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER bulk_request_day BEFORE INSERT ON prep_inventory.bulk_requests
 FOR EACH ROW EXECUTE FUNCTION prep_inventory.guard_bulk_request_day();

REVOKE ALL ON FUNCTION prep_inventory.bulk_run_day_group(date) FROM PUBLIC;
REVOKE ALL ON FUNCTION prep_inventory.guard_bulk_run_day() FROM PUBLIC;
REVOKE ALL ON FUNCTION prep_inventory.guard_bulk_request_day() FROM PUBLIC;
COMMIT;
