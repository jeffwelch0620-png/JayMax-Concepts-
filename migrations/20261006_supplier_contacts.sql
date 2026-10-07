-- After order commands. Contact configuration only; no supplier messages or stock writes.
BEGIN;
CREATE TABLE purchasing.legacy_supplier_contacts (
 store_id text NOT NULL REFERENCES public.stores(id), vendor text NOT NULL,
 raw_record jsonb NOT NULL, PRIMARY KEY(store_id,vendor)
);
INSERT INTO purchasing.legacy_supplier_contacts SELECT store_id,vendor,to_jsonb(c) FROM public.store_vendor_contacts c;
CREATE TABLE purchasing.supplier_contact_events (
 id uuid PRIMARY KEY, store_id text NOT NULL REFERENCES public.stores(id),
 vendor_id text NOT NULL REFERENCES public.vendors(id), version bigint NOT NULL CHECK(version>0),
 order_email text NOT NULL, actor text NOT NULL, note text NOT NULL,
 legacy_vendor text, recorded_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(store_id,vendor_id,version), UNIQUE(id,store_id,vendor_id,version),
 UNIQUE(id,store_id,vendor_id), UNIQUE(id,store_id,legacy_vendor),
 FOREIGN KEY(store_id,legacy_vendor) REFERENCES purchasing.legacy_supplier_contacts(store_id,vendor)
);
CREATE TABLE purchasing.store_supplier_contacts (
 store_id text NOT NULL, vendor_id text NOT NULL, version bigint NOT NULL CHECK(version>0),
 order_email text NOT NULL, event_id uuid NOT NULL, PRIMARY KEY(store_id,vendor_id),
 FOREIGN KEY(event_id,store_id,vendor_id,version) REFERENCES purchasing.supplier_contact_events(id,store_id,vendor_id,version)
);
CREATE TABLE purchasing.legacy_contact_resolutions (
 store_id text NOT NULL, vendor text NOT NULL, event_id uuid NOT NULL,
 PRIMARY KEY(store_id,vendor), FOREIGN KEY(store_id,vendor) REFERENCES purchasing.legacy_supplier_contacts(store_id,vendor),
 FOREIGN KEY(event_id,store_id,vendor) REFERENCES purchasing.supplier_contact_events(id,store_id,legacy_vendor)
);
CREATE TABLE purchasing.supplier_contact_commands (
 request_key uuid PRIMARY KEY, store_id text NOT NULL REFERENCES public.stores(id),
 vendor_id text NOT NULL REFERENCES public.vendors(id), actor text NOT NULL,
 request_fingerprint bytea NOT NULL CHECK(octet_length(request_fingerprint)=32),
 event_id uuid NOT NULL,
 result_snapshot jsonb NOT NULL, recorded_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(event_id,store_id,vendor_id) REFERENCES purchasing.supplier_contact_events(id,store_id,vendor_id)
);
CREATE TRIGGER immutable_fact BEFORE UPDATE OR DELETE ON purchasing.legacy_supplier_contacts
 FOR EACH ROW EXECUTE FUNCTION purchasing.reject_fact_change();
CREATE TRIGGER immutable_fact BEFORE UPDATE OR DELETE ON purchasing.supplier_contact_events
 FOR EACH ROW EXECUTE FUNCTION purchasing.reject_fact_change();
CREATE TRIGGER immutable_fact BEFORE UPDATE OR DELETE ON purchasing.legacy_contact_resolutions
 FOR EACH ROW EXECUTE FUNCTION purchasing.reject_fact_change();
CREATE TRIGGER immutable_fact BEFORE UPDATE OR DELETE ON purchasing.supplier_contact_commands
 FOR EACH ROW EXECUTE FUNCTION purchasing.reject_fact_change();
CREATE TRIGGER retained_legacy_contact BEFORE INSERT OR UPDATE OR DELETE ON public.store_vendor_contacts
 FOR EACH ROW EXECUTE FUNCTION purchasing.reject_fact_change();
CREATE FUNCTION purchasing.version_supplier_contact() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE expected bigint; email text;
BEGIN
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Clear the contact through a reviewed event; retained history cannot be deleted'; END IF;
 IF TG_OP='UPDATE' AND (NEW.store_id,NEW.vendor_id) IS DISTINCT FROM (OLD.store_id,OLD.vendor_id) THEN
  RAISE EXCEPTION 'Supplier contact identity cannot be reassigned';
 END IF;
 expected:=CASE WHEN TG_OP='INSERT' THEN 1 ELSE OLD.version+1 END;
 IF NEW.version<>expected THEN RAISE EXCEPTION 'Supplier contact version is not current'; END IF;
 SELECT order_email INTO email FROM purchasing.supplier_contact_events
  WHERE id=NEW.event_id AND store_id=NEW.store_id AND vendor_id=NEW.vendor_id AND version=NEW.version;
 IF NOT FOUND OR email IS DISTINCT FROM NEW.order_email THEN RAISE EXCEPTION 'Supplier contact needs matching immutable change evidence'; END IF;
 INSERT INTO public.store_state(store_id,revision) VALUES(NEW.store_id,1)
 ON CONFLICT(store_id) DO UPDATE SET revision=store_state.revision+1,updated_at=now();
 RETURN NEW;
END $$;
CREATE TRIGGER version_supplier_contact BEFORE INSERT OR UPDATE OR DELETE ON purchasing.store_supplier_contacts
 FOR EACH ROW EXECUTE FUNCTION purchasing.version_supplier_contact();
REVOKE ALL ON purchasing.legacy_supplier_contacts,purchasing.supplier_contact_events,
 purchasing.store_supplier_contacts,purchasing.legacy_contact_resolutions,purchasing.supplier_contact_commands FROM PUBLIC;
COMMIT;
