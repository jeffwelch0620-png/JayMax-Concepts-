-- Phase 2, chunk 5: homes for the Mongo `projected_sales` and `par_recommendations`
-- collections (AI chat history uses the existing ai_chat_messages table).
-- Name: phase2_projections_and_par_recommendations.

-- Manager-entered projected sales, one per store and day (Prep tab; fed to the par advisor).
CREATE TABLE public.store_sales_projections (
  store_id text NOT NULL REFERENCES public.stores(id),
  date date NOT NULL,
  amount numeric(12,2) NOT NULL DEFAULT 0,
  note text NOT NULL DEFAULT '',
  entered_by text NOT NULL DEFAULT '',
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  PRIMARY KEY (store_id, date)
);

-- AI par advisor output. Advisory only: a par changes only when a manager applies one.
CREATE TABLE public.par_recommendations (
  id text PRIMARY KEY,                                   -- "rec_..." as returned to the app
  store_id text NOT NULL REFERENCES public.stores(id),
  recipe_id uuid NOT NULL REFERENCES public.dishes(id) ON DELETE CASCADE,
  recipe_name text NOT NULL DEFAULT '',
  current_par numeric,
  recommended_par numeric NOT NULL,
  reasoning text NOT NULL DEFAULT '',
  status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'applied', 'dismissed')),
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  applied_at timestamp with time zone
);
CREATE INDEX par_recommendations_store_id_status_idx ON public.par_recommendations (store_id, status, created_at DESC);
CREATE INDEX ai_chat_messages_store_id_ts_idx ON public.ai_chat_messages (store_id, ts);

ALTER TABLE public.store_sales_projections ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.par_recommendations ENABLE ROW LEVEL SECURITY;
