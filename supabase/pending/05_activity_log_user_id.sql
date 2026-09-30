-- Phase 2, chunk 6: the activity log records who made each request; Mongo stored the
-- user id alongside the email. Name: phase2_activity_log_user_id.
ALTER TABLE public.activity_log ADD COLUMN user_id text;
CREATE INDEX activity_log_created_at_idx ON public.activity_log (created_at DESC);
