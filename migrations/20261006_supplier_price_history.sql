-- After shared catalog and native order receiving. No invoice/accounting writes.
BEGIN;
CREATE TABLE purchasing.supplier_price_events (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 event_sequence bigint GENERATED ALWAYS AS IDENTITY UNIQUE,
 store_id text NOT NULL, vendor_item_id uuid NOT NULL, item_code text NOT NULL,
 price numeric CHECK(price>=0 AND price NOT IN ('NaN'::numeric,'Infinity'::numeric,'-Infinity'::numeric)),
 effective_date date, recorded_at timestamptz NOT NULL DEFAULT now(),
 source text NOT NULL CHECK(source IN ('baseline','manual','invoice')),
 actor text NOT NULL, note text NOT NULL,
 pack_snapshot jsonb NOT NULL,
 basis_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
 request_key text UNIQUE, request_fingerprint bytea,
 FOREIGN KEY(store_id,vendor_item_id) REFERENCES purchasing.store_vendor_items(store_id,vendor_item_id),
 FOREIGN KEY(vendor_item_id,item_code) REFERENCES public.vendor_items(id,item_code),
 CHECK(source<>'invoice' OR (price IS NOT NULL AND effective_date IS NOT NULL AND request_key IS NOT NULL)),
 CHECK(request_fingerprint IS NULL OR octet_length(request_fingerprint)=32)
);
CREATE INDEX supplier_price_history ON purchasing.supplier_price_events(store_id,vendor_item_id,event_sequence DESC);
ALTER TABLE purchasing.store_vendor_items ADD COLUMN price_event_id uuid REFERENCES purchasing.supplier_price_events(id);
CREATE FUNCTION purchasing.supplier_pack(sku uuid) RETURNS jsonb LANGUAGE sql STABLE AS $$
 SELECT jsonb_build_object('id',id,'item_code',item_code,'vendor_id',vendor_id,'vendor_sku',vendor_sku,
 'purchase_unit',purchase_unit,'base_per_purchase_unit',base_per_purchase_unit::text,
 'pack_count',pack_count::text,'unit_qty',unit_qty::text,'unit_uom',unit_uom)
 FROM public.vendor_items WHERE id=sku
$$;
-- Existing values are preserved, but their business effective dates are unknown.
INSERT INTO purchasing.supplier_price_events(store_id,vendor_item_id,item_code,price,source,actor,note,pack_snapshot,basis_snapshot)
 SELECT store_id,vendor_item_id,item_code,price,'baseline','migration',
 'Pre-history catalog value; received-date provenance is not certified',purchasing.supplier_pack(vendor_item_id),
 jsonb_build_object('previous_source',price_source,'previous_updated_at',price_updated_at)
 FROM purchasing.store_vendor_items;
UPDATE purchasing.store_vendor_items s SET price_event_id=e.id FROM purchasing.supplier_price_events e
 WHERE e.store_id=s.store_id AND e.vendor_item_id=s.vendor_item_id;
CREATE FUNCTION purchasing.record_supplier_price() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE event purchasing.supplier_price_events; requested uuid;
BEGIN
 requested:=nullif(current_setting('jmax.price_event',true),'')::uuid;
 IF requested IS NOT NULL THEN
  SELECT * INTO STRICT event FROM purchasing.supplier_price_events WHERE id=requested;
  IF (event.store_id,event.vendor_item_id,event.item_code) IS DISTINCT FROM (NEW.store_id,NEW.vendor_item_id,NEW.item_code)
    OR event.price IS DISTINCT FROM NEW.price OR event.pack_snapshot IS DISTINCT FROM purchasing.supplier_pack(NEW.vendor_item_id) THEN
   RAISE EXCEPTION 'Supplier price event does not match its projection';
  END IF;
  NEW.price_event_id:=event.id; NEW.price_updated_at:=event.recorded_at; NEW.price_source:=event.source;
 ELSIF TG_OP='INSERT' OR NEW.price IS DISTINCT FROM OLD.price THEN
  INSERT INTO purchasing.supplier_price_events(store_id,vendor_item_id,item_code,price,effective_date,source,actor,note,pack_snapshot)
  VALUES(NEW.store_id,NEW.vendor_item_id,NEW.item_code,NEW.price,(now() AT TIME ZONE 'UTC')::date,'manual',
   coalesce(nullif(current_setting('jmax.price_actor',true),''),'database:'||current_user),
   'Manual catalog price change; blank means unknown',purchasing.supplier_pack(NEW.vendor_item_id)) RETURNING * INTO event;
  NEW.price_event_id:=event.id; NEW.price_updated_at:=event.recorded_at; NEW.price_source:='manual';
 ELSIF NEW.price_event_id IS DISTINCT FROM OLD.price_event_id OR NEW.price_source IS DISTINCT FROM OLD.price_source
    OR NEW.price_updated_at IS DISTINCT FROM OLD.price_updated_at THEN
  RAISE EXCEPTION 'Supplier price provenance must change through a recorded event';
 END IF;
 RETURN NEW;
END $$;
-- Deferred membership FK permits the first event while a supplier link is inserted.
ALTER TABLE purchasing.supplier_price_events ALTER CONSTRAINT supplier_price_events_store_id_vendor_item_id_fkey DEFERRABLE INITIALLY DEFERRED;
CREATE TRIGGER record_supplier_price BEFORE INSERT OR UPDATE ON purchasing.store_vendor_items
 FOR EACH ROW EXECUTE FUNCTION purchasing.record_supplier_price();
CREATE TRIGGER immutable_fact BEFORE UPDATE OR DELETE ON purchasing.supplier_price_events
 FOR EACH ROW EXECUTE FUNCTION purchasing.reject_fact_change();
REVOKE ALL ON purchasing.supplier_price_events FROM PUBLIC;
COMMIT;
