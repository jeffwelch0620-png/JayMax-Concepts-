-- Salad Bar manager notes (Bert's only) for databases where the manager note journal was
-- installed AFTER 20261029_salad_prep_track.sql. That migration widens the notes table only
-- when it already exists; 20261025_manager_handoff_notes.sql still creates a Daily/Bulk check.
-- Apply right after installing the manager note journal. Safe to repeat: no-op once widened.
BEGIN;
SET LOCAL lock_timeout = '5s';
DO $$
BEGIN
  IF to_regclass('operations.handoff_notes') IS NULL THEN
    RAISE EXCEPTION 'Install the manager note journal before this upgrade';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint
                 WHERE conrelid = 'operations.handoff_notes'::regclass AND conname = 'handoff_notes_salad_store_check') THEN
    ALTER TABLE operations.handoff_notes
      DROP CONSTRAINT handoff_notes_prep_track_check,
      ADD CONSTRAINT handoff_notes_prep_track_check CHECK (prep_track IN ('daily','bulk','salad')),
      ADD CONSTRAINT handoff_notes_salad_store_check CHECK (prep_track <> 'salad' OR store_id = 'berts');
  END IF;
END $$;
COMMIT;
