-- Definition/review foundation only. No stock, batch, waste or sales writers.
-- Requires native purchase, count and physical-unit migrations.
BEGIN;
CREATE SCHEMA prep_inventory;
REVOKE ALL ON SCHEMA prep_inventory FROM PUBLIC;

CREATE TABLE prep_inventory.products (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), store_id text NOT NULL REFERENCES public.stores(id),
 identity_key text NOT NULL CHECK(length(btrim(identity_key))>0),
 base_unit text NOT NULL REFERENCES purchasing.base_units(unit_code),
 created_by text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
 request_key uuid NOT NULL UNIQUE, request_fingerprint bytea NOT NULL CHECK(octet_length(request_fingerprint)=32),
 UNIQUE(store_id,identity_key), UNIQUE(id,store_id,base_unit), UNIQUE(id,store_id)
);
CREATE TABLE prep_inventory.product_versions (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), product_id uuid NOT NULL, store_id text NOT NULL,
 base_unit text NOT NULL, revision integer NOT NULL CHECK(revision>0),
 name text NOT NULL CHECK(length(btrim(name))>0), note text NOT NULL CHECK(length(btrim(note))>0),
 predecessor_id uuid UNIQUE, confirmed_by text NOT NULL, confirmed_at timestamptz NOT NULL DEFAULT now(),
 request_key uuid NOT NULL UNIQUE, request_fingerprint bytea NOT NULL CHECK(octet_length(request_fingerprint)=32),
 FOREIGN KEY(product_id,store_id,base_unit) REFERENCES prep_inventory.products(id,store_id,base_unit),
 UNIQUE(id,product_id,store_id), UNIQUE(id,store_id), UNIQUE(product_id,revision),
 FOREIGN KEY(predecessor_id,product_id,store_id) REFERENCES prep_inventory.product_versions(id,product_id,store_id),
 CHECK((revision=1)=(predecessor_id IS NULL))
);
CREATE TABLE prep_inventory.unit_profiles (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), product_version_id uuid NOT NULL, store_id text NOT NULL,
 source_unit text NOT NULL CHECK(length(btrim(source_unit))>0),
 base_units_per_source_unit numeric NOT NULL CHECK(base_units_per_source_unit>0 AND base_units_per_source_unit NOT IN ('NaN'::numeric,'Infinity'::numeric,'-Infinity'::numeric)),
 revision integer NOT NULL CHECK(revision>0), predecessor_id uuid UNIQUE,
 note text NOT NULL CHECK(length(btrim(note))>0), confirmed_by text NOT NULL, confirmed_at timestamptz NOT NULL DEFAULT now(),
 request_key uuid NOT NULL UNIQUE, request_fingerprint bytea NOT NULL CHECK(octet_length(request_fingerprint)=32),
 FOREIGN KEY(product_version_id,store_id) REFERENCES prep_inventory.product_versions(id,store_id),
 UNIQUE(id,product_version_id,store_id), UNIQUE(id,store_id), UNIQUE(id,product_version_id,store_id,source_unit),
 UNIQUE(product_version_id,source_unit,revision),
 FOREIGN KEY(predecessor_id,product_version_id,store_id,source_unit) REFERENCES prep_inventory.unit_profiles(id,product_version_id,store_id,source_unit),
 CHECK((revision=1)=(predecessor_id IS NULL))
);
CREATE TABLE prep_inventory.recipe_versions (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), product_id uuid NOT NULL, product_version_id uuid NOT NULL, store_id text NOT NULL,
 revision integer NOT NULL CHECK(revision>0), predecessor_id uuid UNIQUE,
 output_profile_id uuid NOT NULL, entered_yield numeric NOT NULL CHECK(entered_yield>0 AND entered_yield NOT IN ('NaN'::numeric,'Infinity'::numeric,'-Infinity'::numeric)),
 usable_base_yield numeric NOT NULL CHECK(usable_base_yield>0 AND usable_base_yield NOT IN ('NaN'::numeric,'Infinity'::numeric,'-Infinity'::numeric)),
 method text NOT NULL CHECK(length(btrim(method))>0), note text NOT NULL CHECK(length(btrim(note))>0),
 review_snapshot jsonb NOT NULL CHECK(jsonb_typeof(review_snapshot)='object'),
 review_hash bytea NOT NULL CHECK(octet_length(review_hash)=32), created_xid xid8 NOT NULL DEFAULT pg_current_xact_id(),
 request_key uuid NOT NULL UNIQUE, request_fingerprint bytea NOT NULL CHECK(octet_length(request_fingerprint)=32),
 recorded_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(product_version_id,product_id,store_id) REFERENCES prep_inventory.product_versions(id,product_id,store_id),
 FOREIGN KEY(output_profile_id,product_version_id,store_id) REFERENCES prep_inventory.unit_profiles(id,product_version_id,store_id),
 UNIQUE(id,store_id), UNIQUE(id,product_id,store_id), UNIQUE(product_id,revision),
 FOREIGN KEY(predecessor_id,product_id,store_id) REFERENCES prep_inventory.recipe_versions(id,product_id,store_id),
 CHECK((revision=1)=(predecessor_id IS NULL))
);
CREATE TABLE prep_inventory.recipe_lines (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), recipe_version_id uuid NOT NULL, store_id text NOT NULL,
 line_number integer NOT NULL CHECK(line_number>0), source_kind text NOT NULL CHECK(source_kind IN ('raw','prepared')),
 raw_item_code text, prepared_recipe_id uuid, prepared_product_version_id uuid, prepared_profile_id uuid,
 entered_quantity numeric NOT NULL CHECK(entered_quantity>0 AND entered_quantity NOT IN ('NaN'::numeric,'Infinity'::numeric,'-Infinity'::numeric)),
 source_unit text NOT NULL CHECK(length(btrim(source_unit))>0), base_unit text NOT NULL REFERENCES purchasing.base_units(unit_code),
 factor numeric NOT NULL CHECK(factor>0 AND factor NOT IN ('NaN'::numeric,'Infinity'::numeric,'-Infinity'::numeric)),
 base_quantity numeric NOT NULL CHECK(base_quantity=entered_quantity*factor),
 source_snapshot jsonb NOT NULL CHECK(jsonb_typeof(source_snapshot)='object'),
 evidence text NOT NULL CHECK(length(btrim(evidence))>0),
 FOREIGN KEY(recipe_version_id,store_id) REFERENCES prep_inventory.recipe_versions(id,store_id),
 FOREIGN KEY(store_id,raw_item_code,base_unit) REFERENCES purchasing.item_bases(store_id,item_code,base_unit),
 FOREIGN KEY(prepared_recipe_id,store_id) REFERENCES prep_inventory.recipe_versions(id,store_id),
 FOREIGN KEY(prepared_profile_id,prepared_product_version_id,store_id) REFERENCES prep_inventory.unit_profiles(id,product_version_id,store_id),
 CHECK((source_kind='raw' AND raw_item_code IS NOT NULL AND prepared_recipe_id IS NULL AND prepared_product_version_id IS NULL AND prepared_profile_id IS NULL)
    OR (source_kind='prepared' AND raw_item_code IS NULL AND prepared_recipe_id IS NOT NULL AND prepared_product_version_id IS NOT NULL AND prepared_profile_id IS NOT NULL)),
 UNIQUE(recipe_version_id,line_number)
);
CREATE TABLE prep_inventory.promotion_decisions (
 recipe_version_id uuid PRIMARY KEY, store_id text NOT NULL,
 review_hash bytea NOT NULL CHECK(octet_length(review_hash)=32), graph_snapshot jsonb NOT NULL CHECK(jsonb_typeof(graph_snapshot)='array'),
 confirmed_by text NOT NULL, confirmed_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(recipe_version_id,store_id) REFERENCES prep_inventory.recipe_versions(id,store_id)
);
CREATE TABLE prep_inventory.legacy_crosswalks (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), store_id text NOT NULL,
 source_type text NOT NULL CHECK(source_type IN ('dish','prep_item')), source_id uuid NOT NULL,
 product_id uuid NOT NULL, recipe_version_id uuid NOT NULL UNIQUE,
 predecessor_id uuid UNIQUE, source_snapshot jsonb NOT NULL CHECK(jsonb_typeof(source_snapshot)='object'),
 source_hash bytea NOT NULL CHECK(octet_length(source_hash)=32), confirmed_by text NOT NULL, confirmed_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(recipe_version_id,product_id,store_id) REFERENCES prep_inventory.recipe_versions(id,product_id,store_id),
 UNIQUE(id,store_id,source_type,source_id,product_id),
 FOREIGN KEY(predecessor_id,store_id,source_type,source_id,product_id) REFERENCES prep_inventory.legacy_crosswalks(id,store_id,source_type,source_id,product_id)
);
CREATE UNIQUE INDEX legacy_mapping_root ON prep_inventory.legacy_crosswalks(store_id,source_type,source_id) WHERE predecessor_id IS NULL;

CREATE FUNCTION prep_inventory.guard_recipe_child() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE parent prep_inventory.recipe_versions; referenced prep_inventory.recipe_versions; profile prep_inventory.unit_profiles; version prep_inventory.product_versions;
BEGIN
 SELECT * INTO parent FROM prep_inventory.recipe_versions WHERE id=NEW.recipe_version_id;
 IF parent.created_xid IS DISTINCT FROM pg_current_xact_id() OR parent.recorded_at IS DISTINCT FROM transaction_timestamp()
 THEN RAISE EXCEPTION 'Approved recipe is sealed; append a version'; END IF;
 IF TG_TABLE_NAME='recipe_lines' THEN
 IF NEW.source_kind='prepared' THEN
  SELECT * INTO referenced FROM prep_inventory.recipe_versions WHERE id=NEW.prepared_recipe_id;
  SELECT * INTO profile FROM prep_inventory.unit_profiles WHERE id=NEW.prepared_profile_id;
  SELECT * INTO version FROM prep_inventory.product_versions WHERE id=NEW.prepared_product_version_id;
  IF referenced.product_version_id IS DISTINCT FROM NEW.prepared_product_version_id OR profile.source_unit IS DISTINCT FROM NEW.source_unit
    OR profile.base_units_per_source_unit IS DISTINCT FROM NEW.factor OR version.base_unit IS DISTINCT FROM NEW.base_unit
  THEN RAISE EXCEPTION 'Prepared ingredient identity and unit versions must match'; END IF;
 END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE FUNCTION prep_inventory.check_recipe_seal() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE profile prep_inventory.unit_profiles;
BEGIN
 SELECT * INTO profile FROM prep_inventory.unit_profiles WHERE id=NEW.output_profile_id;
 IF NEW.usable_base_yield IS DISTINCT FROM NEW.entered_yield*profile.base_units_per_source_unit THEN RAISE EXCEPTION 'Usable yield must match its frozen unit profile'; END IF;
 IF NOT EXISTS(SELECT 1 FROM prep_inventory.recipe_lines WHERE recipe_version_id=NEW.id)
  OR NOT EXISTS(SELECT 1 FROM prep_inventory.promotion_decisions WHERE recipe_version_id=NEW.id AND review_hash=NEW.review_hash)
 THEN RAISE EXCEPTION 'Recipe requires complete ingredients and matching promotion decision'; END IF;
 IF jsonb_typeof(NEW.review_snapshot->'lines') IS DISTINCT FROM 'array' THEN RAISE EXCEPTION 'Recipe requires its reviewed ingredient snapshot'; END IF;
 IF jsonb_array_length(NEW.review_snapshot->'lines')<>(SELECT count(*) FROM prep_inventory.recipe_lines WHERE recipe_version_id=NEW.id)
  OR EXISTS(SELECT 1 FROM prep_inventory.recipe_lines l LEFT JOIN LATERAL (
    SELECT value AS s FROM jsonb_array_elements(NEW.review_snapshot->'lines') WHERE (value->>'line_number')::integer=l.line_number
   ) reviewed ON true WHERE l.recipe_version_id=NEW.id AND (
    reviewed.s IS NULL OR l.source_kind IS DISTINCT FROM reviewed.s->>'source_kind'
    OR l.raw_item_code IS DISTINCT FROM reviewed.s->>'raw_item_code'
    OR l.prepared_recipe_id IS DISTINCT FROM (reviewed.s->>'prepared_recipe_id')::uuid
    OR l.prepared_profile_id IS DISTINCT FROM (reviewed.s->>'prepared_profile_id')::uuid
    OR l.entered_quantity IS DISTINCT FROM (reviewed.s->>'quantity')::numeric
    OR l.source_unit IS DISTINCT FROM reviewed.s->>'source_unit' OR l.base_unit IS DISTINCT FROM reviewed.s->>'base_unit'
    OR l.factor IS DISTINCT FROM (reviewed.s->>'factor')::numeric OR l.base_quantity IS DISTINCT FROM (reviewed.s->>'base_quantity')::numeric
    OR l.evidence IS DISTINCT FROM reviewed.s->>'evidence' OR l.source_snapshot IS DISTINCT FROM reviewed.s->'source_snapshot'
  )) THEN RAISE EXCEPTION 'Sealed ingredients must exactly match the reviewed snapshot'; END IF;
 IF EXISTS(
  WITH RECURSIVE ancestry(recipe_id,product_id) AS (
   SELECT r.id,r.product_id FROM prep_inventory.recipe_lines l JOIN prep_inventory.recipe_versions r ON r.id=l.prepared_recipe_id WHERE l.recipe_version_id=NEW.id
   UNION
   SELECT r.id,r.product_id FROM ancestry a JOIN prep_inventory.recipe_lines l ON l.recipe_version_id=a.recipe_id JOIN prep_inventory.recipe_versions r ON r.id=l.prepared_recipe_id
  ) SELECT 1 FROM ancestry WHERE product_id=NEW.product_id
 ) THEN RAISE EXCEPTION 'Prepared recipe graph cannot return to its output identity'; END IF;
 RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER complete_recipe AFTER INSERT ON prep_inventory.recipe_versions DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION prep_inventory.check_recipe_seal();
CREATE TRIGGER sealed_recipe_lines BEFORE INSERT ON prep_inventory.recipe_lines FOR EACH ROW EXECUTE FUNCTION prep_inventory.guard_recipe_child();
CREATE TRIGGER sealed_recipe_decision BEFORE INSERT ON prep_inventory.promotion_decisions FOR EACH ROW EXECUTE FUNCTION prep_inventory.guard_recipe_child();
CREATE TRIGGER sealed_recipe_crosswalk BEFORE INSERT ON prep_inventory.legacy_crosswalks FOR EACH ROW EXECUTE FUNCTION prep_inventory.guard_recipe_child();
DO $$ DECLARE t text; role_name text; BEGIN
 FOREACH t IN ARRAY ARRAY['products','product_versions','unit_profiles','recipe_versions','recipe_lines','promotion_decisions','legacy_crosswalks'] LOOP
  EXECUTE format('CREATE TRIGGER immutable_definition BEFORE UPDATE OR DELETE ON prep_inventory.%I FOR EACH ROW EXECUTE FUNCTION purchasing.reject_fact_change()',t);
  EXECUTE format('REVOKE ALL ON prep_inventory.%I FROM PUBLIC',t);
 END LOOP;
 FOR role_name IN SELECT rolname FROM pg_roles WHERE rolname IN ('anon','authenticated') LOOP
  EXECUTE format('REVOKE ALL ON SCHEMA prep_inventory FROM %I',role_name);
  EXECUTE format('REVOKE ALL ON ALL TABLES IN SCHEMA prep_inventory FROM %I',role_name);
  EXECUTE format('REVOKE ALL ON ALL FUNCTIONS IN SCHEMA prep_inventory FROM %I',role_name);
 END LOOP;
END $$;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA prep_inventory FROM PUBLIC;
CREATE FUNCTION prep_inventory.guard_version_chain() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE predecessor_revision integer;
BEGIN
 IF NEW.predecessor_id IS NOT NULL THEN
  EXECUTE format('SELECT revision FROM prep_inventory.%I WHERE id=$1',TG_TABLE_NAME) INTO predecessor_revision USING NEW.predecessor_id;
  IF NEW.revision IS DISTINCT FROM predecessor_revision+1 THEN RAISE EXCEPTION 'Definition revisions must follow their predecessor without gaps'; END IF;
 END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION prep_inventory.guard_version_chain() FROM PUBLIC;
CREATE TRIGGER continuous_product_version BEFORE INSERT ON prep_inventory.product_versions FOR EACH ROW EXECUTE FUNCTION prep_inventory.guard_version_chain();
CREATE TRIGGER continuous_unit_version BEFORE INSERT ON prep_inventory.unit_profiles FOR EACH ROW EXECUTE FUNCTION prep_inventory.guard_version_chain();
CREATE TRIGGER continuous_recipe_version BEFORE INSERT ON prep_inventory.recipe_versions FOR EACH ROW EXECUTE FUNCTION prep_inventory.guard_version_chain();
COMMIT;
