-- Comparison revisions only; native purchase/count facts are not rewritten.
BEGIN;
ALTER TABLE purchasing.po_receipts ADD CONSTRAINT po_receipt_identity_unique
 UNIQUE(id,po_id,store_id,document_id,initial_batch_id);
CREATE TABLE purchasing.po_receipt_reconciliations (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), receipt_id uuid NOT NULL,
 po_id uuid NOT NULL, store_id text NOT NULL, document_id uuid NOT NULL,
 initial_batch_id uuid NOT NULL, revision integer NOT NULL CHECK(revision>0),
 previous_reconciliation_id uuid UNIQUE,
 source_version_id uuid NOT NULL, source_correction_id uuid REFERENCES purchasing.corrections(id),
 reviewed_plan jsonb NOT NULL, plan_hash bytea NOT NULL CHECK(octet_length(plan_hash)=32),
 request_key text NOT NULL UNIQUE, request_fingerprint bytea NOT NULL CHECK(octet_length(request_fingerprint)=32),
 confirmed_by text NOT NULL, confirmed_at timestamptz NOT NULL DEFAULT now(),
 note text NOT NULL CHECK(length(btrim(note))>0), created_xid xid8 NOT NULL DEFAULT pg_current_xact_id(),
 FOREIGN KEY(receipt_id,po_id,store_id,document_id,initial_batch_id)
   REFERENCES purchasing.po_receipts(id,po_id,store_id,document_id,initial_batch_id),
 FOREIGN KEY(source_version_id,document_id) REFERENCES purchasing.document_versions(id,document_id),
 UNIQUE(receipt_id,revision), UNIQUE(id,receipt_id), UNIQUE(id,po_id),
 FOREIGN KEY(previous_reconciliation_id,receipt_id) REFERENCES purchasing.po_receipt_reconciliations(id,receipt_id)
);
CREATE UNIQUE INDEX first_po_reconciliation ON purchasing.po_receipt_reconciliations(receipt_id)
 WHERE previous_reconciliation_id IS NULL;
CREATE TABLE purchasing.po_receipt_reconciliation_lines (
 reconciliation_id uuid NOT NULL, po_id uuid NOT NULL, po_line_id uuid,
 source_line_id uuid NOT NULL REFERENCES purchasing.document_lines(id),
 mapping_id uuid NOT NULL REFERENCES purchasing.mapping_decisions(id),
 unit_profile_id uuid REFERENCES purchasing.unit_profiles(id),
 base_quantity numeric NOT NULL CHECK(base_quantity>=0 AND base_quantity NOT IN ('NaN'::numeric,'Infinity'::numeric,'-Infinity'::numeric)),
 base_unit text NOT NULL REFERENCES purchasing.base_units(unit_code),
 PRIMARY KEY(reconciliation_id,source_line_id),
 FOREIGN KEY(reconciliation_id,po_id) REFERENCES purchasing.po_receipt_reconciliations(id,po_id),
 FOREIGN KEY(po_line_id,po_id) REFERENCES public.purchase_order_lines(id,po_id),
 CHECK(po_line_id IS NULL OR unit_profile_id IS NOT NULL)
);
CREATE VIEW purchasing.effective_po_receipts AS
 SELECT r.id,r.po_id,r.store_id,r.document_id,r.initial_batch_id,
 coalesce(n.source_version_id,r.source_version_id) AS source_version_id,
 CASE WHEN n.id IS NULL THEN r.source_correction_id ELSE n.source_correction_id END AS source_correction_id,
 coalesce(n.reviewed_plan,r.reviewed_plan) AS reviewed_plan,coalesce(n.plan_hash,r.plan_hash) AS plan_hash,
 r.complete_order,r.request_key,r.request_fingerprint,r.confirmed_by,r.confirmed_at,r.note,r.created_xid,
 r.reviewed_plan AS original_reviewed_plan,n.id AS reconciliation_id,coalesce(n.revision,0) AS reconciliation_revision
 FROM purchasing.po_receipts r LEFT JOIN LATERAL
 (SELECT * FROM purchasing.po_receipt_reconciliations x WHERE x.receipt_id=r.id ORDER BY revision DESC LIMIT 1) n ON true;

CREATE FUNCTION purchasing.guard_po_reconciliation() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE last_id uuid; last_revision integer;
BEGIN
 PERFORM 1 FROM purchasing.po_receipts WHERE id=NEW.receipt_id FOR UPDATE;
 SELECT id,revision INTO last_id,last_revision FROM purchasing.po_receipt_reconciliations
  WHERE receipt_id=NEW.receipt_id ORDER BY revision DESC LIMIT 1;
 IF NEW.previous_reconciliation_id IS DISTINCT FROM last_id OR NEW.revision<>coalesce(last_revision,0)+1
 THEN RAISE EXCEPTION 'Receipt reconciliation must extend its latest review'; END IF;
 IF NOT EXISTS(SELECT 1 FROM purchasing.current_posting_lines p
   WHERE p.document_id=NEW.document_id AND p.document_version_id=NEW.source_version_id
   AND p.initial_batch_id=NEW.initial_batch_id AND p.correction_id IS NOT DISTINCT FROM NEW.source_correction_id)
 THEN RAISE EXCEPTION 'Receipt reconciliation must use the current posted invoice'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER po_reconciliation_guard BEFORE INSERT ON purchasing.po_receipt_reconciliations
 FOR EACH ROW EXECUTE FUNCTION purchasing.guard_po_reconciliation();
CREATE FUNCTION purchasing.guard_po_reconciliation_line() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE r purchasing.po_receipt_reconciliations; m purchasing.mapping_decisions; u purchasing.unit_profiles;
BEGIN
 SELECT * INTO STRICT r FROM purchasing.po_receipt_reconciliations WHERE id=NEW.reconciliation_id;
 IF r.created_xid<>pg_current_xact_id() THEN RAISE EXCEPTION 'Committed reconciliation is sealed'; END IF;
 SELECT * INTO STRICT m FROM purchasing.mapping_decisions WHERE id=NEW.mapping_id;
 IF NOT EXISTS(SELECT 1 FROM purchasing.current_posting_lines p WHERE p.document_id=r.document_id
   AND p.document_version_id=r.source_version_id AND p.correction_id IS NOT DISTINCT FROM r.source_correction_id
   AND p.initial_batch_id=r.initial_batch_id AND p.line_id=NEW.source_line_id AND p.mapping_id=m.id)
   OR m.classification<>'food' OR m.movement_kind<>'receipt' OR m.store_id<>r.store_id
   OR m.base_quantity<>NEW.base_quantity OR m.base_unit<>NEW.base_unit
 THEN RAISE EXCEPTION 'Reconciliation lines must retain current purchased-food receipts exactly'; END IF;
 IF NEW.po_line_id IS NOT NULL THEN
  SELECT * INTO STRICT u FROM purchasing.unit_profiles WHERE id=NEW.unit_profile_id;
  IF u.store_id<>r.store_id OR u.item_code<>m.item_code OR u.base_unit<>m.base_unit OR u.profile_kind<>'purchase'
   OR NOT EXISTS(SELECT 1 FROM public.purchase_order_lines l WHERE l.id=NEW.po_line_id AND l.po_id=r.po_id
      AND l.item_code=m.item_code AND l.unit=u.source_unit)
  THEN RAISE EXCEPTION 'Reconciliation match differs from the frozen ordered item/unit'; END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER po_reconciliation_line_guard BEFORE INSERT ON purchasing.po_receipt_reconciliation_lines
 FOR EACH ROW EXECUTE FUNCTION purchasing.guard_po_reconciliation_line();
CREATE FUNCTION purchasing.check_complete_po_reconciliation() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE rid uuid; r purchasing.po_receipt_reconciliations; n integer; source_count integer;
BEGIN
 IF TG_TABLE_NAME='po_receipt_reconciliations' THEN rid:=NEW.id; ELSE rid:=NEW.reconciliation_id; END IF;
 SELECT * INTO STRICT r FROM purchasing.po_receipt_reconciliations WHERE id=rid;
 SELECT count(*) INTO n FROM purchasing.po_receipt_reconciliation_lines WHERE reconciliation_id=rid;
 SELECT count(*) INTO source_count FROM purchasing.current_posting_lines p
   JOIN purchasing.mapping_decisions m ON m.id=p.mapping_id WHERE p.document_id=r.document_id
   AND p.document_version_id=r.source_version_id AND p.correction_id IS NOT DISTINCT FROM r.source_correction_id
   AND m.classification='food' AND m.movement_kind='receipt';
 IF n<>source_count OR n<>jsonb_array_length(r.reviewed_plan->'receiptLines') OR EXISTS(
  SELECT 1 FROM jsonb_array_elements(r.reviewed_plan->'receiptLines') p WHERE NOT EXISTS(
   SELECT 1 FROM purchasing.po_receipt_reconciliation_lines l WHERE l.reconciliation_id=rid
    AND l.source_line_id=(p->>'source_line_id')::uuid AND l.mapping_id=(p->>'mapping_id')::uuid
    AND l.po_line_id IS NOT DISTINCT FROM (p->>'po_line_id')::uuid
    AND l.unit_profile_id IS NOT DISTINCT FROM (p->>'unit_profile_id')::uuid
    AND l.base_quantity=(p->>'base_quantity')::numeric AND l.base_unit=p->>'base_unit'))
 THEN RAISE EXCEPTION 'Reconciliation must atomically retain its full current reviewed receipt'; END IF;
 RETURN NEW;
END $$;
CREATE CONSTRAINT TRIGGER complete_po_reconciliation AFTER INSERT ON purchasing.po_receipt_reconciliations
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION purchasing.check_complete_po_reconciliation();
CREATE CONSTRAINT TRIGGER complete_po_reconciliation_line AFTER INSERT ON purchasing.po_receipt_reconciliation_lines
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION purchasing.check_complete_po_reconciliation();
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['po_receipt_reconciliations','po_receipt_reconciliation_lines'] LOOP
  EXECUTE format('CREATE TRIGGER immutable_fact BEFORE UPDATE OR DELETE ON purchasing.%I FOR EACH ROW EXECUTE FUNCTION purchasing.reject_fact_change()',t);
 END LOOP;
END $$;
REVOKE ALL ON ALL TABLES IN SCHEMA purchasing FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA purchasing FROM PUBLIC;
COMMIT;
