-- Salad Bar as a third native prep track beside Daily and Bulk, so Salad plans, day
-- lists, release, assignments, production reports and notes are recorded and reported
-- separately. Salad Bar runs only at Bert's (owner decision 2026-10-29); allowing it at
-- another store is a later migration. Existing rows and Daily/Bulk meaning are unchanged.
BEGIN;
SET LOCAL lock_timeout = '5s';
ALTER TABLE prep_inventory.planning_versions
  DROP CONSTRAINT planning_versions_track_check,
  ADD CONSTRAINT planning_versions_track_check CHECK (track IN ('daily','bulk','salad')),
  ADD CONSTRAINT planning_versions_salad_store_check CHECK (track <> 'salad' OR store_id = 'berts');
-- Day lists and the separately installed manager note journal are widened where present.
DO $$
BEGIN
  IF to_regclass('prep_inventory.day_lists') IS NOT NULL THEN
    ALTER TABLE prep_inventory.day_lists
      DROP CONSTRAINT day_lists_track_check,
      ADD CONSTRAINT day_lists_track_check CHECK (track IN ('daily','bulk','salad')),
      ADD CONSTRAINT day_lists_salad_store_check CHECK (track <> 'salad' OR store_id = 'berts');
  END IF;
  IF to_regclass('operations.handoff_notes') IS NOT NULL THEN
    ALTER TABLE operations.handoff_notes
      DROP CONSTRAINT handoff_notes_prep_track_check,
      ADD CONSTRAINT handoff_notes_prep_track_check CHECK (prep_track IN ('daily','bulk','salad')),
      ADD CONSTRAINT handoff_notes_salad_store_check CHECK (prep_track <> 'salad' OR store_id = 'berts');
  END IF;
END $$;
COMMIT;
