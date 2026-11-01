# Reviewed migration apply order

Generated from `backend/deployment_readiness.py::MIGRATIONS`. Check with `python tools/review_contracts.py --check`. Do not sort SQL filenames.

This order applies to a reviewed legacy application public schema with `20260930_recurring_prep_items.sql` already installed. The reference schema snapshot is not a migration or a fresh-database installer.

For an existing hosted database, compare recorded migration history and object definitions first. Presence alone does not prove an applied checksum. Do not replay this list against partially installed objects, rename previously delivered files, or use an automatic Supabase CLI filename-order apply. A future workflow must reconcile CLI migration history explicitly. This guide does not apply SQL or change the current Supabase connection.

| Step | File |
| --- | --- |
| 1 | [20261004_native_purchase_import.sql](20261004_native_purchase_import.sql) |
| 2 | [20261004_actual_inventory_counts.sql](20261004_actual_inventory_counts.sql) |
| 3 | [20261004_actual_inventory_corrections.sql](20261004_actual_inventory_corrections.sql) |
| 4 | [20261004_actual_inventory_scope_bridges.sql](20261004_actual_inventory_scope_bridges.sql) |
| 5 | [20261004_posted_invoice_corrections.sql](20261004_posted_invoice_corrections.sql) |
| 6 | [20261005_manual_purchase_sources.sql](20261005_manual_purchase_sources.sql) |
| 7 | [20261005_native_order_receiving.sql](20261005_native_order_receiving.sql) |
| 8 | [20261005_po_receipt_reconciliation.sql](20261005_po_receipt_reconciliation.sql) |
| 9 | [20261005_staff_count_drafts.sql](20261005_staff_count_drafts.sql) |
| 10 | [20261005_prep_mapping_foundation.sql](20261005_prep_mapping_foundation.sql) |
| 11 | [20261005_prep_batch_events.sql](20261005_prep_batch_events.sql) |
| 12 | [20261005_prep_observations.sql](20261005_prep_observations.sql) |
| 13 | [20261005_prep_opening_sources.sql](20261005_prep_opening_sources.sql) |
| 14 | [20261005_prep_period_journal.sql](20261005_prep_period_journal.sql) |
| 15 | [20261006_shared_catalog.sql](20261006_shared_catalog.sql) |
| 16 | [20261006_supplier_price_history.sql](20261006_supplier_price_history.sql) |
| 17 | [20261006_order_commands.sql](20261006_order_commands.sql) |
| 18 | [20261006_supplier_contacts.sql](20261006_supplier_contacts.sql) |
| 19 | [20261007_prep_planning.sql](20261007_prep_planning.sql) |
| 20 | [20261007_prep_day_tasks.sql](20261007_prep_day_tasks.sql) |
| 21 | [20261007_prep_execution.sql](20261007_prep_execution.sql) |
| 22 | [20261007_prep_progress.sql](20261007_prep_progress.sql) |
| 23 | [20261007_staff_prep_counts.sql](20261007_staff_prep_counts.sql) |
| 24 | [20261007_prep_containers.sql](20261007_prep_containers.sql) |
| 25 | [20261007_staff_prep_tasks.sql](20261007_staff_prep_tasks.sql) |
| 26 | [20261007_container_waste.sql](20261007_container_waste.sql) |
| 27 | [20261007_staff_prep_production.sql](20261007_staff_prep_production.sql) |
| 28 | [20261008_container_waste_corrections.sql](20261008_container_waste_corrections.sql) |
| 29 | [20261007_native_private_access.sql](20261007_native_private_access.sql) |
| 30 | [20261013_purchase_source_lookup_index.sql](20261013_purchase_source_lookup_index.sql) |
| 31 | [20261018_reviewed_inventory_pars.sql](20261018_reviewed_inventory_pars.sql) |
| 32 | [20261029_salad_prep_track.sql](20261029_salad_prep_track.sql) |
| 33 | [20261029_count_walk_order.sql](20261029_count_walk_order.sql) |
| 34 | [20261029_prep_count_zones.sql](20261029_prep_count_zones.sql) |
| 35 | [20261029_prep_batch_rounding.sql](20261029_prep_batch_rounding.sql) |
| 36 | [20261030_bulk_supply.sql](20261030_bulk_supply.sql) |
| 37 | [20261030_bulk_release_coverage.sql](20261030_bulk_release_coverage.sql) |
| 38 | [20261031_store_transfers.sql](20261031_store_transfers.sql) |
| 39 | [20261031_login_positions.sql](20261031_login_positions.sql) |
| 40 | [20261031_stations.sql](20261031_stations.sql) |

## Separate manager receiving extension

After the reviewed native source order, [20261025_manager_handoff_notes.sql](20261025_manager_handoff_notes.sql) is a separate default-off receiving migration. It is not added to the sealed 31-file reviewed-par installer or the historical runtime candidate. Its independent structure reference and manifest are in `supabase/manager_handoff.schema.sql` and `supabase/manager_handoff.manifest.json`. No live timezone rows or role policies/grants are seeded. A separate exact installation, per-object permission and activation review is required; existing native installers must not apply it automatically.
