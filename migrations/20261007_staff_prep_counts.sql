-- Requires native prep definitions, batches and observations. No Track 1 writes.
BEGIN;
LOCK TABLE public.count_sessions,public.count_lines IN SHARE ROW EXCLUSIVE MODE;
-- Preserve all original legacy prep-session/line fields without treating them as native measurements.
CREATE TABLE prep_inventory.legacy_count_sources (
 source_table text NOT NULL, source_id uuid NOT NULL, raw_record jsonb NOT NULL,
 captured_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(source_table,source_id)
);
INSERT INTO prep_inventory.legacy_count_sources(source_table,source_id,raw_record)
 SELECT 'count_sessions',s.id,to_jsonb(s) FROM public.count_sessions s WHERE count_type IN ('nightly_prep','commissary');
INSERT INTO prep_inventory.legacy_count_sources(source_table,source_id,raw_record)
 SELECT 'count_lines',l.id,to_jsonb(l) FROM public.count_lines l JOIN public.count_sessions s ON s.id=l.session_id
 WHERE s.count_type IN ('nightly_prep','commissary');
CREATE FUNCTION prep_inventory.hold_legacy_count_write() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE before_prep boolean; after_prep boolean;
BEGIN
 IF TG_TABLE_NAME='count_sessions' THEN
  IF TG_OP<>'INSERT' THEN before_prep=OLD.count_type IN ('nightly_prep','commissary'); END IF;
  IF TG_OP<>'DELETE' THEN after_prep=NEW.count_type IN ('nightly_prep','commissary'); END IF;
 ELSE
  IF TG_OP<>'INSERT' THEN SELECT count_type IN ('nightly_prep','commissary') INTO before_prep FROM public.count_sessions WHERE id=OLD.session_id; END IF;
  IF TG_OP<>'DELETE' THEN SELECT count_type IN ('nightly_prep','commissary') INTO after_prep FROM public.count_sessions WHERE id=NEW.session_id; END IF;
 END IF;
 IF coalesce(before_prep,false) OR coalesce(after_prep,false) THEN RAISE EXCEPTION 'Legacy prep count records are retained; use native reviewed counts'; END IF;
 IF TG_OP='DELETE' THEN RETURN OLD; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER retained_prep_count_session BEFORE INSERT OR UPDATE OR DELETE ON public.count_sessions FOR EACH ROW EXECUTE FUNCTION prep_inventory.hold_legacy_count_write();
CREATE TRIGGER retained_prep_count_line BEFORE INSERT OR UPDATE OR DELETE ON public.count_lines FOR EACH ROW EXECUTE FUNCTION prep_inventory.hold_legacy_count_write();
CREATE TRIGGER immutable_legacy_prep_counts BEFORE UPDATE OR DELETE ON prep_inventory.legacy_count_sources FOR EACH ROW EXECUTE FUNCTION purchasing.reject_fact_change();
CREATE TABLE prep_inventory.staff_sheets (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), store_id text NOT NULL REFERENCES public.stores(id),
 performed_at timestamptz NOT NULL, business_date date NOT NULL, timezone_name text NOT NULL,
 sheet_snapshot jsonb NOT NULL CHECK(jsonb_typeof(sheet_snapshot)='object'),
 review_hash bytea NOT NULL CHECK(octet_length(review_hash)=32), issued_by text NOT NULL CHECK(length(btrim(issued_by))>0),
 issued_at timestamptz NOT NULL DEFAULT now(), request_key uuid NOT NULL UNIQUE,
 request_fingerprint bytea NOT NULL CHECK(octet_length(request_fingerprint)=32), UNIQUE(id,store_id),
 CHECK(business_date=(performed_at AT TIME ZONE timezone_name)::date)
);
CREATE TABLE prep_inventory.staff_submissions (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), sheet_id uuid NOT NULL, store_id text NOT NULL,
 revision integer NOT NULL CHECK(revision>0), counter_name text NOT NULL CHECK(length(btrim(counter_name))>0),
 credential_kind text NOT NULL CHECK(credential_kind IN ('bearer','shared_pin')),
 submitted_by text NOT NULL CHECK(length(btrim(submitted_by))>0), submitted_at timestamptz NOT NULL DEFAULT now(),
 note text NOT NULL CHECK(length(btrim(note))>0), quantities jsonb NOT NULL CHECK(jsonb_typeof(quantities)='array'),
 submitted_body jsonb NOT NULL CHECK(jsonb_typeof(submitted_body)='object'),
 request_key uuid NOT NULL UNIQUE, request_fingerprint bytea NOT NULL CHECK(octet_length(request_fingerprint)=32),
 FOREIGN KEY(sheet_id,store_id) REFERENCES prep_inventory.staff_sheets(id,store_id),
 UNIQUE(sheet_id,revision), UNIQUE(id,sheet_id,store_id)
);
CREATE TABLE prep_inventory.staff_decisions (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), sheet_id uuid NOT NULL UNIQUE, store_id text NOT NULL,
 submission_id uuid, decision text NOT NULL CHECK(decision IN ('accepted','rejected')),
 observation_id uuid UNIQUE, observation_purpose text NOT NULL DEFAULT 'count' CHECK(observation_purpose='count'),
 note text NOT NULL CHECK(length(btrim(note))>0), review_snapshot jsonb NOT NULL CHECK(jsonb_typeof(review_snapshot)='object'),
 reviewed_by text NOT NULL CHECK(length(btrim(reviewed_by))>0), reviewed_at timestamptz NOT NULL DEFAULT now(),
 request_key uuid NOT NULL UNIQUE, request_fingerprint bytea NOT NULL CHECK(octet_length(request_fingerprint)=32),
 FOREIGN KEY(sheet_id,store_id) REFERENCES prep_inventory.staff_sheets(id,store_id),
 FOREIGN KEY(submission_id,sheet_id,store_id) REFERENCES prep_inventory.staff_submissions(id,sheet_id,store_id),
 FOREIGN KEY(observation_id,store_id,observation_purpose) REFERENCES prep_inventory.observations(id,store_id,purpose),
 CHECK((decision='accepted' AND submission_id IS NOT NULL AND observation_id IS NOT NULL)
    OR (decision='rejected' AND observation_id IS NULL))
);
CREATE FUNCTION prep_inventory.staff_sheet_current(snapshot jsonb, store text) RETURNS boolean LANGUAGE sql STABLE AS $$
 SELECT jsonb_typeof(snapshot->'items')='array' AND jsonb_array_length(snapshot->'items') BETWEEN 1 AND 500
 AND (SELECT count(*) FROM prep_inventory.products WHERE store_id=store)=jsonb_array_length(snapshot->'items')
 AND (SELECT count(DISTINCT i->>'product_id') FROM jsonb_array_elements(snapshot->'items') i)=jsonb_array_length(snapshot->'items')
 AND NOT EXISTS(SELECT 1 FROM jsonb_array_elements(snapshot->'items') i
  LEFT JOIN prep_inventory.product_versions v ON v.id=(i->>'product_version_id')::uuid AND v.store_id=store
  LEFT JOIN prep_inventory.unit_profiles u ON u.id=(i->>'profile_id')::uuid AND u.store_id=store AND u.product_version_id=v.id
  WHERE v.id IS NULL OR u.id IS NULL OR i->>'product_id' IS DISTINCT FROM v.product_id::text
  OR i->>'name' IS DISTINCT FROM v.name OR i->>'base_unit' IS DISTINCT FROM v.base_unit
  OR i->>'counted_unit' IS DISTINCT FROM u.source_unit OR (i->>'factor')::numeric IS DISTINCT FROM u.base_units_per_source_unit
  OR EXISTS(SELECT 1 FROM prep_inventory.product_versions n WHERE n.product_id=v.product_id AND n.revision>v.revision)
  OR EXISTS(SELECT 1 FROM prep_inventory.unit_profiles n WHERE n.product_version_id=v.id AND n.source_unit=u.source_unit AND n.revision>u.revision))
 AND NOT EXISTS(SELECT 1 FROM prep_inventory.batch_policies p WHERE p.store_id=store AND p.timezone_name IS DISTINCT FROM snapshot->'stamp'->>'timezone_name')
$$;
CREATE FUNCTION prep_inventory.guard_staff_prep_sheet() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 PERFORM 1 FROM public.store_state WHERE store_id=NEW.store_id FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Staff prep counts require store coordination'; END IF;
 IF NEW.sheet_snapshot->>'store_id' IS DISTINCT FROM NEW.store_id
 OR (NEW.sheet_snapshot->'stamp'->>'performed_at')::timestamptz IS DISTINCT FROM NEW.performed_at
 OR (NEW.sheet_snapshot->'stamp'->>'business_date')::date IS DISTINCT FROM NEW.business_date
 OR NEW.sheet_snapshot->'stamp'->>'timezone_name' IS DISTINCT FROM NEW.timezone_name
 OR NEW.sheet_snapshot->'stamp'->'calendar_date_confirmed' IS DISTINCT FROM 'true'::jsonb
 OR coalesce(length(btrim(NEW.sheet_snapshot->'stamp'->>'note')),0)=0
 OR prep_inventory.staff_sheet_current(NEW.sheet_snapshot,NEW.store_id) IS DISTINCT FROM true
 THEN RAISE EXCEPTION 'Issued prep count scope, units or boundary are invalid or stale'; END IF;
 IF EXISTS(SELECT 1 FROM prep_inventory.observations WHERE store_id=NEW.store_id AND purpose='count' AND kind='initial' AND performed_at=NEW.performed_at)
 OR EXISTS(SELECT 1 FROM prep_inventory.staff_sheets s WHERE s.store_id=NEW.store_id AND s.performed_at=NEW.performed_at
  AND NOT EXISTS(SELECT 1 FROM prep_inventory.staff_decisions d WHERE d.sheet_id=s.id AND d.decision='rejected'))
 THEN RAISE EXCEPTION 'A count or active issued sheet already occupies this physical boundary'; END IF;
 RETURN NEW;
END $$;
CREATE FUNCTION prep_inventory.guard_staff_prep_submission() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE sheet prep_inventory.staff_sheets; line jsonb;
BEGIN
 PERFORM 1 FROM public.store_state WHERE store_id=NEW.store_id FOR UPDATE;
 SELECT * INTO sheet FROM prep_inventory.staff_sheets WHERE id=NEW.sheet_id AND store_id=NEW.store_id;
 IF NOT FOUND OR prep_inventory.staff_sheet_current(sheet.sheet_snapshot,NEW.store_id) IS DISTINCT FROM true
 OR EXISTS(SELECT 1 FROM prep_inventory.staff_decisions WHERE sheet_id=NEW.sheet_id)
 OR EXISTS(SELECT 1 FROM prep_inventory.observations WHERE store_id=NEW.store_id AND purpose='count' AND kind='initial' AND performed_at=sheet.performed_at)
 THEN RAISE EXCEPTION 'Prep count sheet is stale or already decided'; END IF;
 IF NEW.revision<>(SELECT coalesce(max(revision),0)+1 FROM prep_inventory.staff_submissions WHERE sheet_id=NEW.sheet_id)
 OR NEW.submitted_body->>'counter_name' IS DISTINCT FROM NEW.counter_name OR NEW.submitted_body->>'note' IS DISTINCT FROM NEW.note
 OR NEW.submitted_body->'lines' IS DISTINCT FROM NEW.quantities
 OR coalesce(NEW.submitted_body->>'expected_review_hash','') !~ '^[a-f0-9]{64}$'
 OR NEW.submitted_body-ARRAY['counter_name','note','lines','expected_review_hash'] IS DISTINCT FROM '{}'::jsonb
 OR jsonb_array_length(NEW.quantities)<>jsonb_array_length(sheet.sheet_snapshot->'items')
 OR (SELECT count(DISTINCT l->>'product_id') FROM jsonb_array_elements(NEW.quantities) l)<>jsonb_array_length(NEW.quantities)
 THEN RAISE EXCEPTION 'Submission must retain exact body, continuous revision and complete issued membership'; END IF;
 FOR line IN SELECT * FROM jsonb_array_elements(NEW.quantities) LOOP
  IF line-ARRAY['product_id','quantity','evidence'] IS DISTINCT FROM '{}'::jsonb
  OR NOT (line ?& ARRAY['product_id','quantity','evidence']) OR jsonb_typeof(line->'evidence') IS DISTINCT FROM 'string'
  OR NOT EXISTS(SELECT 1 FROM jsonb_array_elements(sheet.sheet_snapshot->'items') i WHERE i->>'product_id'=line->>'product_id')
  THEN RAISE EXCEPTION 'Submission quantities differ from issued identities'; END IF;
  IF line->'quantity'<>'null'::jsonb AND (jsonb_typeof(line->'quantity') IS DISTINCT FROM 'string'
   OR (line->>'quantity')::numeric<0 OR (line->>'quantity')::numeric>=1e16
   OR scale(trim_scale((line->>'quantity')::numeric))>12
   OR (line->>'quantity')::numeric IN ('NaN'::numeric,'Infinity'::numeric,'-Infinity'::numeric))
  THEN RAISE EXCEPTION 'Quantity must be finite and nonnegative, or explicitly unknown'; END IF;
 END LOOP;
 RETURN NEW;
END $$;
CREATE FUNCTION prep_inventory.guard_staff_prep_decision() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE sheet prep_inventory.staff_sheets; submission prep_inventory.staff_submissions; observation prep_inventory.observations;
 item jsonb; line jsonb; recorded prep_inventory.count_observations;
BEGIN
 PERFORM 1 FROM public.store_state WHERE store_id=NEW.store_id FOR UPDATE;
 SELECT * INTO sheet FROM prep_inventory.staff_sheets WHERE id=NEW.sheet_id AND store_id=NEW.store_id;
 SELECT * INTO submission FROM prep_inventory.staff_submissions WHERE sheet_id=NEW.sheet_id ORDER BY revision DESC LIMIT 1;
 IF NEW.submission_id IS DISTINCT FROM submission.id
 OR NEW.review_snapshot->'current'->'sheet'->>'id' IS DISTINCT FROM NEW.sheet_id::text
 OR NEW.review_snapshot->'current'->'sheet'->'sheet_snapshot' IS DISTINCT FROM sheet.sheet_snapshot
 OR NEW.review_snapshot->'current'->'latest'->>'id' IS DISTINCT FROM submission.id::text
 OR NEW.review_snapshot->'current'->'latest'->'quantities' IS DISTINCT FROM submission.quantities
 OR NEW.review_snapshot->'decision' IS DISTINCT FROM jsonb_build_object('decision',NEW.decision,'note',NEW.note,'reviewed',true)
 THEN RAISE EXCEPTION 'Decision must review the current immutable sheet and latest submission'; END IF;
 IF NEW.decision='rejected' THEN
  IF NEW.review_snapshot->'observation' IS DISTINCT FROM 'null'::jsonb THEN RAISE EXCEPTION 'Rejection cannot record a physical observation'; END IF;
  RETURN NEW;
 END IF;
 SELECT * INTO observation FROM prep_inventory.observations WHERE id=NEW.observation_id;
 IF prep_inventory.staff_sheet_current(sheet.sheet_snapshot,NEW.store_id) IS DISTINCT FROM true
 OR NEW.review_snapshot->'current'->'errors' IS DISTINCT FROM '[]'::jsonb
 OR observation.kind IS DISTINCT FROM 'initial' OR observation.created_xid IS DISTINCT FROM pg_current_xact_id()
 OR (observation.store_id,observation.performed_at,observation.business_date,observation.timezone_name,observation.recorded_by,observation.reason,observation.request_key,observation.request_fingerprint)
 IS DISTINCT FROM (NEW.store_id,sheet.performed_at,sheet.business_date,sheet.timezone_name,NEW.reviewed_by,NEW.note,NEW.request_key,NEW.request_fingerprint)
 OR NEW.review_snapshot->'observation'->'review' IS DISTINCT FROM observation.review_snapshot
 OR NEW.review_snapshot->'observation'->>'reviewHash' IS DISTINCT FROM encode(observation.review_hash,'hex')
 OR (SELECT count(*) FROM prep_inventory.count_observations WHERE event_id=observation.id)<>jsonb_array_length(sheet.sheet_snapshot->'items')
 THEN RAISE EXCEPTION 'Acceptance requires one new matching reviewed full prep observation'; END IF;
 FOR item IN SELECT * FROM jsonb_array_elements(sheet.sheet_snapshot->'items') LOOP
  SELECT l INTO line FROM jsonb_array_elements(submission.quantities) l WHERE l->>'product_id'=item->>'product_id';
  SELECT * INTO recorded FROM prep_inventory.count_observations WHERE event_id=observation.id AND product_id=(item->>'product_id')::uuid;
  IF line->'quantity'='null'::jsonb OR coalesce(length(btrim(line->>'evidence')),0)=0 OR recorded.id IS NULL
   OR (recorded.product_version_id,recorded.profile_id,recorded.base_unit,recorded.quantity,recorded.factor,recorded.evidence)
    IS DISTINCT FROM ((item->>'product_version_id')::uuid,(item->>'profile_id')::uuid,item->>'base_unit',
       (line->>'quantity')::numeric,(item->>'factor')::numeric,line->>'evidence')
  THEN RAISE EXCEPTION 'Accepted count must match complete submitted measurements and pinned units'; END IF;
 END LOOP;
 RETURN NEW;
END $$;
CREATE FUNCTION prep_inventory.bump_staff_prep_revision() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 UPDATE public.store_state SET revision=revision+1,updated_at=now() WHERE store_id=NEW.store_id;
 RETURN NEW;
END $$;
CREATE TRIGGER valid_staff_prep_sheet BEFORE INSERT ON prep_inventory.staff_sheets FOR EACH ROW EXECUTE FUNCTION prep_inventory.guard_staff_prep_sheet();
CREATE TRIGGER valid_staff_prep_submission BEFORE INSERT ON prep_inventory.staff_submissions FOR EACH ROW EXECUTE FUNCTION prep_inventory.guard_staff_prep_submission();
CREATE TRIGGER valid_staff_prep_decision BEFORE INSERT ON prep_inventory.staff_decisions FOR EACH ROW EXECUTE FUNCTION prep_inventory.guard_staff_prep_decision();
DO $$ DECLARE t text; role_name text; BEGIN
 FOREACH t IN ARRAY ARRAY['staff_sheets','staff_submissions','staff_decisions'] LOOP
  EXECUTE format('CREATE TRIGGER immutable_staff_prep_fact BEFORE UPDATE OR DELETE ON prep_inventory.%I FOR EACH ROW EXECUTE FUNCTION purchasing.reject_fact_change()',t);
  EXECUTE format('CREATE TRIGGER staff_prep_revision AFTER INSERT ON prep_inventory.%I FOR EACH ROW EXECUTE FUNCTION prep_inventory.bump_staff_prep_revision()',t);
  EXECUTE format('REVOKE ALL ON prep_inventory.%I FROM PUBLIC',t);
  FOREACH role_name IN ARRAY ARRAY['anon','authenticated'] LOOP
   IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=role_name) THEN EXECUTE format('REVOKE ALL ON prep_inventory.%I FROM %I',t,role_name); END IF;
  END LOOP;
 END LOOP;
END $$;
REVOKE ALL ON prep_inventory.legacy_count_sources FROM PUBLIC;
REVOKE ALL ON FUNCTION prep_inventory.staff_sheet_current(jsonb,text),prep_inventory.guard_staff_prep_sheet(),
 prep_inventory.guard_staff_prep_submission(),prep_inventory.guard_staff_prep_decision(),prep_inventory.bump_staff_prep_revision(),prep_inventory.hold_legacy_count_write() FROM PUBLIC;
DO $$ DECLARE role_name text; BEGIN
 FOREACH role_name IN ARRAY ARRAY['anon','authenticated'] LOOP
  IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=role_name) THEN
   EXECUTE format('REVOKE ALL ON prep_inventory.legacy_count_sources FROM %I',role_name);
   EXECUTE format('REVOKE ALL ON ALL FUNCTIONS IN SCHEMA prep_inventory FROM %I',role_name);
  END IF;
 END LOOP;
END $$;
COMMIT;
