ALTER TABLE prep_items
  ADD COLUMN IF NOT EXISTS recur_days smallint[] NOT NULL DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS fixed_qty numeric NOT NULL DEFAULT 0;

ALTER TABLE prep_items DROP CONSTRAINT IF EXISTS prep_items_schedule_check;
ALTER TABLE prep_items
  ADD CONSTRAINT prep_items_schedule_check
  CHECK (schedule IN ('daily', 'oneoff', 'recurring'));

ALTER TABLE prep_items DROP CONSTRAINT IF EXISTS prep_items_recur_days_check;
ALTER TABLE prep_items
  ADD CONSTRAINT prep_items_recur_days_check
  CHECK (recur_days <@ ARRAY[0, 1, 2, 3, 4, 5, 6]::smallint[]);

ALTER TABLE prep_items DROP CONSTRAINT IF EXISTS prep_items_recurring_fields_check;
ALTER TABLE prep_items
  ADD CONSTRAINT prep_items_recurring_fields_check
  CHECK (
    schedule <> 'recurring'
    OR (cardinality(recur_days) > 0 AND fixed_qty > 0)
  );
