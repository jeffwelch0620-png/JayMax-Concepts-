-- Phase 2, chunk 1: homes for the Mongo `users`, `state_versions`, `areas` and
-- `sales_periods` collections. Apply once (Supabase SQL editor or apply_migration,
-- name: phase2_app_users_and_store_state), then move this file's content into
-- supabase/schema.sql. See docs/SUPABASE_MIGRATION_PLAN.md, "Phase 2".

CREATE TABLE public.app_users (
  id text PRIMARY KEY,                      -- keeps the Mongo "usr_..." id: tokens carry it as `sub`
  email text NOT NULL UNIQUE,               -- stored lowercased by the app
  password_hash text NOT NULL,              -- pbkdf2$<salt>$<digest>, same format as Mongo
  role text NOT NULL CHECK (role IN ('owner', 'manager', 'staff', 'readonly')),
  locations text[] NOT NULL DEFAULT '{}',   -- Mongo-side restaurant ids (berts/rudds/papa_leonis)
  created_at timestamp with time zone NOT NULL DEFAULT now()
);

-- One row per store: the optimistic-concurrency revision shared by every state write,
-- plus the two per-store settings blobs that were their own Mongo collections.
-- NULL areas / sales_period means "use the app's default".
CREATE TABLE public.store_state (
  store_id text PRIMARY KEY REFERENCES public.stores(id),
  revision integer NOT NULL DEFAULT 0,
  areas jsonb,
  sales_period jsonb,
  updated_at timestamp with time zone NOT NULL DEFAULT now()
);

ALTER TABLE public.app_users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.store_state ENABLE ROW LEVEL SECURITY;
