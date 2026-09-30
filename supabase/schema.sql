-- Reference snapshot of the live Supabase `public` schema (project yrlhwcoirgqmtlvvnzvo),
-- captured read-only 2026-09-30. NOT a migration -- do not apply to the live project.
-- See supabase/README.md.

-- ==========================================================================
-- TABLES
-- ==========================================================================

CREATE TABLE public.activity_log (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  store_id text,
  user_email text,
  role text,
  method text,
  path text,
  status integer,
  created_at timestamp with time zone NOT NULL DEFAULT now()
);

CREATE TABLE public.adjustments (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  store_id text NOT NULL,
  item_code text NOT NULL,
  date date NOT NULL,
  reason text NOT NULL,
  qty numeric NOT NULL,
  direction text NOT NULL,
  note text,
  created_by text,
  created_at timestamp with time zone NOT NULL DEFAULT now()
);

CREATE TABLE public.ai_chat_messages (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  store_id text NOT NULL,
  role text NOT NULL,
  content text NOT NULL,
  ts timestamp with time zone NOT NULL DEFAULT now()
);

CREATE TABLE public.count_lines (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  session_id uuid NOT NULL,
  item_code text,
  dish_id uuid,
  prep_item_id uuid,
  status text NOT NULL,
  qty numeric,
  count_unit text,
  note text,
  saved_by text,
  updated_at timestamp with time zone NOT NULL DEFAULT now()
);

CREATE TABLE public.count_sessions (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  store_id text NOT NULL,
  count_date date NOT NULL,
  count_type text NOT NULL DEFAULT 'nightly_prep'::text,
  counted_by uuid,
  counted_by_name text,
  status text NOT NULL DEFAULT 'open'::text,
  submitted_at timestamp with time zone,
  created_at timestamp with time zone NOT NULL DEFAULT now()
);

CREATE TABLE public.dish_lines (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  dish_id uuid NOT NULL,
  source_type text NOT NULL,
  item_code text,
  prep_dish_id uuid,
  qty numeric NOT NULL,
  uom text
);

CREATE TABLE public.dishes (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  store_id text NOT NULL,
  name text NOT NULL,
  menu_code text,
  recipe_type text NOT NULL DEFAULT 'menu'::text,
  price numeric,
  target_pct numeric,
  yield_qty numeric,
  yield_uom text,
  prep_par numeric,
  procedure text,
  equipment text,
  shelf_life text,
  menu_category text,
  sort_order integer,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  description text,
  photo_url text,
  portion_note text,
  frequency text
);

CREATE TABLE public.inventory_count_submissions (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  store_id text NOT NULL,
  submitted_by text,
  source text NOT NULL DEFAULT 'manager'::text,
  items jsonb NOT NULL DEFAULT '[]'::jsonb,
  submitted_at timestamp with time zone NOT NULL DEFAULT now()
);

CREATE TABLE public.invoice_lines (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  invoice_id uuid NOT NULL,
  vendor_item_id uuid,
  description text,
  qty numeric NOT NULL,
  purchase_unit text,
  unit_price numeric(12,4),
  extended numeric(12,2),
  is_credit boolean NOT NULL DEFAULT false
);

CREATE TABLE public.invoices (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  store_id text NOT NULL,
  delivered_to text,
  vendor_id text NOT NULL,
  invoice_number text,
  invoice_date date NOT NULL,
  total numeric(12,2),
  source text,
  source_file text,
  created_by uuid,
  created_at timestamp with time zone NOT NULL DEFAULT now()
);

CREATE TABLE public.items (
  code text NOT NULL,
  name text NOT NULL,
  category text,
  base_unit text NOT NULL,
  item_type text NOT NULL DEFAULT 'raw'::text,
  is_high_value boolean NOT NULL DEFAULT false,
  active boolean NOT NULL DEFAULT true,
  notes text,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  costing_type text NOT NULL DEFAULT 'portion'::text,
  pack_count numeric,
  unit_qty numeric,
  unit_uom text,
  portion_size numeric,
  portion_uom text
);

CREATE TABLE public.manager_log (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  store_id text NOT NULL,
  shift_date date NOT NULL,
  shift text,
  author_name text NOT NULL,
  author_id uuid,
  tag text,
  body text NOT NULL,
  urgent boolean NOT NULL DEFAULT false,
  status text NOT NULL DEFAULT 'open'::text,
  outcome text,
  closed_by_name text,
  closed_at timestamp with time zone,
  created_at timestamp with time zone NOT NULL DEFAULT now()
);

CREATE TABLE public.people (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  full_name text NOT NULL,
  email text,
  phone text,
  auth_user_id uuid,
  pay_type text,
  active boolean NOT NULL DEFAULT true,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now()
);

CREATE TABLE public.prep_items (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  store_id text NOT NULL,
  name text NOT NULL,
  item_code text,
  container text,
  shelf_life_days numeric,
  par_weekday numeric,
  par_weekend numeric,
  is_task boolean NOT NULL DEFAULT false,
  made_at text,
  sort_order integer,
  active boolean NOT NULL DEFAULT true,
  recipe_id uuid,
  vessel_capacity numeric,
  par_vessels numeric,
  schedule text NOT NULL DEFAULT 'daily'::text,
  note text,
  recur_days smallint[],
  fixed_qty numeric
);

CREATE TABLE public.prep_list_lines (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  list_id uuid NOT NULL,
  prep_item_id uuid,
  recipe_id uuid,
  task_type text NOT NULL DEFAULT 'batch'::text,
  name text,
  yield_uom text,
  yield_qty numeric,
  par numeric,
  on_hand numeric,
  uncounted boolean NOT NULL DEFAULT false,
  needed_units numeric,
  batches_planned numeric,
  batches_done numeric NOT NULL DEFAULT 0,
  make_qty numeric,
  vessel_name text,
  note text,
  done boolean NOT NULL DEFAULT false,
  done_by_name text,
  done_at timestamp with time zone,
  removed boolean NOT NULL DEFAULT false
);

CREATE TABLE public.prep_lists (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  store_id text NOT NULL,
  prep_date date NOT NULL,
  from_count uuid,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  status text NOT NULL DEFAULT 'draft'::text,
  released_at timestamp with time zone,
  released_by text,
  count_type text
);

CREATE TABLE public.prep_logs (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  store_id text NOT NULL,
  kind text NOT NULL,
  dish_id uuid,
  prep_item_id uuid,
  name text,
  batches numeric,
  produced numeric,
  yield_uom text,
  usage jsonb NOT NULL DEFAULT '[]'::jsonb,
  containers jsonb NOT NULL DEFAULT '[]'::jsonb,
  total_cost numeric,
  date date,
  created_at timestamp with time zone NOT NULL DEFAULT now()
);

CREATE TABLE public.prep_overrides (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  store_id text NOT NULL,
  date date NOT NULL,
  type text NOT NULL DEFAULT 'add'::text,
  recipe_id uuid,
  prep_item_id uuid,
  custom_name text,
  par numeric,
  batches numeric,
  note text,
  created_by text,
  created_at timestamp with time zone NOT NULL DEFAULT now()
);

CREATE TABLE public.prep_recipe_stock (
  dish_id uuid,
  store_id text NOT NULL,
  on_hand numeric NOT NULL DEFAULT 0,
  containers jsonb NOT NULL DEFAULT '[]'::jsonb,
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  prep_item_id uuid
);

CREATE TABLE public.purchase_order_lines (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  po_id uuid NOT NULL,
  vendor_item_id uuid,
  item_code text,
  description text,
  qty numeric NOT NULL,
  unit text,
  unit_price numeric,
  extended numeric,
  received_qty numeric
);

CREATE TABLE public.purchase_orders (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  store_id text NOT NULL,
  vendor_id text NOT NULL,
  status text NOT NULL DEFAULT 'draft'::text,
  created_by text,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  approved_by text,
  approved_at timestamp with time zone,
  rejected_reason text,
  sent_at timestamp with time zone,
  received_at timestamp with time zone,
  invoice_id uuid
);

CREATE TABLE public.push_subscriptions (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  store_id text NOT NULL,
  endpoint text NOT NULL,
  keys jsonb NOT NULL,
  created_at timestamp with time zone NOT NULL DEFAULT now()
);

CREATE TABLE public.reporting_periods (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  store_id text NOT NULL,
  period_start date NOT NULL,
  period_end date NOT NULL,
  name text,
  status text NOT NULL DEFAULT 'draft'::text,
  dish_sales jsonb NOT NULL DEFAULT '{}'::jsonb,
  item_counts jsonb NOT NULL DEFAULT '{}'::jsonb,
  saved_at timestamp with time zone,
  created_at timestamp with time zone NOT NULL DEFAULT now()
);

CREATE TABLE public.sales_daily (
  store_id text NOT NULL,
  business_date date NOT NULL,
  net_sales numeric(12,2),
  forecast_sales numeric(12,2),
  hourly_wages numeric(12,2),
  guests integer,
  source text NOT NULL DEFAULT 'toast'::text,
  loaded_at timestamp with time zone NOT NULL DEFAULT now()
);

CREATE TABLE public.staff_members (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  store_id text NOT NULL,
  name text NOT NULL,
  role text NOT NULL DEFAULT 'cook'::text,
  active boolean NOT NULL DEFAULT true,
  created_at timestamp with time zone NOT NULL DEFAULT now()
);

CREATE TABLE public.staff_pins (
  store_id text NOT NULL,
  pin text NOT NULL
);

CREATE TABLE public.staff_tasks (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  store_id text NOT NULL,
  task_type text NOT NULL,
  title text NOT NULL,
  due_date date NOT NULL,
  recurrence text NOT NULL DEFAULT 'once'::text,
  assigned_to text,
  track text NOT NULL DEFAULT 'daily'::text,
  note text,
  status text NOT NULL DEFAULT 'pending'::text,
  completed_by text,
  completed_at timestamp with time zone,
  created_by text,
  created_at timestamp with time zone NOT NULL DEFAULT now()
);

CREATE TABLE public.store_items (
  store_id text NOT NULL,
  item_code text NOT NULL,
  count_unit text NOT NULL,
  base_per_count_unit numeric NOT NULL,
  storage_area text,
  counted_nightly boolean NOT NULL DEFAULT false,
  active boolean NOT NULL DEFAULT true,
  current_stock numeric NOT NULL DEFAULT 0,
  par numeric NOT NULL DEFAULT 0,
  last_counted date,
  last_counted_by text,
  last_counted_at timestamp with time zone,
  order_enabled boolean NOT NULL DEFAULT true,
  sales_tracked boolean NOT NULL DEFAULT true,
  needs_review boolean NOT NULL DEFAULT false
);

CREATE TABLE public.store_roles (
  person_id uuid NOT NULL,
  store_id text NOT NULL,
  role text NOT NULL,
  created_at timestamp with time zone NOT NULL DEFAULT now()
);

CREATE TABLE public.stores (
  id text NOT NULL,
  name text NOT NULL,
  ownership text,
  uses_commissary boolean NOT NULL DEFAULT false,
  color_primary text,
  color_accent text,
  active boolean NOT NULL DEFAULT true,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now()
);

CREATE TABLE public.vendor_items (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  vendor_id text NOT NULL,
  vendor_sku text NOT NULL,
  vendor_description text,
  item_code text,
  purchase_unit text NOT NULL,
  base_per_purchase_unit numeric,
  pack_verified boolean NOT NULL DEFAULT false,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  price numeric,
  price_updated_at timestamp with time zone,
  price_source text,
  preferred boolean NOT NULL DEFAULT false,
  available boolean NOT NULL DEFAULT true,
  pack_count numeric,
  unit_qty numeric,
  unit_uom text
);

CREATE TABLE public.vendors (
  id text NOT NULL,
  name text NOT NULL,
  order_email text,
  rep_name text,
  rep_phone text,
  active boolean NOT NULL DEFAULT true,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now()
);

-- ==========================================================================
-- PRIMARY KEYS
-- ==========================================================================

ALTER TABLE ONLY public.activity_log ADD CONSTRAINT activity_log_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.adjustments ADD CONSTRAINT adjustments_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.ai_chat_messages ADD CONSTRAINT ai_chat_messages_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.count_lines ADD CONSTRAINT count_lines_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.count_sessions ADD CONSTRAINT count_sessions_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.dish_lines ADD CONSTRAINT dish_lines_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.dishes ADD CONSTRAINT dishes_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.inventory_count_submissions ADD CONSTRAINT inventory_count_submissions_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.invoice_lines ADD CONSTRAINT invoice_lines_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.invoices ADD CONSTRAINT invoices_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.items ADD CONSTRAINT items_pkey PRIMARY KEY (code);
ALTER TABLE ONLY public.manager_log ADD CONSTRAINT manager_log_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.people ADD CONSTRAINT people_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.prep_items ADD CONSTRAINT prep_items_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.prep_list_lines ADD CONSTRAINT prep_list_lines_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.prep_lists ADD CONSTRAINT prep_lists_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.prep_logs ADD CONSTRAINT prep_logs_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.prep_overrides ADD CONSTRAINT prep_overrides_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.prep_recipe_stock ADD CONSTRAINT prep_recipe_stock_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.purchase_order_lines ADD CONSTRAINT purchase_order_lines_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.purchase_orders ADD CONSTRAINT purchase_orders_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.push_subscriptions ADD CONSTRAINT push_subscriptions_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.reporting_periods ADD CONSTRAINT reporting_periods_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.sales_daily ADD CONSTRAINT sales_daily_pkey PRIMARY KEY (store_id, business_date);
ALTER TABLE ONLY public.staff_members ADD CONSTRAINT staff_members_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.staff_pins ADD CONSTRAINT staff_pins_pkey PRIMARY KEY (store_id);
ALTER TABLE ONLY public.staff_tasks ADD CONSTRAINT staff_tasks_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.store_items ADD CONSTRAINT store_items_pkey PRIMARY KEY (store_id, item_code);
ALTER TABLE ONLY public.store_roles ADD CONSTRAINT store_roles_pkey PRIMARY KEY (person_id, store_id, role);
ALTER TABLE ONLY public.stores ADD CONSTRAINT stores_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.vendor_items ADD CONSTRAINT vendor_items_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.vendors ADD CONSTRAINT vendors_pkey PRIMARY KEY (id);

-- ==========================================================================
-- UNIQUE CONSTRAINTS
-- ==========================================================================

ALTER TABLE ONLY public.count_sessions ADD CONSTRAINT count_sessions_store_id_count_date_count_type_key UNIQUE (store_id, count_date, count_type);
ALTER TABLE ONLY public.invoices ADD CONSTRAINT invoices_vendor_id_invoice_number_store_id_key UNIQUE (vendor_id, invoice_number, store_id);
ALTER TABLE ONLY public.people ADD CONSTRAINT people_auth_user_id_key UNIQUE (auth_user_id);
ALTER TABLE ONLY public.people ADD CONSTRAINT people_email_key UNIQUE (email);
ALTER TABLE ONLY public.prep_items ADD CONSTRAINT prep_items_store_id_name_key UNIQUE (store_id, name);
ALTER TABLE ONLY public.prep_lists ADD CONSTRAINT prep_lists_store_id_prep_date_key UNIQUE (store_id, prep_date);
ALTER TABLE ONLY public.push_subscriptions ADD CONSTRAINT push_subscriptions_endpoint_key UNIQUE (endpoint);
ALTER TABLE ONLY public.vendor_items ADD CONSTRAINT vendor_items_vendor_id_vendor_sku_key UNIQUE (vendor_id, vendor_sku);

-- ==========================================================================
-- FOREIGN KEYS
-- ==========================================================================

ALTER TABLE ONLY public.activity_log ADD CONSTRAINT activity_log_store_id_fkey FOREIGN KEY (store_id) REFERENCES stores(id);
ALTER TABLE ONLY public.adjustments ADD CONSTRAINT adjustments_item_code_fkey FOREIGN KEY (item_code) REFERENCES items(code);
ALTER TABLE ONLY public.adjustments ADD CONSTRAINT adjustments_store_id_fkey FOREIGN KEY (store_id) REFERENCES stores(id);
ALTER TABLE ONLY public.ai_chat_messages ADD CONSTRAINT ai_chat_messages_store_id_fkey FOREIGN KEY (store_id) REFERENCES stores(id);
ALTER TABLE ONLY public.count_lines ADD CONSTRAINT count_lines_dish_id_fkey FOREIGN KEY (dish_id) REFERENCES dishes(id);
ALTER TABLE ONLY public.count_lines ADD CONSTRAINT count_lines_item_code_fkey FOREIGN KEY (item_code) REFERENCES items(code);
ALTER TABLE ONLY public.count_lines ADD CONSTRAINT count_lines_prep_item_id_fkey FOREIGN KEY (prep_item_id) REFERENCES prep_items(id);
ALTER TABLE ONLY public.count_lines ADD CONSTRAINT count_lines_session_id_fkey FOREIGN KEY (session_id) REFERENCES count_sessions(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.count_sessions ADD CONSTRAINT count_sessions_counted_by_fkey FOREIGN KEY (counted_by) REFERENCES people(id);
ALTER TABLE ONLY public.count_sessions ADD CONSTRAINT count_sessions_store_id_fkey FOREIGN KEY (store_id) REFERENCES stores(id);
ALTER TABLE ONLY public.dish_lines ADD CONSTRAINT dish_lines_dish_id_fkey FOREIGN KEY (dish_id) REFERENCES dishes(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.dish_lines ADD CONSTRAINT dish_lines_item_code_fkey FOREIGN KEY (item_code) REFERENCES items(code);
ALTER TABLE ONLY public.dish_lines ADD CONSTRAINT dish_lines_prep_dish_id_fkey FOREIGN KEY (prep_dish_id) REFERENCES dishes(id);
ALTER TABLE ONLY public.dishes ADD CONSTRAINT dishes_store_id_fkey FOREIGN KEY (store_id) REFERENCES stores(id);
ALTER TABLE ONLY public.inventory_count_submissions ADD CONSTRAINT inventory_count_submissions_store_id_fkey FOREIGN KEY (store_id) REFERENCES stores(id);
ALTER TABLE ONLY public.invoice_lines ADD CONSTRAINT invoice_lines_invoice_id_fkey FOREIGN KEY (invoice_id) REFERENCES invoices(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.invoice_lines ADD CONSTRAINT invoice_lines_vendor_item_id_fkey FOREIGN KEY (vendor_item_id) REFERENCES vendor_items(id);
ALTER TABLE ONLY public.invoices ADD CONSTRAINT invoices_created_by_fkey FOREIGN KEY (created_by) REFERENCES people(id);
ALTER TABLE ONLY public.invoices ADD CONSTRAINT invoices_delivered_to_fkey FOREIGN KEY (delivered_to) REFERENCES stores(id);
ALTER TABLE ONLY public.invoices ADD CONSTRAINT invoices_store_id_fkey FOREIGN KEY (store_id) REFERENCES stores(id);
ALTER TABLE ONLY public.invoices ADD CONSTRAINT invoices_vendor_id_fkey FOREIGN KEY (vendor_id) REFERENCES vendors(id);
ALTER TABLE ONLY public.manager_log ADD CONSTRAINT manager_log_author_id_fkey FOREIGN KEY (author_id) REFERENCES people(id);
ALTER TABLE ONLY public.manager_log ADD CONSTRAINT manager_log_store_id_fkey FOREIGN KEY (store_id) REFERENCES stores(id);
ALTER TABLE ONLY public.prep_items ADD CONSTRAINT prep_items_item_code_fkey FOREIGN KEY (item_code) REFERENCES items(code);
ALTER TABLE ONLY public.prep_items ADD CONSTRAINT prep_items_made_at_fkey FOREIGN KEY (made_at) REFERENCES stores(id);
ALTER TABLE ONLY public.prep_items ADD CONSTRAINT prep_items_recipe_id_fkey FOREIGN KEY (recipe_id) REFERENCES dishes(id);
ALTER TABLE ONLY public.prep_items ADD CONSTRAINT prep_items_store_id_fkey FOREIGN KEY (store_id) REFERENCES stores(id);
ALTER TABLE ONLY public.prep_list_lines ADD CONSTRAINT prep_list_lines_list_id_fkey FOREIGN KEY (list_id) REFERENCES prep_lists(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.prep_list_lines ADD CONSTRAINT prep_list_lines_prep_item_id_fkey FOREIGN KEY (prep_item_id) REFERENCES prep_items(id);
ALTER TABLE ONLY public.prep_list_lines ADD CONSTRAINT prep_list_lines_recipe_id_fkey FOREIGN KEY (recipe_id) REFERENCES dishes(id);
ALTER TABLE ONLY public.prep_lists ADD CONSTRAINT prep_lists_from_count_fkey FOREIGN KEY (from_count) REFERENCES count_sessions(id);
ALTER TABLE ONLY public.prep_lists ADD CONSTRAINT prep_lists_store_id_fkey FOREIGN KEY (store_id) REFERENCES stores(id);
ALTER TABLE ONLY public.prep_logs ADD CONSTRAINT prep_logs_dish_id_fkey FOREIGN KEY (dish_id) REFERENCES dishes(id);
ALTER TABLE ONLY public.prep_logs ADD CONSTRAINT prep_logs_prep_item_id_fkey FOREIGN KEY (prep_item_id) REFERENCES prep_items(id);
ALTER TABLE ONLY public.prep_logs ADD CONSTRAINT prep_logs_store_id_fkey FOREIGN KEY (store_id) REFERENCES stores(id);
ALTER TABLE ONLY public.prep_overrides ADD CONSTRAINT prep_overrides_prep_item_id_fkey FOREIGN KEY (prep_item_id) REFERENCES prep_items(id);
ALTER TABLE ONLY public.prep_overrides ADD CONSTRAINT prep_overrides_recipe_id_fkey FOREIGN KEY (recipe_id) REFERENCES dishes(id);
ALTER TABLE ONLY public.prep_overrides ADD CONSTRAINT prep_overrides_store_id_fkey FOREIGN KEY (store_id) REFERENCES stores(id);
ALTER TABLE ONLY public.prep_recipe_stock ADD CONSTRAINT prep_recipe_stock_dish_id_fkey FOREIGN KEY (dish_id) REFERENCES dishes(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.prep_recipe_stock ADD CONSTRAINT prep_recipe_stock_prep_item_id_fkey FOREIGN KEY (prep_item_id) REFERENCES prep_items(id);
ALTER TABLE ONLY public.prep_recipe_stock ADD CONSTRAINT prep_recipe_stock_store_id_fkey FOREIGN KEY (store_id) REFERENCES stores(id);
ALTER TABLE ONLY public.purchase_order_lines ADD CONSTRAINT purchase_order_lines_item_code_fkey FOREIGN KEY (item_code) REFERENCES items(code);
ALTER TABLE ONLY public.purchase_order_lines ADD CONSTRAINT purchase_order_lines_po_id_fkey FOREIGN KEY (po_id) REFERENCES purchase_orders(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.purchase_order_lines ADD CONSTRAINT purchase_order_lines_vendor_item_id_fkey FOREIGN KEY (vendor_item_id) REFERENCES vendor_items(id);
ALTER TABLE ONLY public.purchase_orders ADD CONSTRAINT purchase_orders_invoice_id_fkey FOREIGN KEY (invoice_id) REFERENCES invoices(id);
ALTER TABLE ONLY public.purchase_orders ADD CONSTRAINT purchase_orders_store_id_fkey FOREIGN KEY (store_id) REFERENCES stores(id);
ALTER TABLE ONLY public.purchase_orders ADD CONSTRAINT purchase_orders_vendor_id_fkey FOREIGN KEY (vendor_id) REFERENCES vendors(id);
ALTER TABLE ONLY public.push_subscriptions ADD CONSTRAINT push_subscriptions_store_id_fkey FOREIGN KEY (store_id) REFERENCES stores(id);
ALTER TABLE ONLY public.reporting_periods ADD CONSTRAINT reporting_periods_store_id_fkey FOREIGN KEY (store_id) REFERENCES stores(id);
ALTER TABLE ONLY public.sales_daily ADD CONSTRAINT sales_daily_store_id_fkey FOREIGN KEY (store_id) REFERENCES stores(id);
ALTER TABLE ONLY public.staff_members ADD CONSTRAINT staff_members_store_id_fkey FOREIGN KEY (store_id) REFERENCES stores(id);
ALTER TABLE ONLY public.staff_pins ADD CONSTRAINT staff_pins_store_id_fkey FOREIGN KEY (store_id) REFERENCES stores(id);
ALTER TABLE ONLY public.staff_tasks ADD CONSTRAINT staff_tasks_store_id_fkey FOREIGN KEY (store_id) REFERENCES stores(id);
ALTER TABLE ONLY public.store_items ADD CONSTRAINT store_items_item_code_fkey FOREIGN KEY (item_code) REFERENCES items(code);
ALTER TABLE ONLY public.store_items ADD CONSTRAINT store_items_store_id_fkey FOREIGN KEY (store_id) REFERENCES stores(id);
ALTER TABLE ONLY public.store_roles ADD CONSTRAINT store_roles_person_id_fkey FOREIGN KEY (person_id) REFERENCES people(id);
ALTER TABLE ONLY public.store_roles ADD CONSTRAINT store_roles_store_id_fkey FOREIGN KEY (store_id) REFERENCES stores(id);
ALTER TABLE ONLY public.vendor_items ADD CONSTRAINT vendor_items_item_code_fkey FOREIGN KEY (item_code) REFERENCES items(code);
ALTER TABLE ONLY public.vendor_items ADD CONSTRAINT vendor_items_vendor_id_fkey FOREIGN KEY (vendor_id) REFERENCES vendors(id);

-- ==========================================================================
-- CHECK CONSTRAINTS
-- ==========================================================================

ALTER TABLE ONLY public.adjustments ADD CONSTRAINT adjustments_direction_check CHECK ((direction = ANY (ARRAY['add'::text, 'remove'::text])));
ALTER TABLE ONLY public.ai_chat_messages ADD CONSTRAINT ai_chat_messages_role_check CHECK ((role = ANY (ARRAY['user'::text, 'assistant'::text])));
ALTER TABLE ONLY public.count_lines ADD CONSTRAINT count_lines_qty_check CHECK ((qty >= (0)::numeric));
ALTER TABLE ONLY public.count_lines ADD CONSTRAINT count_lines_status_check CHECK ((status = ANY (ARRAY['counted'::text, 'not_counted'::text])));
ALTER TABLE ONLY public.count_sessions ADD CONSTRAINT count_sessions_count_type_check CHECK ((count_type = ANY (ARRAY['nightly_prep'::text, 'monthly_high_value'::text, 'full_inventory'::text, 'commissary'::text])));
ALTER TABLE ONLY public.count_sessions ADD CONSTRAINT count_sessions_status_check CHECK ((status = ANY (ARRAY['open'::text, 'submitted'::text, 'reopened'::text])));
ALTER TABLE ONLY public.dish_lines ADD CONSTRAINT dish_lines_source_type_check CHECK ((source_type = ANY (ARRAY['item'::text, 'prep'::text])));
ALTER TABLE ONLY public.dishes ADD CONSTRAINT dishes_recipe_type_check CHECK ((recipe_type = ANY (ARRAY['menu'::text, 'prep'::text])));
ALTER TABLE ONLY public.inventory_count_submissions ADD CONSTRAINT inventory_count_submissions_source_check CHECK ((source = ANY (ARRAY['manager'::text, 'staff_pwa'::text])));
ALTER TABLE ONLY public.items ADD CONSTRAINT items_costing_type_check CHECK ((costing_type = ANY (ARRAY['portion'::text, 'usage'::text])));
ALTER TABLE ONLY public.items ADD CONSTRAINT items_item_type_check CHECK ((item_type = ANY (ARRAY['raw'::text, 'prep'::text, 'commissary'::text, 'paper'::text, 'chemical'::text, 'other'::text])));
ALTER TABLE ONLY public.manager_log ADD CONSTRAINT closed_needs_outcome CHECK (((status = 'open'::text) OR (outcome IS NOT NULL)));
ALTER TABLE ONLY public.manager_log ADD CONSTRAINT manager_log_shift_check CHECK ((shift = ANY (ARRAY['open'::text, 'mid'::text, 'close'::text])));
ALTER TABLE ONLY public.manager_log ADD CONSTRAINT manager_log_status_check CHECK ((status = ANY (ARRAY['open'::text, 'closed'::text])));
ALTER TABLE ONLY public.manager_log ADD CONSTRAINT manager_log_tag_check CHECK ((tag = ANY (ARRAY['note'::text, 'repair'::text, 'incident'::text, 'guest'::text, '86'::text, 'staff'::text, 'must_do'::text])));
ALTER TABLE ONLY public.people ADD CONSTRAINT people_pay_type_check CHECK ((pay_type = ANY (ARRAY['hourly'::text, 'salary'::text, 'owner'::text])));
ALTER TABLE ONLY public.prep_items ADD CONSTRAINT prep_items_recur_days_range_check CHECK (((recur_days IS NULL) OR (recur_days <@ ARRAY[(0)::smallint, (1)::smallint, (2)::smallint, (3)::smallint, (4)::smallint, (5)::smallint, (6)::smallint])));
ALTER TABLE ONLY public.prep_items ADD CONSTRAINT prep_items_recurring_requires_fields_check CHECK (((schedule <> 'recurring'::text) OR ((recur_days IS NOT NULL) AND (cardinality(recur_days) > 0) AND (fixed_qty IS NOT NULL) AND (fixed_qty > (0)::numeric))));
ALTER TABLE ONLY public.prep_items ADD CONSTRAINT prep_items_schedule_check CHECK ((schedule = ANY (ARRAY['daily'::text, 'oneoff'::text, 'recurring'::text])));
ALTER TABLE ONLY public.prep_items ADD CONSTRAINT prep_items_source_check CHECK ((num_nonnulls(item_code, recipe_id) = 1));
ALTER TABLE ONLY public.prep_list_lines ADD CONSTRAINT prep_list_lines_task_type_check CHECK ((task_type = ANY (ARRAY['batch'::text, 'task'::text])));
ALTER TABLE ONLY public.prep_lists ADD CONSTRAINT prep_lists_count_type_check CHECK ((count_type = ANY (ARRAY['nightly_prep'::text, 'monthly_high_value'::text, 'full_inventory'::text, 'commissary'::text])));
ALTER TABLE ONLY public.prep_lists ADD CONSTRAINT prep_lists_status_check CHECK ((status = ANY (ARRAY['draft'::text, 'released'::text])));
ALTER TABLE ONLY public.prep_logs ADD CONSTRAINT prep_logs_kind_check CHECK ((kind = ANY (ARRAY['batch'::text, 'sales_usage'::text, 'container_use'::text])));
ALTER TABLE ONLY public.prep_overrides ADD CONSTRAINT prep_overrides_type_check CHECK ((type = ANY (ARRAY['add'::text, 'par'::text, 'remove'::text])));
ALTER TABLE ONLY public.prep_recipe_stock ADD CONSTRAINT prep_recipe_stock_source_check CHECK ((num_nonnulls(dish_id, prep_item_id) = 1));
ALTER TABLE ONLY public.purchase_orders ADD CONSTRAINT purchase_orders_status_check CHECK ((status = ANY (ARRAY['draft'::text, 'pending'::text, 'approved'::text, 'sent'::text, 'received'::text, 'rejected'::text])));
ALTER TABLE ONLY public.reporting_periods ADD CONSTRAINT reporting_periods_status_check CHECK ((status = ANY (ARRAY['draft'::text, 'closed'::text])));
ALTER TABLE ONLY public.staff_members ADD CONSTRAINT staff_members_role_check CHECK ((role = ANY (ARRAY['cook'::text, 'owner_admin'::text])));
ALTER TABLE ONLY public.staff_tasks ADD CONSTRAINT staff_tasks_recurrence_check CHECK ((recurrence = ANY (ARRAY['once'::text, 'daily'::text, 'weekly'::text])));
ALTER TABLE ONLY public.staff_tasks ADD CONSTRAINT staff_tasks_status_check CHECK ((status = ANY (ARRAY['pending'::text, 'done'::text])));
ALTER TABLE ONLY public.staff_tasks ADD CONSTRAINT staff_tasks_task_type_check CHECK ((task_type = ANY (ARRAY['count'::text, 'prep'::text])));
ALTER TABLE ONLY public.store_items ADD CONSTRAINT store_items_base_per_count_unit_check CHECK ((base_per_count_unit > (0)::numeric));
ALTER TABLE ONLY public.store_roles ADD CONSTRAINT store_roles_role_check CHECK ((role = ANY (ARRAY['owner'::text, 'gm'::text, 'manager'::text, 'lead'::text, 'staff'::text, 'consultant'::text])));
ALTER TABLE ONLY public.vendor_items ADD CONSTRAINT vendor_items_base_per_purchase_unit_check CHECK ((base_per_purchase_unit > (0)::numeric));

-- ==========================================================================
-- INDEXES (non-constraint-backing)
-- ==========================================================================

CREATE INDEX count_sessions_store_id_count_date_idx ON public.count_sessions USING btree (store_id, count_date);
CREATE INDEX inventory_count_submissions_store_id_submitted_at_idx ON public.inventory_count_submissions USING btree (store_id, submitted_at DESC);
CREATE INDEX invoice_lines_invoice_id_idx ON public.invoice_lines USING btree (invoice_id);
CREATE INDEX invoices_store_id_invoice_date_idx ON public.invoices USING btree (store_id, invoice_date);
CREATE INDEX manager_log_store_id_status_shift_date_idx ON public.manager_log USING btree (store_id, status, shift_date);
CREATE INDEX prep_items_store_id_idx ON public.prep_items USING btree (store_id);
CREATE UNIQUE INDEX prep_recipe_stock_dish_store_uq ON public.prep_recipe_stock USING btree (store_id, dish_id) WHERE (dish_id IS NOT NULL);
CREATE UNIQUE INDEX prep_recipe_stock_prepitem_store_uq ON public.prep_recipe_stock USING btree (store_id, prep_item_id) WHERE (prep_item_id IS NOT NULL);

-- ==========================================================================
-- FUNCTIONS (public schema)
-- jmax_toast_* belong to the separate Toast POS integration
-- (add_private_toast_analytics_landing_zone) and write to the "integrations" schema.
-- ==========================================================================

CREATE OR REPLACE FUNCTION public.jmax_toast_finish_sync(p_sync_run_id uuid, p_status text, p_records_written integer, p_error_summary text DEFAULT NULL::text)
 RETURNS void
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'integrations'
AS $function$
begin
  if p_status not in ('succeeded', 'failed') then
    raise exception 'Invalid sync status';
  end if;
  update toast_sync_runs
  set status = p_status, finished_at = now(), records_written = p_records_written, error_summary = p_error_summary
  where id = p_sync_run_id;
end;
$function$;

CREATE OR REPLACE FUNCTION public.jmax_toast_start_sync(p_report_kind text, p_start_date date, p_end_date date)
 RETURNS uuid
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'integrations'
AS $function$
declare v_id uuid;
begin
  insert into toast_sync_runs (status, report_kind, requested_start_date, requested_end_date)
  values ('started', p_report_kind, p_start_date, p_end_date)
  returning id into v_id;
  return v_id;
end;
$function$;

CREATE OR REPLACE FUNCTION public.jmax_toast_store_payloads(p_sync_run_id uuid, p_payloads jsonb)
 RETURNS integer
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'integrations'
AS $function$
declare
  v_count integer;
begin
  insert into toast_report_payloads (
    sync_run_id, toast_restaurant_guid, report_kind, business_date, payload
  )
  select
    p_sync_run_id,
    item.toast_restaurant_guid,
    item.report_kind,
    item.business_date,
    item.payload
  from jsonb_to_recordset(p_payloads) as item(
    toast_restaurant_guid uuid,
    report_kind text,
    business_date date,
    payload jsonb
  );
  get diagnostics v_count = row_count;
  return v_count;
end;
$function$;

CREATE OR REPLACE FUNCTION public.jmax_touch_updated_at()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
begin new.updated_at = now(); return new; end
$function$;

-- ==========================================================================
-- TRIGGERS
-- ==========================================================================

CREATE TRIGGER t_items BEFORE UPDATE ON public.items FOR EACH ROW EXECUTE FUNCTION jmax_touch_updated_at();
CREATE TRIGGER t_people BEFORE UPDATE ON public.people FOR EACH ROW EXECUTE FUNCTION jmax_touch_updated_at();
CREATE TRIGGER t_stores BEFORE UPDATE ON public.stores FOR EACH ROW EXECUTE FUNCTION jmax_touch_updated_at();
CREATE TRIGGER t_vitems BEFORE UPDATE ON public.vendor_items FOR EACH ROW EXECUTE FUNCTION jmax_touch_updated_at();
CREATE TRIGGER t_vendors BEFORE UPDATE ON public.vendors FOR EACH ROW EXECUTE FUNCTION jmax_touch_updated_at();

-- ==========================================================================
-- ROW LEVEL SECURITY -- enabled on every table, zero policies (deny-all for
-- anon/authenticated; the backend's postgres role bypasses RLS).
-- ==========================================================================

ALTER TABLE public.activity_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.adjustments ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ai_chat_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.count_lines ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.count_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.dish_lines ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.dishes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.inventory_count_submissions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.invoice_lines ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.invoices ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.items ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.manager_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.people ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.prep_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.prep_list_lines ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.prep_lists ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.prep_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.prep_overrides ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.prep_recipe_stock ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.purchase_order_lines ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.purchase_orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.push_subscriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.reporting_periods ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sales_daily ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.staff_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.staff_pins ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.staff_tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.store_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.store_roles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.stores ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.vendor_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.vendors ENABLE ROW LEVEL SECURITY;
