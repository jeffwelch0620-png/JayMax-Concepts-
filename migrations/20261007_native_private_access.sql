-- Final native permission boundary. Apply only after the reviewed native chain.
-- Backend database owner access is unchanged; no stock, source or login data writes.
BEGIN;
SET LOCAL search_path=pg_catalog;
DO $$ DECLARE s text; r text; p record;
BEGIN
 FOREACH s IN ARRAY ARRAY['purchasing','actual_inventory','prep_inventory'] LOOP
  IF NOT EXISTS(SELECT 1 FROM pg_namespace WHERE nspname=s) THEN
   RAISE EXCEPTION 'Install all native schemas before the final permission boundary';
  END IF;
  EXECUTE format('REVOKE ALL ON SCHEMA %I FROM PUBLIC',s);
  EXECUTE format('REVOKE ALL ON ALL TABLES IN SCHEMA %I FROM PUBLIC',s);
  EXECUTE format('REVOKE ALL ON ALL SEQUENCES IN SCHEMA %I FROM PUBLIC',s);
  EXECUTE format('REVOKE ALL ON ALL FUNCTIONS IN SCHEMA %I FROM PUBLIC',s);
  FOREACH r IN ARRAY ARRAY['anon','authenticated'] LOOP
   IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=r) THEN
    EXECUTE format('REVOKE ALL ON SCHEMA %I FROM %I',s,r);
    EXECUTE format('REVOKE ALL ON ALL TABLES IN SCHEMA %I FROM %I',s,r);
    EXECUTE format('REVOKE ALL ON ALL SEQUENCES IN SCHEMA %I FROM %I',s,r);
    EXECUTE format('REVOKE ALL ON ALL FUNCTIONS IN SCHEMA %I FROM %I',s,r);
   END IF;
  END LOOP;
 END LOOP;
 -- The reference public snapshot includes these future Toast RPCs. RLS on
 -- tables does not restrict a security-definer function's execute permission.
 FOR p IN SELECT f.oid FROM pg_proc f JOIN pg_namespace n ON n.oid=f.pronamespace
  WHERE n.nspname='public' AND f.proname IN ('jmax_toast_start_sync','jmax_toast_finish_sync','jmax_toast_store_payloads')
 LOOP
  EXECUTE format('REVOKE ALL ON FUNCTION %s FROM PUBLIC',p.oid::regprocedure);
  FOREACH r IN ARRAY ARRAY['anon','authenticated'] LOOP
   IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=r) THEN
    EXECUTE format('REVOKE ALL ON FUNCTION %s FROM %I',p.oid::regprocedure,r);
   END IF;
  END LOOP;
 END LOOP;
END $$;
-- Future DDL can create new grants. Re-run the read-only preflight after every
-- migration; this migration does not claim to override other creators' defaults.
COMMIT;
