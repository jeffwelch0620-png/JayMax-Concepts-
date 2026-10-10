-- Explicit shared identities; mutable supplier choices/prices belong to a store.
-- No invoice, count, posting, prep or sales facts are changed.
BEGIN;
ALTER TABLE public.store_items ADD COLUMN control_number text;
UPDATE public.store_items SET control_number=CASE
 WHEN item_code LIKE (CASE WHEN store_id='papa' THEN 'papa_leonis' ELSE store_id END)||'\_%' ESCAPE '\'
 THEN substring(item_code FROM length(CASE WHEN store_id='papa' THEN 'papa_leonis' ELSE store_id END)+2)
 ELSE item_code END;
ALTER TABLE public.store_items ADD CONSTRAINT store_control_nonblank CHECK(control_number IS NOT NULL AND length(btrim(control_number))>0);
CREATE UNIQUE INDEX store_control_number_unique ON public.store_items(store_id,control_number);
CREATE FUNCTION purchasing.default_store_control_number() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE prefix text := (CASE WHEN NEW.store_id='papa' THEN 'papa_leonis' ELSE NEW.store_id END)||'_';
BEGIN
 IF NEW.control_number IS NULL THEN
  NEW.control_number:=CASE WHEN left(NEW.item_code,length(prefix))=prefix THEN substring(NEW.item_code FROM length(prefix)+1) ELSE NEW.item_code END;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER default_store_control BEFORE INSERT ON public.store_items FOR EACH ROW EXECUTE FUNCTION purchasing.default_store_control_number();
REVOKE ALL ON FUNCTION purchasing.default_store_control_number() FROM PUBLIC;
ALTER TABLE public.vendor_items ADD CONSTRAINT vendor_items_id_item_unique UNIQUE(id,item_code);
CREATE TABLE purchasing.store_vendor_items (
 store_id text NOT NULL, item_code text NOT NULL, vendor_item_id uuid NOT NULL,
 preferred boolean NOT NULL DEFAULT false, available boolean NOT NULL DEFAULT false,
 price numeric CHECK(price>=0 AND price NOT IN ('NaN'::numeric,'Infinity'::numeric,'-Infinity'::numeric)),
 price_updated_at timestamptz, price_source text,
 PRIMARY KEY(store_id,vendor_item_id),
 FOREIGN KEY(store_id,item_code) REFERENCES public.store_items(store_id,item_code),
 FOREIGN KEY(vendor_item_id,item_code) REFERENCES public.vendor_items(id,item_code)
);
INSERT INTO purchasing.store_vendor_items(store_id,item_code,vendor_item_id,preferred,available,price,price_updated_at,price_source)
 SELECT si.store_id,si.item_code,vi.id,vi.preferred,vi.available,vi.price,vi.price_updated_at,vi.price_source
 FROM public.store_items si JOIN public.vendor_items vi ON vi.item_code=si.item_code;
REVOKE ALL ON purchasing.store_vendor_items FROM PUBLIC;
COMMIT;
