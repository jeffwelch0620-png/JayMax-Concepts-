-- Reference snapshot of the live Supabase `public` schema (project yrlhwcoirgqmtlvvnzvo)
-- as of 2026-09-30, after the Phase 2 migrations (phase2_* in supabase/README.md).
-- Generated with pg_dump --schema-only from the phase-1 snapshot plus those migrations.
-- NOT a migration -- do not apply to the live project. See supabase/README.md.

--
-- PostgreSQL database dump
--

-- Dumped from database version 16.13 (Ubuntu 16.13-0ubuntu0.24.04.1)
-- Dumped by pg_dump version 16.13 (Ubuntu 16.13-0ubuntu0.24.04.1)

--
-- Name: jmax_toast_finish_sync(uuid, text, integer, text); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.jmax_toast_finish_sync(p_sync_run_id uuid, p_status text, p_records_written integer, p_error_summary text DEFAULT NULL::text) RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'integrations'
    AS $$
begin
  if p_status not in ('succeeded', 'failed') then
    raise exception 'Invalid sync status';
  end if;
  update toast_sync_runs
  set status = p_status, finished_at = now(), records_written = p_records_written, error_summary = p_error_summary
  where id = p_sync_run_id;
end;
$$;

--
-- Name: jmax_toast_start_sync(text, date, date); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.jmax_toast_start_sync(p_report_kind text, p_start_date date, p_end_date date) RETURNS uuid
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'integrations'
    AS $$
declare v_id uuid;
begin
  insert into toast_sync_runs (status, report_kind, requested_start_date, requested_end_date)
  values ('started', p_report_kind, p_start_date, p_end_date)
  returning id into v_id;
  return v_id;
end;
$$;

--
-- Name: jmax_toast_store_payloads(uuid, jsonb); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.jmax_toast_store_payloads(p_sync_run_id uuid, p_payloads jsonb) RETURNS integer
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'integrations'
    AS $$
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
$$;

--
-- Name: jmax_touch_updated_at(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.jmax_touch_updated_at() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
begin new.updated_at = now(); return new; end
$$;

--
-- Name: activity_log; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.activity_log (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    store_id text,
    user_email text,
    role text,
    method text,
    path text,
    status integer,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    user_id text
);

--
-- Name: adjustments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.adjustments (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    store_id text NOT NULL,
    item_code text,
    date date NOT NULL,
    reason text NOT NULL,
    qty numeric NOT NULL,
    direction text NOT NULL,
    note text,
    created_by text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    ref text NOT NULL,
    control_number text NOT NULL,
    qty_basis text DEFAULT 'purchase'::text NOT NULL,
    CONSTRAINT adjustments_direction_check CHECK ((direction = ANY (ARRAY['add'::text, 'remove'::text]))),
    CONSTRAINT adjustments_qty_basis_check CHECK ((qty_basis = ANY (ARRAY['purchase'::text, 'portion'::text])))
);

--
-- Name: ai_chat_messages; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ai_chat_messages (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    store_id text NOT NULL,
    role text NOT NULL,
    content text NOT NULL,
    ts timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ai_chat_messages_role_check CHECK ((role = ANY (ARRAY['user'::text, 'assistant'::text])))
);

--
-- Name: app_users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.app_users (
    id text NOT NULL,
    email text NOT NULL,
    password_hash text NOT NULL,
    role text NOT NULL,
    locations text[] DEFAULT '{}'::text[] NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT app_users_role_check CHECK ((role = ANY (ARRAY['owner'::text, 'manager'::text, 'staff'::text, 'readonly'::text])))
);

--
-- Name: count_lines; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.count_lines (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    session_id uuid NOT NULL,
    item_code text,
    dish_id uuid,
    prep_item_id uuid,
    status text NOT NULL,
    qty numeric,
    count_unit text,
    note text,
    saved_by text,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT count_lines_qty_check CHECK ((qty >= (0)::numeric)),
    CONSTRAINT count_lines_status_check CHECK ((status = ANY (ARRAY['counted'::text, 'not_counted'::text])))
);

--
-- Name: count_sessions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.count_sessions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    store_id text NOT NULL,
    count_date date NOT NULL,
    count_type text DEFAULT 'nightly_prep'::text NOT NULL,
    counted_by uuid,
    counted_by_name text,
    status text DEFAULT 'open'::text NOT NULL,
    submitted_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT count_sessions_count_type_check CHECK ((count_type = ANY (ARRAY['nightly_prep'::text, 'monthly_high_value'::text, 'full_inventory'::text, 'commissary'::text]))),
    CONSTRAINT count_sessions_status_check CHECK ((status = ANY (ARRAY['open'::text, 'submitted'::text, 'reopened'::text])))
);

--
-- Name: dish_lines; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.dish_lines (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    dish_id uuid NOT NULL,
    source_type text NOT NULL,
    item_code text,
    prep_dish_id uuid,
    qty numeric NOT NULL,
    uom text,
    CONSTRAINT dish_lines_source_type_check CHECK ((source_type = ANY (ARRAY['item'::text, 'prep'::text])))
);

--
-- Name: dishes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.dishes (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    store_id text NOT NULL,
    name text NOT NULL,
    menu_code text,
    recipe_type text DEFAULT 'menu'::text NOT NULL,
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
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    description text,
    photo_url text,
    portion_note text,
    frequency text,
    CONSTRAINT dishes_recipe_type_check CHECK ((recipe_type = ANY (ARRAY['menu'::text, 'prep'::text])))
);

--
-- Name: inventory_count_submissions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.inventory_count_submissions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    store_id text NOT NULL,
    submitted_by text,
    source text DEFAULT 'manager'::text NOT NULL,
    items jsonb DEFAULT '[]'::jsonb NOT NULL,
    submitted_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT inventory_count_submissions_source_check CHECK ((source = ANY (ARRAY['manager'::text, 'staff_pwa'::text])))
);

--
-- Name: invoice_lines; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.invoice_lines (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    invoice_id uuid NOT NULL,
    vendor_item_id uuid,
    description text,
    qty numeric NOT NULL,
    purchase_unit text,
    unit_price numeric(12,4),
    extended numeric(12,2),
    is_credit boolean DEFAULT false NOT NULL
);

--
-- Name: invoices; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.invoices (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    store_id text NOT NULL,
    delivered_to text,
    vendor_id text NOT NULL,
    invoice_number text,
    invoice_date date NOT NULL,
    total numeric(12,2),
    source text,
    source_file text,
    created_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);

--
-- Name: items; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.items (
    code text NOT NULL,
    name text NOT NULL,
    category text,
    base_unit text NOT NULL,
    item_type text DEFAULT 'raw'::text NOT NULL,
    is_high_value boolean DEFAULT false NOT NULL,
    active boolean DEFAULT true NOT NULL,
    notes text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    costing_type text DEFAULT 'portion'::text NOT NULL,
    pack_count numeric,
    unit_qty numeric,
    unit_uom text,
    portion_size numeric,
    portion_uom text,
    CONSTRAINT items_costing_type_check CHECK ((costing_type = ANY (ARRAY['portion'::text, 'usage'::text]))),
    CONSTRAINT items_item_type_check CHECK ((item_type = ANY (ARRAY['raw'::text, 'prep'::text, 'commissary'::text, 'paper'::text, 'chemical'::text, 'other'::text])))
);

--
-- Name: manager_log; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.manager_log (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    store_id text NOT NULL,
    shift_date date NOT NULL,
    shift text,
    author_name text NOT NULL,
    author_id uuid,
    tag text,
    body text NOT NULL,
    urgent boolean DEFAULT false NOT NULL,
    status text DEFAULT 'open'::text NOT NULL,
    outcome text,
    closed_by_name text,
    closed_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT closed_needs_outcome CHECK (((status = 'open'::text) OR (outcome IS NOT NULL))),
    CONSTRAINT manager_log_shift_check CHECK ((shift = ANY (ARRAY['open'::text, 'mid'::text, 'close'::text]))),
    CONSTRAINT manager_log_status_check CHECK ((status = ANY (ARRAY['open'::text, 'closed'::text]))),
    CONSTRAINT manager_log_tag_check CHECK ((tag = ANY (ARRAY['note'::text, 'repair'::text, 'incident'::text, 'guest'::text, '86'::text, 'staff'::text, 'must_do'::text])))
);

--
-- Name: par_recommendations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.par_recommendations (
    id text NOT NULL,
    store_id text NOT NULL,
    recipe_id uuid NOT NULL,
    recipe_name text DEFAULT ''::text NOT NULL,
    current_par numeric,
    recommended_par numeric NOT NULL,
    reasoning text DEFAULT ''::text NOT NULL,
    status text DEFAULT 'pending'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    applied_at timestamp with time zone,
    CONSTRAINT par_recommendations_status_check CHECK ((status = ANY (ARRAY['pending'::text, 'applied'::text, 'dismissed'::text])))
);

--
-- Name: people; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.people (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    full_name text NOT NULL,
    email text,
    phone text,
    auth_user_id uuid,
    pay_type text,
    active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT people_pay_type_check CHECK ((pay_type = ANY (ARRAY['hourly'::text, 'salary'::text, 'owner'::text])))
);

--
-- Name: prep_items; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.prep_items (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    store_id text NOT NULL,
    name text NOT NULL,
    item_code text,
    container text,
    shelf_life_days numeric,
    par_weekday numeric,
    par_weekend numeric,
    is_task boolean DEFAULT false NOT NULL,
    made_at text,
    sort_order integer,
    active boolean DEFAULT true NOT NULL,
    recipe_id uuid,
    vessel_capacity numeric,
    par_vessels numeric,
    schedule text DEFAULT 'daily'::text NOT NULL,
    note text,
    recur_days smallint[],
    fixed_qty numeric,
    CONSTRAINT prep_items_recur_days_range_check CHECK (((recur_days IS NULL) OR (recur_days <@ ARRAY[(0)::smallint, (1)::smallint, (2)::smallint, (3)::smallint, (4)::smallint, (5)::smallint, (6)::smallint]))),
    CONSTRAINT prep_items_recurring_requires_fields_check CHECK (((schedule <> 'recurring'::text) OR ((recur_days IS NOT NULL) AND (cardinality(recur_days) > 0) AND (fixed_qty IS NOT NULL) AND (fixed_qty > (0)::numeric)))),
    CONSTRAINT prep_items_schedule_check CHECK ((schedule = ANY (ARRAY['daily'::text, 'oneoff'::text, 'recurring'::text]))),
    CONSTRAINT prep_items_source_check CHECK ((num_nonnulls(item_code, recipe_id) = 1))
);

--
-- Name: prep_list_lines; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.prep_list_lines (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    list_id uuid NOT NULL,
    prep_item_id uuid,
    recipe_id uuid,
    task_type text DEFAULT 'batch'::text NOT NULL,
    name text,
    yield_uom text,
    yield_qty numeric,
    par numeric,
    on_hand numeric,
    uncounted boolean DEFAULT false NOT NULL,
    needed_units numeric,
    batches_planned numeric,
    batches_done numeric DEFAULT 0 NOT NULL,
    make_qty numeric,
    vessel_name text,
    note text,
    done boolean DEFAULT false NOT NULL,
    done_by_name text,
    done_at timestamp with time zone,
    removed boolean DEFAULT false NOT NULL,
    CONSTRAINT prep_list_lines_task_type_check CHECK ((task_type = ANY (ARRAY['batch'::text, 'task'::text])))
);

--
-- Name: prep_lists; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.prep_lists (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    store_id text NOT NULL,
    prep_date date NOT NULL,
    from_count uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    status text DEFAULT 'draft'::text NOT NULL,
    released_at timestamp with time zone,
    released_by text,
    count_type text,
    CONSTRAINT prep_lists_count_type_check CHECK ((count_type = ANY (ARRAY['nightly_prep'::text, 'monthly_high_value'::text, 'full_inventory'::text, 'commissary'::text]))),
    CONSTRAINT prep_lists_status_check CHECK ((status = ANY (ARRAY['draft'::text, 'released'::text])))
);

--
-- Name: prep_logs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.prep_logs (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    store_id text NOT NULL,
    kind text NOT NULL,
    dish_id uuid,
    prep_item_id uuid,
    name text,
    batches numeric,
    produced numeric,
    yield_uom text,
    usage jsonb DEFAULT '[]'::jsonb NOT NULL,
    containers jsonb DEFAULT '[]'::jsonb NOT NULL,
    total_cost numeric,
    date date,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT prep_logs_kind_check CHECK ((kind = ANY (ARRAY['batch'::text, 'sales_usage'::text, 'container_use'::text])))
);

--
-- Name: prep_overrides; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.prep_overrides (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    store_id text NOT NULL,
    date date NOT NULL,
    type text DEFAULT 'add'::text NOT NULL,
    recipe_id uuid,
    prep_item_id uuid,
    custom_name text,
    par numeric,
    batches numeric,
    note text,
    created_by text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT prep_overrides_type_check CHECK ((type = ANY (ARRAY['add'::text, 'par'::text, 'remove'::text])))
);

--
-- Name: prep_recipe_stock; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.prep_recipe_stock (
    dish_id uuid,
    store_id text NOT NULL,
    on_hand numeric DEFAULT 0 NOT NULL,
    containers jsonb DEFAULT '[]'::jsonb NOT NULL,
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    prep_item_id uuid,
    CONSTRAINT prep_recipe_stock_source_check CHECK ((num_nonnulls(dish_id, prep_item_id) = 1))
);

--
-- Name: purchase_order_lines; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.purchase_order_lines (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    po_id uuid NOT NULL,
    vendor_item_id uuid,
    item_code text,
    description text,
    qty numeric NOT NULL,
    unit text,
    unit_price numeric,
    extended numeric,
    received_qty numeric,
    "position" integer DEFAULT 0 NOT NULL,
    control_number text,
    name text DEFAULT ''::text NOT NULL,
    vendor_sku text DEFAULT ''::text NOT NULL
);

--
-- Name: purchase_orders; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.purchase_orders (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    store_id text NOT NULL,
    vendor_id text,
    status text DEFAULT 'draft'::text NOT NULL,
    created_by text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    approved_by text,
    approved_at timestamp with time zone,
    rejected_reason text,
    sent_at timestamp with time zone,
    received_at timestamp with time zone,
    invoice_id uuid,
    ref text NOT NULL,
    vendor_name text DEFAULT 'Unassigned'::text NOT NULL,
    note text DEFAULT ''::text NOT NULL,
    total numeric(12,2) DEFAULT 0 NOT NULL,
    submitted_at timestamp with time zone,
    receipt_started_at timestamp with time zone,
    invoice_number text,
    receipt_match jsonb,
    emailed_to text,
    emailed_at timestamp with time zone,
    history jsonb DEFAULT '[]'::jsonb NOT NULL,
    CONSTRAINT purchase_orders_status_check CHECK ((status = ANY (ARRAY['draft'::text, 'pending'::text, 'approved'::text, 'sent'::text, 'receiving'::text, 'received'::text, 'rejected'::text])))
);

--
-- Name: push_subscriptions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.push_subscriptions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    store_id text NOT NULL,
    endpoint text NOT NULL,
    keys jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);

--
-- Name: reporting_periods; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.reporting_periods (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    store_id text NOT NULL,
    period_start date NOT NULL,
    period_end date NOT NULL,
    name text,
    status text DEFAULT 'draft'::text NOT NULL,
    dish_sales jsonb DEFAULT '{}'::jsonb NOT NULL,
    item_counts jsonb DEFAULT '{}'::jsonb NOT NULL,
    saved_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    ref text NOT NULL,
    CONSTRAINT reporting_periods_status_check CHECK ((status = ANY (ARRAY['draft'::text, 'closed'::text])))
);

--
-- Name: sales_daily; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sales_daily (
    store_id text NOT NULL,
    business_date date NOT NULL,
    net_sales numeric(12,2),
    forecast_sales numeric(12,2),
    hourly_wages numeric(12,2),
    guests integer,
    source text DEFAULT 'toast'::text NOT NULL,
    loaded_at timestamp with time zone DEFAULT now() NOT NULL
);

--
-- Name: staff_members; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.staff_members (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    store_id text NOT NULL,
    name text NOT NULL,
    role text DEFAULT 'cook'::text NOT NULL,
    active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT staff_members_role_check CHECK ((role = ANY (ARRAY['cook'::text, 'owner_admin'::text])))
);

--
-- Name: staff_pins; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.staff_pins (
    store_id text NOT NULL,
    pin text NOT NULL
);

--
-- Name: staff_tasks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.staff_tasks (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    store_id text NOT NULL,
    task_type text NOT NULL,
    title text NOT NULL,
    due_date date NOT NULL,
    recurrence text DEFAULT 'once'::text NOT NULL,
    assigned_to text,
    track text DEFAULT 'daily'::text NOT NULL,
    note text,
    status text DEFAULT 'pending'::text NOT NULL,
    completed_by text,
    completed_at timestamp with time zone,
    created_by text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT staff_tasks_recurrence_check CHECK ((recurrence = ANY (ARRAY['once'::text, 'daily'::text, 'weekly'::text]))),
    CONSTRAINT staff_tasks_status_check CHECK ((status = ANY (ARRAY['pending'::text, 'done'::text]))),
    CONSTRAINT staff_tasks_task_type_check CHECK ((task_type = ANY (ARRAY['count'::text, 'prep'::text])))
);

--
-- Name: store_items; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.store_items (
    store_id text NOT NULL,
    item_code text NOT NULL,
    count_unit text NOT NULL,
    base_per_count_unit numeric NOT NULL,
    storage_area text,
    counted_nightly boolean DEFAULT false NOT NULL,
    active boolean DEFAULT true NOT NULL,
    current_stock numeric DEFAULT 0 NOT NULL,
    par numeric DEFAULT 0 NOT NULL,
    last_counted date,
    last_counted_by text,
    last_counted_at timestamp with time zone,
    order_enabled boolean DEFAULT true NOT NULL,
    sales_tracked boolean DEFAULT true NOT NULL,
    needs_review boolean DEFAULT false NOT NULL,
    CONSTRAINT store_items_base_per_count_unit_check CHECK ((base_per_count_unit > (0)::numeric))
);

--
-- Name: store_roles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.store_roles (
    person_id uuid NOT NULL,
    store_id text NOT NULL,
    role text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT store_roles_role_check CHECK ((role = ANY (ARRAY['owner'::text, 'gm'::text, 'manager'::text, 'lead'::text, 'staff'::text, 'consultant'::text])))
);

--
-- Name: store_sales_projections; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.store_sales_projections (
    store_id text NOT NULL,
    date date NOT NULL,
    amount numeric(12,2) DEFAULT 0 NOT NULL,
    note text DEFAULT ''::text NOT NULL,
    entered_by text DEFAULT ''::text NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);

--
-- Name: store_state; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.store_state (
    store_id text NOT NULL,
    revision integer DEFAULT 0 NOT NULL,
    areas jsonb,
    sales_period jsonb,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);

--
-- Name: store_vendor_contacts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.store_vendor_contacts (
    store_id text NOT NULL,
    vendor text NOT NULL,
    order_email text DEFAULT ''::text NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);

--
-- Name: stores; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.stores (
    id text NOT NULL,
    name text NOT NULL,
    ownership text,
    uses_commissary boolean DEFAULT false NOT NULL,
    color_primary text,
    color_accent text,
    active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);

--
-- Name: vendor_items; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.vendor_items (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    vendor_id text NOT NULL,
    vendor_sku text NOT NULL,
    vendor_description text,
    item_code text,
    purchase_unit text NOT NULL,
    base_per_purchase_unit numeric,
    pack_verified boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    price numeric,
    price_updated_at timestamp with time zone,
    price_source text,
    preferred boolean DEFAULT false NOT NULL,
    available boolean DEFAULT true NOT NULL,
    pack_count numeric,
    unit_qty numeric,
    unit_uom text,
    CONSTRAINT vendor_items_base_per_purchase_unit_check CHECK ((base_per_purchase_unit > (0)::numeric))
);

--
-- Name: vendors; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.vendors (
    id text NOT NULL,
    name text NOT NULL,
    order_email text,
    rep_name text,
    rep_phone text,
    active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);

--
-- Name: activity_log activity_log_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.activity_log
    ADD CONSTRAINT activity_log_pkey PRIMARY KEY (id);

--
-- Name: adjustments adjustments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.adjustments
    ADD CONSTRAINT adjustments_pkey PRIMARY KEY (id);

--
-- Name: ai_chat_messages ai_chat_messages_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ai_chat_messages
    ADD CONSTRAINT ai_chat_messages_pkey PRIMARY KEY (id);

--
-- Name: app_users app_users_email_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.app_users
    ADD CONSTRAINT app_users_email_key UNIQUE (email);

--
-- Name: app_users app_users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.app_users
    ADD CONSTRAINT app_users_pkey PRIMARY KEY (id);

--
-- Name: count_lines count_lines_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.count_lines
    ADD CONSTRAINT count_lines_pkey PRIMARY KEY (id);

--
-- Name: count_sessions count_sessions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.count_sessions
    ADD CONSTRAINT count_sessions_pkey PRIMARY KEY (id);

--
-- Name: count_sessions count_sessions_store_id_count_date_count_type_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.count_sessions
    ADD CONSTRAINT count_sessions_store_id_count_date_count_type_key UNIQUE (store_id, count_date, count_type);

--
-- Name: dish_lines dish_lines_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dish_lines
    ADD CONSTRAINT dish_lines_pkey PRIMARY KEY (id);

--
-- Name: dishes dishes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dishes
    ADD CONSTRAINT dishes_pkey PRIMARY KEY (id);

--
-- Name: inventory_count_submissions inventory_count_submissions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.inventory_count_submissions
    ADD CONSTRAINT inventory_count_submissions_pkey PRIMARY KEY (id);

--
-- Name: invoice_lines invoice_lines_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.invoice_lines
    ADD CONSTRAINT invoice_lines_pkey PRIMARY KEY (id);

--
-- Name: invoices invoices_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.invoices
    ADD CONSTRAINT invoices_pkey PRIMARY KEY (id);

--
-- Name: invoices invoices_vendor_id_invoice_number_store_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.invoices
    ADD CONSTRAINT invoices_vendor_id_invoice_number_store_id_key UNIQUE (vendor_id, invoice_number, store_id);

--
-- Name: items items_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.items
    ADD CONSTRAINT items_pkey PRIMARY KEY (code);

--
-- Name: manager_log manager_log_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manager_log
    ADD CONSTRAINT manager_log_pkey PRIMARY KEY (id);

--
-- Name: par_recommendations par_recommendations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.par_recommendations
    ADD CONSTRAINT par_recommendations_pkey PRIMARY KEY (id);

--
-- Name: people people_auth_user_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.people
    ADD CONSTRAINT people_auth_user_id_key UNIQUE (auth_user_id);

--
-- Name: people people_email_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.people
    ADD CONSTRAINT people_email_key UNIQUE (email);

--
-- Name: people people_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.people
    ADD CONSTRAINT people_pkey PRIMARY KEY (id);

--
-- Name: prep_items prep_items_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.prep_items
    ADD CONSTRAINT prep_items_pkey PRIMARY KEY (id);

--
-- Name: prep_items prep_items_store_id_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.prep_items
    ADD CONSTRAINT prep_items_store_id_name_key UNIQUE (store_id, name);

--
-- Name: prep_list_lines prep_list_lines_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.prep_list_lines
    ADD CONSTRAINT prep_list_lines_pkey PRIMARY KEY (id);

--
-- Name: prep_lists prep_lists_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.prep_lists
    ADD CONSTRAINT prep_lists_pkey PRIMARY KEY (id);

--
-- Name: prep_lists prep_lists_store_id_prep_date_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.prep_lists
    ADD CONSTRAINT prep_lists_store_id_prep_date_key UNIQUE (store_id, prep_date);

--
-- Name: prep_logs prep_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.prep_logs
    ADD CONSTRAINT prep_logs_pkey PRIMARY KEY (id);

--
-- Name: prep_overrides prep_overrides_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.prep_overrides
    ADD CONSTRAINT prep_overrides_pkey PRIMARY KEY (id);

--
-- Name: prep_recipe_stock prep_recipe_stock_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.prep_recipe_stock
    ADD CONSTRAINT prep_recipe_stock_pkey PRIMARY KEY (id);

--
-- Name: purchase_order_lines purchase_order_lines_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_lines
    ADD CONSTRAINT purchase_order_lines_pkey PRIMARY KEY (id);

--
-- Name: purchase_orders purchase_orders_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_orders
    ADD CONSTRAINT purchase_orders_pkey PRIMARY KEY (id);

--
-- Name: purchase_orders purchase_orders_ref_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_orders
    ADD CONSTRAINT purchase_orders_ref_key UNIQUE (ref);

--
-- Name: push_subscriptions push_subscriptions_endpoint_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.push_subscriptions
    ADD CONSTRAINT push_subscriptions_endpoint_key UNIQUE (endpoint);

--
-- Name: push_subscriptions push_subscriptions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.push_subscriptions
    ADD CONSTRAINT push_subscriptions_pkey PRIMARY KEY (id);

--
-- Name: reporting_periods reporting_periods_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reporting_periods
    ADD CONSTRAINT reporting_periods_pkey PRIMARY KEY (id);

--
-- Name: sales_daily sales_daily_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sales_daily
    ADD CONSTRAINT sales_daily_pkey PRIMARY KEY (store_id, business_date);

--
-- Name: staff_members staff_members_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.staff_members
    ADD CONSTRAINT staff_members_pkey PRIMARY KEY (id);

--
-- Name: staff_pins staff_pins_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.staff_pins
    ADD CONSTRAINT staff_pins_pkey PRIMARY KEY (store_id);

--
-- Name: staff_tasks staff_tasks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.staff_tasks
    ADD CONSTRAINT staff_tasks_pkey PRIMARY KEY (id);

--
-- Name: store_items store_items_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.store_items
    ADD CONSTRAINT store_items_pkey PRIMARY KEY (store_id, item_code);

--
-- Name: store_roles store_roles_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.store_roles
    ADD CONSTRAINT store_roles_pkey PRIMARY KEY (person_id, store_id, role);

--
-- Name: store_sales_projections store_sales_projections_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.store_sales_projections
    ADD CONSTRAINT store_sales_projections_pkey PRIMARY KEY (store_id, date);

--
-- Name: store_state store_state_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.store_state
    ADD CONSTRAINT store_state_pkey PRIMARY KEY (store_id);

--
-- Name: store_vendor_contacts store_vendor_contacts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.store_vendor_contacts
    ADD CONSTRAINT store_vendor_contacts_pkey PRIMARY KEY (store_id, vendor);

--
-- Name: stores stores_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.stores
    ADD CONSTRAINT stores_pkey PRIMARY KEY (id);

--
-- Name: vendor_items vendor_items_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.vendor_items
    ADD CONSTRAINT vendor_items_pkey PRIMARY KEY (id);

--
-- Name: vendor_items vendor_items_vendor_id_vendor_sku_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.vendor_items
    ADD CONSTRAINT vendor_items_vendor_id_vendor_sku_key UNIQUE (vendor_id, vendor_sku);

--
-- Name: vendors vendors_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.vendors
    ADD CONSTRAINT vendors_pkey PRIMARY KEY (id);

--
-- Name: activity_log_created_at_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX activity_log_created_at_idx ON public.activity_log USING btree (created_at DESC);

--
-- Name: adjustments_store_id_date_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX adjustments_store_id_date_idx ON public.adjustments USING btree (store_id, date);

--
-- Name: ai_chat_messages_store_id_ts_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ai_chat_messages_store_id_ts_idx ON public.ai_chat_messages USING btree (store_id, ts);

--
-- Name: count_sessions_store_id_count_date_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX count_sessions_store_id_count_date_idx ON public.count_sessions USING btree (store_id, count_date);

--
-- Name: inventory_count_submissions_store_id_submitted_at_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX inventory_count_submissions_store_id_submitted_at_idx ON public.inventory_count_submissions USING btree (store_id, submitted_at DESC);

--
-- Name: invoice_lines_invoice_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX invoice_lines_invoice_id_idx ON public.invoice_lines USING btree (invoice_id);

--
-- Name: invoices_store_id_invoice_date_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX invoices_store_id_invoice_date_idx ON public.invoices USING btree (store_id, invoice_date);

--
-- Name: manager_log_store_id_status_shift_date_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX manager_log_store_id_status_shift_date_idx ON public.manager_log USING btree (store_id, status, shift_date);

--
-- Name: par_recommendations_store_id_status_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX par_recommendations_store_id_status_idx ON public.par_recommendations USING btree (store_id, status, created_at DESC);

--
-- Name: prep_items_store_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX prep_items_store_id_idx ON public.prep_items USING btree (store_id);

--
-- Name: prep_recipe_stock_dish_store_uq; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX prep_recipe_stock_dish_store_uq ON public.prep_recipe_stock USING btree (store_id, dish_id) WHERE (dish_id IS NOT NULL);

--
-- Name: prep_recipe_stock_prepitem_store_uq; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX prep_recipe_stock_prepitem_store_uq ON public.prep_recipe_stock USING btree (store_id, prep_item_id) WHERE (prep_item_id IS NOT NULL);

--
-- Name: purchase_order_lines_po_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX purchase_order_lines_po_id_idx ON public.purchase_order_lines USING btree (po_id, "position");

--
-- Name: purchase_orders_status_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX purchase_orders_status_idx ON public.purchase_orders USING btree (status);

--
-- Name: purchase_orders_store_id_created_at_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX purchase_orders_store_id_created_at_idx ON public.purchase_orders USING btree (store_id, created_at DESC);

--
-- Name: reporting_periods_store_id_period_start_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX reporting_periods_store_id_period_start_idx ON public.reporting_periods USING btree (store_id, period_start);

--
-- Name: items t_items; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER t_items BEFORE UPDATE ON public.items FOR EACH ROW EXECUTE FUNCTION public.jmax_touch_updated_at();

--
-- Name: people t_people; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER t_people BEFORE UPDATE ON public.people FOR EACH ROW EXECUTE FUNCTION public.jmax_touch_updated_at();

--
-- Name: stores t_stores; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER t_stores BEFORE UPDATE ON public.stores FOR EACH ROW EXECUTE FUNCTION public.jmax_touch_updated_at();

--
-- Name: vendors t_vendors; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER t_vendors BEFORE UPDATE ON public.vendors FOR EACH ROW EXECUTE FUNCTION public.jmax_touch_updated_at();

--
-- Name: vendor_items t_vitems; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER t_vitems BEFORE UPDATE ON public.vendor_items FOR EACH ROW EXECUTE FUNCTION public.jmax_touch_updated_at();

--
-- Name: activity_log activity_log_store_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.activity_log
    ADD CONSTRAINT activity_log_store_id_fkey FOREIGN KEY (store_id) REFERENCES public.stores(id);

--
-- Name: adjustments adjustments_item_code_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.adjustments
    ADD CONSTRAINT adjustments_item_code_fkey FOREIGN KEY (item_code) REFERENCES public.items(code);

--
-- Name: adjustments adjustments_store_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.adjustments
    ADD CONSTRAINT adjustments_store_id_fkey FOREIGN KEY (store_id) REFERENCES public.stores(id);

--
-- Name: ai_chat_messages ai_chat_messages_store_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ai_chat_messages
    ADD CONSTRAINT ai_chat_messages_store_id_fkey FOREIGN KEY (store_id) REFERENCES public.stores(id);

--
-- Name: count_lines count_lines_dish_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.count_lines
    ADD CONSTRAINT count_lines_dish_id_fkey FOREIGN KEY (dish_id) REFERENCES public.dishes(id);

--
-- Name: count_lines count_lines_item_code_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.count_lines
    ADD CONSTRAINT count_lines_item_code_fkey FOREIGN KEY (item_code) REFERENCES public.items(code);

--
-- Name: count_lines count_lines_prep_item_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.count_lines
    ADD CONSTRAINT count_lines_prep_item_id_fkey FOREIGN KEY (prep_item_id) REFERENCES public.prep_items(id);

--
-- Name: count_lines count_lines_session_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.count_lines
    ADD CONSTRAINT count_lines_session_id_fkey FOREIGN KEY (session_id) REFERENCES public.count_sessions(id) ON DELETE CASCADE;

--
-- Name: count_sessions count_sessions_counted_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.count_sessions
    ADD CONSTRAINT count_sessions_counted_by_fkey FOREIGN KEY (counted_by) REFERENCES public.people(id);

--
-- Name: count_sessions count_sessions_store_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.count_sessions
    ADD CONSTRAINT count_sessions_store_id_fkey FOREIGN KEY (store_id) REFERENCES public.stores(id);

--
-- Name: dish_lines dish_lines_dish_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dish_lines
    ADD CONSTRAINT dish_lines_dish_id_fkey FOREIGN KEY (dish_id) REFERENCES public.dishes(id) ON DELETE CASCADE;

--
-- Name: dish_lines dish_lines_item_code_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dish_lines
    ADD CONSTRAINT dish_lines_item_code_fkey FOREIGN KEY (item_code) REFERENCES public.items(code);

--
-- Name: dish_lines dish_lines_prep_dish_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dish_lines
    ADD CONSTRAINT dish_lines_prep_dish_id_fkey FOREIGN KEY (prep_dish_id) REFERENCES public.dishes(id);

--
-- Name: dishes dishes_store_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dishes
    ADD CONSTRAINT dishes_store_id_fkey FOREIGN KEY (store_id) REFERENCES public.stores(id);

--
-- Name: inventory_count_submissions inventory_count_submissions_store_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.inventory_count_submissions
    ADD CONSTRAINT inventory_count_submissions_store_id_fkey FOREIGN KEY (store_id) REFERENCES public.stores(id);

--
-- Name: invoice_lines invoice_lines_invoice_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.invoice_lines
    ADD CONSTRAINT invoice_lines_invoice_id_fkey FOREIGN KEY (invoice_id) REFERENCES public.invoices(id) ON DELETE CASCADE;

--
-- Name: invoice_lines invoice_lines_vendor_item_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.invoice_lines
    ADD CONSTRAINT invoice_lines_vendor_item_id_fkey FOREIGN KEY (vendor_item_id) REFERENCES public.vendor_items(id);

--
-- Name: invoices invoices_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.invoices
    ADD CONSTRAINT invoices_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.people(id);

--
-- Name: invoices invoices_delivered_to_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.invoices
    ADD CONSTRAINT invoices_delivered_to_fkey FOREIGN KEY (delivered_to) REFERENCES public.stores(id);

--
-- Name: invoices invoices_store_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.invoices
    ADD CONSTRAINT invoices_store_id_fkey FOREIGN KEY (store_id) REFERENCES public.stores(id);

--
-- Name: invoices invoices_vendor_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.invoices
    ADD CONSTRAINT invoices_vendor_id_fkey FOREIGN KEY (vendor_id) REFERENCES public.vendors(id);

--
-- Name: manager_log manager_log_author_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manager_log
    ADD CONSTRAINT manager_log_author_id_fkey FOREIGN KEY (author_id) REFERENCES public.people(id);

--
-- Name: manager_log manager_log_store_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manager_log
    ADD CONSTRAINT manager_log_store_id_fkey FOREIGN KEY (store_id) REFERENCES public.stores(id);

--
-- Name: par_recommendations par_recommendations_recipe_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.par_recommendations
    ADD CONSTRAINT par_recommendations_recipe_id_fkey FOREIGN KEY (recipe_id) REFERENCES public.dishes(id) ON DELETE CASCADE;

--
-- Name: par_recommendations par_recommendations_store_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.par_recommendations
    ADD CONSTRAINT par_recommendations_store_id_fkey FOREIGN KEY (store_id) REFERENCES public.stores(id);

--
-- Name: prep_items prep_items_item_code_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.prep_items
    ADD CONSTRAINT prep_items_item_code_fkey FOREIGN KEY (item_code) REFERENCES public.items(code);

--
-- Name: prep_items prep_items_made_at_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.prep_items
    ADD CONSTRAINT prep_items_made_at_fkey FOREIGN KEY (made_at) REFERENCES public.stores(id);

--
-- Name: prep_items prep_items_recipe_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.prep_items
    ADD CONSTRAINT prep_items_recipe_id_fkey FOREIGN KEY (recipe_id) REFERENCES public.dishes(id);

--
-- Name: prep_items prep_items_store_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.prep_items
    ADD CONSTRAINT prep_items_store_id_fkey FOREIGN KEY (store_id) REFERENCES public.stores(id);

--
-- Name: prep_list_lines prep_list_lines_list_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.prep_list_lines
    ADD CONSTRAINT prep_list_lines_list_id_fkey FOREIGN KEY (list_id) REFERENCES public.prep_lists(id) ON DELETE CASCADE;

--
-- Name: prep_list_lines prep_list_lines_prep_item_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.prep_list_lines
    ADD CONSTRAINT prep_list_lines_prep_item_id_fkey FOREIGN KEY (prep_item_id) REFERENCES public.prep_items(id);

--
-- Name: prep_list_lines prep_list_lines_recipe_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.prep_list_lines
    ADD CONSTRAINT prep_list_lines_recipe_id_fkey FOREIGN KEY (recipe_id) REFERENCES public.dishes(id);

--
-- Name: prep_lists prep_lists_from_count_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.prep_lists
    ADD CONSTRAINT prep_lists_from_count_fkey FOREIGN KEY (from_count) REFERENCES public.count_sessions(id);

--
-- Name: prep_lists prep_lists_store_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.prep_lists
    ADD CONSTRAINT prep_lists_store_id_fkey FOREIGN KEY (store_id) REFERENCES public.stores(id);

--
-- Name: prep_logs prep_logs_dish_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.prep_logs
    ADD CONSTRAINT prep_logs_dish_id_fkey FOREIGN KEY (dish_id) REFERENCES public.dishes(id);

--
-- Name: prep_logs prep_logs_prep_item_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.prep_logs
    ADD CONSTRAINT prep_logs_prep_item_id_fkey FOREIGN KEY (prep_item_id) REFERENCES public.prep_items(id);

--
-- Name: prep_logs prep_logs_store_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.prep_logs
    ADD CONSTRAINT prep_logs_store_id_fkey FOREIGN KEY (store_id) REFERENCES public.stores(id);

--
-- Name: prep_overrides prep_overrides_prep_item_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.prep_overrides
    ADD CONSTRAINT prep_overrides_prep_item_id_fkey FOREIGN KEY (prep_item_id) REFERENCES public.prep_items(id);

--
-- Name: prep_overrides prep_overrides_recipe_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.prep_overrides
    ADD CONSTRAINT prep_overrides_recipe_id_fkey FOREIGN KEY (recipe_id) REFERENCES public.dishes(id);

--
-- Name: prep_overrides prep_overrides_store_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.prep_overrides
    ADD CONSTRAINT prep_overrides_store_id_fkey FOREIGN KEY (store_id) REFERENCES public.stores(id);

--
-- Name: prep_recipe_stock prep_recipe_stock_dish_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.prep_recipe_stock
    ADD CONSTRAINT prep_recipe_stock_dish_id_fkey FOREIGN KEY (dish_id) REFERENCES public.dishes(id) ON DELETE CASCADE;

--
-- Name: prep_recipe_stock prep_recipe_stock_prep_item_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.prep_recipe_stock
    ADD CONSTRAINT prep_recipe_stock_prep_item_id_fkey FOREIGN KEY (prep_item_id) REFERENCES public.prep_items(id);

--
-- Name: prep_recipe_stock prep_recipe_stock_store_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.prep_recipe_stock
    ADD CONSTRAINT prep_recipe_stock_store_id_fkey FOREIGN KEY (store_id) REFERENCES public.stores(id);

--
-- Name: purchase_order_lines purchase_order_lines_item_code_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_lines
    ADD CONSTRAINT purchase_order_lines_item_code_fkey FOREIGN KEY (item_code) REFERENCES public.items(code);

--
-- Name: purchase_order_lines purchase_order_lines_po_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_lines
    ADD CONSTRAINT purchase_order_lines_po_id_fkey FOREIGN KEY (po_id) REFERENCES public.purchase_orders(id) ON DELETE CASCADE;

--
-- Name: purchase_order_lines purchase_order_lines_vendor_item_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_lines
    ADD CONSTRAINT purchase_order_lines_vendor_item_id_fkey FOREIGN KEY (vendor_item_id) REFERENCES public.vendor_items(id);

--
-- Name: purchase_orders purchase_orders_invoice_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_orders
    ADD CONSTRAINT purchase_orders_invoice_id_fkey FOREIGN KEY (invoice_id) REFERENCES public.invoices(id);

--
-- Name: purchase_orders purchase_orders_store_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_orders
    ADD CONSTRAINT purchase_orders_store_id_fkey FOREIGN KEY (store_id) REFERENCES public.stores(id);

--
-- Name: purchase_orders purchase_orders_vendor_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_orders
    ADD CONSTRAINT purchase_orders_vendor_id_fkey FOREIGN KEY (vendor_id) REFERENCES public.vendors(id);

--
-- Name: push_subscriptions push_subscriptions_store_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.push_subscriptions
    ADD CONSTRAINT push_subscriptions_store_id_fkey FOREIGN KEY (store_id) REFERENCES public.stores(id);

--
-- Name: reporting_periods reporting_periods_store_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reporting_periods
    ADD CONSTRAINT reporting_periods_store_id_fkey FOREIGN KEY (store_id) REFERENCES public.stores(id);

--
-- Name: sales_daily sales_daily_store_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sales_daily
    ADD CONSTRAINT sales_daily_store_id_fkey FOREIGN KEY (store_id) REFERENCES public.stores(id);

--
-- Name: staff_members staff_members_store_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.staff_members
    ADD CONSTRAINT staff_members_store_id_fkey FOREIGN KEY (store_id) REFERENCES public.stores(id);

--
-- Name: staff_pins staff_pins_store_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.staff_pins
    ADD CONSTRAINT staff_pins_store_id_fkey FOREIGN KEY (store_id) REFERENCES public.stores(id);

--
-- Name: staff_tasks staff_tasks_store_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.staff_tasks
    ADD CONSTRAINT staff_tasks_store_id_fkey FOREIGN KEY (store_id) REFERENCES public.stores(id);

--
-- Name: store_items store_items_item_code_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.store_items
    ADD CONSTRAINT store_items_item_code_fkey FOREIGN KEY (item_code) REFERENCES public.items(code);

--
-- Name: store_items store_items_store_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.store_items
    ADD CONSTRAINT store_items_store_id_fkey FOREIGN KEY (store_id) REFERENCES public.stores(id);

--
-- Name: store_roles store_roles_person_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.store_roles
    ADD CONSTRAINT store_roles_person_id_fkey FOREIGN KEY (person_id) REFERENCES public.people(id);

--
-- Name: store_roles store_roles_store_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.store_roles
    ADD CONSTRAINT store_roles_store_id_fkey FOREIGN KEY (store_id) REFERENCES public.stores(id);

--
-- Name: store_sales_projections store_sales_projections_store_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.store_sales_projections
    ADD CONSTRAINT store_sales_projections_store_id_fkey FOREIGN KEY (store_id) REFERENCES public.stores(id);

--
-- Name: store_state store_state_store_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.store_state
    ADD CONSTRAINT store_state_store_id_fkey FOREIGN KEY (store_id) REFERENCES public.stores(id);

--
-- Name: store_vendor_contacts store_vendor_contacts_store_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.store_vendor_contacts
    ADD CONSTRAINT store_vendor_contacts_store_id_fkey FOREIGN KEY (store_id) REFERENCES public.stores(id);

--
-- Name: vendor_items vendor_items_item_code_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.vendor_items
    ADD CONSTRAINT vendor_items_item_code_fkey FOREIGN KEY (item_code) REFERENCES public.items(code);

--
-- Name: vendor_items vendor_items_vendor_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.vendor_items
    ADD CONSTRAINT vendor_items_vendor_id_fkey FOREIGN KEY (vendor_id) REFERENCES public.vendors(id);

--
-- Name: activity_log; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.activity_log ENABLE ROW LEVEL SECURITY;

--
-- Name: adjustments; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.adjustments ENABLE ROW LEVEL SECURITY;

--
-- Name: ai_chat_messages; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.ai_chat_messages ENABLE ROW LEVEL SECURITY;

--
-- Name: app_users; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.app_users ENABLE ROW LEVEL SECURITY;

--
-- Name: count_lines; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.count_lines ENABLE ROW LEVEL SECURITY;

--
-- Name: count_sessions; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.count_sessions ENABLE ROW LEVEL SECURITY;

--
-- Name: dish_lines; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.dish_lines ENABLE ROW LEVEL SECURITY;

--
-- Name: dishes; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.dishes ENABLE ROW LEVEL SECURITY;

--
-- Name: inventory_count_submissions; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.inventory_count_submissions ENABLE ROW LEVEL SECURITY;

--
-- Name: invoice_lines; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.invoice_lines ENABLE ROW LEVEL SECURITY;

--
-- Name: invoices; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.invoices ENABLE ROW LEVEL SECURITY;

--
-- Name: items; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.items ENABLE ROW LEVEL SECURITY;

--
-- Name: manager_log; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.manager_log ENABLE ROW LEVEL SECURITY;

--
-- Name: par_recommendations; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.par_recommendations ENABLE ROW LEVEL SECURITY;

--
-- Name: people; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.people ENABLE ROW LEVEL SECURITY;

--
-- Name: prep_items; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.prep_items ENABLE ROW LEVEL SECURITY;

--
-- Name: prep_list_lines; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.prep_list_lines ENABLE ROW LEVEL SECURITY;

--
-- Name: prep_lists; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.prep_lists ENABLE ROW LEVEL SECURITY;

--
-- Name: prep_logs; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.prep_logs ENABLE ROW LEVEL SECURITY;

--
-- Name: prep_overrides; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.prep_overrides ENABLE ROW LEVEL SECURITY;

--
-- Name: prep_recipe_stock; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.prep_recipe_stock ENABLE ROW LEVEL SECURITY;

--
-- Name: purchase_order_lines; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.purchase_order_lines ENABLE ROW LEVEL SECURITY;

--
-- Name: purchase_orders; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.purchase_orders ENABLE ROW LEVEL SECURITY;

--
-- Name: push_subscriptions; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.push_subscriptions ENABLE ROW LEVEL SECURITY;

--
-- Name: reporting_periods; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.reporting_periods ENABLE ROW LEVEL SECURITY;

--
-- Name: sales_daily; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.sales_daily ENABLE ROW LEVEL SECURITY;

--
-- Name: staff_members; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.staff_members ENABLE ROW LEVEL SECURITY;

--
-- Name: staff_pins; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.staff_pins ENABLE ROW LEVEL SECURITY;

--
-- Name: staff_tasks; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.staff_tasks ENABLE ROW LEVEL SECURITY;

--
-- Name: store_items; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.store_items ENABLE ROW LEVEL SECURITY;

--
-- Name: store_roles; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.store_roles ENABLE ROW LEVEL SECURITY;

--
-- Name: store_sales_projections; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.store_sales_projections ENABLE ROW LEVEL SECURITY;

--
-- Name: store_state; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.store_state ENABLE ROW LEVEL SECURITY;

--
-- Name: store_vendor_contacts; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.store_vendor_contacts ENABLE ROW LEVEL SECURITY;

--
-- Name: stores; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.stores ENABLE ROW LEVEL SECURITY;

--
-- Name: vendor_items; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.vendor_items ENABLE ROW LEVEL SECURITY;

--
-- Name: vendors; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.vendors ENABLE ROW LEVEL SECURITY;

--
-- PostgreSQL database dump complete
--
