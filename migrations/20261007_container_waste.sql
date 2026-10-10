-- Atomic Track 2 container loss and existing waste journal, with paired reversals.
BEGIN;
ALTER TABLE prep_inventory.container_commands DROP CONSTRAINT container_commands_action_check;
ALTER TABLE prep_inventory.container_commands ADD CHECK(action IN ('definition','profile','fill','send','return','unpack','void_fill','undo','waste','undo_waste'));
ALTER TABLE prep_inventory.container_moves DROP CONSTRAINT container_moves_action_check;
DO $$ DECLARE c record; BEGIN
 FOR c IN SELECT conname FROM pg_constraint WHERE conrelid='prep_inventory.container_moves'::regclass AND contype='c'
  AND pg_get_constraintdef(oid) LIKE '%target_move_id%' LOOP
  EXECUTE format('ALTER TABLE prep_inventory.container_moves DROP CONSTRAINT %I',c.conname);
 END LOOP;
END $$;
ALTER TABLE prep_inventory.container_moves ADD COLUMN compartment text;
ALTER TABLE prep_inventory.container_moves ADD CHECK(action IN ('send','return','unpack','void_fill','undo','waste','undo_waste'));
ALTER TABLE prep_inventory.container_moves ADD CHECK(
 (action IN ('send','return','unpack') AND quantity IS NOT NULL AND target_move_id IS NULL AND compartment IS NULL)
 OR (action='undo' AND quantity IS NULL AND target_move_id IS NOT NULL AND compartment IS NULL)
 OR (action='void_fill' AND quantity IS NULL AND target_move_id IS NULL AND compartment IS NULL)
 OR (action='waste' AND quantity IS NOT NULL AND target_move_id IS NULL AND compartment IS NOT NULL AND compartment IN ('storage','service'))
 OR (action='undo_waste' AND quantity IS NULL AND target_move_id IS NOT NULL AND compartment IS NOT NULL AND compartment IN ('storage','service')));
ALTER TABLE prep_inventory.container_moves ADD UNIQUE(id,store_id);
CREATE TABLE prep_inventory.container_waste_links (
 command_id uuid PRIMARY KEY, store_id text NOT NULL, move_id uuid NOT NULL UNIQUE, observation_id uuid NOT NULL UNIQUE,
 undo_of_command_id uuid UNIQUE, recorded_at timestamptz NOT NULL DEFAULT now(), UNIQUE(command_id,store_id),
 FOREIGN KEY(command_id,store_id) REFERENCES prep_inventory.container_commands(id,store_id),
 FOREIGN KEY(move_id,store_id) REFERENCES prep_inventory.container_moves(id,store_id),
 FOREIGN KEY(observation_id,store_id) REFERENCES prep_inventory.observations(id,store_id),
 FOREIGN KEY(undo_of_command_id,store_id) REFERENCES prep_inventory.container_waste_links(command_id,store_id)
);
CREATE OR REPLACE FUNCTION prep_inventory.check_container_move() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE f prep_inventory.container_fills; last prep_inventory.container_moves; q numeric; ds numeric:=0; dv numeric:=0; n integer; st numeric; sv numeric; body jsonb;
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
   IF last.id IS DISTINCT FROM NEW.target_move_id OR last.action IS DISTINCT FROM 'waste' OR NEW.performed_at<>last.performed_at OR NEW.compartment IS DISTINCT FROM last.compartment
   THEN RAISE EXCEPTION 'Waste reversal requires latest original loss at original instant'; END IF;
   ds:=-last.storage_delta;dv:=-last.service_delta;
 END CASE;
 IF (NEW.storage_delta,NEW.service_delta) IS DISTINCT FROM (ds,dv) OR st+ds<0 OR sv+dv<0
  OR (NEW.action NOT IN ('undo','undo_waste','void_fill') AND NEW.performed_at<greatest(f.performed_at,(SELECT max(performed_at) FROM prep_inventory.container_moves WHERE fill_id=f.id)))
 THEN RAISE EXCEPTION 'Container movement is unbalanced, overdrawn or out of order'; END IF;
 RETURN NEW;
END $$;
CREATE FUNCTION prep_inventory.guard_container_waste_link() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE c prep_inventory.container_commands; o prep_inventory.observations; m prep_inventory.container_moves;
BEGIN
 SELECT * INTO STRICT c FROM prep_inventory.container_commands WHERE id=NEW.command_id;
 SELECT * INTO STRICT o FROM prep_inventory.observations WHERE id=NEW.observation_id;
 SELECT * INTO STRICT m FROM prep_inventory.container_moves WHERE id=NEW.move_id;
 IF c.created_xid IS DISTINCT FROM pg_current_xact_id() OR o.created_xid IS DISTINCT FROM c.created_xid
  OR c.recorded_at IS DISTINCT FROM transaction_timestamp() OR o.recorded_at IS DISTINCT FROM c.recorded_at
  OR m.command_id IS DISTINCT FROM c.id OR c.result_id IS DISTINCT FROM m.id OR c.action NOT IN ('waste','undo_waste')
 THEN RAISE EXCEPTION 'Container waste link must join its exact command, move and observation atomically'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER container_waste_link_guard BEFORE INSERT ON prep_inventory.container_waste_links FOR EACH ROW EXECUTE FUNCTION prep_inventory.guard_container_waste_link();
CREATE TRIGGER container_waste_link_immutable BEFORE UPDATE OR DELETE ON prep_inventory.container_waste_links FOR EACH ROW EXECUTE FUNCTION purchasing.reject_fact_change();
CREATE FUNCTION prep_inventory.seal_container_waste_command() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE l prep_inventory.container_waste_links; old prep_inventory.container_waste_links; o prep_inventory.observations;
 m prep_inventory.container_moves; f prep_inventory.container_fills; p prep_inventory.container_profiles; body jsonb;
BEGIN
 SELECT * INTO l FROM prep_inventory.container_waste_links WHERE command_id=NEW.id;
 IF NEW.action NOT IN ('waste','undo_waste') THEN
  IF l.command_id IS NOT NULL THEN RAISE EXCEPTION 'Ordinary container movement cannot create waste'; END IF;
  RETURN NULL;
 END IF;
 IF l.command_id IS NULL THEN RAISE EXCEPTION 'Container waste requires its paired immutable journal entry'; END IF;
 SELECT * INTO STRICT m FROM prep_inventory.container_moves WHERE id=l.move_id;
 SELECT * INTO STRICT f FROM prep_inventory.container_fills WHERE id=m.fill_id;
 SELECT * INTO STRICT p FROM prep_inventory.container_profiles WHERE id=f.profile_id;
 SELECT * INTO STRICT o FROM prep_inventory.observations WHERE id=l.observation_id;
 body:=o.review_snapshot->'body';
 IF o.purpose<>'waste' OR (o.store_id,o.source_batch_id,o.product_id,o.base_unit,o.performed_at,o.business_date,o.timezone_name,o.recorded_by,o.request_key,o.request_fingerprint)
   IS DISTINCT FROM (NEW.store_id,f.source_batch_id,f.product_id,f.base_unit,m.performed_at,m.business_date,m.timezone_name,NEW.recorded_by,NEW.request_key,NEW.request_fingerprint)
  OR NEW.review_snapshot->'waste' IS DISTINCT FROM o.review_snapshot
  OR NEW.review_snapshot->>'wasteReviewHash' IS DISTINCT FROM encode(o.review_hash,'hex')
  OR (o.review_snapshot->>'container_fill_id')::uuid IS DISTINCT FROM f.id
 THEN RAISE EXCEPTION 'Container loss differs from its linked waste scope and reviewed history'; END IF;
 IF NEW.action='waste' THEN
  IF o.kind<>'initial' OR l.undo_of_command_id IS NOT NULL OR o.reason IS DISTINCT FROM m.note
   OR NEW.review_snapshot->>'wasteEffect' IS DISTINCT FROM 'measured_loss'
   OR body->>'category' IS DISTINCT FROM NEW.review_snapshot->'body'->>'category'
   OR (body->>'quantity')::numeric IS DISTINCT FROM m.quantity OR (body->>'factor')::numeric IS DISTINCT FROM f.factor
   OR body->>'source_unit' IS DISTINCT FROM p.source_unit OR (body->>'profile_id')::uuid IS DISTINCT FROM p.unit_profile_id
   OR (body->>'product_version_id')::uuid IS DISTINCT FROM p.product_version_id
   OR (o.review_snapshot->>'baseQuantity')::numeric IS DISTINCT FROM -(m.storage_delta+m.service_delta)
  THEN RAISE EXCEPTION 'Container waste must record its exact measured pinned-unit withdrawal once'; END IF;
 ELSE
  SELECT * INTO old FROM prep_inventory.container_waste_links WHERE command_id=l.undo_of_command_id;
  IF old.move_id IS DISTINCT FROM m.target_move_id OR o.predecessor_id IS DISTINCT FROM old.observation_id OR o.kind<>'void'
   OR o.reason IS DISTINCT FROM m.note OR NEW.review_snapshot->>'wasteEffect' IS DISTINCT FROM 'reverse_loss'
   OR (NEW.review_snapshot->'sources'->>'undo_of_command_id')::uuid IS DISTINCT FROM old.command_id
   OR (m.storage_delta+m.service_delta) IS DISTINCT FROM (SELECT -quantity FROM prep_inventory.waste_movements WHERE event_id=old.observation_id AND side='apply')
  THEN RAISE EXCEPTION 'Waste reversal must restore container contents and void the original withdrawal together'; END IF;
 END IF;
 RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER container_waste_command_seal AFTER INSERT ON prep_inventory.container_commands DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION prep_inventory.seal_container_waste_command();
CREATE FUNCTION prep_inventory.seal_linked_waste_observation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.review_snapshot ? 'container_fill_id' OR EXISTS(SELECT 1 FROM prep_inventory.container_waste_links WHERE observation_id=NEW.predecessor_id) THEN
  IF NOT EXISTS(SELECT 1 FROM prep_inventory.container_waste_links WHERE observation_id=NEW.id) THEN
   RAISE EXCEPTION 'Container waste cannot be recorded or corrected separately from its contents movement';
  END IF;
 END IF;
 RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER linked_waste_observation_seal AFTER INSERT ON prep_inventory.observations DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION prep_inventory.seal_linked_waste_observation();
REVOKE ALL ON prep_inventory.container_waste_links FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA prep_inventory FROM PUBLIC;
DO $$ DECLARE r text; BEGIN
 FOREACH r IN ARRAY ARRAY['anon','authenticated'] LOOP
  IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=r) THEN
   EXECUTE format('REVOKE ALL ON prep_inventory.container_waste_links FROM %I',r);
   EXECUTE format('REVOKE ALL ON ALL FUNCTIONS IN SCHEMA prep_inventory FROM %I',r);
  END IF;
 END LOOP;
END $$;
COMMIT;
