-- Operational receiving links existing purchase facts; it creates no accounting facts.
BEGIN;
CREATE TABLE purchasing.unit_profiles (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 store_id text NOT NULL, item_code text NOT NULL,
 profile_kind text NOT NULL CHECK(profile_kind IN ('count','purchase')),
 vendor_item_id uuid REFERENCES public.vendor_items(id),
 context_key text NOT NULL,
 revision integer NOT NULL CHECK(revision>0),
 source_unit text NOT NULL CHECK(length(btrim(source_unit))>0),
 base_unit text NOT NULL,
 base_units_per_source_unit numeric NOT NULL CHECK(base_units_per_source_unit>0 AND base_units_per_source_unit NOT IN ('NaN'::numeric,'Infinity'::numeric,'-Infinity'::numeric)),
 source_snapshot jsonb NOT NULL, source_fingerprint bytea NOT NULL CHECK(octet_length(source_fingerprint)=32),
 request_key text NOT NULL UNIQUE, request_fingerprint bytea NOT NULL CHECK(octet_length(request_fingerprint)=32),
 confirmed_by text NOT NULL, confirmed_at timestamptz NOT NULL DEFAULT now(), note text NOT NULL CHECK(length(btrim(note))>0),
 FOREIGN KEY(store_id,item_code,base_unit) REFERENCES purchasing.item_bases(store_id,item_code,base_unit),
 UNIQUE(store_id,item_code,profile_kind,context_key,revision),
 CHECK(profile_kind='count' AND vendor_item_id IS NULL AND context_key='' OR profile_kind='purchase' AND vendor_item_id IS NOT NULL AND context_key=vendor_item_id::text)
);
ALTER TABLE public.purchase_orders ADD CONSTRAINT purchase_orders_id_store_unique UNIQUE(id,store_id);
ALTER TABLE public.purchase_order_lines ADD CONSTRAINT purchase_order_lines_id_po_unique UNIQUE(id,po_id);
CREATE TABLE purchasing.po_receipts (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), po_id uuid NOT NULL, store_id text NOT NULL,
 document_id uuid NOT NULL UNIQUE, source_version_id uuid NOT NULL,
 source_correction_id uuid REFERENCES purchasing.corrections(id),
 initial_batch_id uuid NOT NULL REFERENCES purchasing.posting_batches(id),
 reviewed_plan jsonb NOT NULL, plan_hash bytea NOT NULL CHECK(octet_length(plan_hash)=32),
 complete_order boolean NOT NULL, request_key text NOT NULL UNIQUE,
 request_fingerprint bytea NOT NULL CHECK(octet_length(request_fingerprint)=32),
 confirmed_by text NOT NULL, confirmed_at timestamptz NOT NULL DEFAULT now(), note text NOT NULL CHECK(length(btrim(note))>0),
 created_xid xid8 NOT NULL DEFAULT pg_current_xact_id(),
 FOREIGN KEY(po_id,store_id) REFERENCES public.purchase_orders(id,store_id),
 FOREIGN KEY(document_id,store_id) REFERENCES purchasing.document_identities(id,store_id),
 FOREIGN KEY(source_version_id,document_id) REFERENCES purchasing.document_versions(id,document_id),
 UNIQUE(id,po_id)
);
CREATE TABLE purchasing.po_receipt_lines (
 receipt_id uuid NOT NULL, po_id uuid NOT NULL, po_line_id uuid,
 source_line_id uuid NOT NULL REFERENCES purchasing.document_lines(id),
 mapping_id uuid NOT NULL REFERENCES purchasing.mapping_decisions(id),
 unit_profile_id uuid REFERENCES purchasing.unit_profiles(id),
 base_quantity numeric NOT NULL CHECK(base_quantity>=0 AND base_quantity NOT IN ('NaN'::numeric,'Infinity'::numeric,'-Infinity'::numeric)),
 base_unit text NOT NULL REFERENCES purchasing.base_units(unit_code),
 PRIMARY KEY(receipt_id,source_line_id),
 FOREIGN KEY(receipt_id,po_id) REFERENCES purchasing.po_receipts(id,po_id),
 FOREIGN KEY(po_line_id,po_id) REFERENCES public.purchase_order_lines(id,po_id),
 CHECK(po_line_id IS NULL OR unit_profile_id IS NOT NULL)
);
CREATE FUNCTION purchasing.guard_received_order() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF EXISTS(SELECT 1 FROM purchasing.po_receipts WHERE po_id=OLD.id) THEN
  IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Received order history cannot be deleted'; END IF;
  IF (to_jsonb(NEW)-ARRAY['status','received_at','receipt_started_at','invoice_number','receipt_match','history'])
    IS DISTINCT FROM (to_jsonb(OLD)-ARRAY['status','received_at','receipt_started_at','invoice_number','receipt_match','history'])
  THEN RAISE EXCEPTION 'Received order details require reconciliation'; END IF;
 END IF;
 RETURN CASE WHEN TG_OP='DELETE' THEN OLD ELSE NEW END;
END $$;
CREATE FUNCTION purchasing.guard_po_receipt_line() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE r purchasing.po_receipts; m purchasing.mapping_decisions; u purchasing.unit_profiles;
BEGIN
 SELECT * INTO STRICT r FROM purchasing.po_receipts WHERE id=NEW.receipt_id;
 IF r.created_xid<>pg_current_xact_id() THEN RAISE EXCEPTION 'A committed receipt is sealed'; END IF;
 SELECT * INTO STRICT m FROM purchasing.mapping_decisions WHERE id=NEW.mapping_id;
 IF NOT EXISTS(SELECT 1 FROM purchasing.current_posting_lines p WHERE p.document_id=r.document_id
    AND p.document_version_id=r.source_version_id AND p.correction_id IS NOT DISTINCT FROM r.source_correction_id
    AND p.initial_batch_id=r.initial_batch_id AND p.line_id=NEW.source_line_id AND p.mapping_id=m.id)
 OR m.classification<>'food' OR m.movement_kind<>'receipt' OR m.store_id<>r.store_id
 OR NEW.base_quantity<>m.base_quantity OR NEW.base_unit<>m.base_unit
 THEN RAISE EXCEPTION 'Receipt must link the current verified food purchase exactly'; END IF;
 IF NEW.po_line_id IS NOT NULL THEN
  SELECT * INTO STRICT u FROM purchasing.unit_profiles WHERE id=NEW.unit_profile_id;
  IF u.store_id<>r.store_id OR u.item_code<>m.item_code OR u.base_unit<>m.base_unit OR u.profile_kind<>'purchase'
    OR NOT EXISTS(SELECT 1 FROM public.purchase_order_lines l JOIN public.purchase_orders o ON o.id=l.po_id
       JOIN public.vendor_items vi ON vi.id=u.vendor_item_id WHERE l.id=NEW.po_line_id AND l.po_id=r.po_id
       AND l.item_code=m.item_code AND l.unit=u.source_unit AND vi.vendor_id=o.vendor_id AND vi.vendor_sku=l.vendor_sku)
  THEN RAISE EXCEPTION 'Order item or purchase unit differs from its verified profile'; END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER native_receipt_line_guard BEFORE INSERT ON purchasing.po_receipt_lines
 FOR EACH ROW EXECUTE FUNCTION purchasing.guard_po_receipt_line();
CREATE FUNCTION purchasing.check_complete_po_receipt() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE rid uuid; r purchasing.po_receipts; n integer;
BEGIN
 IF TG_TABLE_NAME='po_receipts' THEN
   rid:=NEW.id;
 ELSE
   rid:=NEW.receipt_id;
 END IF;
 SELECT * INTO STRICT r FROM purchasing.po_receipts WHERE id=rid;
 SELECT count(*) INTO n FROM purchasing.po_receipt_lines WHERE receipt_id=rid;
 IF n=0 OR n<>jsonb_array_length(r.reviewed_plan->'receiptLines') OR EXISTS(
   SELECT 1 FROM jsonb_array_elements(r.reviewed_plan->'receiptLines') p WHERE NOT EXISTS(
    SELECT 1 FROM purchasing.po_receipt_lines l WHERE l.receipt_id=rid AND l.source_line_id=(p->>'source_line_id')::uuid
     AND l.mapping_id=(p->>'mapping_id')::uuid AND l.po_line_id IS NOT DISTINCT FROM (p->>'po_line_id')::uuid
     AND l.base_quantity=(p->>'base_quantity')::numeric AND l.base_unit=p->>'base_unit'))
 THEN RAISE EXCEPTION 'Receiving must retain its complete reviewed source lines atomically'; END IF;
 RETURN NEW;
END $$;
CREATE CONSTRAINT TRIGGER complete_native_receipt AFTER INSERT ON purchasing.po_receipts
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION purchasing.check_complete_po_receipt();
CREATE CONSTRAINT TRIGGER complete_native_receipt_line AFTER INSERT ON purchasing.po_receipt_lines
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION purchasing.check_complete_po_receipt();
CREATE FUNCTION purchasing.guard_received_order_line() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE target_po uuid;
BEGIN
 IF TG_OP='INSERT' THEN target_po:=NEW.po_id; ELSE target_po:=OLD.po_id; END IF;
 IF EXISTS(SELECT 1 FROM purchasing.po_receipts WHERE po_id=target_po)
 THEN RAISE EXCEPTION 'Received order lines are retained; use reconciliation'; END IF;
 RETURN CASE WHEN TG_OP='DELETE' THEN OLD ELSE NEW END;
END $$;
CREATE TRIGGER native_received_order_guard BEFORE UPDATE OR DELETE ON public.purchase_orders
 FOR EACH ROW EXECUTE FUNCTION purchasing.guard_received_order();
CREATE TRIGGER native_received_line_guard BEFORE INSERT OR UPDATE OR DELETE ON public.purchase_order_lines
 FOR EACH ROW EXECUTE FUNCTION purchasing.guard_received_order_line();
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['unit_profiles','po_receipts','po_receipt_lines'] LOOP
  EXECUTE format('CREATE TRIGGER immutable_fact BEFORE UPDATE OR DELETE ON purchasing.%I FOR EACH ROW EXECUTE FUNCTION purchasing.reject_fact_change()',t);
 END LOOP;
END $$;
REVOKE ALL ON ALL TABLES IN SCHEMA purchasing FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA purchasing FROM PUBLIC;
COMMIT;
