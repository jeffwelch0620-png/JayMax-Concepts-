# MongoDB → Supabase (Postgres) Migration Plan

Status: **all 6 chunks done and live-verified**. All real MongoDB data is in Supabase,
`/api/pg/*` has full backend coverage for Vendors/Items/Invoices/Dishes/Prep/Staff, and
the frontend (`frontend/src/lib/api.js`) routes through it end-to-end via
`REACT_APP_USE_PG`/`USE_PG` (both currently `false` — off by default). Chunk 6 connected
to the real Supabase database (via the Supavisor pooler, see the note below), found and
fixed a real asyncpg date-encoding bug, and verified every area works correctly live in
the browser against real migrated data. `server.py`'s existing `/api/...` routes still
run entirely on MongoDB and are untouched — nothing has cut over for real users yet;
flipping both `USE_PG` flags to `true` is what a real cutover would look like. This doc
is the reference for that work as
it continues across sessions.

## Frontend wiring plan

The two backend areas have genuinely different API shapes on the frontend today,
which is what actually determines how this splits into chunks — not the backend's
Vendors/Items/Invoices vs. Prep split:

- **Prep is already granular.** `lib/api.js`'s prep functions
  (`getCountSession`, `saveCountEntry`, `generatePrepList`, `completeTask`,
  `listPrepItems`, etc.) each call one specific action endpoint, and the new
  `/api/pg/prepcount`/`/api/pg/preplists`/`/api/pg/prep-items`/`/api/pg/prep-overrides`
  endpoints were deliberately built to return the same field shapes. Wiring this is
  mostly swapping which base path these functions hit, component code barely changes.
- **Items/Purchases/Invoices/Vendors are not.** They all flow through one generic
  blob: `fetchState(rid)` returns `{items, purchases, dishes, adjustments, prepStock,
  prepLogs, salesPeriod, areas, reportingPeriods}` in one call, and `putCollection`
  replaces an entire array at once. The new endpoints are proper granular REST
  (`GET/POST /api/pg/items/{store}`, `GET/POST /api/pg/invoices/{store}`, etc.). There
  is no direct swap here — something has to reshape one into the other.

Chunks, in order:

1. **API client additions** (`lib/api.js`) — add every new `/api/pg/*` call as its own
   function, no component changes yet. Safe, mechanical, needed regardless of what
   comes after. ✅ Done — ~26 `pg*`-prefixed functions added, dev server compiled clean.
2. **Prep frontend wiring** — ✅ Done, gated behind a flag. `DATABASE_URL` still has a
   placeholder password, so `/api/pg/*` 503s locally — cutting `PrepTab.js` straight
   over to `pg*` calls would have broken the live Prep tab until that password lands.
   Instead, the *existing* exported function names in `lib/api.js`
   (`getCountSession`, `saveCountEntry`, `submitCount`, `countHistory`, `getPrepList`,
   `generatePrepList`, `updatePrepList`, `releasePrepList`, `completeTask`,
   `addItemToList`, `listPrepItems`, `createPrepItem`, `updatePrepItem`,
   `deletePrepItem`, `listOverrides`, `addOverride`, `deleteOverride`,
   `applyPrepSales`, `useContainer`) now dispatch to either the Mongo route or the
   matching `pg*` function based on `const USE_PG = process.env.REACT_APP_USE_PG ===
   "true"` — default `false`, so nothing changes for the running app today.
   `PrepTab.js` itself was **not touched** — it still calls plain `api.getCountSession`
   etc., unaware of the flag. When `USE_PG` is on, `pgStoreId(rid)` remaps the
   Mongo-side restaurant id to the Postgres store id (`papa_leonis` → `papa`; `berts`/
   `rudds` unchanged) before calling the `pg*` function. `prepReport`,
   `getProjections`/`putProjection`, `getStaffPin`/`verifyStaffPin`, and
   `getParRecs`/`applyParRec`/`dismissParRec` (Planning tab's projections, PIN, AI par
   advisor, and the Inventory Log's date-range report) have **no pg backend yet** and
   are untouched — they stay on Mongo regardless of the flag until that backend work
   happens. To exercise the pg path once `DATABASE_URL` is real: set
   `REACT_APP_USE_PG=true` in `frontend/.env` and restart the dev server.
3. **State-blob adapter for Items/Purchases/Invoices/Vendors** — ✅ Done, also gated
   behind `USE_PG`.
   - **Schema gap found and fixed first**: the frontend's `itemDerived()` (`calc.js`)
     computes `portionsPerUnit`/`costPerPortion` from an item's `packCount`/`unitQty`/
     `unitUOM`/`portionSize`/`portionUOM` (and per-vendor-SKU overrides of the same), plus
     a Mongo `itemType` field (`"portion"`/`"usage"`, a costing-granularity flag —
     unrelated to Postgres's same-named `item_type` classification column). None of that
     existed in the pg schema; it only stored the pre-collapsed `base_per_count_unit`/
     `base_per_purchase_unit`, which can't be reverse-engineered into pack/unit
     components. Building the adapter on top of that would have silently produced wrong
     cost-per-portion numbers. Fixed via migration `add_item_costing_fields`: added
     `costing_type`/`pack_count`/`unit_qty`/`unit_uom`/`portion_size`/`portion_uom` to
     `items`, `order_enabled`/`sales_tracked`/`needs_review` to `store_items` (and started
     using the table's pre-existing, previously-unused `active` column), and
     `pack_count`/`unit_qty`/`unit_uom` to `vendor_items`. Backfilled all 20
     already-migrated items from the original Mongo export
     (`scripts/backfill_item_costing_fields.py`) rather than guessing — verified 0 items
     missing pack data after.
   - **Backend fixes made alongside** (`backend/server.py`): `ItemIn`/`VendorSkuIn`/
     `_item_row_to_api` extended for the new fields; `pg_create_item`'s vendor-SKU insert
     was append-only (no upsert) — editing an item and re-saving would have duplicated
     every SKU row on each save, so it now deletes and re-inserts the item's vendor_items
     on every save (a save always carries the item's complete list, same "whole document"
     semantics as Mongo); added `DELETE /api/pg/items/{store_id}/{code}` (didn't exist —
     needed so `putCollection("items", ...)` can express a real deletion), which also
     drops the global `items`/`vendor_items` rows once no store references them.
   - **The adapter** (`frontend/src/lib/api.js`): `fetchState`/`putCollection` now branch
     on `USE_PG` for exactly `name === "items"`/`"purchases"` — dishes/adjustments/
     prepStock/salesPeriod/areas/reportingPeriods still always come from Mongo (chunk 4
     territory). `pgItemToMongoItem`/`mongoItemToPgBody` translate item shape both ways,
     `pgFetchItemsAndPurchases` flattens pg's grouped `invoices[].lines[]` into Mongo's
     flat one-record-per-line `purchases` shape, `pgPutItems`/`pgPutPurchases` diff the
     incoming array against a fresh pg fetch to turn "whole array replace" into
     create/update/delete calls against the granular endpoints. `VENDOR_NAME_TO_ID`
     mirrors the same 5-vendor map `scripts/migrate_items_and_invoices.py` used for the
     original data migration. Every existing component (Dashboard, Setup, Invoices,
     Purchase Orders, Adjustments, History, Costing) keeps reading `items`/`purchases`
     exactly as before — untouched.
   - **Known limitations** (documented, not blocking since `USE_PG` defaults off):
     an invoice line's vendor must be one of those same 5 canonical vendors — a
     free-text vendor name from CSV auto-import falls back to `"other"`; purchases/
     invoices are only ever appended by the adapter, never edited or deleted (matches
     what `InvoicesTab.js` actually does today — nothing edits purchase history); a
     vendor SKU's free-text `packDescription` (e.g. "50lb bag") isn't stored in Postgres
     at all, so the adapter reconstructs a generic one from pack/unit numbers instead of
     round-tripping the original text.
4. **Dishes/Recipes** (Menu, Costing, Recipe Cards) — ✅ Done, gated behind `USE_PG`.
   - **No pg endpoints existed at all** — `dishes`/`dish_lines` had real migrated data
     (13 dishes) and Prep's own backend already read them internally for its own math
     (`_pg_raw_portions` etc.), but nothing exposed a list/create/update/delete REST
     surface for the frontend. Added `GET/POST /api/pg/dishes/{store_id}` and
     `DELETE /api/pg/dishes/{store_id}/{dish_id}` (`backend/server.py`), mirroring the
     Items pattern: POST upserts (an `id` in the body updates that dish, no `id` creates
     one), and a save fully replaces that dish's `dish_lines` (delete-then-reinsert,
     same "whole document" semantics as items' vendor_skus). Delete relies on the
     schema's existing FK constraints (`dish_lines.prep_dish_id`, `prep_logs`,
     `prep_items`, `prep_list_lines`, `prep_overrides`, `count_lines` all reference
     `dishes.id` without `ON DELETE CASCADE`) and translates the resulting
     `ForeignKeyViolationError` into a clean 400 instead of a 500 — verified against the
     real database (deleting a prep recipe still referenced by another recipe's lines
     correctly raises `23503`, caught as expected).
   - **A real id-shape difference, not glossed over**: pg dish ids are actual Postgres
     uuids; the Mongo side uses client-generated strings (`uid()` in `calc.js`, e.g.
     `"dish_m1x2y3_ab12c"`). Prep's chunk-2 endpoints already return pg uuids as
     `recipeId` everywhere (prep stock, prep list tasks, overrides). So the adapter
     presents `dish.id` as the real pg uuid (not a translated/preserved Mongo id) —
     the only choice consistent with what chunk 2 already shipped — and
     `mongoDishToPgBody` (`frontend/src/lib/api.js`) detects a non-uuid `id` (a
     brand-new dish from `CostingTab`'s `emptyDish()`) and omits it so the backend
     inserts a fresh row rather than trying to `UPDATE ... WHERE id = 'dish_xxx'`.
   - **Known limitation, real and unresolved**: `reportingPeriods.dishSales` (Sales
     Tracking, `SalesTrackingTab.js`) is keyed by the OLD Mongo dish id and is not
     migrated or remapped by this chunk. Under `USE_PG`, Sales Tracking's per-dish
     sales lookups will not resolve against the new uuids — that tab needs its own
     migration pass (out of this chunk's scope: Menu/Costing/Recipe Cards) before a
     real cutover. Also unhandled: creating a brand-new prep recipe and a brand-new
     menu item referencing it in the *same* save isn't dependency-ordered (dish_lines'
     FK needs the prep dish saved first) — the adapter saves sequentially in array
     order rather than in parallel specifically so normal one-dish-at-a-time edits
     stay safe, but a batch of new cross-referencing dishes in one save could still hit
     the FK before its target exists. Matches how `CostingTab.js` is actually used
     (one dish edited and saved at a time) — not a live risk today.
   - Legacy `qtyPortions` alias on dish lines (some old records use it instead of
     `qty`) is read as a fallback on write; the adapter always emits `qty` on read.
5. **Staff PIN portal (PWA)** — ✅ Done, gated behind `USE_PG`.
   - No new schema needed for most of it: `staff_pins`/`staff_members`/`staff_tasks`/
     `push_subscriptions` were already in the pre-existing schema, just unused until
     now. One real gap found: Mongo's staff item-counting feature
     (`inventory_count_submissions` — the PIN portal's "Enter Counts", a *different*
     feature from Prep's evening count) allows unlimited independent submissions per
     day, each its own Count History entry. `count_sessions`/`count_lines` couldn't
     represent that — they have a `UNIQUE(store_id, count_date, count_type)` built for
     Prep's one-session-per-day evening count; reusing them would have silently
     collapsed multiple same-day submissions into one, losing real history. Added a
     dedicated `inventory_count_submissions` table instead (migration
     `add_inventory_count_submissions`), storing each submission's item snapshot as
     jsonb, matching Mongo's denormalized document shape directly.
   - **Second bug found and fixed proactively** (not by Copilot's review this time —
     found while building): `_is_pin_optional()` in the auth middleware only ever
     checked the raw `/api/staff/...` path. Every new `/api/pg/staff/*` route would
     have hit the blanket 401 *before* its own PIN-fallback logic ever ran, silently
     breaking the entire PIN-only staff model (Prep Sheet, Enter Counts, task portal)
     under `USE_PG` whenever `AUTH_REQUIRED=true` — the same class of bug the
     `route_path`-stripping fix (from the earlier Copilot review round) already fixed
     for `OWNER_PATHS`/`STAFF_PATHS`/`STAFF_WRITE_PATHS`, just in the one place that
     fix didn't reach. Fixed the same way: strip `/api/pg` before matching.
   - **Scope boundary, deliberate**: covers exactly what `StaffSheet.js`/`StaffTab.js`/
     `SchedulingTab.js`/`push.js` call — PIN get/set, roster CRUD, verify, identify,
     prep sheet view + complete (reuses chunk 2's `_pg_complete_task_core` directly),
     staff item-counts view + save, task inbox + manager CRUD, web push. The separate
     manager-facing `/counts/{rid}/submit` + `/counts/{rid}/history`
     (`CountsTab.js`'s own "Enter Counts" tab — a different feature that happens to
     share the same audit table) was left un-gated on the frontend on purpose (out of
     this chunk's stated scope) — **but see chunk 5.5 below**, which made the backend
     itself pg-aware for exactly this endpoint, since it turned out to matter.
   - All 19 endpoints verified: SQL dry-run tested directly against real Supabase data
     via rollback transactions (PIN upsert, staff member insert, the item-counts join
     query, task insert with recurrence, push subscription upsert, and the jsonb
     count-submission insert all confirmed working).
5.5. **Backend integration gap, found and fixed before live verification** — asked
   proactively ("any other schema gaps to check before chunk 6?") and traced every
   backend code path touching `items`/`purchases`/`dishes`/`adjustments`/Prep
   collections directly, rather than through the gated `/api/pg/*` routes. This isn't
   a schema gap (no missing columns) — it's that chunks 1-5 only gated the
   *frontend's own* calls. Several Mongo-native backend features never got told about
   the cutover, so flipping `USE_PG` on for a restaurant would have left them silently
   reading or writing the wrong database:
   - **Write-side (data would go to the wrong place)**: manager "Enter Counts" submit
     (`/api/counts/{rid}/submit`, `CountsTab.js`) wrote `currentStock` to Mongo `items`
     even though the app would display Postgres's; PO receiving
     (`/api/orders/{rid}/{oid}/receive`) did the same for received quantities; PO →
     invoice price sync (`apply_prices`) wrote vendor SKU prices to Mongo `items`. PO
     receiving's invoice-matching (`_match_invoice`) also read Mongo `purchases`, so
     it would report "invoice not found" for every invoice entered after cutover.
   - **Read-side (dashboards/AI would show stale numbers)**: Owner Dashboard
     (`/api/owner/summary`, `/api/owner/prep-summary`) and the AI Assistant
     (`/api/ai/chat`) both compute their rollups straight from Mongo `items`/
     `purchases`/`dishes`/`adjustments`/Prep collections.
   - Adjustments and Purchase Orders themselves turned out fine: Adjustments never
     touches `items` (pure append-only waste log), and POs are internally consistent
     since they're entirely unmigrated (PO data only ever lives in Mongo either way —
     just not started, not desynced).
   - **Fix**: added a backend-side `USE_PG` flag (`backend/.env`, separate from but
     meant to be set alongside the frontend's `REACT_APP_USE_PG`), since the frontend
     flag alone has no way to reach server-side aggregation code. Each of the 6 paths
     above now branches on it: `submit_count`/`count_history` reuse chunk 5's
     `_pg_apply_and_record_counts`/`inventory_count_submissions` directly (so manager
     and staff submissions land in the same place once both are on Postgres);
     `receive_order`'s stock bump became an atomic `current_stock + $1` update (a
     small correctness improvement over the old fetch-then-set, which could race);
     `_match_invoice` and `apply_prices` got pg-native equivalents
     (`_pg_invoice_lines_by_number`, `_pg_apply_prices`); Owner Dashboard and the AI
     Assistant share a new `_pg_owner_view(rid)` helper that reads items/purchases/
     dishes/prep_stock from Postgres and reshapes them into the exact Mongo shape
     `item_derived`/`recipe_cost`/`raw_portions` already expect, so those pure-Python
     costing functions work completely unchanged.
   - Verified: all new SQL dry-run tested against real Supabase data; ran the full
     pytest suite with `USE_PG=true` while `DATABASE_URL` still has the placeholder
     password — every one of these paths now correctly 503s (fail-open, no crashes)
     instead of silently touching the wrong database; re-ran with `USE_PG=false`
     (the real default) and confirmed the baseline is unchanged (57 passing, same 6
     pre-existing environmental failures).
6. **Live verification** — ✅ Done. The real `DATABASE_URL` was configured (via the
   Supavisor connection pooler on port 6543 — the direct `db.<ref>.supabase.co:5432`
   host is IPv6-only and didn't resolve from this dev machine; see the pooler note
   below) and `USE_PG=true` was set on both frontend and backend.
   - **Real bug found and fixed**: every single date-column write (`prep_lists.prep_date`,
     `count_sessions.count_date`, `invoices.invoice_date`, `prep_overrides.date`,
     `staff_tasks.due_date`, `store_items.last_counted`, and the
     `inventory_count_submissions.submitted_at` timestamptz filter — 13 call sites in
     all) was passing a bare ISO string as an asyncpg bind parameter. asyncpg does
     client-side binary encoding of bind parameters (unlike a SQL text literal, which
     Postgres itself casts at parse time) and needs a real `datetime.date`/`datetime`
     object, raising `DataError: ... 'str' object has no attribute 'toordinal'`
     otherwise. This had never surfaced before because every one of chunks 1-5's SQL
     dry-run checks used literal dates typed directly into the query string, not bound
     parameters — live verification was the first time these ran through the actual
     driver path the app uses. First caught live in the browser (Prep List showed
     "Couldn't load this prep list"); fixed with one `_pg_date()` helper applied at
     every site, then re-verified the same flows worked (correct empty states, not
     errors) and re-ran the full pytest suite under `USE_PG=true` to confirm no other
     date-column site was missed.
   - **Verified working live, end to end, in the browser**: Dashboard (real inventory
     value, food-cost %, low-stock list), Owner Dashboard (`_pg_owner_view` rollup
     across all three restaurants), Item Setup (list + edit form, correct
     portions-per-unit/cost-per-portion, including the `OF-001` "no portion data" edge
     case), Invoice Master (real invoice history, including the documented
     `INV-100902` vendor-mismatch judgment call), Menu Costing (a recipe with both
     `sourceType: "item"` and `sourceType: "prep"` ingredient lines resolving
     correctly), Prep (List, Evening Count, Inventory & Log), and the Staff PIN portal
     (PIN unlock via the default-PIN fallback, Tasks, Prep, Counts views).
   - **Supabase branch testing was attempted first and abandoned**: created a dev
     branch to test destructively without risking real data, but branches replay
     migrations onto an empty database and it failed (`MIGRATIONS_FAILED`) — traced to
     an unrelated `add_private_toast_analytics_landing_zone` migration (confirmed with
     the user: a coworker's separate Toast POS integration, not part of this
     migration) that a fresh branch's migration replay couldn't satisfy. Deleted the
     branch and verified against the real project instead, using pg-specific test
     files plus careful manual browser checks.
   - **Real, if minor, incident during verification**: running the *full* pytest
     suite (not just the pg-specific files) with `USE_PG=true` let two purchase-order
     tests actually receive real inventory against `rudds_WI-001` (Russet Potatoes) in
     the live database — a `+16` drift from its migrated value (`100.0` → `116.0`).
     Checked every item across all three restaurants against the original migration
     backup; nothing else was affected. Restored `rudds_WI-001` to `100.0` (confirmed
     with the user before writing to the shared database). Lesson: once `USE_PG=true`
     actually works, the full test suite is no longer safe to run against the real
     project without a disposable branch or database — pg-specific tests plus manual
     spot-checks is the right default until branch testing is fixed or a disposable
     project exists.
   - Both `USE_PG` flags were returned to `false` afterward — same off-by-default
     posture as every other chunk. Flip both together (`backend/.env` and
     `frontend/.env`) when ready for a real cutover.

**Connecting to Supabase from this dev machine**: the direct connection host
(`db.<project-ref>.supabase.co:5432`) is IPv6-only on the free tier and did not
resolve locally. Use the Supavisor connection pooler instead — swap the username to
`postgres.<project-ref>`, the host to `aws-<N>-<region>.pooler.supabase.com`, and the
port to `6543` (transaction mode; matches `db_pg.py`'s existing
`statement_cache_size=0`, which transaction-mode pooling requires). Also: a password
containing `@` (or any other URL-reserved character) must be percent-encoded in
`DATABASE_URL` (`@` → `%40`), or asyncpg's DSN parser fails with a confusing
IPv6-bracket parsing error.

The migration has now been live-tested through the Supavisor pooler; the verification
results and remaining limitations are recorded in chunk 6 below.

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
  transform. The migration script now generates a deterministic, unavailable
  placeholder `vendor_items` row for this vendor/item pair so the historical invoice
  line is retained rather than silently reassigned or dropped.

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

### Applied — prep_recipe_stock + prep_logs data (via `scripts/migrate_prep_stock_and_logs.py`)

1 prep_recipe_stock row + 24 prep_logs migrated and verified (14 `batch`, 5
`container_use`, 5 `sales_usage` — every non-`sales_usage` log correctly resolved a
`dish_id`; `sales_usage` rows are legitimately dish-less at the top level since their
recipe reference lives inside the `usage` jsonb blob instead).

Found one more schema gap along the way: `prep_logs.kind` only allowed
`('batch','sales_usage')`, but the real data also uses `'container_use'` (moving
stock from a prep batch into a service container) — widened via migration
`prep_logs_kind_container_use`.

Verified via `information_schema.columns` — all three tables match this shape
exactly.

### Applied — count_sessions/count_lines + prep_lists/prep_list_lines data (via `scripts/migrate_counts_and_prep_lists.py`)

Found the same gap here as with `prep_list_lines`: `count_lines.item_code` was
`NOT NULL` as part of the `(session_id, item_code)` primary key, but the Prep evening
count (`count_type = 'nightly_prep'/'commissary'`) counts on-hand *recipe* quantities,
not inventory items — there was no way to reference a `dishes` row at all. Rebuilt
(table was empty) with a surrogate `id` PK and added `dish_id`, `prep_item_id`,
`saved_by`. Also added `status`/`released_at`/`released_by` to `prep_lists`, which had
no release-tracking columns at all in the original design.

7 count_sessions + 7 count_lines + 5 prep_lists + 5 prep_list_lines migrated and
verified — 0 unresolved references anywhere (every `dish_id`/`from_count`/`recipe_id`
FK resolved cleanly, including `prep_lists.from_count` resolving to the
just-migrated `count_sessions` rows by natural key).

**Known, deliberate gap**: Mongo's per-session `revisions[]` (archived snapshots from
earlier submit/reopen cycles) was **not** migrated — only each session's current/
latest state came over. In the actual data this is redundant anyway (every revision
duplicates the final submitted state, an artifact of the submit flow, not real
divergent history), but a session with genuinely different revision history would
lose it under this migration. No table exists yet to hold it if this needs revisiting.

## Step 3 status: data migration + backend endpoints done

All real Prep data is in Supabase (dishes/dish_lines, prep_recipe_stock, prep_logs,
count_sessions/count_lines, prep_lists/prep_list_lines), and `/api/pg/*` now has full
backend coverage for Prep, ported function-for-function from the Mongo version:
`_pg_deduct_and_stock`/`_pg_deduct_item_and_stock` (the shared stock-deduction/costing
core), `_pg_raw_portions` (recursive prep-within-prep resolution over `dish_lines`),
`_pg_item_derived` (cost/portions from the item's preferred `vendor_item`, not
`store_items.base_per_count_unit` — those can differ once purchase_unit and count_unit
diverge, even though they're equal for every item in the currently-migrated data),
evening count session flow (get-or-create/entry/submit/history), prep list
generate/get/update/release/complete-task/add-item (the `generate` endpoint is the
most complex port — par overrides, removed overrides, one-off adds, governed-recipe
exclusion, batch/vessel math, all mirrored from the real `generate_prep_list`), Prep
Items catalog CRUD, and Day Overrides CRUD.

**Three more schema gaps found while writing this** (all fixed):
- `prep_overrides.type` only allowed `add`/`remove` — the actual code (`OverrideIn`)
  supports a third value, `par` (a one-date par adjustment with no add/remove).
  Widened via migration `prep_overrides_type_par`.
- `prep_items` was missing `vessel_capacity`, `par_vessels`, `schedule`, `note` — real
  fields the create/update endpoints require. Added via `prep_items_missing_columns`
  (kept `par_weekday`/`par_weekend` as schema headroom, both set to Mongo's single
  flat `par` value for now since nothing differentiates weekday/weekend yet).
- `prep_recipe_stock` only supported recipe-keyed stock (`dish_id NOT NULL` in the
  original PK) — but a prep item sourced directly from an inventory item (not a
  recipe) also tracks its own on-hand stock. Had 1 real row, so **altered** (not
  dropped): added a surrogate `id` PK, added `prep_item_id`, made `dish_id` nullable,
  added a `CHECK (num_nonnulls(dish_id, prep_item_id) = 1)` and two partial unique
  indexes so both keying styles can upsert correctly. Migration
  `prep_recipe_stock_item_sourced`.
- `prep_lists` had no `count_type` column (Mongo stores `track` directly; Postgres
  only had it reachable via a join through `from_count`) — added directly and
  backfilled the 5 already-migrated rows, matching Mongo's shape and avoiding a join
  on every list lookup. Migration `prep_lists_count_type`.

**Also added**: automatic jsonb encode/decode on the Postgres connection
(`backend/db_pg.py`'s `_init_connection`) — the Prep module's `usage`/`containers`
log fields are jsonb-heavy, and manual `json.dumps`/`json.loads` on every touch would
have been easy to get wrong somewhere.

**Known, deliberate gap carried over from the count-session flow**: since revision
history isn't tracked (see above), `save_count_entry`'s Postgres version always
updates the count line in place, even if the session was already submitted — the
Mongo version archives a revision snapshot first in that case. Matches the earlier
decision not to build a revisions table.

**Verified**: server boots clean, existing Mongo routes still 200, every new
`/api/pg/*` Prep route 503s cleanly (not crashes) with Postgres still unreachable,
full pytest suite unchanged (same 6 known-environmental failures, zero regressions).
**Not yet verified**: the actual Prep business logic end to end — needs the real
`DATABASE_URL` password to run the queries themselves. Frontend still doesn't talk
to Postgres anywhere.

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
- **`inventory_count_submissions`**: dedicated table added by migration
  `add_inventory_count_submissions`; each row stores the submitted item snapshot as
  jsonb so multiple same-day submissions remain separate history entries.

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
