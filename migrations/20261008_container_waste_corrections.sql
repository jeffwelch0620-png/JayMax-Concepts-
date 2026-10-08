-- Apply after 20261007_container_waste.sql. Additive correction; prior facts and retry hashes remain unchanged.
BEGIN;
SET LOCAL lock_timeout = '5s';
CREATE FUNCTION prep_inventory.can_reverse_container_waste(p_fill uuid,p_target uuid)
RETURNS boolean LANGUAGE sql STABLE AS $$
 SELECT EXISTS(SELECT 1 FROM prep_inventory.container_moves target
  WHERE target.id=p_target AND target.fill_id=p_fill AND target.action='waste'
   AND NOT EXISTS(SELECT 1 FROM prep_inventory.container_moves later
    WHERE later.fill_id=p_fill AND later.revision>target.revision
     AND (later.action NOT IN ('send','return','undo')
      OR (later.action='undo' AND NOT EXISTS(SELECT 1 FROM prep_inventory.container_moves original
        WHERE original.id=later.target_move_id AND original.fill_id=p_fill AND original.action IN ('send','return'))))))
$$;
CREATE OR REPLACE FUNCTION prep_inventory.check_container_move() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE f prep_inventory.container_fills; last prep_inventory.container_moves; target prep_inventory.container_moves; q numeric; ds numeric:=0; dv numeric:=0; n integer; st numeric; sv numeric; body jsonb;
BEGIN
 SELECT * INTO f FROM prep_inventory.container_fills WHERE id=NEW.fill_id;
 SELECT * INTO last FROM prep_inventory.container_moves WHERE fill_id=f.id ORDER BY revision DESC LIMIT 1;
 SELECT count(*),coalesce(sum(storage_delta),0)+f.base_quantity,coalesce(sum(service_delta),0) INTO n,st,sv FROM prep_inventory.container_moves WHERE fill_id=f.id;
 SELECT review_snapshot->'body' INTO body FROM prep_inventory.container_commands WHERE id=NEW.command_id;
 IF NEW.revision<>n+1 OR NEW.timezone_name<>f.timezone_name OR body->'calendar_date_confirmed' IS DISTINCT FROM 'true'::jsonb
  OR body->>'action' IS DISTINCT FROM NEW.action OR (body->>'quantity')::numeric IS DISTINCT FROM NEW.quantity
  OR EXISTS(SELECT 1 FROM prep_inventory.container_moves WHERE fill_id=f.id AND action='void_fill')
 THEN RAISE EXCEPTION 'Movement requires current container revision and exact reviewed quantity'; END IF;
 q:=NEW.quantity*f.factor;
 CASE NEW.action
  WHEN 'send' THEN ds:=-q;dv:=q;
  WHEN 'return' THEN ds:=q;dv:=-q;
  WHEN 'unpack' THEN ds:=-q;
  WHEN 'void_fill' THEN
   IF n<>0 OR NEW.performed_at<>f.performed_at THEN RAISE EXCEPTION 'Only unused fill at its original instant can be voided'; END IF;
   ds:=-f.base_quantity;
  WHEN 'undo' THEN
   IF last.id IS DISTINCT FROM NEW.target_move_id OR last.action NOT IN ('send','return','unpack') OR NEW.performed_at<>last.performed_at THEN RAISE EXCEPTION 'Undo requires latest original movement at original instant'; END IF;
   ds:=-last.storage_delta;dv:=-last.service_delta;
  WHEN 'waste' THEN
   IF body->'contents_measured' IS DISTINCT FROM 'true'::jsonb OR body->>'compartment' IS DISTINCT FROM NEW.compartment
    OR body->>'category' NOT IN ('storage_spoilage','service_discard','other') OR body->>'category' IS NULL
    OR (body->>'category'='storage_spoilage' AND NEW.compartment<>'storage')
    OR (body->>'category'='service_discard' AND NEW.compartment<>'service')
   THEN RAISE EXCEPTION 'Container waste requires explicit measured loss and matching category'; END IF;
   IF NEW.compartment='storage' THEN ds:=-q; ELSE dv:=-q; END IF;
  WHEN 'undo_waste' THEN
   SELECT * INTO target FROM prep_inventory.container_moves WHERE id=NEW.target_move_id AND fill_id=f.id;
   IF NOT prep_inventory.can_reverse_container_waste(f.id,NEW.target_move_id)
    OR NEW.performed_at IS DISTINCT FROM target.performed_at OR NEW.compartment IS DISTINCT FROM target.compartment
   THEN RAISE EXCEPTION 'Waste reversal requires an unreversed loss with no later quantity-changing dependencies'; END IF;
   ds:=-target.storage_delta;dv:=-target.service_delta;
 END CASE;
 IF (NEW.storage_delta,NEW.service_delta) IS DISTINCT FROM (ds,dv) OR st+ds<0 OR sv+dv<0
  OR (NEW.action='undo_waste' AND st+sv+ds+dv>f.base_quantity)
 OR (NEW.action NOT IN ('undo','undo_waste','void_fill') AND NEW.performed_at<greatest(f.performed_at,(SELECT max(performed_at) FROM prep_inventory.container_moves WHERE fill_id=f.id)))
 THEN RAISE EXCEPTION 'Container movement is unbalanced, overdrawn or out of order'; END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION prep_inventory.can_reverse_container_waste(uuid,uuid) FROM PUBLIC;
DO $$ DECLARE r text; BEGIN
 FOREACH r IN ARRAY ARRAY['anon','authenticated'] LOOP
  IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=r) THEN
   EXECUTE format('REVOKE ALL ON FUNCTION prep_inventory.can_reverse_container_waste(uuid,uuid) FROM %I',r);
  END IF;
 END LOOP;
END $$;
COMMIT;
