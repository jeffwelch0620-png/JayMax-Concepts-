-- Auditor position (Jeff 2026-11-18 and 2026-11-19): a read-only login for the daily ops check and
-- the Tier 1 Inventory MCP server. It signs in with the existing `readonly` access class, which the
-- server refuses every change; the position adds analytics (GM-level, never wages). Replaces the
-- position check from 20261031_login_positions.sql with the same rules plus AUD on readonly.
-- Seeds nothing; changes no stock, food or accounting records.
BEGIN;
SET LOCAL lock_timeout = '5s';

ALTER TABLE public.app_users DROP CONSTRAINT app_users_position_matches_role;
ALTER TABLE public.app_users ADD CONSTRAINT app_users_position_matches_role CHECK (
 position IS NULL
 OR (position IN ('OWN', 'OPS') AND role = 'owner')
 OR (position IN ('GM', 'KM', 'FOHM', 'BPM', 'SL-BOH', 'SL-FOH') AND role = 'manager')
 OR (position IN ('BPC', 'LC-GRL', 'LC-PZA', 'LC-APZ', 'LC-EXP', 'LC-SLP', 'LC-FRY', 'LC-PRP', 'LC-SBA',
                  'FOH-SRV', 'FOH-HST', 'FOH-RUN', 'FOH-BW', 'DSH') AND role = 'staff')
 OR (position = 'AUD' AND role = 'readonly')
);
COMMIT;
