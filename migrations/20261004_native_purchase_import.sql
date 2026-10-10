-- Native invoice capture and initial purchase posting, 2026-10-04.
-- Apply explicitly in a disposable environment first. No automatic startup DDL.
-- Requires the application public schema. Enable UI/API only after this migration.
-- Received dates are DATE facts; optional timestamps never invent receipt times.
-- Corrected/reissued posted invoices and closed periods remain held for review.
BEGIN;
CREATE SCHEMA purchasing;

CREATE FUNCTION purchasing.text_cells(value jsonb) RETURNS boolean
LANGUAGE sql IMMUTABLE STRICT AS $$
 SELECT CASE WHEN jsonb_typeof(value) <> 'array' THEN false ELSE
   NOT EXISTS (SELECT 1 FROM jsonb_array_elements(value) AS x WHERE jsonb_typeof(x) <> 'string') END
$$;

CREATE FUNCTION purchasing.reject_fact_change() RETURNS trigger
LANGUAGE plpgsql AS $$ BEGIN
 RAISE EXCEPTION 'Immutable purchase fact: append a new version or linked correction';
END $$;

CREATE TABLE purchasing.import_files (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 store_id text NOT NULL REFERENCES public.stores(id),
 source_sha256 bytea NOT NULL CHECK (octet_length(source_sha256)=32),
 source_bytes bytea NOT NULL,
 original_filename text NOT NULL,
 mime_type text NOT NULL,
 encoding_hint text,
 captured_at timestamptz NOT NULL DEFAULT now(),
 captured_by text NOT NULL,
 CHECK (source_sha256=sha256(source_bytes)),
 UNIQUE(store_id,source_sha256)
);
CREATE TABLE purchasing.upload_attempts (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 file_id uuid NOT NULL REFERENCES purchasing.import_files(id),
 attempt_key text NOT NULL UNIQUE,
 supplied_filename text NOT NULL,
 attempted_by text NOT NULL,
 attempted_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE purchasing.parse_runs (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 file_id uuid NOT NULL REFERENCES purchasing.import_files(id),
 parser_version text NOT NULL,
 detected_vendor_format text,
 encoding_used text,
 header_cells jsonb NOT NULL CHECK (purchasing.text_cells(header_cells)),
 parse_errors jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(parse_errors)='array'),
 parsed_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(file_id,parser_version)
);
CREATE TABLE purchasing.raw_rows (
 parse_run_id uuid NOT NULL REFERENCES purchasing.parse_runs(id),
 row_ordinal integer NOT NULL CHECK (row_ordinal>0),
 raw_values jsonb NOT NULL CHECK (purchasing.text_cells(raw_values)),
 parse_errors jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(parse_errors)='array'),
 PRIMARY KEY(parse_run_id,row_ordinal)
 -- Unequal widths are retained with parse errors; never rejected at raw capture.
);

CREATE TABLE purchasing.document_identities (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 store_id text NOT NULL REFERENCES public.stores(id),
 vendor_id text NOT NULL REFERENCES public.vendors(id),
 vendor_branch_key text NOT NULL,
 customer_account_key text NOT NULL,
 document_type text NOT NULL CHECK (document_type IN ('invoice','credit')),
 document_number text NOT NULL CHECK (length(btrim(document_number))>0),
 created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(store_id,vendor_id,vendor_branch_key,customer_account_key,document_type,document_number),
 UNIQUE(id,store_id)
 -- Missing or ambiguous identity stays captured, awaiting review.
 -- Invoice date is a fact, not a way to bypass duplicate-document detection.
 -- Vendor number reuse needs a verified identity namespace before production.
);
CREATE TABLE purchasing.document_versions (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 document_id uuid NOT NULL REFERENCES purchasing.document_identities(id),
 revision integer NOT NULL CHECK (revision>0),
 canonical_fingerprint bytea NOT NULL CHECK (octet_length(canonical_fingerprint)=32),
 expected_line_count integer NOT NULL CHECK (expected_line_count>0),
 parser_version text NOT NULL,
 source_currency text,
 confirmed_currency text NOT NULL CHECK (confirmed_currency ~ '^[A-Z]{3}$'),
 header_consistency_confirmed boolean NOT NULL DEFAULT false,
 projection_errors text[] NOT NULL DEFAULT '{}',
 observed_at timestamptz NOT NULL DEFAULT now(),
    document_number text,
    document_type_raw text,
    invoice_date date,
    customer_number text,
    customer_name_snapshot text,
    account_number text,
    purchase_order_reference text,
    vendor_branch_reference text,
    sales_representative_reference text,
    ordered_date date,
    vendor_order_number text,
    payment_terms_raw text,
    shipped_date date,
    delivery_adjustment_source numeric CHECK (delivery_adjustment_source IS NULL OR delivery_adjustment_source NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)),
    net_after_adjustment_source numeric CHECK (net_after_adjustment_source IS NULL OR net_after_adjustment_source NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)),
    net_before_adjustment_source numeric CHECK (net_before_adjustment_source IS NULL OR net_before_adjustment_source NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)),
    credit_memo_reference text,
    credit_memo_date date,
    subtotal_source numeric CHECK (subtotal_source IS NULL OR subtotal_source NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)),
    discount_source numeric CHECK (discount_source IS NULL OR discount_source NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)),
    fees_source numeric CHECK (fees_source IS NULL OR fees_source NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)),
    tax_source numeric CHECK (tax_source IS NULL OR tax_source NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)),
    total_source numeric CHECK (total_source IS NULL OR total_source NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)),
    ordered_quantity_control_source numeric CHECK (ordered_quantity_control_source IS NULL OR ordered_quantity_control_source NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)),
    shipped_quantity_control_source numeric CHECK (shipped_quantity_control_source IS NULL OR shipped_quantity_control_source NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)),
    route_number text,
    route_stop_reference text,
 UNIQUE(document_id,revision),
 UNIQUE(document_id,canonical_fingerprint),
 UNIQUE(id,document_id)
 -- Additional/unknown source fields remain in raw_rows, linked below.
);
CREATE TABLE purchasing.document_lines (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 document_version_id uuid NOT NULL REFERENCES purchasing.document_versions(id),
 line_ordinal integer NOT NULL CHECK (line_ordinal>0),
 source_line_key text,
    vendor_sku_snapshot text,
    description_snapshot text,
    product_label_raw text,
    pack_description_raw text,
    weight_source numeric CHECK (weight_source IS NULL OR weight_source NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)),
    ordered_quantity_source numeric CHECK (ordered_quantity_source IS NULL OR ordered_quantity_source NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)),
    shipped_quantity_source numeric CHECK (shipped_quantity_source IS NULL OR shipped_quantity_source NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)),
    adjusted_quantity_source numeric CHECK (adjusted_quantity_source IS NULL OR adjusted_quantity_source NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)),
    pricing_unit_raw text,
    unit_price_source numeric CHECK (unit_price_source IS NULL OR unit_price_source NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)),
    extended_amount_source numeric CHECK (extended_amount_source IS NULL OR extended_amount_source NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)),
    vendor_reference_raw text,
    manufacturer_name_snapshot text,
    manufacturer_product_number text,
    brand_snapshot text,
    vendor_uom_raw text,
    net_price_source numeric CHECK (net_price_source IS NULL OR net_price_source NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)),
    printed_sequence_reference text,
    vendor_category_raw text,
    gtin_text text,
    custom_product_number text,
    custom_product_description text,
 UNIQUE(document_version_id,line_ordinal),
 UNIQUE(id,document_version_id)
 -- Repeated SKU lines remain distinct. source_line_key is not SKU-only.
);
CREATE TABLE purchasing.document_parties (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 document_version_id uuid NOT NULL REFERENCES purchasing.document_versions(id),
 party_role text NOT NULL CHECK (party_role IN ('customer','bill_to','ship_to','remit_to','ship_from')),
    name_snapshot text,
    address_line_1 text,
    address_line_2 text,
    city text,
    state text,
    postal_code text,
    phone_text text,
    attention_raw text,
    department_reference text,
    department_name text,
 UNIQUE(document_version_id,party_role)
);
CREATE TABLE purchasing.document_source_rows (
 parse_run_id uuid NOT NULL,
 row_ordinal integer NOT NULL,
 document_version_id uuid NOT NULL REFERENCES purchasing.document_versions(id),
 document_line_id uuid,
 PRIMARY KEY(parse_run_id,row_ordinal),
 FOREIGN KEY(parse_run_id,row_ordinal) REFERENCES purchasing.raw_rows(parse_run_id,row_ordinal),
 FOREIGN KEY(document_line_id,document_version_id) REFERENCES purchasing.document_lines(id,document_version_id)
 -- Multiple overlapping files can link to one canonical document/line.
);

CREATE TABLE purchasing.base_units (
 unit_code text PRIMARY KEY,
 dimension text NOT NULL CHECK (dimension IN ('mass','volume','count'))
);
CREATE TABLE purchasing.item_bases (
 store_id text NOT NULL,
 item_code text NOT NULL,
 base_unit text NOT NULL REFERENCES purchasing.base_units(unit_code),
 PRIMARY KEY(store_id,item_code),
 UNIQUE(store_id,item_code,base_unit),
 FOREIGN KEY(store_id,item_code) REFERENCES public.store_items(store_id,item_code)
 -- One fixed actual-inventory unit per store/item. Recipe portions are separate.
);
INSERT INTO purchasing.base_units(unit_code,dimension) VALUES
 ('lb','mass'),('oz','mass'),('g','mass'),('kg','mass'),
 ('fl_oz','volume'),('ml','volume'),('l','volume'),('gal','volume'),('each','count');

CREATE TABLE purchasing.mapping_decisions (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 line_id uuid NOT NULL REFERENCES purchasing.document_lines(id),
 revision integer NOT NULL CHECK (revision>0),
 store_id text NOT NULL REFERENCES public.stores(id),
 classification text NOT NULL CHECK (classification IN ('food','nonfood','fee','tax')),
 movement_kind text NOT NULL CHECK (movement_kind IN ('receipt','physical_return','price_credit','no_inventory')),
 item_code text,
 base_unit text,
 received_quantity numeric,
 received_unit text,
 base_units_per_received_unit numeric CHECK (base_units_per_received_unit>0),
 base_quantity numeric GENERATED ALWAYS AS (
   CASE WHEN movement_kind IN ('receipt','physical_return')
   THEN received_quantity * base_units_per_received_unit ELSE 0 END) STORED,
 inventory_cost_amount numeric NOT NULL,
 inventory_record_date date,
 goods_received_date date,
 returned_date date,
 inventory_effective_at timestamptz,
 goods_received_at timestamptz,
 returned_at timestamptz,
 credit_original_line_id uuid REFERENCES purchasing.document_lines(id),
 pricing_basis text NOT NULL,
 conversion_snapshot jsonb NOT NULL CHECK (jsonb_typeof(conversion_snapshot)='object'),
 cost_policy_version text NOT NULL,
 mapping_method text NOT NULL CHECK (mapping_method IN ('verified_sku','manual')),
 confirmed_by text NOT NULL,
 confirmed_at timestamptz NOT NULL DEFAULT now(),
 decision_note text NOT NULL,
 FOREIGN KEY(store_id,item_code) REFERENCES public.store_items(store_id,item_code),
 FOREIGN KEY(store_id,item_code,base_unit) REFERENCES purchasing.item_bases(store_id,item_code,base_unit),
 UNIQUE(line_id,revision),
 UNIQUE(id,line_id),
 CHECK (classification='food' OR (movement_kind='no_inventory' AND inventory_cost_amount=0 AND item_code IS NULL)),
 CHECK (classification<>'food' OR movement_kind='no_inventory' OR (item_code IS NOT NULL AND base_unit IS NOT NULL AND length(btrim(base_unit))>0 AND inventory_record_date IS NOT NULL)),
 CHECK (movement_kind<>'no_inventory' OR (inventory_cost_amount=0 AND (received_quantity IS NULL OR received_quantity=0))),
 CHECK (movement_kind NOT IN ('receipt','physical_return') OR (received_quantity IS NOT NULL AND received_unit IS NOT NULL AND base_units_per_received_unit IS NOT NULL)),
 CHECK (movement_kind<>'receipt' OR (goods_received_date IS NOT NULL AND inventory_record_date=goods_received_date)),
 CHECK (movement_kind<>'physical_return' OR (returned_date IS NOT NULL AND inventory_record_date=returned_date)),
 CHECK (movement_kind<>'receipt' OR (received_quantity>=0 AND inventory_cost_amount>=0)),
 CHECK (movement_kind<>'physical_return' OR (received_quantity<0 AND inventory_cost_amount<=0)),
 CHECK (movement_kind<>'price_credit' OR (inventory_cost_amount<=0 AND (received_quantity IS NULL OR received_quantity=0))),
 CHECK (movement_kind<>'price_credit' OR credit_original_line_id IS NOT NULL),
 CHECK (inventory_cost_amount NOT IN ('NaN'::numeric,'Infinity'::numeric,'-Infinity'::numeric)),
 CHECK (received_quantity IS NULL OR received_quantity NOT IN ('NaN'::numeric,'Infinity'::numeric,'-Infinity'::numeric)),
 CHECK (base_units_per_received_unit IS NULL OR base_units_per_received_unit NOT IN ('NaN'::numeric,'Infinity'::numeric,'-Infinity'::numeric))
);

CREATE TABLE purchasing.reconciliation_checks (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 document_version_id uuid NOT NULL REFERENCES purchasing.document_versions(id),
 revision integer NOT NULL CHECK (revision>0),
 line_total numeric NOT NULL,
 expected_document_total numeric NOT NULL,
 stated_document_total numeric NOT NULL,
 unexplained_delta numeric GENERATED ALWAYS AS (stated_document_total-expected_document_total) STORED,
 status text NOT NULL CHECK (status IN ('balanced','held')),
 component_explanation jsonb NOT NULL CHECK (jsonb_typeof(component_explanation)='object'),
 confirmed_by text NOT NULL,
 checked_at timestamptz NOT NULL DEFAULT now(),
 CHECK (status<>'balanced' OR stated_document_total=expected_document_total),
 UNIQUE(document_version_id,revision),
 UNIQUE(id,document_version_id)
 -- No tolerance silently writes off the US Foods $1.23 difference.
);
CREATE TABLE purchasing.posting_batches (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 document_id uuid NOT NULL UNIQUE REFERENCES purchasing.document_identities(id),
 document_version_id uuid NOT NULL,
 reconciliation_id uuid NOT NULL,
 idempotency_key text NOT NULL UNIQUE,
 request_fingerprint bytea NOT NULL CHECK (octet_length(request_fingerprint)=32),
 posted_by text NOT NULL,
 posted_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(document_version_id,document_id) REFERENCES purchasing.document_versions(id,document_id),
 FOREIGN KEY(reconciliation_id,document_version_id) REFERENCES purchasing.reconciliation_checks(id,document_version_id),
 UNIQUE(id,document_version_id)
 -- One initial purchase batch per document, even across revised/reordered files.
 -- Corrections require an explicit reversal/replacement workflow before cutover;
 -- v1 intentionally refuses a second posting rather than replacing history.
);
CREATE TABLE purchasing.posting_lines (
 batch_id uuid NOT NULL,
 document_version_id uuid NOT NULL,
 line_id uuid NOT NULL UNIQUE,
 mapping_id uuid NOT NULL UNIQUE,
 PRIMARY KEY(batch_id,line_id),
 FOREIGN KEY(batch_id,document_version_id) REFERENCES purchasing.posting_batches(id,document_version_id),
 FOREIGN KEY(line_id,document_version_id) REFERENCES purchasing.document_lines(id,document_version_id),
 FOREIGN KEY(mapping_id,line_id) REFERENCES purchasing.mapping_decisions(id,line_id)
);

CREATE VIEW purchasing.actual_purchase_facts AS
 SELECT i.store_id,i.vendor_id,i.id AS document_id,pl.line_id,pl.mapping_id,
 m.item_code,m.base_unit,m.base_quantity,m.inventory_cost_amount,
 m.inventory_record_date,m.goods_received_date,m.returned_date,
 m.inventory_effective_at,m.goods_received_at,m.cost_policy_version,
 l.extended_amount_source AS vendor_line_amount,d.confirmed_currency
 FROM purchasing.posting_lines pl
 JOIN purchasing.posting_batches b ON b.id=pl.batch_id
 JOIN purchasing.document_identities i ON i.id=b.document_id
 JOIN purchasing.document_versions d ON d.id=pl.document_version_id
 JOIN purchasing.document_lines l ON l.id=pl.line_id
 JOIN purchasing.mapping_decisions m ON m.id=pl.mapping_id
 WHERE m.classification='food';

CREATE FUNCTION purchasing.guard_line_addition() RETURNS trigger
LANGUAGE plpgsql AS $$ BEGIN
 PERFORM 1 FROM purchasing.document_versions WHERE id=NEW.document_version_id FOR UPDATE;
 IF EXISTS (SELECT 1 FROM purchasing.posting_batches WHERE document_version_id=NEW.document_version_id)
 THEN RAISE EXCEPTION 'Posted document version is sealed'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER seal_posted_lines BEFORE INSERT ON purchasing.document_lines
FOR EACH ROW EXECUTE FUNCTION purchasing.guard_line_addition();
CREATE TRIGGER seal_posted_parties BEFORE INSERT ON purchasing.document_parties
FOR EACH ROW EXECUTE FUNCTION purchasing.guard_line_addition();

CREATE FUNCTION purchasing.lock_mapping_version() RETURNS trigger
LANGUAGE plpgsql AS $$ BEGIN
 PERFORM 1 FROM purchasing.document_versions d
 JOIN purchasing.document_lines l ON l.document_version_id=d.id
 WHERE l.id=NEW.line_id FOR UPDATE OF d;
 RETURN NEW;
END $$;
CREATE TRIGGER serialize_mapping BEFORE INSERT ON purchasing.mapping_decisions
FOR EACH ROW EXECUTE FUNCTION purchasing.lock_mapping_version();

CREATE FUNCTION purchasing.post_document(p_version uuid,p_key text,p_actor text,p_fingerprint bytea) RETURNS uuid
LANGUAGE plpgsql AS $$
DECLARE d purchasing.document_versions; i purchasing.document_identities;
 r purchasing.reconciliation_checks; prior purchasing.posting_batches;
 b uuid; n integer; mapped integer; source_sum numeric; source_total numeric;
BEGIN
 SELECT * INTO STRICT d FROM purchasing.document_versions WHERE id=p_version FOR UPDATE;
 SELECT * INTO STRICT i FROM purchasing.document_identities WHERE id=d.document_id FOR UPDATE;
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
   SELECT 1 FROM purchasing.actual_purchase_facts original
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

CREATE FUNCTION purchasing.guard_legacy_invoice() RETURNS trigger
LANGUAGE plpgsql AS $$ BEGIN
 PERFORM pg_advisory_xact_lock(hashtext('purchase-invoice'),
    hashtext(concat_ws('|',NEW.store_id,NEW.vendor_id,btrim(NEW.invoice_number))));
 IF EXISTS (SELECT 1 FROM purchasing.document_identities i
    JOIN purchasing.posting_batches b ON b.document_id=i.id
    WHERE i.store_id=NEW.store_id AND i.vendor_id=NEW.vendor_id
      AND i.document_number=btrim(NEW.invoice_number))
 THEN RAISE EXCEPTION 'Invoice already posted in the native purchase ledger'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER native_purchase_duplicate_guard BEFORE INSERT OR UPDATE ON public.invoices
FOR EACH ROW EXECUTE FUNCTION purchasing.guard_legacy_invoice();

DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['import_files','upload_attempts','parse_runs','raw_rows',
 'document_identities','document_versions','document_lines','document_parties',
 'document_source_rows','base_units','item_bases','mapping_decisions','reconciliation_checks','posting_batches','posting_lines']
 LOOP
  EXECUTE format('CREATE TRIGGER immutable_fact BEFORE UPDATE OR DELETE ON purchasing.%I FOR EACH ROW EXECUTE FUNCTION purchasing.reject_fact_change()',t);
 END LOOP;
END $$;
-- Dedicated schema is private to the backend database role, not public clients.
REVOKE ALL ON SCHEMA purchasing FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA purchasing FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA purchasing FROM PUBLIC;
COMMIT;
