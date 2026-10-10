-- Internal Track 2 reservations/transfers. Never deduct purchased inventory.
BEGIN;
LOCK TABLE public.prep_recipe_stock,public.prep_logs IN SHARE ROW EXCLUSIVE MODE;
CREATE TABLE prep_inventory.legacy_container_sources (
 source_table text NOT NULL, source_id text NOT NULL, store_id text NOT NULL,
 raw_record jsonb NOT NULL, captured_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(source_table,source_id,store_id)
);
INSERT INTO prep_inventory.legacy_container_sources SELECT 'prep_recipe_stock',id::text,store_id,to_jsonb(r),now() FROM public.prep_recipe_stock r;
INSERT INTO prep_inventory.legacy_container_sources SELECT 'prep_logs',id::text,store_id,to_jsonb(r),now() FROM public.prep_logs r;
-- Preserve original mixed prep/sales/container history; do not convert it into facts.
CREATE TRIGGER legacy_prep_stock_hold BEFORE INSERT OR UPDATE OR DELETE ON public.prep_recipe_stock FOR EACH ROW EXECUTE FUNCTION purchasing.reject_fact_change();
CREATE TRIGGER legacy_prep_log_hold BEFORE INSERT OR UPDATE OR DELETE ON public.prep_logs FOR EACH ROW EXECUTE FUNCTION purchasing.reject_fact_change();
CREATE TRIGGER legacy_container_raw_hold BEFORE UPDATE OR DELETE ON prep_inventory.legacy_container_sources FOR EACH ROW EXECUTE FUNCTION purchasing.reject_fact_change();

CREATE TABLE prep_inventory.container_commands (
 id uuid PRIMARY KEY, store_id text NOT NULL REFERENCES public.stores(id), action text NOT NULL,
 result_id uuid NOT NULL UNIQUE, review_snapshot jsonb NOT NULL, review_hash bytea NOT NULL CHECK(octet_length(review_hash)=32),
 recorded_by text NOT NULL CHECK(length(btrim(recorded_by))>0), recorded_at timestamptz NOT NULL DEFAULT now(),
 created_xid xid8 NOT NULL DEFAULT pg_current_xact_id(), request_key uuid NOT NULL UNIQUE,
 request_fingerprint bytea NOT NULL CHECK(octet_length(request_fingerprint)=32), UNIQUE(id,store_id),
 CHECK(action IN ('definition','profile','fill','send','return','unpack','void_fill','undo'))
);
CREATE TABLE prep_inventory.container_definitions (
 id uuid PRIMARY KEY, command_id uuid NOT NULL UNIQUE, store_id text NOT NULL,
 root_id uuid NOT NULL, predecessor_id uuid UNIQUE, revision integer NOT NULL CHECK(revision>0),
 name text NOT NULL CHECK(length(btrim(name))>0), capacity_unit text NOT NULL CHECK(capacity_unit IN ('lb','oz','g','kg','fl_oz','ml','l','gal','each')),
 stated_capacity numeric, brimful_capacity numeric, usable_capacity numeric, evidence text NOT NULL CHECK(length(btrim(evidence))>0),
 recorded_at timestamptz NOT NULL DEFAULT now(), UNIQUE(id,store_id), UNIQUE(root_id,revision),
 FOREIGN KEY(command_id,store_id) REFERENCES prep_inventory.container_commands(id,store_id),
 FOREIGN KEY(root_id,store_id) REFERENCES prep_inventory.container_definitions(id,store_id),
 FOREIGN KEY(predecessor_id,store_id) REFERENCES prep_inventory.container_definitions(id,store_id),
 CHECK((predecessor_id IS NULL AND root_id=id AND revision=1) OR (predecessor_id IS NOT NULL AND revision>1)),
 CHECK(stated_capacity IS NULL OR (stated_capacity>0 AND stated_capacity<1e16 AND scale(stated_capacity)<=12)),
 CHECK(brimful_capacity IS NULL OR (brimful_capacity>0 AND brimful_capacity<1e16 AND scale(brimful_capacity)<=12)),
 CHECK(usable_capacity IS NULL OR (usable_capacity>0 AND usable_capacity<1e16 AND scale(usable_capacity)<=12)),
 CHECK(usable_capacity IS NULL OR brimful_capacity IS NULL OR usable_capacity<=brimful_capacity)
);
CREATE TABLE prep_inventory.container_profiles (
 id uuid PRIMARY KEY, command_id uuid NOT NULL UNIQUE, store_id text NOT NULL,
 root_id uuid NOT NULL, predecessor_id uuid UNIQUE, revision integer NOT NULL CHECK(revision>0),
 definition_id uuid NOT NULL, container_root_id uuid NOT NULL, product_version_id uuid NOT NULL, product_id uuid NOT NULL, unit_profile_id uuid NOT NULL,
 source_unit text NOT NULL, base_unit text NOT NULL, factor numeric NOT NULL,
 usable_quantity numeric NOT NULL CHECK(usable_quantity>0 AND usable_quantity<1e16 AND scale(usable_quantity)<=12),
 usable_base_quantity numeric NOT NULL CHECK(usable_base_quantity=usable_quantity*factor), evidence text NOT NULL CHECK(length(btrim(evidence))>0),
 recorded_at timestamptz NOT NULL DEFAULT now(), UNIQUE(id,store_id), UNIQUE(root_id,revision),
 FOREIGN KEY(command_id,store_id) REFERENCES prep_inventory.container_commands(id,store_id),
 FOREIGN KEY(root_id,store_id) REFERENCES prep_inventory.container_profiles(id,store_id),
 FOREIGN KEY(predecessor_id,store_id) REFERENCES prep_inventory.container_profiles(id,store_id),
 FOREIGN KEY(definition_id,store_id) REFERENCES prep_inventory.container_definitions(id,store_id),
 FOREIGN KEY(container_root_id,store_id) REFERENCES prep_inventory.container_definitions(id,store_id),
 FOREIGN KEY(product_version_id,product_id,store_id) REFERENCES prep_inventory.product_versions(id,product_id,store_id),
 FOREIGN KEY(unit_profile_id,product_version_id,store_id) REFERENCES prep_inventory.unit_profiles(id,product_version_id,store_id),
 CHECK((predecessor_id IS NULL AND root_id=id AND revision=1) OR (predecessor_id IS NOT NULL AND revision>1))
);
CREATE UNIQUE INDEX container_one_profile_root ON prep_inventory.container_profiles(container_root_id,product_id) WHERE predecessor_id IS NULL;
CREATE TABLE prep_inventory.container_fills (
 id uuid PRIMARY KEY, command_id uuid NOT NULL UNIQUE, store_id text NOT NULL,
 profile_id uuid NOT NULL, source_batch_id uuid NOT NULL, product_id uuid NOT NULL, base_unit text NOT NULL,
 label text NOT NULL CHECK(length(btrim(label))>0), quantity numeric NOT NULL CHECK(quantity>0 AND quantity<1e16 AND scale(quantity)<=12),
 factor numeric NOT NULL, base_quantity numeric NOT NULL CHECK(base_quantity=quantity*factor),
 performed_at timestamptz NOT NULL, business_date date NOT NULL, timezone_name text NOT NULL, note text NOT NULL CHECK(length(btrim(note))>0),
 recorded_at timestamptz NOT NULL DEFAULT now(), UNIQUE(id,store_id),
 FOREIGN KEY(command_id,store_id) REFERENCES prep_inventory.container_commands(id,store_id),
 FOREIGN KEY(profile_id,store_id) REFERENCES prep_inventory.container_profiles(id,store_id),
 FOREIGN KEY(source_batch_id,store_id,product_id,base_unit) REFERENCES prep_inventory.batch_events(id,store_id,product_id,base_unit),
 CHECK(business_date=(performed_at AT TIME ZONE timezone_name)::date)
);
CREATE TABLE prep_inventory.container_moves (
 id uuid PRIMARY KEY, command_id uuid NOT NULL UNIQUE, store_id text NOT NULL, fill_id uuid NOT NULL,
 revision integer NOT NULL CHECK(revision>0), action text NOT NULL CHECK(action IN ('send','return','unpack','void_fill','undo')),
 quantity numeric CHECK(quantity>0 AND quantity<1e16 AND scale(quantity)<=12), target_move_id uuid UNIQUE,
 storage_delta numeric NOT NULL, service_delta numeric NOT NULL,
 performed_at timestamptz NOT NULL, business_date date NOT NULL, timezone_name text NOT NULL, note text NOT NULL CHECK(length(btrim(note))>0),
 recorded_at timestamptz NOT NULL DEFAULT now(), UNIQUE(fill_id,revision),
 FOREIGN KEY(command_id,store_id) REFERENCES prep_inventory.container_commands(id,store_id),
 FOREIGN KEY(fill_id,store_id) REFERENCES prep_inventory.container_fills(id,store_id),
 FOREIGN KEY(target_move_id) REFERENCES prep_inventory.container_moves(id),
 CHECK(business_date=(performed_at AT TIME ZONE timezone_name)::date),
 CHECK((action IN ('send','return','unpack') AND quantity IS NOT NULL AND target_move_id IS NULL)
    OR (action='undo' AND quantity IS NULL AND target_move_id IS NOT NULL)
    OR (action='void_fill' AND quantity IS NULL AND target_move_id IS NULL))
);
CREATE INDEX container_fill_source ON prep_inventory.container_fills(source_batch_id);
CREATE OR REPLACE FUNCTION prep_inventory.lot_used(source_id uuid) RETURNS numeric LANGUAGE sql STABLE AS $$
 SELECT -(coalesce((SELECT sum(quantity) FROM prep_inventory.batch_movements WHERE source_batch_id=source_id),0)
   +coalesce((SELECT sum(quantity) FROM prep_inventory.waste_movements WHERE source_batch_id=source_id),0))
   +coalesce((SELECT sum(base_quantity) FROM prep_inventory.container_fills WHERE source_batch_id=source_id),0)
   +coalesce((SELECT sum(m.storage_delta+m.service_delta) FROM prep_inventory.container_moves m JOIN prep_inventory.container_fills f ON f.id=m.fill_id WHERE f.source_batch_id=source_id),0)
$$;
CREATE FUNCTION prep_inventory.container_lot_timeline(source_id uuid) RETURNS TABLE(performed_at timestamptz,used numeric) LANGUAGE sql STABLE AS $$
 WITH changes AS (
  SELECT e.performed_at,-m.quantity AS quantity FROM prep_inventory.batch_movements m JOIN prep_inventory.batch_events e ON e.id=m.event_id WHERE m.source_batch_id=source_id
  UNION ALL SELECT e.performed_at,-m.quantity FROM prep_inventory.waste_movements m JOIN prep_inventory.observations e ON e.id=m.event_id WHERE m.source_batch_id=source_id
  UNION ALL SELECT f.performed_at,f.base_quantity FROM prep_inventory.container_fills f WHERE f.source_batch_id=source_id
  UNION ALL SELECT m.performed_at,m.storage_delta+m.service_delta FROM prep_inventory.container_moves m JOIN prep_inventory.container_fills f ON f.id=m.fill_id WHERE f.source_batch_id=source_id
 ), grouped AS (SELECT c.performed_at,sum(quantity) AS quantity FROM changes c GROUP BY c.performed_at)
 SELECT g.performed_at,sum(quantity) OVER (ORDER BY g.performed_at) FROM grouped g
$$;
CREATE FUNCTION prep_inventory.container_available_since(source_id uuid,instant timestamptz) RETURNS numeric LANGUAGE sql STABLE AS $$
 SELECT coalesce((SELECT sum(quantity) FROM prep_inventory.batch_movements WHERE event_id=source_id AND side='apply' AND kind='output'),0)
  -greatest(coalesce((SELECT used FROM prep_inventory.container_lot_timeline(source_id) WHERE performed_at<=instant ORDER BY performed_at DESC LIMIT 1),0),
    coalesce((SELECT max(used) FROM prep_inventory.container_lot_timeline(source_id) WHERE performed_at>=instant),0))
$$;
CREATE FUNCTION prep_inventory.assert_container_timeline(location_id text) RETURNS void LANGUAGE plpgsql AS $$
DECLARE source_id uuid; output numeric;
BEGIN
 FOR source_id IN SELECT DISTINCT source_batch_id FROM prep_inventory.container_fills WHERE store_id=location_id LOOP
  SELECT coalesce(sum(quantity),0) INTO output FROM prep_inventory.batch_movements WHERE event_id=source_id AND side='apply' AND kind='output';
  IF EXISTS(SELECT 1 FROM prep_inventory.container_lot_timeline(source_id) WHERE used<0 OR used>output) THEN RAISE EXCEPTION 'Container lot cannot borrow from future unpacking or overdraw at a physical instant'; END IF;
 END LOOP;
END $$;
CREATE FUNCTION prep_inventory.seal_container_timeline() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN PERFORM prep_inventory.assert_container_timeline(NEW.store_id); RETURN NULL; END $$;
CREATE CONSTRAINT TRIGGER batch_container_timeline AFTER INSERT ON prep_inventory.batch_events DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION prep_inventory.seal_container_timeline();
CREATE CONSTRAINT TRIGGER waste_container_timeline AFTER INSERT ON prep_inventory.observations DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION prep_inventory.seal_container_timeline();
CREATE FUNCTION prep_inventory.guard_container_command() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 PERFORM 1 FROM public.store_state WHERE store_id=NEW.store_id FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Container command requires store coordination'; END IF;
 IF NEW.review_snapshot->>'store_id' IS DISTINCT FROM NEW.store_id OR NEW.review_snapshot->>'action' IS DISTINCT FROM NEW.action
  OR NEW.review_snapshot->'body'->>'action' IS DISTINCT FROM NEW.action
  OR NEW.review_snapshot->>'accountingEffect' IS DISTINCT FROM 'none' OR NEW.review_snapshot->>'consumptionEffect' IS DISTINCT FROM 'none'
  THEN RAISE EXCEPTION 'Container command differs from reviewed scope'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER container_command_guard BEFORE INSERT ON prep_inventory.container_commands FOR EACH ROW EXECUTE FUNCTION prep_inventory.guard_container_command();
CREATE FUNCTION prep_inventory.guard_container_child() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE command prep_inventory.container_commands; expected jsonb; actual jsonb; root_value uuid; body_record jsonb; k text;
BEGIN
 SELECT * INTO command FROM prep_inventory.container_commands WHERE id=NEW.command_id;
 IF command.created_xid IS DISTINCT FROM pg_current_xact_id() OR command.recorded_at IS DISTINCT FROM transaction_timestamp()
   OR command.result_id IS DISTINCT FROM NEW.id OR command.review_snapshot->>'table' IS DISTINCT FROM TG_TABLE_NAME
 THEN RAISE EXCEPTION 'Container command is sealed or child differs'; END IF;
 -- Compare typed facts, including numeric and timestamp semantics, to the child.
 IF TG_TABLE_NAME IN ('container_definitions','container_profiles') THEN
  root_value:=coalesce((command.review_snapshot->'facts'->>'root_id')::uuid,NEW.id);
  expected:=command.review_snapshot->'facts'||jsonb_build_object('root_id',root_value);
 ELSE expected:=command.review_snapshot->'facts'; END IF;
 EXECUTE format('SELECT to_jsonb(jsonb_populate_record(NULL::prep_inventory.%I,$1))',TG_TABLE_NAME) INTO expected USING expected;
 actual:=to_jsonb(NEW)-ARRAY['id','command_id','store_id','recorded_at'];
 IF actual IS DISTINCT FROM (expected-ARRAY['id','command_id','store_id','recorded_at']) THEN RAISE EXCEPTION 'Container child differs from reviewed facts'; END IF;
 EXECUTE format('SELECT to_jsonb(jsonb_populate_record(NULL::prep_inventory.%I,$1))',TG_TABLE_NAME) INTO body_record USING command.review_snapshot->'body';
 FOR k IN SELECT jsonb_object_keys(command.review_snapshot->'body') LOOP
  IF actual ? k AND actual->k IS DISTINCT FROM body_record->k THEN RAISE EXCEPTION 'Container facts differ from submitted measurement'; END IF;
 END LOOP;
 RETURN NEW;
END $$;
CREATE FUNCTION prep_inventory.container_unit_scale(unit_name text) RETURNS numeric LANGUAGE sql IMMUTABLE AS $$
 SELECT CASE unit_name WHEN 'lb' THEN 453.59237 WHEN 'oz' THEN 28.349523125 WHEN 'g' THEN 1 WHEN 'kg' THEN 1000
  WHEN 'fl_oz' THEN 29.5735295625 WHEN 'gal' THEN 3785.411784 WHEN 'ml' THEN 1 WHEN 'l' THEN 1000 WHEN 'each' THEN 1 END
$$;
CREATE FUNCTION prep_inventory.check_container_definition() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE old prep_inventory.container_definitions;
BEGIN
 IF NEW.predecessor_id IS NOT NULL THEN
  SELECT * INTO old FROM prep_inventory.container_definitions WHERE id=NEW.predecessor_id;
  IF NEW.root_id<>old.root_id OR NEW.revision<>old.revision+1 THEN RAISE EXCEPTION 'Definition must extend its current root'; END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE FUNCTION prep_inventory.check_container_profile() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE d prep_inventory.container_definitions; u prep_inventory.unit_profiles; v prep_inventory.product_versions; old prep_inventory.container_profiles;
BEGIN
 SELECT * INTO d FROM prep_inventory.container_definitions WHERE id=NEW.definition_id;
 SELECT * INTO u FROM prep_inventory.unit_profiles WHERE id=NEW.unit_profile_id;
 SELECT * INTO v FROM prep_inventory.product_versions WHERE id=NEW.product_version_id;
 IF d.root_id IS DISTINCT FROM NEW.container_root_id OR (u.source_unit,u.base_units_per_source_unit,v.base_unit) IS DISTINCT FROM (NEW.source_unit,NEW.factor,NEW.base_unit)
  OR EXISTS(SELECT 1 FROM prep_inventory.container_definitions WHERE predecessor_id=d.id)
  OR EXISTS(SELECT 1 FROM prep_inventory.unit_profiles WHERE predecessor_id=u.id)
  OR EXISTS(SELECT 1 FROM prep_inventory.product_versions WHERE predecessor_id=v.id)
  OR (SELECT review_snapshot->'body'->'product_fill_measured' FROM prep_inventory.container_commands WHERE id=NEW.command_id) IS DISTINCT FROM 'true'::jsonb
 THEN RAISE EXCEPTION 'Product fill requires current verified definitions and measured conversion'; END IF;
 IF d.usable_capacity IS NOT NULL AND
  (CASE WHEN d.capacity_unit IN ('lb','oz','g','kg') THEN 'mass' WHEN d.capacity_unit='each' THEN 'count' ELSE 'volume' END)
   = (CASE WHEN NEW.base_unit IN ('lb','oz','g','kg') THEN 'mass' WHEN NEW.base_unit='each' THEN 'count' ELSE 'volume' END)
  AND NEW.usable_base_quantity*prep_inventory.container_unit_scale(NEW.base_unit)>d.usable_capacity*prep_inventory.container_unit_scale(d.capacity_unit)
 THEN RAISE EXCEPTION 'Food fill exceeds verified same-dimension usable capacity'; END IF;
 IF NEW.predecessor_id IS NOT NULL THEN
  SELECT * INTO old FROM prep_inventory.container_profiles WHERE id=NEW.predecessor_id;
  IF (NEW.root_id,NEW.revision,NEW.container_root_id,NEW.product_id) IS DISTINCT FROM (old.root_id,old.revision+1,old.container_root_id,old.product_id) THEN RAISE EXCEPTION 'Profile must extend the same identity'; END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE FUNCTION prep_inventory.check_container_fill() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE p prep_inventory.container_profiles; b prep_inventory.batch_events; body jsonb;
BEGIN
 SELECT * INTO p FROM prep_inventory.container_profiles WHERE id=NEW.profile_id;
 SELECT * INTO b FROM prep_inventory.batch_events WHERE id=NEW.source_batch_id;
 SELECT review_snapshot->'body' INTO body FROM prep_inventory.container_commands WHERE id=NEW.command_id;
 IF (p.product_id,p.base_unit,p.factor) IS DISTINCT FROM (NEW.product_id,NEW.base_unit,NEW.factor)
  OR NEW.base_quantity>p.usable_base_quantity OR b.kind='void' OR b.performed_at>NEW.performed_at
  OR EXISTS(SELECT 1 FROM prep_inventory.batch_events WHERE predecessor_id=b.id)
  OR EXISTS(SELECT 1 FROM prep_inventory.container_profiles WHERE predecessor_id=p.id)
  OR EXISTS(SELECT 1 FROM prep_inventory.container_definitions WHERE predecessor_id=p.definition_id)
  OR EXISTS(SELECT 1 FROM prep_inventory.product_versions WHERE predecessor_id=p.product_version_id)
  OR EXISTS(SELECT 1 FROM prep_inventory.unit_profiles WHERE predecessor_id=p.unit_profile_id)
  OR body->'contents_measured' IS DISTINCT FROM 'true'::jsonb OR body->'calendar_date_confirmed' IS DISTINCT FROM 'true'::jsonb
  OR (body->>'quantity')::numeric IS DISTINCT FROM NEW.quantity OR body->>'label' IS DISTINCT FROM NEW.label
  OR (SELECT timezone_name FROM prep_inventory.batch_policies WHERE store_id=NEW.store_id) IS DISTINCT FROM NEW.timezone_name
 THEN RAISE EXCEPTION 'Fill requires exact measured contents, verified profile and current source'; END IF;
 RETURN NEW;
END $$;
CREATE FUNCTION prep_inventory.check_container_move() RETURNS trigger LANGUAGE plpgsql AS $$
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
 END CASE;
 IF (NEW.storage_delta,NEW.service_delta) IS DISTINCT FROM (ds,dv) OR st+ds<0 OR sv+dv<0
  OR (NEW.action NOT IN ('undo','void_fill') AND NEW.performed_at<greatest(f.performed_at,(SELECT max(performed_at) FROM prep_inventory.container_moves WHERE fill_id=f.id)))
 THEN RAISE EXCEPTION 'Container movement is unbalanced, overdrawn or out of order'; END IF;
 RETURN NEW;
END $$;
CREATE FUNCTION prep_inventory.seal_container_command() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE total integer; child_count integer; table_name text;
BEGIN
 table_name:=NEW.review_snapshot->>'table';
 IF table_name IS DISTINCT FROM (CASE NEW.action WHEN 'definition' THEN 'container_definitions' WHEN 'profile' THEN 'container_profiles' WHEN 'fill' THEN 'container_fills' ELSE 'container_moves' END) THEN RAISE EXCEPTION 'Command action/table mismatch'; END IF;
 SELECT (SELECT count(*) FROM prep_inventory.container_definitions WHERE command_id=NEW.id)
  +(SELECT count(*) FROM prep_inventory.container_profiles WHERE command_id=NEW.id)
  +(SELECT count(*) FROM prep_inventory.container_fills WHERE command_id=NEW.id)
  +(SELECT count(*) FROM prep_inventory.container_moves WHERE command_id=NEW.id) INTO total;
 EXECUTE format('SELECT count(*) FROM prep_inventory.%I WHERE command_id=$1 AND id=$2',table_name) INTO child_count USING NEW.id,NEW.result_id;
 IF total<>1 OR child_count<>1 THEN RAISE EXCEPTION 'Command requires exactly one immutable result'; END IF;
 PERFORM prep_inventory.assert_lot_allocations(NEW.store_id);
 PERFORM prep_inventory.assert_container_timeline(NEW.store_id);
 RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER container_command_seal AFTER INSERT ON prep_inventory.container_commands DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION prep_inventory.seal_container_command();
CREATE TRIGGER definition_check BEFORE INSERT ON prep_inventory.container_definitions FOR EACH ROW EXECUTE FUNCTION prep_inventory.check_container_definition();
CREATE TRIGGER profile_check BEFORE INSERT ON prep_inventory.container_profiles FOR EACH ROW EXECUTE FUNCTION prep_inventory.check_container_profile();
CREATE TRIGGER fill_check BEFORE INSERT ON prep_inventory.container_fills FOR EACH ROW EXECUTE FUNCTION prep_inventory.check_container_fill();
CREATE TRIGGER move_check BEFORE INSERT ON prep_inventory.container_moves FOR EACH ROW EXECUTE FUNCTION prep_inventory.check_container_move();
DO $$ DECLARE t text; r text; BEGIN
 FOREACH t IN ARRAY ARRAY['container_definitions','container_profiles','container_fills','container_moves'] LOOP
  EXECUTE format('CREATE TRIGGER container_child_guard BEFORE INSERT ON prep_inventory.%I FOR EACH ROW EXECUTE FUNCTION prep_inventory.guard_container_child()',t);
 END LOOP;
 FOREACH t IN ARRAY ARRAY['container_commands','container_definitions','container_profiles','container_fills','container_moves'] LOOP
  EXECUTE format('CREATE TRIGGER container_immutable BEFORE UPDATE OR DELETE ON prep_inventory.%I FOR EACH ROW EXECUTE FUNCTION purchasing.reject_fact_change()',t);
 END LOOP;
 REVOKE ALL ON ALL TABLES IN SCHEMA prep_inventory FROM PUBLIC;
 REVOKE ALL ON ALL FUNCTIONS IN SCHEMA prep_inventory FROM PUBLIC;
 FOREACH r IN ARRAY ARRAY['anon','authenticated'] LOOP
  IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=r) THEN
   EXECUTE format('REVOKE ALL ON ALL TABLES IN SCHEMA prep_inventory FROM %I',r);
   EXECUTE format('REVOKE ALL ON ALL FUNCTIONS IN SCHEMA prep_inventory FROM %I',r);
  END IF;
 END LOOP;
END $$;
COMMIT;
