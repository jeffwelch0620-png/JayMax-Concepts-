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
