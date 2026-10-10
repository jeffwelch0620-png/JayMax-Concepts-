# Backend runtime permission assessment

The later [workflow checkpoint](RUNTIME_PERMISSION_WORKFLOW_CHECKPOINT.md)
records **seven passing selected local cases** under a per-object nonowner
candidate across purchasing, physical counts/corrections, staff review, orders,
supplier settings, waste and prep analytics. It identifies necessary private
row-lock UPDATE rights and read-only access to legacy reporting periods.
The assessment below preserves the earlier staff-production-only prototype;
its schema-wide grants are not the current candidate. Hosted-role approval remains open.

October 8, 2026. Local prototype only; no hosted role, grant, policy or ownership
was changed. This is a workflow permission assessment, not deployable grant SQL.

The current Supabase connection uses `postgres`, which owns private application
tables and has RLS-bypass authority. Its passing hosted tests do not establish
runtime least privilege. The disposable PostgreSQL test instead acquires every
connection as a new nonowner role, verifies its privilege flags, and repeats that
selection after the pool restart. The role has no superuser, RLS bypass, CREATEDB,
CREATEROLE or ownership, and is removed after its disposable database is dropped.

## Permissions exercised by the local prototype

| Area | Prototype access | Verified boundary / limitation |
| --- | --- | --- |
| `purchasing`, `actual_inventory`, `prep_inventory` | Schema usage; table SELECT/INSERT; sequence usage/SELECT; function execution | No private UPDATE, DELETE, TRUNCATE or DDL authority. Private journal deletion and schema alteration are denied. These schema-wide grants are broader than a final per-object model. |
| Public catalog and roster | SELECT on 11 explicitly named tables; fixture-scoped SELECT policies | Another original store is invisible. This uses one invented location, not final multi-location identity policy. |
| Catalog tables locked during review | UPDATE table ACL on items, store_items, dishes, dish_lines and prep_items | SHARE table locks require a write ACL. No UPDATE policy is supplied on these catalog rows; attempted item rewrite affects zero rows. |
| `public.staff_members` | SELECT/INSERT and UPDATE ACL with fixture-scoped policies | The guarded roster `FOR SHARE` row read also requires a visible UPDATE policy. The prototype therefore permits update of that fixture's roster rows; it is not a read-only roster design. |
| `public.store_state` | Fixture-scoped SELECT/INSERT/UPDATE | Required for location revisions and serialized writes. Other stores remain outside the fixture policy. |
| `public.activity_log` | SELECT/INSERT with invented-email filter | Actual middleware activity writes are verified. The invented-email predicate is a test fixture rule, not production authorization. |

The 11 public tables are stores, items, store_items, dishes, dish_lines, prep_items,
vendor_items, vendors, staff_members, store_state and activity_log. Vendor lookup
is limited to the two invented fixture vendor identities. Public row policies
remain enabled; no owner bypass is used during the application requests.

An initially missing roster UPDATE policy caused the trigger to reject assignment
even after its ordinary SELECT preview succeeded. Adding the scoped policy locally
made the full assignment, pending-production, independent-acceptance, explicit
finish and fresh-pool retry workflow pass. The existing trigger was preserved.

## Recommended next design

Separate the migration/administration connection from a dedicated server-only
runtime role. Keep ordinary browser/client roles unable to read private purchasing,
accounting and prep schemas. Do not put the backend connection secret in frontend
configuration. Preserve application role/location checks and database integrity
guards together.

Inventory every query, trigger dependency, table lock, sequence and function used
by the workflows that will actually be enabled. Replace the prototype's broad
private SELECT/INSERT/function grants with a reviewed per-object matrix where
practical, accounting for triggers that read other journals. Verify grants after
new migrations rather than relying on accidental default privileges.

Resolve the roster lock tradeoff explicitly. Retaining current invoker guards needs
the scoped UPDATE visibility demonstrated here and allows that role to update
matching roster rows. A tightly scoped database function could reduce direct
roster write access, but would introduce a privileged boundary requiring careful
ownership, search-path, execution-grant and concurrency review. Do not silently
remove the lock or weaken the current snapshot guard to make a test pass.

Choose whether the trusted backend role can read every location with application
authorization, or needs transaction-scoped database location policies. Test policy
state reset on connection reuse and failures if adopting the latter. Never grant
the fixture policies to `anon`, `authenticated` or an existing broad service role
as a substitute for this design.

Before applying hosted permissions, exercise purchasing, physical count/period
closure, prep/waste, count review, task/production review and analytics reads under
the final role. This step covers staff production only. Then run a bounded hosted
synthetic trial and independently verify original rows, migration history,
denials, replay and Track 1 separation. Browser/Data API exposure and full managed
recovery remain independent release checks.
