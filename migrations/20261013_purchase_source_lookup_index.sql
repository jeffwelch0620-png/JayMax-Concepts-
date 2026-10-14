-- Additive lookup support for the latest captured source of an invoice version.
-- Keep existing migrations and immutable source rows unchanged.
BEGIN;
SET LOCAL lock_timeout = '5s';
CREATE INDEX document_source_rows_version_run_idx
    ON purchasing.document_source_rows USING btree (document_version_id, parse_run_id);
COMMIT;
