# Supabase schema

`schema.sql` is a **reference snapshot** of the live `public` schema (project
`yrlhwcoirgqmtlvvnzvo`), as of 2026-09-30 after the Phase 2 migrations. It exists so the schema is
reviewable and diffable in git; it is not a migration and must not be applied to the
live project.

Migrations applied to the live project at snapshot time (`supabase_migrations.schema_migrations`):

| Version | Name |
|---|---|
| 20260929135736 | inventory_balance_and_pricing |
| 20260929135747 | purchase_orders |
| 20260929135757 | adjustments_and_reporting |
| 20260929135810 | menu_and_recipes |
| 20260929135821 | prep_extras |
| 20260929135830 | staff_pin_portal |
| 20260929135839 | staff_tasks_and_push |
| 20260929135849 | ai_and_activity |
| 20260929145121 | prep_schema_extensions |
| 20260929145338 | dishes_missing_columns |
| 20260929150348 | prep_logs_kind_container_use |
| 20260929150653 | count_lines_and_prep_lists_extensions |
| 20260929151135 | prep_overrides_type_par |
| 20260929151247 | prep_lists_count_type |
| 20260929151335 | prep_items_missing_columns |
| 20260929151436 | prep_recipe_stock_item_sourced |
| 20260929154701 | add_item_costing_fields |
| 20260929163134 | add_private_toast_analytics_landing_zone (Toast POS integration, separate work) |
| 20260929210257 | add_inventory_count_submissions |
| 20260930005411 | prep_items_recurring_schedule |
| 20260930130026 | phase2_app_users_and_store_state |
| 20260930130040 | phase2_purchase_orders |
| 20260930130047 | phase2_adjustments_and_reporting_periods |
| 20260930130058 | phase2_projections_and_par_recommendations |
| 20260930130104 | phase2_activity_log_user_id |

The phase2_* SQL is in git history under `supabase/pending/` (removed once applied).

`migrations/20260930_recurring_prep_items.sql` (recurring prep items) is **already
applied** as `20260930005411 prep_items_recurring_schedule` -- do not re-run it. The
live columns are nullable and its checks exist under other names
(`prep_items_recur_days_range_check`, `prep_items_recurring_requires_fields_check`);
re-running would only add two duplicate checks. `schema.sql` reflects the live state.

## Access model

- The backend connects with `DATABASE_URL` as the `postgres` role (via the Supavisor
  pooler), which bypasses RLS. All authorization is enforced in `backend/server.py`.
- RLS is **enabled with zero policies on every table** — deliberate: it makes the
  auto-generated Data API (PostgREST) deny all access for the `anon`/`authenticated`
  roles. Do not add permissive policies or disable RLS on any table.
- New tables must be created with `ALTER TABLE ... ENABLE ROW LEVEL SECURITY;`.
- No policies are needed while only the backend queries the database. Write them only if
  something ever reads through the Data API or a client-side Supabase SDK -- and then only
  for exactly the rows that client may see.

## Refreshing

With the Supabase CLI linked to the project, `supabase db pull` writes the remote schema
as a migration file under `supabase/migrations/`; regenerate `schema.sql` with
`supabase db dump --schema public -f supabase/schema.sql`.
