-- Phase 2, chunk 2: make purchase_orders / purchase_order_lines able to hold the full
-- Mongo purchase-order document, and add per-store supplier emails (Mongo
-- `vendor_contacts`). Name: phase2_purchase_orders. Expects purchase_orders to be empty
-- (POs were never migrated in phase 1) -- the NOT NULL on `ref` fails loudly otherwise.

-- Header -------------------------------------------------------------------------
ALTER TABLE public.purchase_orders
  ADD COLUMN ref text NOT NULL,                              -- public "po_..." id used in URLs, emails, PDFs
  ADD COLUMN vendor_name text NOT NULL DEFAULT 'Unassigned', -- free text, as typed on the PO
  ADD COLUMN note text NOT NULL DEFAULT '',
  ADD COLUMN total numeric(12,2) NOT NULL DEFAULT 0,
  ADD COLUMN submitted_at timestamp with time zone,
  ADD COLUMN receipt_started_at timestamp with time zone,
  ADD COLUMN invoice_number text,
  ADD COLUMN receipt_match jsonb,
  ADD COLUMN emailed_to text,
  ADD COLUMN emailed_at timestamp with time zone,
  ADD COLUMN history jsonb NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE public.purchase_orders ADD CONSTRAINT purchase_orders_ref_key UNIQUE (ref);
-- vendor_id stays as the link to vendors when the typed name matches one; "Unassigned"
-- and one-off suppliers have no vendors row.
ALTER TABLE public.purchase_orders ALTER COLUMN vendor_id DROP NOT NULL;
-- 'receiving' is the transient claim state while a receipt is being applied.
ALTER TABLE public.purchase_orders DROP CONSTRAINT purchase_orders_status_check;
ALTER TABLE public.purchase_orders ADD CONSTRAINT purchase_orders_status_check
  CHECK (status = ANY (ARRAY['draft', 'pending', 'approved', 'sent', 'receiving', 'received', 'rejected']));

CREATE INDEX purchase_orders_store_id_created_at_idx ON public.purchase_orders (store_id, created_at DESC);
CREATE INDEX purchase_orders_status_idx ON public.purchase_orders (status);

-- Lines --------------------------------------------------------------------------
ALTER TABLE public.purchase_order_lines
  ADD COLUMN position integer NOT NULL DEFAULT 0,
  ADD COLUMN control_number text,
  ADD COLUMN name text NOT NULL DEFAULT '',
  ADD COLUMN vendor_sku text NOT NULL DEFAULT '';

CREATE INDEX purchase_order_lines_po_id_idx ON public.purchase_order_lines (po_id, position);

-- Supplier emails ----------------------------------------------------------------
CREATE TABLE public.store_vendor_contacts (
  store_id text NOT NULL REFERENCES public.stores(id),
  vendor text NOT NULL,                       -- vendor name as used on POs
  order_email text NOT NULL DEFAULT '',
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  PRIMARY KEY (store_id, vendor)
);
ALTER TABLE public.store_vendor_contacts ENABLE ROW LEVEL SECURITY;
