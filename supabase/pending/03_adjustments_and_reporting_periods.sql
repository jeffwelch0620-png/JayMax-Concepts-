-- Phase 2, chunk 3: let adjustments / reporting_periods hold the frontend's records
-- (Mongo collections of the same names). Name: phase2_adjustments_and_reporting_periods.
-- Expects both tables to be empty (never migrated in phase 1) -- the NOT NULL columns
-- fail loudly otherwise.

-- `ref` = the client-generated id ("adj_..." / "period_..."), which is what the app uses.
ALTER TABLE public.adjustments
  ADD COLUMN ref text NOT NULL,
  ADD COLUMN control_number text NOT NULL,
  ADD COLUMN qty_basis text NOT NULL DEFAULT 'purchase' CHECK (qty_basis IN ('purchase', 'portion'));
-- item_code stays as the catalog link when the item exists; an adjustment for a
-- since-deleted item keeps its control_number instead of failing the FK.
ALTER TABLE public.adjustments ALTER COLUMN item_code DROP NOT NULL;
CREATE INDEX adjustments_store_id_date_idx ON public.adjustments (store_id, date);

ALTER TABLE public.reporting_periods ADD COLUMN ref text NOT NULL;
CREATE INDEX reporting_periods_store_id_period_start_idx ON public.reporting_periods (store_id, period_start);
