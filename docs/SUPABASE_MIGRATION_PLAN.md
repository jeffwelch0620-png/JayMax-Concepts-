# MongoDB → Supabase (Postgres) Migration Plan

Status: **step 2 in progress, step 3 scoped** — schema and real data done for
Vendors/Items/Invoices; step 3 (Prep) is scoped below but not built yet.
`server.py`'s existing `/api/...` routes still run entirely on MongoDB and are
untouched — nothing has cut over yet. This doc is the reference for that work as it
continues across sessions.

## Applied migrations (step 1 — schema only)

Run via the Supabase MCP `apply_migration` tool against project `yrlhwcoirgqmtlvvnzvo`,
each tracked and independently reviewable:

1. `inventory_balance_and_pricing` — `store_items` gains `current_stock`, `par`,
   `last_counted`, `last_counted_by`, `last_counted_at`; `vendor_items` gains `price`,
   `price_updated_at`, `price_source`, `preferred`, `available`.
2. `purchase_orders` — `purchase_orders`, `purchase_order_lines`.
3. `adjustments_and_reporting` — `adjustments`, `reporting_periods`.
4. `menu_and_recipes` — `dishes`, `dish_lines`.
5. `prep_extras` — `prep_recipe_stock`, `prep_logs`, `prep_overrides`.
6. `staff_pin_portal` — `staff_members`, `staff_pins`.
7. `staff_tasks_and_push` — `staff_tasks`, `push_subscriptions`.
8. `ai_and_activity` — `ai_chat_messages`, `activity_log`.

All new tables have RLS enabled with no policies yet, matching the 16 tables that
already existed — consistent with the "backend connects via service role, RLS
deferred" decision below. Verified via `list_tables`: 30 tables total in `public`,
`stores` still has its original 4 rows untouched.

## Step 2 progress — Vendors / Items / Invoices

**Backend code** (`backend/db_pg.py`, new `/api/pg/*` routes in `server.py`): done,
committed. Connection fails open — if Postgres is unreachable (e.g. `DATABASE_URL`'s
password placeholder isn't filled in), the app still boots and every existing
Mongo-backed route keeps working; only `/api/pg/*` 503s. Verified locally: server
starts clean, `/api/health` still 200, `/api/pg/vendors` 503s cleanly rather than
crashing, full pytest suite unchanged.

**Real data migrated** (via `scripts/migrate_items_and_invoices.py`, applied through
the Supabase MCP connection — doesn't need `DATABASE_URL`): 20 items, 20 store_items,
22 vendor_items, 9 invoices, 16 invoice_lines. Verified: `sum(invoice_lines.extended)`
equals `sum(invoices.total)` exactly ($1,607.98), confirming no lines were dropped or
double-counted.

Two real judgment calls made during this transform, worth knowing about:

- **`items.code` is generated as `{mongoRestaurantId}_{controlNumber}`** (e.g.
  `berts_WI-001`), not the bare `controlNumber`. Mongo's `controlNumber` is only
  unique *within* a restaurant — the same code ("WI-001") refers to three completely
  different real products across the three restaurants in the current data. This
  migration treats every (restaurant, controlNumber) pair as its own item rather than
  guessing which items are "actually the same product" across locations.
  **Recognizing genuine cross-location duplicates and consolidating them is a real
  data-quality decision for later, not something this pass did.**
- **One purchase (`INV-100902`, Paper Napkins at berts) was recorded against a
  different vendor (US Foods) than the item's only known SKU (Webstaurant)** — a real
  inconsistency already present in the source Mongo data, not introduced by the
  transform. Preserved as-recorded: a second `vendor_items` row was added
  (`us_foods`/`berts_OF-001`, marked non-preferred, no real SKU number on file) rather
  than silently reassigning that purchase to Webstaurant.

**Not done yet**:
- Local end-to-end verification of the `/api/pg/*` endpoints (blocked on the real
  `DATABASE_URL` password).
- Frontend wiring (Invoice Master / Item Setup / Vendors still read/write the
  Mongo-backed `/api/state/{rid}` and `/api/vendor-contacts/{rid}`).

## Step 3 scope — Prep (not built yet)

Mongo source collections: `dishes` (13 docs — both menu items and prep recipes,
distinguished by `recipeType`), `prep_count_sessions` (7), `prep_lists` (5),
`prep_logs` (24), `prep_overrides` (5), `prep_stock` (1). No `prep_items` Mongo
collection exists at all — the Daily/Bulk "standing Prep Item" catalog feature is
built in the app's code but nobody has ever actually created one in this database, so
there's zero data to migrate for it, only behavior to support going forward.

### Mapping

| Mongo | Postgres | Notes |
|---|---|---|
| `dishes` (recipeType=menu/prep) | `dishes` + `dish_lines` | Same restaurant-scoped `controlNumber` problem as Items — recipe lines reference item control numbers, need the same `{restaurant}_{controlNumber}` remap. Prep-sourced lines (`sourceType: "prep"`) map to `dish_lines.prep_dish_id`. |
| `prep_count_sessions` | `count_sessions` + `count_lines` | **Good native fit** — `count_sessions.count_type` already has `'nightly_prep'` and `'commissary'` values in its check constraint, which line up exactly with today's Daily/Bulk evening-count split. No `track` column needed; the type *is* the track. |
| `prep_lists` (+ embedded `tasks[]`) | `prep_lists` + `prep_list_lines` | Existing `prep_list_lines` doesn't carry everything a Mongo task does (`yieldQty`, `neededUnits`, `uncounted`, `vesselName`) — needs a few more columns, or those get derived at read-time instead of stored. |
| `prep_stock` | `prep_recipe_stock` (added in step 1) | Direct fit. |
| `prep_logs` | `prep_logs` (added in step 1) | Direct fit — `usage[]`/`containers[]` map straight onto the existing `jsonb` columns. |
| `prep_overrides` | `prep_overrides` (added in step 1) | Needs `custom_name`, `type` (add/remove?), `batches` columns added — the version from step 1 only sketched name/qty. |
| *(nothing — feature unused)* | `prep_items` (already existed, part of the original 16) | **Schema gap**: only has `item_code`, no way to reference a *recipe*-sourced prep item (today's app supports both `sourceType: "item"` and `sourceType: "prep"`). Needs a nullable `recipe_id uuid REFERENCES dishes(id)` added alongside `item_code`. |

### Decisions (confirmed)

1. **`prep_items.made_at`**: faithful port of today's behavior — `store_id = made_at`
   for daily items, `made_at = 'comm'` for bulk items. The extra cross-store
   flexibility the column technically allows is not used in this pass.
2. **`prep_overrides.type`**: `CHECK (type IN ('add', 'remove'))` — both are real,
   confirmed values.

### Applied — schema extensions (migration `prep_schema_extensions`)

All three of `prep_items`, `prep_list_lines`, `prep_overrides` were empty (verified
before altering), so `prep_list_lines`/`prep_overrides` were dropped and recreated
rather than patched with ALTERs — cleaner than accumulating ALTER statements for
tables with no data and no dependents yet:

- **`prep_items`**: added `recipe_id uuid REFERENCES dishes(id)`, plus
  `CHECK (num_nonnulls(item_code, recipe_id) = 1)` — a prep item is sourced from
  exactly one of an inventory item or a recipe, never both, never neither.
- **`prep_list_lines`**: rebuilt with a surrogate `id` primary key (the old
  `(list_id, prep_item_id)` composite couldn't hold once a task might have no
  `prep_item_id` — recipe-direct or freeform override-added tasks). Added
  `recipe_id`, `task_type`, `name`, `yield_uom`, `yield_qty`, `uncounted`,
  `needed_units`, `batches_planned`, `batches_done`, `vessel_name`, `note`, `removed`
  — matching the real Mongo task shape.
- **`prep_overrides`**: rebuilt with `type` (add/remove, constrained), `custom_name`,
  `par`, `batches`, `note`, `created_by` replacing the step-1 sketch's `name`/`qty`.

Also found while transforming the real data: `dishes` was missing `description`,
`photo_url`, `portion_note`, `frequency` — real fields the current app uses on every
menu item / prep recipe. Added via migration `dishes_missing_columns`.

### Applied — dishes + dish_lines data (via `scripts/migrate_dishes.py`)

13 dishes (8 menu, 5 prep) + 29 dish_lines (22 item-sourced, 7 prep-sourced) migrated
and verified — 0 unresolved references (every `item_code`/`prep_dish_id` FK resolved
cleanly). Recipe-to-recipe references (`sourceType: "prep"` lines, e.g. a pizza
recipe pointing at its dough-batch prep recipe) were resolved by looking the target
dish up by `(store_id, name)` after insertion — names are unique within each
restaurant in the current data, so this needed no fabricated ids.

**Next**: `prep_stock` → `prep_recipe_stock` and `prep_logs` (direct fits, small — 1
and 24 rows), then the harder pieces: `prep_count_sessions` →
`count_sessions`/`count_lines` and `prep_lists`+tasks → `prep_lists`/`prep_list_lines`.

Verified via `information_schema.columns` — all three tables match this shape
exactly.

### Suggested build order within step 3

1. Extend schema: `prep_items` gets `recipe_id`; `prep_list_lines` gets the missing task
   fields; `prep_overrides` gets its real columns (superseding the step-1 sketch).
2. Migrate `dishes` (both menu and prep recipes) + `dish_lines` — needed first since
   everything else in Prep references a recipe.
3. Migrate `prep_stock` → `prep_recipe_stock`, `prep_logs` (direct fits).
4. Migrate `prep_count_sessions` → `count_sessions`/`count_lines`,
   `prep_lists`+tasks → `prep_lists`/`prep_list_lines`, `prep_overrides`.
5. Backend endpoints under `/api/pg/`: recipes/dishes CRUD (Menu Costing), Prep Items
   catalog CRUD, Evening Count session flow, Prep List generate/release/complete-task,
   prep stock deduction on task completion, prep logs, prep overrides.

## Decisions made so far

- **Target project**: `jaymaxcorp@gmail.com's Project` (ref `yrlhwcoirgqmtlvvnzvo`), org
  `flijkjpzkmphymcistku`. Connection details in `backend/.env` (`SUPABASE_URL`,
  `SUPABASE_ANON_KEY`, `DATABASE_URL` — the real DB password was added directly to
  `.env` by the user, never typed into chat).
- **A hand-designed schema already exists** in that project (16 tables: `stores`,
  `people`, `store_roles`, `vendors`, `items`, `store_items`, `vendor_items`,
  `invoices`, `invoice_lines`, `count_sessions`, `count_lines`, `prep_items`,
  `prep_lists`, `prep_list_lines`, `manager_log`, `sales_daily`), RLS enabled on all of
  them with **no policies written yet**, and `stores` already seeded with the real 4
  locations (including a business fact not present anywhere in the current app: each
  store's ownership split, and the commissary modeled as its own store `comm` rather
  than a `track` field). **This is the target schema — build around it, don't replace
  it.**
- **Auth**: adopt real Supabase Auth (`people.auth_user_id` → `auth.users`), replacing
  the current hand-rolled PBKDF2/HMAC session-token system entirely.
- **`manager_log`**: schema only for now. The table gets created (it's part of the
  existing design) but the feature itself is not built in this pass — a separate
  follow-up project once the migration is stable.
- **Scope**: extend the existing schema with whatever tables are needed so nothing
  currently working is lost — Menu Costing, Purchase Orders, running stock balance,
  Waste/Adjustments, vendor pricing, Reporting Periods/COGS, the Staff PIN portal +
  roster, employee tasks/push notifications, AI chat history, and the activity log all
  need a home. See "New tables to add" below.
- **RLS**: tables are RLS-enabled with zero policies (fully locked down to the
  anon/authenticated keys right now). Per the standing "keep security simple until
  fully deployed" preference from earlier in this project, the backend will connect
  with the Postgres **service role** (bypasses RLS) and keep deciding authorization in
  FastAPI, same as today's `collaboration_security` middleware. Writing real RLS
  policies is a deferred hardening step, not part of this migration.
- **Data safety before this started**: full MongoDB export
  (`python scripts/export_mongo_backup.py`) → `backups/2026-09-29_133440_pre-supabase-migration/`
  (gitignored). Code snapshot: git tag `pre-supabase-migration` on `main`, migration
  work happens on the `supabase-migration` branch.

## Existing schema (already in Supabase, not yet altered)

`stores`, `people`, `store_roles`, `vendors`, `items`, `store_items`, `vendor_items`,
`invoices`, `invoice_lines`, `count_sessions`, `count_lines`, `prep_items`,
`prep_lists`, `prep_list_lines`, `manager_log`, `sales_daily`.

Full column/FK detail is in the live project — use the Supabase MCP tools
(`list_tables` with `verbose: true`) to re-fetch it rather than trusting this doc to
stay in sync, since the schema may evolve during the migration itself.

Two structural differences from the current MongoDB shape worth calling out
explicitly, since they change behavior, not just storage:

1. **Item identity is split three ways.** Today, Mongo's `items` collection is one
   flat per-restaurant document holding identity (name, category), per-store tracking
   config (par, currentStock, storageArea), and an embedded `vendorSkus[]` array all
   together. The new schema splits this into `items` (global catalog, keyed by
   `code`), `store_items` (per-store tracking config), and `vendor_items` (per-vendor
   SKU/pack info) — a real normalization, not just a rename.
2. **No running stock balance exists yet.** The current app maintains a live
   `currentStock` per item, continuously deducted by purchases/prep completion/waste
   and corrected by physical counts. The existing `store_items`/`count_lines` design
   only has point-in-time count snapshots — nothing computes or stores a running
   balance. This needs to be added (see below) rather than assumed away, since
   Dashboard's Live Inventory Value, Next Order Exposure, and the prep-deduction flow
   all depend on a real-time balance, not just the last count.

## New tables to add

Sketched here at the column level for planning; exact types/constraints get finalized
when each is actually created (via `apply_migration`, tracked as a proper Postgres
migration, not ad-hoc `execute_sql`).

- **`store_items` gets new columns** (not a new table): `current_stock numeric`,
  `par numeric`, `last_counted date`, `last_counted_by text`, `last_counted_at
  timestamptz`. This is the running balance the current app relies on everywhere.
- **`vendor_items` gets new columns**: `price numeric`, `price_updated_at
  timestamptz`, `price_source text`, `preferred boolean default false`, `available
  boolean default true`. Price *history* comes from `invoice_lines.unit_price` over
  time (already dated), matching today's "two-purchase price change" logic — no
  separate price-history table needed.
- **`purchase_orders`**: `id uuid pk`, `store_id fk`, `vendor_id fk`, `status text
  check(draft/pending/approved/sent/received/rejected)`, `created_by text`,
  `created_at`, `approved_by text`, `approved_at`, `rejected_reason text`, `sent_at`,
  `invoice_id fk→invoices nullable` (set once a PO is received and turned into an
  invoice).
- **`purchase_order_lines`**: `id uuid pk`, `po_id fk`, `vendor_item_id fk nullable`,
  `item_code fk nullable`, `description text`, `qty numeric`, `unit text`,
  `unit_price numeric`, `extended numeric`, `received_qty numeric nullable`.
- **`adjustments`**: `id uuid pk`, `store_id fk`, `item_code fk`, `date date`,
  `reason text`, `qty numeric`, `direction text check(add/remove)`, `note text`,
  `created_by text`, `created_at`.
- **`reporting_periods`**: `id uuid pk`, `store_id fk`, `period_start date`,
  `period_end date`, `name text`, `status text check(draft/closed)`, `dish_sales
  jsonb`, `item_counts jsonb`, `saved_at timestamptz`. Kept as jsonb rather than fully
  normalized for the first pass — mirrors the current Mongo shape closely and is fast
  to build against; revisit if reporting queries end up needing to filter inside those
  blobs often.
- **`dishes`** (menu items + prep recipes, currently one Mongo collection distinguished
  by `recipeType`): `id uuid pk`, `store_id fk`, `name text`, `menu_code text`,
  `recipe_type text check(menu/prep)`, `price numeric`, `target_pct numeric`,
  `yield_qty numeric`, `yield_uom text`, `prep_par numeric`, `procedure text`,
  `equipment text`, `shelf_life text`, `menu_category text`, `sort_order int`.
- **`dish_lines`** (recipe ingredients): `id uuid pk`, `dish_id fk`, `source_type text
  check(item/prep)`, `item_code fk nullable`, `prep_dish_id fk nullable→dishes.id`,
  `qty numeric`, `uom text`.
- **`prep_recipe_stock`**: `dish_id fk`, `store_id fk`, `on_hand numeric`,
  `containers jsonb`, PK `(dish_id, store_id)`.
- **`prep_logs`**: `id uuid pk`, `store_id fk`, `kind text check(batch/sales_usage)`,
  `dish_id fk nullable`, `prep_item_id fk nullable→prep_items`, `name text`, `batches
  numeric`, `produced numeric`, `yield_uom text`, `usage jsonb`, `containers jsonb`,
  `total_cost numeric`, `date date`, `created_at`.
- **`prep_overrides`**: `id uuid pk`, `store_id fk`, `date date`, plus the one-off
  prep-list-addition fields from the current collection.
- **Staff PIN portal** (what the "Staff" tab / StaffSheet PWA use, distinct from
  `people`/`store_roles` which model full accounts):
  - **`staff_members`**: `id uuid pk`, `store_id fk`, `name text`, `role text
    check(cook/owner_admin)`, `active bool`, `created_at`.
  - **`staff_pins`**: `store_id fk pk`, `pin text`.
- **`staff_tasks`**: `id uuid pk`, `store_id fk`, `task_type text check(count/prep)`,
  `title text`, `due_date date`, `recurrence text`, `assigned_to text`, `track text`,
  `note text`, `status text`, `completed_by text`, `completed_at`, `created_by text`,
  `created_at`.
- **`push_subscriptions`**: `id uuid pk`, `store_id fk`, `endpoint text unique`, `keys
  jsonb`, `created_at`.
- **`ai_chat_messages`**: `id uuid pk`, `store_id fk`, `role text
  check(user/assistant)`, `content text`, `ts timestamptz`.
- **`activity_log`**: `id uuid pk`, `store_id fk nullable`, `user_email text`, `role
  text`, `method text`, `path text`, `status int`, `created_at`.
- **`inventory_count_submissions`**: already effectively covered by
  `count_sessions`/`count_lines` (which are more normalized than the Mongo version) —
  no new table needed, just map onto those instead of porting the Mongo shape as-is.

## Auth migration

- Move from custom `AUTH_SECRET`/PBKDF2/HMAC tokens to Supabase Auth. `people.auth_user_id`
  links a `people` row to a real `auth.users` row.
- Owner/manager/staff/readonly roles move from `people`/`store_roles` (`role text
  check(owner/gm/manager/lead/staff/consultant)` — note this role set is different
  from today's `owner/manager/staff/readonly` and needs a mapping decision).
- The Staff PIN portal (shared PIN, no account) stays outside Supabase Auth by design
  — it's meant to be account-free. The "Owner/Admin identified via PIN" elevation
  (mints a real session today) would need to mint a real Supabase session instead of
  the current custom HMAC token — needs Supabase's admin API (service role) to do this
  server-side.
- Bootstrap flow (`/api/auth/bootstrap`, one-time token to create the first owner)
  needs a Supabase-Auth-native equivalent.

## Backend approach

- Keep FastAPI. Replace Motor (`AsyncIOMotorClient`) calls with a Postgres driver —
  likely `asyncpg` directly or SQLAlchemy's async engine, connecting via
  `DATABASE_URL` with the **service role** (bypasses RLS; authorization stays decided
  in Python, matching today's middleware).
- This is a full rewrite of the data-access code in `server.py`, not a thin adapter —
  every endpoint currently does schemaless Mongo document reads/writes and needs real
  SQL (joins, foreign keys, transactions where multiple tables change together, e.g.
  receiving a PO touching `purchase_orders`, `invoices`, `invoice_lines`, and
  `store_items.current_stock` all at once).
- Recommend migrating one feature area at a time (e.g., Vendors/Items/Invoices first,
  since that's what the existing schema already covers most completely) rather than
  attempting the whole backend in one pass — each area can be built, tested, and
  verified against the live Supabase project independently.

## Data migration mechanics

1. Source: the JSON export in `backups/<timestamp>_pre-supabase-migration/` (one file
   per Mongo collection, `bson.json_util` format).
2. A transform script per collection maps Mongo documents to the new relational shape
   (e.g. `items` Mongo docs split across `items`/`store_items`/`vendor_items` rows).
3. Insert via the Supabase MCP tools or a Python script using the service-role
   connection — not by hand.
4. Re-run `scripts/export_mongo_backup.py` immediately before the real cutover (not
   just once now) so the migrated data reflects the actual state at cutover time, not
   whatever existed when planning started.

## Suggested order of work

1. Apply the new-table migrations above (via `apply_migration`, one migration file per
   logical group — e.g. inventory balance + PO tables together, prep/menu tables
   together, staff/PIN tables together).
2. Migrate Vendors → Items → Invoices (the best-covered area) first: backend
   endpoints, data transform, verify against a live restaurant's real purchase
   history.
3. Migrate Prep (recipes, prep items, prep lists, prep stock, prep logs).
4. Migrate Counts (nightly + the Count History feature) onto `count_sessions`/`count_lines`.
5. Migrate Purchase Orders, Adjustments, Reporting Periods/Dashboard COGS.
6. Migrate Staff (accounts via Supabase Auth + `people`/`store_roles`; PIN portal via
   `staff_members`/`staff_pins`).
7. Migrate Employee tasks/push notifications, AI chat history, activity log.
8. Auth cutover (bootstrap flow, login, session handling) — likely needs to happen
   alongside step 6, not strictly after everything else, since most endpoints depend
   on auth working.
9. Frontend: swap `frontend/src/lib/api.js` calls as each backend area moves, not all
   at once — the app can run against a mix of "already migrated" and "still Mongo"
   endpoints during the transition if the branch stays deployable throughout.
