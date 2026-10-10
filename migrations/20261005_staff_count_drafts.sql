-- Staff measurements remain separate until explicit manager acceptance.
-- Requires the native count/correction/scope and physical-unit migrations.
BEGIN;
CREATE TABLE actual_inventory.staff_sheets (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), store_id text NOT NULL,
 scope_id uuid NOT NULL, count_date date NOT NULL,
 timing text NOT NULL CHECK(timing IN ('before_receipts','after_receipts')),
 note text NOT NULL CHECK(length(btrim(note))>0),
 sheet_snapshot jsonb NOT NULL CHECK(jsonb_typeof(sheet_snapshot)='object'),
 request_key uuid NOT NULL UNIQUE,
 request_fingerprint bytea NOT NULL CHECK(octet_length(request_fingerprint)=32),
 issued_by text NOT NULL, issued_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(scope_id,store_id) REFERENCES actual_inventory.scopes(id,store_id),
 UNIQUE(id,store_id)
);
CREATE TABLE actual_inventory.staff_submissions (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), sheet_id uuid NOT NULL, store_id text NOT NULL,
 revision integer NOT NULL CHECK(revision>0),
 counter_name text NOT NULL CHECK(length(btrim(counter_name))>0),
 credential_kind text NOT NULL CHECK(credential_kind IN ('bearer','shared_pin')),
 submitted_by text NOT NULL, submitted_at timestamptz NOT NULL DEFAULT now(),
 note text NOT NULL CHECK(length(btrim(note))>0),
 quantities jsonb NOT NULL CHECK(jsonb_typeof(quantities)='array'),
 request_key uuid NOT NULL UNIQUE,
 request_fingerprint bytea NOT NULL CHECK(octet_length(request_fingerprint)=32),
 FOREIGN KEY(sheet_id,store_id) REFERENCES actual_inventory.staff_sheets(id,store_id),
 UNIQUE(sheet_id,revision), UNIQUE(id,sheet_id,store_id)
);
CREATE TABLE actual_inventory.staff_decisions (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), sheet_id uuid NOT NULL UNIQUE, store_id text NOT NULL,
 submission_id uuid, decision text NOT NULL CHECK(decision IN ('accepted','rejected')),
 snapshot_id uuid UNIQUE, note text NOT NULL CHECK(length(btrim(note))>0),
 review_snapshot jsonb NOT NULL CHECK(jsonb_typeof(review_snapshot)='object'),
 reviewed_by text NOT NULL, reviewed_at timestamptz NOT NULL DEFAULT now(),
 request_key uuid NOT NULL UNIQUE,
 request_fingerprint bytea NOT NULL CHECK(octet_length(request_fingerprint)=32),
 FOREIGN KEY(sheet_id,store_id) REFERENCES actual_inventory.staff_sheets(id,store_id),
 FOREIGN KEY(submission_id,sheet_id,store_id) REFERENCES actual_inventory.staff_submissions(id,sheet_id,store_id),
 FOREIGN KEY(snapshot_id,store_id) REFERENCES actual_inventory.count_snapshots(id,store_id),
 CHECK((decision='accepted' AND submission_id IS NOT NULL AND snapshot_id IS NOT NULL)
    OR (decision='rejected' AND snapshot_id IS NULL))
);
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['staff_sheets','staff_submissions','staff_decisions'] LOOP
  EXECUTE format('CREATE TRIGGER immutable_fact BEFORE UPDATE OR DELETE ON actual_inventory.%I
      FOR EACH ROW EXECUTE FUNCTION purchasing.reject_fact_change()',t);
  EXECUTE format('REVOKE ALL ON actual_inventory.%I FROM PUBLIC',t);
 END LOOP;
END $$;
CREATE INDEX staff_sheet_store_date ON actual_inventory.staff_sheets(store_id,count_date DESC,issued_at DESC);
COMMIT;
