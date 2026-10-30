-- Roles (Jeff 2026-10-30): each login may carry a position from the JMAX org hierarchy (a role
-- code). Its access class (`role`) stays, and every existing check keeps using it; the position
-- must belong to that class (backend/positions.py holds the same table). A login without a
-- position keeps exactly what its access class allowed before.
BEGIN;
SET LOCAL lock_timeout = '5s';

ALTER TABLE public.app_users ADD COLUMN position text;
ALTER TABLE public.app_users ADD CONSTRAINT app_users_position_matches_role CHECK (
 position IS NULL
 OR (position IN ('OWN', 'OPS') AND role = 'owner')
 OR (position IN ('GM', 'KM', 'FOHM', 'BPM', 'SL-BOH', 'SL-FOH') AND role = 'manager')
 OR (position IN ('BPC', 'LC-GRL', 'LC-PZA', 'LC-APZ', 'LC-EXP', 'LC-SLP', 'LC-FRY', 'LC-PRP', 'LC-SBA',
                  'FOH-SRV', 'FOH-HST', 'FOH-RUN', 'FOH-BW', 'DSH') AND role = 'staff')
);
COMMIT;
