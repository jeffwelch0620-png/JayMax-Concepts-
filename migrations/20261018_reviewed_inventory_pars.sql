-- Planning metadata only. Existing store_items.par numbers keep their unknown basis.
-- Requires native physical unit profiles. Never runs on application startup.
BEGIN;
CREATE TABLE purchasing.inventory_par_versions (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), store_id text NOT NULL, item_code text NOT NULL,
 revision integer NOT NULL CHECK(revision>0), predecessor_id uuid UNIQUE,
 unit_profile_id uuid NOT NULL REFERENCES purchasing.unit_profiles(id),
 source_unit text NOT NULL CHECK(length(btrim(source_unit))>0),
 quantity numeric NOT NULL CHECK(quantity>=0 AND quantity<1e16 AND scale(trim_scale(quantity))<=12),
 factor numeric NOT NULL CHECK(factor>0 AND factor<1e16 AND scale(trim_scale(factor))<=12),
 base_unit text NOT NULL, base_quantity numeric NOT NULL CHECK(base_quantity=quantity*factor),
 confirmed boolean NOT NULL, coverage_note text NOT NULL CHECK(length(btrim(coverage_note)) BETWEEN 1 AND 2000),
 actor text NOT NULL CHECK(length(btrim(actor))>0), recorded_at timestamptz NOT NULL DEFAULT now(),
 request_key uuid NOT NULL UNIQUE, request_fingerprint bytea NOT NULL CHECK(octet_length(request_fingerprint)=32),
 FOREIGN KEY(store_id,item_code,base_unit) REFERENCES purchasing.item_bases(store_id,item_code,base_unit),
 UNIQUE(id,store_id,item_code), UNIQUE(store_id,item_code,revision),
 FOREIGN KEY(predecessor_id,store_id,item_code) REFERENCES purchasing.inventory_par_versions(id,store_id,item_code),
 CHECK((revision=1)=(predecessor_id IS NULL))
);
CREATE UNIQUE INDEX inventory_par_root ON purchasing.inventory_par_versions(store_id,item_code) WHERE predecessor_id IS NULL;
CREATE FUNCTION purchasing.guard_inventory_par() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE prior purchasing.inventory_par_versions; profile purchasing.unit_profiles;
BEGIN
 PERFORM pg_advisory_xact_lock(hashtext('inventory-par'),hashtext(NEW.store_id||'|'||NEW.item_code));
 SELECT * INTO prior FROM purchasing.inventory_par_versions WHERE store_id=NEW.store_id AND item_code=NEW.item_code ORDER BY revision DESC LIMIT 1;
 IF NEW.revision<>coalesce(prior.revision,0)+1 OR NEW.predecessor_id IS DISTINCT FROM prior.id THEN
  RAISE EXCEPTION 'Par history requires the current predecessor';
 END IF;
 SELECT * INTO STRICT profile FROM purchasing.unit_profiles WHERE id=NEW.unit_profile_id;
 IF NEW.confirmed AND profile.id IS DISTINCT FROM (SELECT id FROM purchasing.unit_profiles
  WHERE store_id=NEW.store_id AND item_code=NEW.item_code AND profile_kind='count' ORDER BY revision DESC LIMIT 1) THEN
  RAISE EXCEPTION 'Confirm the current count profile before reviewing a par';
 END IF;
 IF (profile.store_id,profile.item_code,profile.profile_kind,profile.source_unit,profile.base_unit,profile.base_units_per_source_unit)
  IS DISTINCT FROM (NEW.store_id,NEW.item_code,'count'::text,NEW.source_unit,NEW.base_unit,NEW.factor) THEN
  RAISE EXCEPTION 'Par must retain its location count profile and exact physical conversion';
 END IF;
 IF NOT NEW.confirmed AND (prior.id IS NULL OR NOT prior.confirmed OR
  (NEW.unit_profile_id,NEW.source_unit,NEW.quantity,NEW.factor,NEW.base_unit,NEW.base_quantity)
  IS DISTINCT FROM (prior.unit_profile_id,prior.source_unit,prior.quantity,prior.factor,prior.base_unit,prior.base_quantity)) THEN
  RAISE EXCEPTION 'Withdrawing review must retain the confirmed predecessor quantities';
 END IF;
 INSERT INTO public.store_state(store_id,revision) VALUES(NEW.store_id,1)
 ON CONFLICT(store_id) DO UPDATE SET revision=store_state.revision+1,updated_at=now();
 RETURN NEW;
END $$;
CREATE TRIGGER valid_inventory_par BEFORE INSERT ON purchasing.inventory_par_versions FOR EACH ROW EXECUTE FUNCTION purchasing.guard_inventory_par();
CREATE TRIGGER immutable_inventory_par BEFORE UPDATE OR DELETE ON purchasing.inventory_par_versions FOR EACH ROW EXECUTE FUNCTION purchasing.reject_fact_change();
CREATE TRIGGER retained_inventory_par BEFORE TRUNCATE ON purchasing.inventory_par_versions FOR EACH STATEMENT EXECUTE FUNCTION purchasing.reject_fact_change();
ALTER TABLE purchasing.inventory_par_versions ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON purchasing.inventory_par_versions FROM PUBLIC;
REVOKE ALL ON FUNCTION purchasing.guard_inventory_par() FROM PUBLIC;
DO $$ DECLARE role_name text; BEGIN
 FOREACH role_name IN ARRAY ARRAY['anon','authenticated'] LOOP
  IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=role_name) THEN
   EXECUTE format('REVOKE ALL ON purchasing.inventory_par_versions FROM %I',role_name);
   EXECUTE format('REVOKE ALL ON FUNCTION purchasing.guard_inventory_par() FROM %I',role_name);
  END IF;
 END LOOP;
END $$;
COMMIT;
