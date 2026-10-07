-- Requires reviewed prep mapping foundation and canonical catalog migrations.
-- Metadata only. No change to purchased inventory or operational prep journals.
BEGIN;
CREATE TABLE prep_inventory.legacy_planning_sources (
 source_id uuid PRIMARY KEY, store_id text NOT NULL REFERENCES public.stores(id), raw_record jsonb NOT NULL
);
INSERT INTO prep_inventory.legacy_planning_sources SELECT id,store_id,to_jsonb(p) FROM public.prep_items p;
CREATE TABLE prep_inventory.planning_versions (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), store_id text NOT NULL, product_id uuid NOT NULL,
 revision integer NOT NULL CHECK(revision>0), predecessor_id uuid UNIQUE,
 recipe_version_id uuid NOT NULL, unit_profile_id uuid NOT NULL,
 track text NOT NULL CHECK(track IN ('daily','bulk')),
 schedule text NOT NULL CHECK(schedule IN ('daily','recurring','on_demand')),
 weekday_par numeric NOT NULL CHECK(weekday_par>=0 AND weekday_par NOT IN ('NaN'::numeric,'Infinity'::numeric,'-Infinity'::numeric)),
 weekend_par numeric NOT NULL CHECK(weekend_par>=0 AND weekend_par NOT IN ('NaN'::numeric,'Infinity'::numeric,'-Infinity'::numeric)),
 recur_days integer[] NOT NULL, fixed_quantity numeric,
 active boolean NOT NULL, note text NOT NULL CHECK(length(btrim(note))>0), actor text NOT NULL CHECK(length(btrim(actor))>0),
 request_key uuid NOT NULL UNIQUE, request_fingerprint bytea NOT NULL CHECK(octet_length(request_fingerprint)=32),
 recorded_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(recipe_version_id,product_id,store_id) REFERENCES prep_inventory.recipe_versions(id,product_id,store_id),
 FOREIGN KEY(unit_profile_id,store_id) REFERENCES prep_inventory.unit_profiles(id,store_id),
 UNIQUE(id,product_id,store_id), UNIQUE(product_id,revision),
 FOREIGN KEY(predecessor_id,product_id,store_id) REFERENCES prep_inventory.planning_versions(id,product_id,store_id),
 CHECK((revision=1)=(predecessor_id IS NULL)),
 CHECK(recur_days <@ ARRAY[0,1,2,3,4,5,6] AND array_position(recur_days,NULL) IS NULL),
 CHECK((schedule='recurring' AND cardinality(recur_days)>0 AND fixed_quantity IS NOT NULL AND fixed_quantity>0 AND fixed_quantity NOT IN ('NaN'::numeric,'Infinity'::numeric,'-Infinity'::numeric))
    OR (schedule<>'recurring' AND cardinality(recur_days)=0 AND fixed_quantity IS NULL))
);
CREATE UNIQUE INDEX planning_root ON prep_inventory.planning_versions(product_id) WHERE predecessor_id IS NULL;
CREATE FUNCTION prep_inventory.guard_planning_version() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE recipe prep_inventory.recipe_versions; profile prep_inventory.unit_profiles; prior prep_inventory.planning_versions;
BEGIN
 SELECT * INTO recipe FROM prep_inventory.recipe_versions WHERE id=NEW.recipe_version_id;
 SELECT * INTO profile FROM prep_inventory.unit_profiles WHERE id=NEW.unit_profile_id;
 IF profile.product_version_id IS DISTINCT FROM recipe.product_version_id THEN RAISE EXCEPTION 'Planning unit must belong to the recipe output definition'; END IF;
 IF cardinality(NEW.recur_days)<>(SELECT count(DISTINCT d) FROM unnest(NEW.recur_days) d) THEN RAISE EXCEPTION 'Planning weekdays cannot repeat'; END IF;
 IF NOT NEW.active THEN
  SELECT * INTO prior FROM prep_inventory.planning_versions WHERE id=NEW.predecessor_id;
  IF NOT FOUND OR NOT prior.active OR
    (NEW.recipe_version_id,NEW.unit_profile_id,NEW.track,NEW.schedule,NEW.weekday_par,NEW.weekend_par,NEW.recur_days,NEW.fixed_quantity)
    IS DISTINCT FROM (prior.recipe_version_id,prior.unit_profile_id,prior.track,prior.schedule,prior.weekday_par,prior.weekend_par,prior.recur_days,prior.fixed_quantity)
    THEN RAISE EXCEPTION 'Retirement must preserve an active predecessor planning definition'; END IF;
 END IF;
 INSERT INTO public.store_state(store_id,revision) VALUES(NEW.store_id,1)
 ON CONFLICT(store_id) DO UPDATE SET revision=store_state.revision+1,updated_at=now();
 RETURN NEW;
END $$;
CREATE TRIGGER valid_planning_version BEFORE INSERT ON prep_inventory.planning_versions FOR EACH ROW EXECUTE FUNCTION prep_inventory.guard_planning_version();
CREATE TRIGGER continuous_planning_version BEFORE INSERT ON prep_inventory.planning_versions FOR EACH ROW EXECUTE FUNCTION prep_inventory.guard_version_chain();
CREATE TRIGGER immutable_plan BEFORE UPDATE OR DELETE ON prep_inventory.planning_versions FOR EACH ROW EXECUTE FUNCTION purchasing.reject_fact_change();
CREATE TRIGGER immutable_planning_source BEFORE UPDATE OR DELETE ON prep_inventory.legacy_planning_sources FOR EACH ROW EXECUTE FUNCTION purchasing.reject_fact_change();
CREATE TRIGGER retained_prep_metadata BEFORE INSERT OR UPDATE OR DELETE ON public.prep_items FOR EACH ROW EXECUTE FUNCTION purchasing.reject_fact_change();
REVOKE ALL ON prep_inventory.legacy_planning_sources,prep_inventory.planning_versions FROM PUBLIC;
REVOKE ALL ON FUNCTION prep_inventory.guard_planning_version() FROM PUBLIC;
COMMIT;
