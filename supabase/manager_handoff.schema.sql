-- Generated fictional PostgreSQL 17 structure reference only. NOT an installer or permission proof.
--
-- PostgreSQL database dump
--


-- Dumped from database version 17.11
-- Dumped by pg_dump version 17.11

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: operations; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA operations;


--
-- Name: guard_handoff_header(); Type: FUNCTION; Schema: operations; Owner: -
--

CREATE FUNCTION operations.guard_handoff_header() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog'
    AS $$
BEGIN
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Handoff history cannot be deleted'; END IF;
 IF TG_OP='INSERT' THEN
  IF NEW.revision<>1 OR NEW.status<>'draft' OR NEW.first_submitted_at IS NOT NULL THEN
   RAISE EXCEPTION 'Create a first draft revision'; END IF;
 ELSE
  IF ROW(NEW.id,NEW.store_id,NEW.business_date,NEW.prep_track,NEW.creator_id,NEW.timezone_name,NEW.settings_revision,NEW.created_at)
   IS DISTINCT FROM ROW(OLD.id,OLD.store_id,OLD.business_date,OLD.prep_track,OLD.creator_id,OLD.timezone_name,OLD.settings_revision,OLD.created_at)
   OR NEW.revision<>OLD.revision+1 OR (OLD.status='submitted' AND NEW.status<>'submitted')
   OR (OLD.first_submitted_at IS NOT NULL AND NEW.first_submitted_at IS DISTINCT FROM OLD.first_submitted_at)
   THEN RAISE EXCEPTION 'Handoff context and revision history are immutable'; END IF;
 END IF;
 RETURN NEW;
END $$;


--
-- Name: guard_handoff_history(); Type: FUNCTION; Schema: operations; Owner: -
--

CREATE FUNCTION operations.guard_handoff_history() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog'
    AS $$
DECLARE h operations.handoff_notes%ROWTYPE; previous_status text;
BEGIN
 IF TG_OP<>'INSERT' THEN RAISE EXCEPTION 'Handoff evidence is append-only'; END IF;
 IF TG_TABLE_NAME='handoff_note_revisions' THEN
  SELECT * INTO h FROM operations.handoff_notes WHERE store_id=NEW.store_id AND id=NEW.note_id;
  IF NOT FOUND OR h.revision<>NEW.revision OR h.status<>NEW.status THEN
   RAISE EXCEPTION 'Revision must match the current scoped header'; END IF;
  IF NEW.revision=1 THEN
   IF NEW.action<>'create_draft' OR NEW.status<>'draft' THEN RAISE EXCEPTION 'Invalid first draft'; END IF;
  ELSE
   SELECT status INTO previous_status FROM operations.handoff_note_revisions
    WHERE store_id=NEW.store_id AND note_id=NEW.note_id AND revision=NEW.revision-1;
   IF NOT FOUND OR NOT ((previous_status='draft' AND NEW.action='save_draft' AND NEW.status='draft')
    OR (previous_status='draft' AND NEW.action='submit' AND NEW.status='submitted')
    OR (previous_status='submitted' AND NEW.action='correct' AND NEW.status='submitted'))
    THEN RAISE EXCEPTION 'Invalid handoff transition'; END IF;
  END IF;
 END IF;
 RETURN NEW;
END $$;


--
-- Name: refuse_handoff_truncate(); Type: FUNCTION; Schema: operations; Owner: -
--

CREATE FUNCTION operations.refuse_handoff_truncate() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog'
    AS $$
BEGIN
 RAISE EXCEPTION 'Handoff history cannot be truncated';
END $$;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: handoff_command_receipts; Type: TABLE; Schema: operations; Owner: -
--

CREATE TABLE operations.handoff_command_receipts (
    store_id text NOT NULL,
    actor_id text NOT NULL,
    request_key uuid NOT NULL,
    request_fingerprint text NOT NULL,
    note_id uuid NOT NULL,
    accepted_revision integer NOT NULL,
    recorded_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT handoff_command_receipts_actor_id_check CHECK (((length(actor_id) >= 1) AND (length(actor_id) <= 160))),
    CONSTRAINT handoff_command_receipts_request_fingerprint_check CHECK ((request_fingerprint ~ '^[a-f0-9]{64}$'::text))
);


--
-- Name: handoff_note_revisions; Type: TABLE; Schema: operations; Owner: -
--

CREATE TABLE operations.handoff_note_revisions (
    store_id text NOT NULL,
    note_id uuid NOT NULL,
    revision integer NOT NULL,
    action text NOT NULL,
    actor_id text NOT NULL,
    recorded_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    status text NOT NULL,
    summary text NOT NULL,
    next_shift_note text NOT NULL,
    reported_readiness text NOT NULL,
    correction_reason text DEFAULT ''::text NOT NULL,
    CONSTRAINT handoff_note_revisions_action_check CHECK ((action = ANY (ARRAY['create_draft'::text, 'save_draft'::text, 'submit'::text, 'correct'::text]))),
    CONSTRAINT handoff_note_revisions_actor_id_check CHECK (((length(actor_id) >= 1) AND (length(actor_id) <= 160))),
    CONSTRAINT handoff_note_revisions_check CHECK ((((action = 'correct'::text) AND (length(btrim(correction_reason)) > 0)) OR ((action <> 'correct'::text) AND (correction_reason = ''::text)))),
    CONSTRAINT handoff_note_revisions_correction_reason_check CHECK ((length(correction_reason) <= 2000)),
    CONSTRAINT handoff_note_revisions_next_shift_note_check CHECK ((length(next_shift_note) <= 4000)),
    CONSTRAINT handoff_note_revisions_reported_readiness_check CHECK ((reported_readiness = ANY (ARRAY['not_assessed'::text, 'ready'::text, 'action_needed'::text]))),
    CONSTRAINT handoff_note_revisions_revision_check CHECK ((revision > 0)),
    CONSTRAINT handoff_note_revisions_status_check CHECK ((status = ANY (ARRAY['draft'::text, 'submitted'::text]))),
    CONSTRAINT handoff_note_revisions_summary_check CHECK (((length(btrim(summary)) >= 1) AND (length(btrim(summary)) <= 6000)))
);


--
-- Name: handoff_notes; Type: TABLE; Schema: operations; Owner: -
--

CREATE TABLE operations.handoff_notes (
    id uuid NOT NULL,
    store_id text NOT NULL,
    business_date date NOT NULL,
    prep_track text NOT NULL,
    creator_id text NOT NULL,
    timezone_name text NOT NULL,
    settings_revision integer NOT NULL,
    revision integer NOT NULL,
    status text NOT NULL,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    updated_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    first_submitted_at timestamp with time zone,
    CONSTRAINT handoff_notes_check CHECK ((((status = 'draft'::text) AND (first_submitted_at IS NULL)) OR ((status = 'submitted'::text) AND (first_submitted_at IS NOT NULL)))),
    CONSTRAINT handoff_notes_creator_id_check CHECK (((length(creator_id) >= 1) AND (length(creator_id) <= 160))),
    CONSTRAINT handoff_notes_prep_track_check CHECK ((prep_track = ANY (ARRAY['daily'::text, 'bulk'::text]))),
    CONSTRAINT handoff_notes_revision_check CHECK ((revision > 0)),
    CONSTRAINT handoff_notes_settings_revision_check CHECK ((settings_revision > 0)),
    CONSTRAINT handoff_notes_status_check CHECK ((status = ANY (ARRAY['draft'::text, 'submitted'::text])))
);


--
-- Name: store_settings; Type: TABLE; Schema: operations; Owner: -
--

CREATE TABLE operations.store_settings (
    store_id text NOT NULL,
    timezone_name text NOT NULL,
    revision integer NOT NULL,
    CONSTRAINT store_settings_revision_check CHECK ((revision > 0)),
    CONSTRAINT store_settings_timezone_name_check CHECK (((length(timezone_name) >= 1) AND (length(timezone_name) <= 100)))
);


--
-- Name: handoff_command_receipts handoff_command_receipts_pkey; Type: CONSTRAINT; Schema: operations; Owner: -
--

ALTER TABLE ONLY operations.handoff_command_receipts
    ADD CONSTRAINT handoff_command_receipts_pkey PRIMARY KEY (store_id, actor_id, request_key);


--
-- Name: handoff_note_revisions handoff_note_revisions_pkey; Type: CONSTRAINT; Schema: operations; Owner: -
--

ALTER TABLE ONLY operations.handoff_note_revisions
    ADD CONSTRAINT handoff_note_revisions_pkey PRIMARY KEY (store_id, note_id, revision);


--
-- Name: handoff_notes handoff_notes_pkey; Type: CONSTRAINT; Schema: operations; Owner: -
--

ALTER TABLE ONLY operations.handoff_notes
    ADD CONSTRAINT handoff_notes_pkey PRIMARY KEY (id);


--
-- Name: handoff_notes handoff_notes_store_id_business_date_prep_track_key; Type: CONSTRAINT; Schema: operations; Owner: -
--

ALTER TABLE ONLY operations.handoff_notes
    ADD CONSTRAINT handoff_notes_store_id_business_date_prep_track_key UNIQUE (store_id, business_date, prep_track);


--
-- Name: handoff_notes handoff_notes_store_id_id_key; Type: CONSTRAINT; Schema: operations; Owner: -
--

ALTER TABLE ONLY operations.handoff_notes
    ADD CONSTRAINT handoff_notes_store_id_id_key UNIQUE (store_id, id);


--
-- Name: store_settings store_settings_pkey; Type: CONSTRAINT; Schema: operations; Owner: -
--

ALTER TABLE ONLY operations.store_settings
    ADD CONSTRAINT store_settings_pkey PRIMARY KEY (store_id);


--
-- Name: handoff_notes handoff_header_guard; Type: TRIGGER; Schema: operations; Owner: -
--

CREATE TRIGGER handoff_header_guard BEFORE INSERT OR DELETE OR UPDATE ON operations.handoff_notes FOR EACH ROW EXECUTE FUNCTION operations.guard_handoff_header();


--
-- Name: handoff_notes handoff_notes_no_truncate; Type: TRIGGER; Schema: operations; Owner: -
--

CREATE TRIGGER handoff_notes_no_truncate BEFORE TRUNCATE ON operations.handoff_notes FOR EACH STATEMENT EXECUTE FUNCTION operations.refuse_handoff_truncate();


--
-- Name: handoff_command_receipts handoff_receipt_guard; Type: TRIGGER; Schema: operations; Owner: -
--

CREATE TRIGGER handoff_receipt_guard BEFORE DELETE OR UPDATE ON operations.handoff_command_receipts FOR EACH ROW EXECUTE FUNCTION operations.guard_handoff_history();


--
-- Name: handoff_command_receipts handoff_receipts_no_truncate; Type: TRIGGER; Schema: operations; Owner: -
--

CREATE TRIGGER handoff_receipts_no_truncate BEFORE TRUNCATE ON operations.handoff_command_receipts FOR EACH STATEMENT EXECUTE FUNCTION operations.refuse_handoff_truncate();


--
-- Name: handoff_note_revisions handoff_revision_guard; Type: TRIGGER; Schema: operations; Owner: -
--

CREATE TRIGGER handoff_revision_guard BEFORE INSERT OR DELETE OR UPDATE ON operations.handoff_note_revisions FOR EACH ROW EXECUTE FUNCTION operations.guard_handoff_history();


--
-- Name: handoff_note_revisions handoff_revisions_no_truncate; Type: TRIGGER; Schema: operations; Owner: -
--

CREATE TRIGGER handoff_revisions_no_truncate BEFORE TRUNCATE ON operations.handoff_note_revisions FOR EACH STATEMENT EXECUTE FUNCTION operations.refuse_handoff_truncate();


--
-- Name: handoff_command_receipts handoff_command_receipts_store_id_note_id_accepted_revisio_fkey; Type: FK CONSTRAINT; Schema: operations; Owner: -
--

ALTER TABLE ONLY operations.handoff_command_receipts
    ADD CONSTRAINT handoff_command_receipts_store_id_note_id_accepted_revisio_fkey FOREIGN KEY (store_id, note_id, accepted_revision) REFERENCES operations.handoff_note_revisions(store_id, note_id, revision);


--
-- Name: handoff_notes handoff_current_revision_fk; Type: FK CONSTRAINT; Schema: operations; Owner: -
--

ALTER TABLE ONLY operations.handoff_notes
    ADD CONSTRAINT handoff_current_revision_fk FOREIGN KEY (store_id, id, revision) REFERENCES operations.handoff_note_revisions(store_id, note_id, revision) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: handoff_note_revisions handoff_note_revisions_store_id_note_id_fkey; Type: FK CONSTRAINT; Schema: operations; Owner: -
--

ALTER TABLE ONLY operations.handoff_note_revisions
    ADD CONSTRAINT handoff_note_revisions_store_id_note_id_fkey FOREIGN KEY (store_id, note_id) REFERENCES operations.handoff_notes(store_id, id);


--
-- Name: handoff_notes handoff_notes_store_id_fkey; Type: FK CONSTRAINT; Schema: operations; Owner: -
--

ALTER TABLE ONLY operations.handoff_notes
    ADD CONSTRAINT handoff_notes_store_id_fkey FOREIGN KEY (store_id) REFERENCES operations.store_settings(store_id);


--
-- Name: store_settings store_settings_store_id_fkey; Type: FK CONSTRAINT; Schema: operations; Owner: -
--

ALTER TABLE ONLY operations.store_settings
    ADD CONSTRAINT store_settings_store_id_fkey FOREIGN KEY (store_id) REFERENCES public.stores(id);


--
-- Name: handoff_command_receipts; Type: ROW SECURITY; Schema: operations; Owner: -
--

ALTER TABLE operations.handoff_command_receipts ENABLE ROW LEVEL SECURITY;

--
-- Name: handoff_note_revisions; Type: ROW SECURITY; Schema: operations; Owner: -
--

ALTER TABLE operations.handoff_note_revisions ENABLE ROW LEVEL SECURITY;

--
-- Name: handoff_notes; Type: ROW SECURITY; Schema: operations; Owner: -
--

ALTER TABLE operations.handoff_notes ENABLE ROW LEVEL SECURITY;

--
-- Name: store_settings; Type: ROW SECURITY; Schema: operations; Owner: -
--

ALTER TABLE operations.store_settings ENABLE ROW LEVEL SECURITY;

--
-- PostgreSQL database dump complete
--
