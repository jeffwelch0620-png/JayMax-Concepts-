-- Apply after native purchases, counts, period corrections and scope bridges.
-- Append-only, whole-document reversals and replacements; no live data import.
BEGIN;
CREATE TABLE purchasing.corrections (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 initial_batch_id uuid NOT NULL REFERENCES purchasing.posting_batches(id),
 previous_correction_id uuid UNIQUE REFERENCES purchasing.corrections(id),
 replacement_version_id uuid NOT NULL REFERENCES purchasing.document_versions(id),
 reconciliation_id uuid NOT NULL REFERENCES purchasing.reconciliation_checks(id),
 idempotency_key text NOT NULL UNIQUE,
 request_fingerprint bytea NOT NULL CHECK(octet_length(request_fingerprint)=32),
 reviewed_plan jsonb NOT NULL CHECK(jsonb_typeof(reviewed_plan)='object'),
 reason text NOT NULL CHECK(length(btrim(reason))>0),
 corrected_by text NOT NULL, corrected_at timestamptz NOT NULL DEFAULT now(),
 created_xid bigint NOT NULL DEFAULT txid_current(),
 UNIQUE(id,initial_batch_id)
);
CREATE UNIQUE INDEX correction_one_root ON purchasing.corrections(initial_batch_id)
 WHERE previous_correction_id IS NULL;
CREATE INDEX correction_batch_history ON purchasing.corrections(initial_batch_id,corrected_at);
CREATE TABLE purchasing.correction_lines (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 correction_id uuid NOT NULL REFERENCES purchasing.corrections(id),
 polarity integer NOT NULL CHECK(polarity IN (-1,1)),
 line_id uuid NOT NULL REFERENCES purchasing.document_lines(id),
 mapping_id uuid NOT NULL,
 FOREIGN KEY(mapping_id,line_id) REFERENCES purchasing.mapping_decisions(id,line_id),
 UNIQUE(correction_id,polarity,line_id)
);
-- Full current dispositions, including fee/tax/nonfood lines, support later corrections.
CREATE VIEW purchasing.current_posting_lines AS
 SELECT b.id AS initial_batch_id,b.document_id,b.document_version_id,
 pl.line_id,pl.mapping_id,NULL::uuid AS correction_id
 FROM purchasing.posting_batches b JOIN purchasing.posting_lines pl ON pl.batch_id=b.id
 WHERE NOT EXISTS(SELECT 1 FROM purchasing.corrections c WHERE c.initial_batch_id=b.id)
 UNION ALL
 SELECT c.initial_batch_id,b.document_id,c.replacement_version_id,cl.line_id,cl.mapping_id,c.id
 FROM purchasing.corrections c JOIN purchasing.posting_batches b ON b.id=c.initial_batch_id
 JOIN purchasing.correction_lines cl ON cl.correction_id=c.id AND cl.polarity=1
 WHERE NOT EXISTS(SELECT 1 FROM purchasing.corrections next WHERE next.previous_correction_id=c.id);
CREATE VIEW purchasing.current_purchase_facts AS
 SELECT i.store_id,i.vendor_id,i.id AS document_id,pl.line_id,pl.mapping_id,
 m.item_code,m.base_unit,m.base_quantity,m.inventory_cost_amount,
 m.inventory_record_date,m.goods_received_date,m.returned_date,
 m.inventory_effective_at,m.goods_received_at,m.cost_policy_version,
 l.extended_amount_source AS vendor_line_amount,d.confirmed_currency
 FROM purchasing.current_posting_lines pl
 JOIN purchasing.document_identities i ON i.id=pl.document_id
 JOIN purchasing.document_versions d ON d.id=pl.document_version_id
 JOIN purchasing.document_lines l ON l.id=pl.line_id
 JOIN purchasing.mapping_decisions m ON m.id=pl.mapping_id WHERE m.classification='food';
-- Keep original column names/types; append stable event identifiers for audit displays.
CREATE OR REPLACE VIEW purchasing.actual_purchase_facts AS
 SELECT i.store_id,i.vendor_id,i.id AS document_id,pl.line_id,pl.mapping_id,
 m.item_code,m.base_unit,m.base_quantity,m.inventory_cost_amount,
 m.inventory_record_date,m.goods_received_date,m.returned_date,
 m.inventory_effective_at,m.goods_received_at,m.cost_policy_version,
 l.extended_amount_source AS vendor_line_amount,d.confirmed_currency,
 pl.mapping_id AS fact_id,'initial'::text AS fact_kind,NULL::uuid AS correction_id
 FROM purchasing.posting_lines pl JOIN purchasing.posting_batches b ON b.id=pl.batch_id
 JOIN purchasing.document_identities i ON i.id=b.document_id
 JOIN purchasing.document_versions d ON d.id=pl.document_version_id
 JOIN purchasing.document_lines l ON l.id=pl.line_id
 JOIN purchasing.mapping_decisions m ON m.id=pl.mapping_id WHERE m.classification='food'
 UNION ALL
 SELECT i.store_id,i.vendor_id,i.id,cl.line_id,cl.mapping_id,
 m.item_code,m.base_unit,m.base_quantity*cl.polarity,m.inventory_cost_amount*cl.polarity,
 m.inventory_record_date,m.goods_received_date,m.returned_date,
 m.inventory_effective_at,m.goods_received_at,m.cost_policy_version,
 l.extended_amount_source,d.confirmed_currency,cl.id,
 CASE WHEN cl.polarity=-1 THEN 'reversal' ELSE 'replacement' END,c.id
 FROM purchasing.correction_lines cl JOIN purchasing.corrections c ON c.id=cl.correction_id
 JOIN purchasing.posting_batches b ON b.id=c.initial_batch_id
 JOIN purchasing.document_identities i ON i.id=b.document_id
 JOIN purchasing.document_lines l ON l.id=cl.line_id
 JOIN purchasing.document_versions d ON d.id=l.document_version_id
 JOIN purchasing.mapping_decisions m ON m.id=cl.mapping_id WHERE m.classification='food';

CREATE FUNCTION purchasing.validate_review(p_version uuid) RETURNS uuid LANGUAGE plpgsql AS $$
DECLARE d purchasing.document_versions; i purchasing.document_identities;
 r purchasing.reconciliation_checks; n integer; mapped integer; source_sum numeric; source_total numeric;
BEGIN
 SELECT * INTO STRICT i FROM purchasing.document_identities WHERE id=(SELECT document_id FROM purchasing.document_versions WHERE id=p_version) FOR UPDATE;
 SELECT * INTO STRICT d FROM purchasing.document_versions WHERE id=p_version FOR UPDATE;
 IF cardinality(d.projection_errors)>0 OR d.confirmed_currency<>'USD'
 THEN RAISE EXCEPTION 'Source projection and USD currency must be confirmed'; END IF;
 IF d.revision<>(SELECT max(revision) FROM purchasing.document_versions WHERE document_id=i.id)
 THEN RAISE EXCEPTION 'Review the latest source version before posting'; END IF;
 -- Serialize with the guarded legacy invoice writer, including older app builds.
 PERFORM pg_advisory_xact_lock(hashtext('purchase-invoice'),
     hashtext(concat_ws('|',i.store_id,i.vendor_id,i.document_number)));
 IF EXISTS (SELECT 1 FROM public.invoices WHERE store_id=i.store_id AND vendor_id=i.vendor_id
     AND btrim(invoice_number)=i.document_number)
 THEN RAISE EXCEPTION 'Legacy invoice already exists; reconcile before posting'; END IF;
 IF EXISTS (SELECT 1 FROM purchasing.document_identities other
     JOIN purchasing.posting_batches posted ON posted.document_id=other.id
     WHERE other.store_id=i.store_id AND other.vendor_id=i.vendor_id AND other.document_type=i.document_type
       AND other.document_number=i.document_number AND other.id<>i.id)
 THEN RAISE EXCEPTION 'Invoice number already posted under a different identity namespace'; END IF;
 INSERT INTO public.store_state(store_id) VALUES(i.store_id) ON CONFLICT(store_id) DO NOTHING;
 PERFORM 1 FROM public.store_state WHERE store_id=i.store_id FOR UPDATE;
 IF EXISTS (SELECT 1 FROM purchasing.document_lines l
     JOIN LATERAL (SELECT * FROM purchasing.mapping_decisions WHERE line_id=l.id ORDER BY revision DESC LIMIT 1) m ON true
     JOIN public.reporting_periods p ON p.store_id=i.store_id AND p.status='closed'
       AND m.inventory_record_date BETWEEN p.period_start AND p.period_end
     WHERE l.document_version_id=p_version)
 THEN RAISE EXCEPTION 'Closed inventory period requires correction review'; END IF;
 IF NOT d.header_consistency_confirmed THEN RAISE EXCEPTION 'Repeated headers not confirmed consistent'; END IF;
 SELECT count(*),sum(extended_amount_source) INTO n,source_sum
 FROM purchasing.document_lines WHERE document_version_id=p_version;
 IF n<>d.expected_line_count OR EXISTS (
   SELECT 1 FROM purchasing.document_lines WHERE document_version_id=p_version AND extended_amount_source IS NULL)
 THEN RAISE EXCEPTION 'Incomplete source document'; END IF;
 SELECT * INTO r FROM purchasing.reconciliation_checks
 WHERE document_version_id=p_version ORDER BY revision DESC LIMIT 1;
 IF NOT FOUND OR r.status<>'balanced' OR r.line_total<>source_sum
 THEN RAISE EXCEPTION 'Missing, held or stale reconciliation'; END IF;
 source_total:=coalesce(d.total_source,d.net_after_adjustment_source);
 IF source_total IS NULL OR source_total<>r.stated_document_total
 THEN RAISE EXCEPTION 'Source total not reconciled'; END IF;
 IF d.subtotal_source IS NOT NULL AND d.subtotal_source<>source_sum
 THEN RAISE EXCEPTION 'Source subtotal does not match line amounts'; END IF;
 IF d.total_source IS NOT NULL THEN
  IF d.fees_source IS NULL OR d.tax_source IS NULL OR d.discount_source IS NULL
  THEN RAISE EXCEPTION 'Missing source total components'; END IF;
  IF d.discount_source<>0 THEN RAISE EXCEPTION 'Discount allocation policy requires review'; END IF;
  IF r.expected_document_total<>source_sum+d.fees_source+d.tax_source-d.discount_source
  THEN RAISE EXCEPTION 'Reconciliation does not match retained invoice components'; END IF;
 ELSE
  IF d.delivery_adjustment_source IS NULL OR d.delivery_adjustment_source<>0
   OR d.net_before_adjustment_source IS NULL OR d.net_before_adjustment_source<>d.net_after_adjustment_source
  THEN RAISE EXCEPTION 'Vendor adjustment interpretation requires review'; END IF;
  IF r.expected_document_total<>source_sum
  THEN RAISE EXCEPTION 'Unexplained source total difference'; END IF;
 END IF;
 IF d.document_number IS NULL OR btrim(d.document_number)<>i.document_number
  OR d.document_type_raw IS NULL OR
   (CASE WHEN lower(btrim(d.document_type_raw)) IN ('credit memo','creditmemo','credit_memo')
     THEN 'credit' ELSE lower(btrim(d.document_type_raw)) END)<>i.document_type
 THEN RAISE EXCEPTION 'Document identity differs from source header'; END IF;
 SELECT count(*) INTO mapped FROM purchasing.document_lines l
 JOIN LATERAL (SELECT * FROM purchasing.mapping_decisions
  WHERE line_id=l.id ORDER BY revision DESC LIMIT 1) m ON true
 WHERE l.document_version_id=p_version AND m.store_id=i.store_id;
 IF mapped<>n THEN RAISE EXCEPTION 'Every source line needs a verified disposition'; END IF;
 IF EXISTS (
  SELECT 1 FROM purchasing.document_lines l
  JOIN LATERAL (SELECT * FROM purchasing.mapping_decisions WHERE line_id=l.id ORDER BY revision DESC LIMIT 1) m ON true
  WHERE l.document_version_id=p_version AND m.classification='food'
   AND m.inventory_cost_amount<>l.extended_amount_source
 ) THEN RAISE EXCEPTION 'Food costs must use source line amounts; taxes and fees stay separate'; END IF;
 IF EXISTS (
  SELECT 1 FROM purchasing.document_lines l
  JOIN LATERAL (SELECT * FROM purchasing.mapping_decisions WHERE line_id=l.id ORDER BY revision DESC LIMIT 1) m ON true
  WHERE l.document_version_id=p_version AND m.movement_kind='price_credit'
  AND NOT EXISTS (
   SELECT 1 FROM purchasing.current_purchase_facts original
   JOIN purchasing.mapping_decisions om ON om.id=original.mapping_id
   WHERE original.line_id=m.credit_original_line_id AND original.store_id=m.store_id
    AND original.item_code=m.item_code AND original.base_unit=m.base_unit AND original.vendor_id=i.vendor_id
    AND om.movement_kind='receipt'
  )
 ) THEN RAISE EXCEPTION 'Price credit requires a matching posted original receipt'; END IF;

 RETURN r.id;
END $$;

CREATE FUNCTION purchasing.correct_document(p_version uuid,p_key text,p_actor text,p_fingerprint bytea,
 p_initial uuid,p_previous uuid,p_plan jsonb,p_reason text) RETURNS uuid LANGUAGE plpgsql AS $$
DECLARE b purchasing.posting_batches; d purchasing.document_versions;
 prior purchasing.corrections; latest uuid; rid uuid; cid uuid; sid text;
BEGIN
 PERFORM 1 FROM purchasing.document_identities WHERE id=(SELECT document_id FROM purchasing.document_versions WHERE id=p_version) FOR UPDATE;
 SELECT * INTO STRICT d FROM purchasing.document_versions WHERE id=p_version FOR UPDATE;
 SELECT * INTO STRICT b FROM purchasing.posting_batches WHERE document_id=d.document_id;
 IF b.id<>p_initial THEN RAISE EXCEPTION 'Original posting changed; review again'; END IF;
 SELECT * INTO prior FROM purchasing.corrections WHERE idempotency_key=p_key;
 IF FOUND THEN
  IF prior.initial_batch_id=b.id AND prior.request_fingerprint=p_fingerprint THEN RETURN prior.id; END IF;
  RAISE EXCEPTION 'Correction retry key was used for another review';
 END IF;
 SELECT c.id INTO latest FROM purchasing.corrections c WHERE c.initial_batch_id=b.id
  AND NOT EXISTS(SELECT 1 FROM purchasing.corrections n WHERE n.previous_correction_id=c.id);
 IF latest IS DISTINCT FROM p_previous THEN RAISE EXCEPTION 'Invoice changed; preview its current posting again'; END IF;
 SELECT store_id INTO STRICT sid FROM purchasing.document_identities WHERE id=b.document_id;
 PERFORM pg_advisory_xact_lock(hashtext('purchase-invoice'),hashtext(concat_ws('|',sid,
  (SELECT vendor_id FROM purchasing.document_identities WHERE id=b.document_id),d.document_number)));
 INSERT INTO public.store_state(store_id) VALUES(sid) ON CONFLICT(store_id) DO NOTHING;
 PERFORM 1 FROM public.store_state WHERE store_id=sid FOR UPDATE;
 -- Old dates must be checked even when the replacement moves the receipt elsewhere
 -- or reclassifies it outside food. New dates are also checked by mapping guards.
 IF EXISTS(SELECT 1 FROM purchasing.current_purchase_facts f
   JOIN actual_inventory.active_period_closures p ON p.store_id=f.store_id
    AND f.inventory_record_date>=p.period_start AND f.inventory_record_date<p.period_end_exclusive
   WHERE f.document_id=b.document_id)
 OR EXISTS(SELECT 1 FROM purchasing.current_purchase_facts f JOIN public.reporting_periods p
   ON p.store_id=f.store_id AND p.status='closed' AND f.inventory_record_date BETWEEN p.period_start AND p.period_end
   WHERE f.document_id=b.document_id)
 THEN RAISE EXCEPTION 'Reopen affected old inventory periods before reversing this invoice'; END IF;
 IF EXISTS(SELECT 1 FROM purchasing.current_posting_lines original
   JOIN purchasing.mapping_decisions om ON om.id=original.mapping_id
   JOIN purchasing.current_posting_lines dependent ON dependent.document_id<>original.document_id
   JOIN purchasing.mapping_decisions dm ON dm.id=dependent.mapping_id
   WHERE original.document_id=b.document_id AND dm.credit_original_line_id=original.line_id)
 THEN RAISE EXCEPTION 'Linked credits or returns require reconciliation before replacing this receipt'; END IF;
 rid:=purchasing.validate_review(p_version);
 INSERT INTO purchasing.corrections(initial_batch_id,previous_correction_id,replacement_version_id,
  reconciliation_id,idempotency_key,request_fingerprint,reviewed_plan,reason,corrected_by)
 VALUES(b.id,p_previous,p_version,rid,p_key,p_fingerprint,p_plan,p_reason,p_actor) RETURNING id INTO cid;
 -- Inserting the correction changes the current view; select the previous generation explicitly.
 INSERT INTO purchasing.correction_lines(correction_id,polarity,line_id,mapping_id)
 SELECT cid,-1,pl.line_id,pl.mapping_id FROM purchasing.posting_lines pl WHERE p_previous IS NULL AND pl.batch_id=b.id
 UNION ALL SELECT cid,-1,cl.line_id,cl.mapping_id FROM purchasing.correction_lines cl
  WHERE p_previous IS NOT NULL AND cl.correction_id=p_previous AND cl.polarity=1;
 INSERT INTO purchasing.correction_lines(correction_id,polarity,line_id,mapping_id)
 SELECT cid,1,l.id,m.id FROM purchasing.document_lines l JOIN LATERAL
  (SELECT id FROM purchasing.mapping_decisions WHERE line_id=l.id ORDER BY revision DESC LIMIT 1) m ON true
 WHERE l.document_version_id=p_version;
 RETURN cid;
END $$;
-- Preserve direct initial-post validation while ensuring credits reference effective receipts.
CREATE OR REPLACE FUNCTION purchasing.post_document(p_version uuid,p_key text,p_actor text,p_fingerprint bytea) RETURNS uuid
LANGUAGE plpgsql AS $$
DECLARE d purchasing.document_versions; i purchasing.document_identities;
 r purchasing.reconciliation_checks; prior purchasing.posting_batches;
 b uuid; n integer; mapped integer; source_sum numeric; source_total numeric;
BEGIN
 SELECT * INTO STRICT i FROM purchasing.document_identities WHERE id=(SELECT document_id FROM purchasing.document_versions WHERE id=p_version) FOR UPDATE;
 SELECT * INTO STRICT d FROM purchasing.document_versions WHERE id=p_version FOR UPDATE;
 IF cardinality(d.projection_errors)>0 OR d.confirmed_currency<>'USD'
 THEN RAISE EXCEPTION 'Source projection and USD currency must be confirmed'; END IF;
 SELECT * INTO prior FROM purchasing.posting_batches WHERE document_id=i.id;
 IF FOUND THEN
   IF prior.document_version_id=p_version AND prior.idempotency_key=p_key
    AND prior.request_fingerprint=p_fingerprint THEN RETURN prior.id; END IF;
   RAISE EXCEPTION 'Document already posted; use linked correction workflow';
 END IF;
 IF d.revision<>(SELECT max(revision) FROM purchasing.document_versions WHERE document_id=i.id)
 THEN RAISE EXCEPTION 'Review the latest source version before posting'; END IF;
 -- Serialize with the guarded legacy invoice writer, including older app builds.
 PERFORM pg_advisory_xact_lock(hashtext('purchase-invoice'),
     hashtext(concat_ws('|',i.store_id,i.vendor_id,i.document_number)));
 IF EXISTS (SELECT 1 FROM public.invoices WHERE store_id=i.store_id AND vendor_id=i.vendor_id
     AND btrim(invoice_number)=i.document_number)
 THEN RAISE EXCEPTION 'Legacy invoice already exists; reconcile before posting'; END IF;
 IF EXISTS (SELECT 1 FROM purchasing.document_identities other
     JOIN purchasing.posting_batches posted ON posted.document_id=other.id
     WHERE other.store_id=i.store_id AND other.vendor_id=i.vendor_id AND other.document_type=i.document_type
       AND other.document_number=i.document_number AND other.id<>i.id)
 THEN RAISE EXCEPTION 'Invoice number already posted under a different identity namespace'; END IF;
 INSERT INTO public.store_state(store_id) VALUES(i.store_id) ON CONFLICT(store_id) DO NOTHING;
 PERFORM 1 FROM public.store_state WHERE store_id=i.store_id FOR UPDATE;
 IF EXISTS (SELECT 1 FROM purchasing.document_lines l
     JOIN LATERAL (SELECT * FROM purchasing.mapping_decisions WHERE line_id=l.id ORDER BY revision DESC LIMIT 1) m ON true
     JOIN public.reporting_periods p ON p.store_id=i.store_id AND p.status='closed'
       AND m.inventory_record_date BETWEEN p.period_start AND p.period_end
     WHERE l.document_version_id=p_version)
 THEN RAISE EXCEPTION 'Closed inventory period requires correction review'; END IF;
 IF NOT d.header_consistency_confirmed THEN RAISE EXCEPTION 'Repeated headers not confirmed consistent'; END IF;
 SELECT count(*),sum(extended_amount_source) INTO n,source_sum
 FROM purchasing.document_lines WHERE document_version_id=p_version;
 IF n<>d.expected_line_count OR EXISTS (
   SELECT 1 FROM purchasing.document_lines WHERE document_version_id=p_version AND extended_amount_source IS NULL)
 THEN RAISE EXCEPTION 'Incomplete source document'; END IF;
 SELECT * INTO r FROM purchasing.reconciliation_checks
 WHERE document_version_id=p_version ORDER BY revision DESC LIMIT 1;
 IF NOT FOUND OR r.status<>'balanced' OR r.line_total<>source_sum
 THEN RAISE EXCEPTION 'Missing, held or stale reconciliation'; END IF;
 source_total:=coalesce(d.total_source,d.net_after_adjustment_source);
 IF source_total IS NULL OR source_total<>r.stated_document_total
 THEN RAISE EXCEPTION 'Source total not reconciled'; END IF;
 IF d.subtotal_source IS NOT NULL AND d.subtotal_source<>source_sum
 THEN RAISE EXCEPTION 'Source subtotal does not match line amounts'; END IF;
 IF d.total_source IS NOT NULL THEN
  IF d.fees_source IS NULL OR d.tax_source IS NULL OR d.discount_source IS NULL
  THEN RAISE EXCEPTION 'Missing source total components'; END IF;
  IF d.discount_source<>0 THEN RAISE EXCEPTION 'Discount allocation policy requires review'; END IF;
  IF r.expected_document_total<>source_sum+d.fees_source+d.tax_source-d.discount_source
  THEN RAISE EXCEPTION 'Reconciliation does not match retained invoice components'; END IF;
 ELSE
  IF d.delivery_adjustment_source IS NULL OR d.delivery_adjustment_source<>0
   OR d.net_before_adjustment_source IS NULL OR d.net_before_adjustment_source<>d.net_after_adjustment_source
  THEN RAISE EXCEPTION 'Vendor adjustment interpretation requires review'; END IF;
  IF r.expected_document_total<>source_sum
  THEN RAISE EXCEPTION 'Unexplained source total difference'; END IF;
 END IF;
 IF d.document_number IS NULL OR btrim(d.document_number)<>i.document_number
  OR d.document_type_raw IS NULL OR
   (CASE WHEN lower(btrim(d.document_type_raw)) IN ('credit memo','creditmemo','credit_memo')
     THEN 'credit' ELSE lower(btrim(d.document_type_raw)) END)<>i.document_type
 THEN RAISE EXCEPTION 'Document identity differs from source header'; END IF;
 SELECT count(*) INTO mapped FROM purchasing.document_lines l
 JOIN LATERAL (SELECT * FROM purchasing.mapping_decisions
  WHERE line_id=l.id ORDER BY revision DESC LIMIT 1) m ON true
 WHERE l.document_version_id=p_version AND m.store_id=i.store_id;
 IF mapped<>n THEN RAISE EXCEPTION 'Every source line needs a verified disposition'; END IF;
 IF EXISTS (
  SELECT 1 FROM purchasing.document_lines l
  JOIN LATERAL (SELECT * FROM purchasing.mapping_decisions WHERE line_id=l.id ORDER BY revision DESC LIMIT 1) m ON true
  WHERE l.document_version_id=p_version AND m.classification='food'
   AND m.inventory_cost_amount<>l.extended_amount_source
 ) THEN RAISE EXCEPTION 'Food costs must use source line amounts; taxes and fees stay separate'; END IF;
 IF EXISTS (
  SELECT 1 FROM purchasing.document_lines l
  JOIN LATERAL (SELECT * FROM purchasing.mapping_decisions WHERE line_id=l.id ORDER BY revision DESC LIMIT 1) m ON true
  WHERE l.document_version_id=p_version AND m.movement_kind='price_credit'
  AND NOT EXISTS (
   SELECT 1 FROM purchasing.current_purchase_facts original
   JOIN purchasing.mapping_decisions om ON om.id=original.mapping_id
   WHERE original.line_id=m.credit_original_line_id AND original.store_id=m.store_id
    AND original.item_code=m.item_code AND original.base_unit=m.base_unit AND original.vendor_id=i.vendor_id
    AND om.movement_kind='receipt'
  )
 ) THEN RAISE EXCEPTION 'Price credit requires a matching posted original receipt'; END IF;
 INSERT INTO purchasing.posting_batches(document_id,document_version_id,reconciliation_id,idempotency_key,posted_by,request_fingerprint)
 VALUES(i.id,p_version,r.id,p_key,p_actor,p_fingerprint) RETURNING id INTO b;
 INSERT INTO purchasing.posting_lines(batch_id,document_version_id,line_id,mapping_id)
 SELECT b,p_version,l.id,m.id FROM purchasing.document_lines l
 JOIN LATERAL (SELECT id FROM purchasing.mapping_decisions WHERE line_id=l.id ORDER BY revision DESC LIMIT 1) m ON true
 WHERE l.document_version_id=p_version;
 RETURN b;
END $$;

CREATE TRIGGER immutable_fact BEFORE UPDATE OR DELETE ON purchasing.corrections
 FOR EACH ROW EXECUTE FUNCTION purchasing.reject_fact_change();
CREATE TRIGGER immutable_fact BEFORE UPDATE OR DELETE ON purchasing.correction_lines
 FOR EACH ROW EXECUTE FUNCTION purchasing.reject_fact_change();
-- Backend SQL callers must obey the same identity, lineage and date guards.
CREATE FUNCTION purchasing.guard_correction() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE b purchasing.posting_batches; sid text; latest uuid; vid uuid; rid uuid;
BEGIN
 SELECT * INTO STRICT b FROM purchasing.posting_batches WHERE id=NEW.initial_batch_id;
 SELECT document_id INTO STRICT vid FROM purchasing.document_versions WHERE id=NEW.replacement_version_id;
 IF vid<>b.document_id THEN RAISE EXCEPTION 'Correction cannot change invoice identity'; END IF;
 SELECT store_id INTO STRICT sid FROM purchasing.document_identities WHERE id=b.document_id FOR UPDATE;
 PERFORM 1 FROM purchasing.document_versions WHERE id=NEW.replacement_version_id FOR UPDATE;
 PERFORM pg_advisory_xact_lock(hashtext('purchase-invoice'),hashtext(concat_ws('|',sid,
  (SELECT vendor_id FROM purchasing.document_identities WHERE id=b.document_id),
  (SELECT document_number FROM purchasing.document_identities WHERE id=b.document_id))));
 INSERT INTO public.store_state(store_id) VALUES(sid) ON CONFLICT DO NOTHING;
 PERFORM 1 FROM public.store_state WHERE store_id=sid FOR UPDATE;
 SELECT c.id INTO latest FROM purchasing.corrections c WHERE c.initial_batch_id=b.id
  AND NOT EXISTS(SELECT 1 FROM purchasing.corrections n WHERE n.previous_correction_id=c.id);
 IF latest IS DISTINCT FROM NEW.previous_correction_id THEN RAISE EXCEPTION 'Correction must replace the current generation'; END IF;
 IF EXISTS(SELECT 1 FROM purchasing.current_purchase_facts f JOIN actual_inventory.active_period_closures p
  ON p.store_id=f.store_id AND f.inventory_record_date>=p.period_start AND f.inventory_record_date<p.period_end_exclusive
  WHERE f.document_id=b.document_id)
 OR EXISTS(SELECT 1 FROM purchasing.current_purchase_facts f JOIN public.reporting_periods p
  ON p.store_id=f.store_id AND p.status='closed' AND f.inventory_record_date BETWEEN p.period_start AND p.period_end
  WHERE f.document_id=b.document_id)
 OR EXISTS(SELECT 1 FROM purchasing.document_lines l JOIN LATERAL
  (SELECT * FROM purchasing.mapping_decisions WHERE line_id=l.id ORDER BY revision DESC LIMIT 1) m ON true
  JOIN actual_inventory.active_period_closures p ON p.store_id=sid
   AND m.inventory_record_date>=p.period_start AND m.inventory_record_date<p.period_end_exclusive
  WHERE l.document_version_id=NEW.replacement_version_id AND m.classification='food')
 THEN RAISE EXCEPTION 'Reopen both old and replacement inventory dates before correction'; END IF;
 IF EXISTS(SELECT 1 FROM purchasing.current_posting_lines original
  JOIN purchasing.current_posting_lines dependent ON dependent.document_id<>original.document_id
  JOIN purchasing.mapping_decisions dm ON dm.id=dependent.mapping_id
  WHERE original.document_id=b.document_id AND dm.credit_original_line_id=original.line_id)
 THEN RAISE EXCEPTION 'Reconcile linked credits or returns before replacing their receipt'; END IF;
 rid:=purchasing.validate_review(NEW.replacement_version_id);
 IF rid<>NEW.reconciliation_id THEN RAISE EXCEPTION 'Correction requires the current balanced reconciliation'; END IF;
 NEW.created_xid:=txid_current();
 RETURN NEW;
END $$;
CREATE TRIGGER validate_correction BEFORE INSERT ON purchasing.corrections
 FOR EACH ROW EXECUTE FUNCTION purchasing.guard_correction();

-- Validate once per correction at commit, with no quadratic per-line rescans.
CREATE FUNCTION purchasing.guard_complete_correction() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE c purchasing.corrections; reversed integer; replaced integer; expected integer;
BEGIN
 SELECT * INTO STRICT c FROM purchasing.corrections WHERE id=NEW.id;
 SELECT count(*) INTO reversed FROM purchasing.correction_lines WHERE correction_id=c.id AND polarity=-1;
 SELECT count(*) INTO replaced FROM purchasing.correction_lines WHERE correction_id=c.id AND polarity=1;
 IF c.previous_correction_id IS NULL THEN
  SELECT count(*) INTO expected FROM purchasing.posting_lines WHERE batch_id=c.initial_batch_id;
  IF EXISTS(SELECT 1 FROM purchasing.correction_lines l WHERE l.correction_id=c.id AND l.polarity=-1
    AND NOT EXISTS(SELECT 1 FROM purchasing.posting_lines prior_entry WHERE prior_entry.batch_id=c.initial_batch_id
      AND prior_entry.line_id=l.line_id AND prior_entry.mapping_id=l.mapping_id)) THEN
   RAISE EXCEPTION 'Reversal must cancel the exact initial mappings'; END IF;
 ELSE
  SELECT count(*) INTO expected FROM purchasing.correction_lines WHERE correction_id=c.previous_correction_id AND polarity=1;
  IF EXISTS(SELECT 1 FROM purchasing.correction_lines l WHERE l.correction_id=c.id AND l.polarity=-1
    AND NOT EXISTS(SELECT 1 FROM purchasing.correction_lines prior_entry WHERE prior_entry.correction_id=c.previous_correction_id
      AND prior_entry.polarity=1 AND prior_entry.line_id=l.line_id AND prior_entry.mapping_id=l.mapping_id)) THEN
   RAISE EXCEPTION 'Reversal must cancel the exact previous replacement'; END IF;
 END IF;
 IF reversed<>expected OR reversed=0 OR replaced<>(SELECT count(*) FROM purchasing.document_lines WHERE document_version_id=c.replacement_version_id)
 OR EXISTS(SELECT 1 FROM purchasing.correction_lines cl JOIN purchasing.document_lines l ON l.id=cl.line_id
   WHERE cl.correction_id=c.id AND cl.polarity=1 AND (l.document_version_id<>c.replacement_version_id
     OR cl.mapping_id<>(SELECT id FROM purchasing.mapping_decisions WHERE line_id=l.id ORDER BY revision DESC LIMIT 1)))
 THEN RAISE EXCEPTION 'Invoice correction must include the complete reversal and complete replacement'; END IF;
 RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER complete_correction AFTER INSERT ON purchasing.corrections
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION purchasing.guard_complete_correction();
CREATE FUNCTION purchasing.seal_correction_lines() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF (SELECT created_xid FROM purchasing.corrections WHERE id=NEW.correction_id) IS DISTINCT FROM txid_current()
 THEN RAISE EXCEPTION 'Committed correction entries are sealed'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER seal_correction BEFORE INSERT ON purchasing.correction_lines
 FOR EACH ROW EXECUTE FUNCTION purchasing.seal_correction_lines();
-- Seal replacement source versions too, independently of API read-back.
CREATE OR REPLACE FUNCTION purchasing.guard_line_addition() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 PERFORM 1 FROM purchasing.document_versions WHERE id=NEW.document_version_id FOR UPDATE;
 IF EXISTS(SELECT 1 FROM purchasing.posting_batches WHERE document_version_id=NEW.document_version_id)
 OR EXISTS(SELECT 1 FROM purchasing.corrections WHERE replacement_version_id=NEW.document_version_id)
 THEN RAISE EXCEPTION 'Posted document version is sealed'; END IF; RETURN NEW;
END $$;
REVOKE ALL ON ALL TABLES IN SCHEMA purchasing FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA purchasing FROM PUBLIC;
COMMIT;
