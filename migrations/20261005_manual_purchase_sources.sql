-- Retained receipt attachments; all purchase facts still use the existing ledger.
BEGIN;
ALTER TABLE purchasing.import_files ADD CONSTRAINT import_files_id_store_unique UNIQUE(id,store_id);
CREATE TABLE purchasing.manual_attachments (
 record_file_id uuid NOT NULL,
 attachment_file_id uuid NOT NULL,
 store_id text NOT NULL,
 PRIMARY KEY(record_file_id,attachment_file_id),
 FOREIGN KEY(record_file_id,store_id) REFERENCES purchasing.import_files(id,store_id),
 FOREIGN KEY(attachment_file_id,store_id) REFERENCES purchasing.import_files(id,store_id),
 CHECK(record_file_id<>attachment_file_id)
);
CREATE FUNCTION purchasing.guard_manual_attachment() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE source jsonb;
BEGIN
 IF NOT EXISTS(SELECT 1 FROM purchasing.parse_runs WHERE file_id=NEW.record_file_id AND parser_version='manual-document-v1')
 THEN RAISE EXCEPTION 'A retained manual source record is required'; END IF;
 SELECT convert_from(source_bytes,'UTF8')::jsonb INTO source FROM purchasing.import_files WHERE id=NEW.record_file_id;
 IF NOT (source->'attachment_ids' ? NEW.attachment_file_id::text)
 THEN RAISE EXCEPTION 'Attachment is not named in the immutable source record'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER source_attachment_guard BEFORE INSERT ON purchasing.manual_attachments
 FOR EACH ROW EXECUTE FUNCTION purchasing.guard_manual_attachment();
CREATE TRIGGER immutable_fact BEFORE UPDATE OR DELETE ON purchasing.manual_attachments
 FOR EACH ROW EXECUTE FUNCTION purchasing.reject_fact_change();
REVOKE ALL ON purchasing.manual_attachments FROM PUBLIC;
REVOKE ALL ON FUNCTION purchasing.guard_manual_attachment() FROM PUBLIC;
COMMIT;
