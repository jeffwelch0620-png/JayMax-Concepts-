# Supabase schema

`schema.sql` is a **reference snapshot** of the live `public` schema (project
`yrlhwcoirgqmtlvvnzvo`), captured read-only on 2026-09-30. It exists so the schema is
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

## Access model

- The backend connects with `DATABASE_URL` as the `postgres` role (via the Supavisor
  pooler), which bypasses RLS. All authorization is enforced in `backend/server.py`.
- RLS is **enabled with zero policies on every table** — deliberate: it makes the
  auto-generated Data API (PostgREST) deny all access for the `anon`/`authenticated`
  roles. Do not add permissive policies or disable RLS on any table.
- New tables must be created with `ALTER TABLE ... ENABLE ROW LEVEL SECURITY;`.

## Refreshing

With the Supabase CLI linked to the project, `supabase db pull` writes the remote schema
as a migration file under `supabase/migrations/`; regenerate `schema.sql` with
`supabase db dump --schema public -f supabase/schema.sql`.
