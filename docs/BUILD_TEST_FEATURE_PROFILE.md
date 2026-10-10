# Native build/test feature settings

Generated from the reviewed feature map. This is a proposed testing profile, not evidence of live Render settings and not an instruction to enable features before their schema, permissions, and workflow checks pass.

Keep the existing hosted Supabase connection, session pooler, and private backend credentials during build. Paid IPv4, connection/role changes, and operational release decisions are deferred. No connection secret belongs in frontend settings or this document.

Both `USE_PG=true` and `REACT_APP_USE_PG=true` are required for PostgreSQL. For each reviewed feature, backend and frontend must agree; the browser settings require a frontend rebuild. `render.yaml` does not declare these native flags, so review dashboard overrides without exposing their secrets.

A database with `purchasing.store_vendor_items` installed requires the PURCHASE_IMPORT, ACTUAL_INVENTORY, and CATALOG_MAPPING foundation together for catalog loading. Turning all native flags off does not restore legacy catalog compatibility after installation. The load error provides a retry and diagnosis; it does not bypass that compatibility hold.

The full native testing profile below sets both columns to `true` only after each installed module is reviewed. A narrower profile must set both sides to `false` for held modules and honor all listed prerequisites.

| Backend setting | Frontend build setting | Prerequisites |
| --- | --- | --- |
| `PURCHASE_IMPORT_ENABLED=true` | `REACT_APP_NATIVE_PURCHASES=true` | None |
| `ACTUAL_INVENTORY_ENABLED=true` | `REACT_APP_ACTUAL_INVENTORY=true` | PURCHASE_IMPORT |
| `CATALOG_MAPPING_ENABLED=true` | `REACT_APP_CATALOG_MAPPING=true` | ACTUAL_INVENTORY |
| `ORDER_WORKFLOW_ENABLED=true` | `REACT_APP_ORDER_WORKFLOW=true` | CATALOG_MAPPING |
| `SUPPLIER_CONTACTS_ENABLED=true` | `REACT_APP_SUPPLIER_CONTACTS=true` | ORDER_WORKFLOW |
| `PREP_SETUP_ENABLED=true` | `REACT_APP_PREP_SETUP=true` | PURCHASE_IMPORT |
| `PREP_BATCHES_ENABLED=true` | `REACT_APP_PREP_BATCHES=true` | PREP_SETUP |
| `PREP_OBSERVATIONS_ENABLED=true` | `REACT_APP_PREP_OBSERVATIONS=true` | PREP_BATCHES |
| `PREP_PLANNING_ENABLED=true` | `REACT_APP_PREP_PLANNING=true` | PREP_SETUP, CATALOG_MAPPING |
| `PREP_DAY_TASKS_ENABLED=true` | `REACT_APP_PREP_DAY_TASKS=true` | PREP_PLANNING, PREP_OBSERVATIONS |
| `PREP_EXECUTION_ENABLED=true` | `REACT_APP_PREP_EXECUTION=true` | PREP_DAY_TASKS |
| `STAFF_PREP_COUNTS_ENABLED=true` | `REACT_APP_STAFF_PREP_COUNTS=true` | PREP_OBSERVATIONS |
| `PREP_CONTAINERS_ENABLED=true` | `REACT_APP_PREP_CONTAINERS=true` | PREP_OBSERVATIONS |
| `STAFF_PREP_TASKS_ENABLED=true` | `REACT_APP_STAFF_PREP_TASKS=true` | PREP_EXECUTION |
| `STAFF_PREP_PRODUCTION_ENABLED=true` | `REACT_APP_STAFF_PREP_PRODUCTION=true` | STAFF_PREP_TASKS |

Run the existing `backend/deployment_readiness.py` configuration review with private backend and frontend settings. A matching configuration does not prove schema installation or runtime permissions; complete its read-only catalog checks separately. Authentication/PIN redesign remains deferred in build and required before operational use.
