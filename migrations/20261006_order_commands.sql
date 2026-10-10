-- After shared catalog/native receiving. No purchasing or accounting facts added.
BEGIN;
-- Unknown estimates must survive installations whose older bootstrap used NOT NULL.
ALTER TABLE public.purchase_orders ALTER COLUMN total DROP NOT NULL;
ALTER TABLE public.purchase_order_lines ALTER COLUMN unit_price DROP NOT NULL;
ALTER TABLE public.purchase_order_lines ALTER COLUMN extended DROP NOT NULL;
ALTER TABLE public.purchase_orders ADD COLUMN order_version bigint NOT NULL DEFAULT 1 CHECK(order_version>0);
ALTER TABLE public.purchase_orders ADD COLUMN archived_at timestamptz;
ALTER TABLE public.purchase_orders ADD COLUMN creator_actor text;
ALTER TABLE public.vendors ADD COLUMN catalog_version bigint NOT NULL DEFAULT 1 CHECK(catalog_version>0);
CREATE TABLE purchasing.order_commands (
 request_key uuid PRIMARY KEY, store_id text NOT NULL, po_id uuid NOT NULL,
 action text NOT NULL CHECK(action IN ('create','edit','submit','approve','reject','reopen','send','archive','reorder')),
 actor text NOT NULL, request_fingerprint bytea NOT NULL CHECK(octet_length(request_fingerprint)=32),
 result_snapshot jsonb NOT NULL, recorded_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(po_id,store_id) REFERENCES public.purchase_orders(id,store_id)
);
CREATE TRIGGER immutable_fact BEFORE UPDATE OR DELETE ON purchasing.order_commands
 FOR EACH ROW EXECUTE FUNCTION purchasing.reject_fact_change();
CREATE FUNCTION purchasing.version_order() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Archive orders instead of deleting retained history'; END IF;
 IF TG_OP='UPDATE' THEN NEW.order_version:=OLD.order_version+1; END IF;
 INSERT INTO public.store_state(store_id,revision) VALUES(NEW.store_id,1)
 ON CONFLICT(store_id) DO UPDATE SET revision=store_state.revision+1,updated_at=now();
 RETURN NEW;
END $$;
CREATE TRIGGER version_order BEFORE INSERT OR UPDATE OR DELETE ON public.purchase_orders
 FOR EACH ROW EXECUTE FUNCTION purchasing.version_order();
CREATE FUNCTION purchasing.guard_order_content() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE status text; archived timestamptz; target uuid;
BEGIN
 target:=CASE WHEN TG_OP='DELETE' THEN OLD.po_id ELSE NEW.po_id END;
 SELECT p.status,p.archived_at INTO status,archived FROM public.purchase_orders p WHERE p.id=target FOR UPDATE;
 IF archived IS NOT NULL THEN RAISE EXCEPTION 'Archived order content is retained'; END IF;
 IF status<>'draft' AND NOT (TG_OP='UPDATE' AND
    (to_jsonb(NEW)-'received_qty') IS NOT DISTINCT FROM (to_jsonb(OLD)-'received_qty')) THEN
  RAISE EXCEPTION 'Only draft order content can change';
 END IF;
 IF TG_OP='UPDATE' AND NEW.po_id IS DISTINCT FROM OLD.po_id THEN RAISE EXCEPTION 'Order line identity cannot be reassigned'; END IF;
 UPDATE public.purchase_orders SET order_version=order_version+1 WHERE id=target;
 RETURN CASE WHEN TG_OP='DELETE' THEN OLD ELSE NEW END;
END $$;
CREATE TRIGGER version_order_content BEFORE INSERT OR UPDATE OR DELETE ON public.purchase_order_lines
 FOR EACH ROW EXECUTE FUNCTION purchasing.guard_order_content();
CREATE FUNCTION purchasing.version_vendor() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE store text;
BEGIN
 IF TG_OP='UPDATE' AND (to_jsonb(NEW)-'updated_at'-'catalog_version') IS NOT DISTINCT FROM
                          (to_jsonb(OLD)-'updated_at'-'catalog_version') THEN
  NEW.catalog_version:=OLD.catalog_version; RETURN NEW;
 END IF;
 PERFORM pg_advisory_xact_lock(70620261006::bigint);
 IF TG_OP='UPDATE' THEN NEW.catalog_version:=OLD.catalog_version+1; END IF;
 -- Fixed store order also covers vendors not yet linked to a product.
 FOR store IN SELECT id FROM public.stores ORDER BY id LOOP
  INSERT INTO public.store_state(store_id,revision) VALUES(store,1) ON CONFLICT(store_id)
   DO UPDATE SET revision=store_state.revision+1,updated_at=now();
 END LOOP;
 RETURN NEW;
END $$;
CREATE TRIGGER version_vendor BEFORE UPDATE ON public.vendors FOR EACH ROW EXECUTE FUNCTION purchasing.version_vendor();
CREATE FUNCTION purchasing.new_vendor_revision() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE store text;
BEGIN
 PERFORM pg_advisory_xact_lock(70620261006::bigint);
 FOR store IN SELECT id FROM public.stores ORDER BY id LOOP
  INSERT INTO public.store_state(store_id,revision) VALUES(store,1) ON CONFLICT(store_id)
   DO UPDATE SET revision=store_state.revision+1,updated_at=now();
 END LOOP;
 RETURN NEW;
END $$;
CREATE TRIGGER new_vendor_revision AFTER INSERT ON public.vendors FOR EACH ROW EXECUTE FUNCTION purchasing.new_vendor_revision();
REVOKE ALL ON purchasing.order_commands FROM PUBLIC;
COMMIT;
