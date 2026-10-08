# Runtime permission narrowing and read-only verifier

October 8, 2026. Local candidate only. No hosted query, role/grant/policy change,
real invoice import, feature-flag file change, push, merge or publication in this
step. The earlier [workflow checkpoint](RUNTIME_PERMISSION_WORKFLOW_CHECKPOINT.md)
records the seven-case candidate and its retained diagnostics.

## Permission changes

The candidate's grant matrix now lives in `backend/runtime_permissions.py` and is
shared by the local-only fixture and its verifier. Native views remain SELECT
only. Native tables allow SELECT and INSERT except these six read-only objects:

| Read-only object | Reason |
| --- | --- |
| `purchasing.base_units` | Fixed migration-installed dictionary. |
| `purchasing.legacy_supplier_contacts` | Preserved original contact capture. |
| `prep_inventory.legacy_planning_sources` | Preserved original planning capture. |
| `prep_inventory.legacy_count_sources` | Preserved original prep-count capture. |
| `prep_inventory.legacy_container_sources` | Preserved original container capture. |
| `prep_inventory.legacy_day_sources` | Preserved original day/list capture. |

Source review found no runtime writers for the five legacy captures. Their
migrations populate them before runtime permission application. INSERT remains
on `prep_inventory.legacy_crosswalks` and `purchasing.legacy_contact_resolutions`:
reviewed mapping/contact decisions create new links there. An original capture
and its subsequent resolution are separate records.

The eight specific private UPDATE grants, 21 public-table permissions and
dedicated backend RLS policies remain as documented in the previous checkpoint.
Row-lock permissions still depend on the enabled immutable guards; the verifier
checks those guard definitions and enabled state. Native journal DELETE,
TRUNCATE, REFERENCES, TRIGGER, MAINTAIN, ownership, grant delegation and schema
creation are outside the candidate. The existing identity sequence needs no
explicit grant for identity-generated inserts; ordinary sequence access is held.

Nineteen native non-trigger invoker functions receive EXECUTE. Exact signatures
and definition hashes now replace name-only approval; an overload, altered body
or security-definer change holds the fixture before any grants are issued.
Trigger function definitions are verified even though no explicit runtime EXECUTE
is granted on them. Further unused INSERT/EXECUTE review is still required; this
candidate is not a completed claim of minimum permissions for every app route.

## Independently built catalog reference

`docs/RUNTIME_CATALOG_CONTRACT.json` was generated from a fresh invented database
on the dedicated loopback PostgreSQL 17.11 cluster, using the reviewed public
reference and all 29 native migration files. It pins **94 exact function signatures
and hashes**, and **123 relation fingerprints: 115 tables, seven views, one identity
sequence**. It does not contain function bodies, business rows or credentials.

Each relation fingerprint covers its column types, nullability, identity/generated
properties and defaults; constraints including validated/deferred state; user
triggers and their enabled state; view definitions/options; and RLS flags. Owner
and effective access are checked independently. The source SQL hashes, public
reference hash and candidate permission-matrix hash bind the frozen reference.
Changing the source or matrix requires another deliberate reference review.

The target being assessed never supplies its own accepted baseline. These counts
describe the local reviewed reference; they are not an assertion that the hosted
catalog matches it. Previously retained hosted preservation evidence has its own
original-column baseline. Hosted additions must be reconciled and reviewed before
this strict candidate can be promoted.

## Read-only assessment

`runtime_permissions.inspect(connection, role_name)` opens its own repeatable-read,
read-only transaction and uses `pg_catalog` as its search path. It refuses an
existing transaction, uses a statement timeout and reads only catalog metadata
and privilege predicates. It neither selects business rows nor applies grants,
policies, SQL migrations or SET ROLE.

It holds on:

- Missing or excessive effective table/view/sequence privileges, including PUBLIC
  and inherited access, column-only ACLs and grant options.
- Privileged role flags, ownership, database/schema creation or any unreviewed
  direct/transitive role membership. NOINHERIT alone does not prohibit SET ROLE.
- Changed/missing/new functions, exact signatures, bodies, definer status or
  unexpected EXECUTE access, including the existing public Toast definer RPCs.
- Changed/missing/new relation contracts, disabled guards, altered constraints,
  columns, view definitions/options and RLS settings.
- Missing/altered dedicated backend policies or additional applicable policies,
  including restrictive policies that can block a required operation.
- An unreviewed PostgreSQL major version.

The schemas assessed are public and the three native schemas; the integrations
schema is also checked if present. Installed extension-owned objects are outside
the frozen application contract. Managed Auth/Storage/Vault, platform roles,
extension contents and permissions in unrelated schemas require their separate
managed-platform review. Browser/Data API access is still a separate gate.

The catalog-reader connection and assessed runtime role are reported separately.
`passed_local_candidate` always includes `operationalReleaseApproved: false` and
`hostedRoleLoginVerified: false`. The shared deployment inspector's independent
`backend_owner_access_not_proven` hold remains in place. Catalog permission checks
do not replace actual backend LOGIN/pool, application authorization or route tests.

## Local validation

The six selected verifier cases pass in `runtime-verifier-final.xml` (290.26
seconds), covering the pinned profile; unchanged catalog, all local application
row fingerprints and migration ledger before/after repeated inspections; missing
and excessive grants; sequence access; table/column/function/schema grant options;
column-only SELECT on `app_users.email`; inherited and non-inherited assumable
roles; function body/overload/definer changes; disabled triggers; altered RLS and
applicable policies; schema creation; table/function ownership; privileged role
flags; and a missing role.

The clean reference passes through both the administrator catalog reader and a
connection that selects the nonowner role. The independent deployment inspector
still holds the latter's owner-access gate. This verifies a catalog reader using
SET ROLE, not an actual separately authenticated hosted LOGIN connection.

Two earlier verifier attempts remain retained separately. Both passed the static
profile test and failed five database cases in the new verifier: first ambiguous
binding of a relation ID to a text overload; then an incorrect integer-column
signature. A read-only probe of the local server's builtin signatures established
the required `name, oid, smallint, text` form. Explicit casts corrected those
queries. These were verifier implementation failures, not evidence that the app's
inventory workflows had changed. The initial catalog capture also exposed a
PostgreSQL metadata byte-decoding issue; catalog character fields now explicitly
return text. Final reference captures match. No earlier diagnostic is overwritten
or counted as a successful result. The existing multipart deprecation warning
remains.

The first narrowed seven-case workflow run passed the installer-based staff case
but held the other six cases before issuing grants: older fixture `read_text()`
calls normalized CRLF in stored function bodies, unlike the exact-byte installer.
The reference was not relaxed or regenerated to match those altered definitions.
The runtime fixture now preserves the reviewed SQL bytes during parent setup and
when completing the migration chain. This change is limited to reviewed fixture
SQL paths; the SQL files and production installer are unchanged. A dedicated
fixture-safety case passes, checking byte-for-byte equality and parent teardown
after invented permission-preparation failure. A completed parent setup now
cleans up its own test clients/pools/database even if runtime preparation fails.
The first failed workflow attempt predates that cleanup correction; no claim is
made that every earlier failed fixture database was removed.

All seven selected exact-SQL workflow regressions pass in
`runtime-narrowed-exact-sql-workflows.xml` (230.26 seconds): physical accounting/
correction/period replay, staff count/production, order receiving/independence,
supplier price adoption, supplier contacts, paired container-waste correction,
and saved prep analytics/reopening. Original synthetic invoice bytes and request
keys remain intact; Track 1 reports/facts retain their expected values. The
physical fixture retains its $60 earlier and $21 final reports; the staff fixture
retains $55. These are distinct invented scenarios, not hosted accounting changes.

Together with the six verifier cases and the one fixture-safety case, **14 selected
local checks pass**. This is not a full-suite, actual hosted LOGIN, browser/Data
API or GitHub CI result. Earlier failures remain separately retained. The
dedicated test server is stopped. The protected original 40-path continuation
and prior evidence packages are verified unchanged when packaging this checkpoint.

## Remaining release work

Review remaining catalog deletion/other routes and unused grants; reconcile the
hosted catalog with an approved permission reference; then review a narrowly
scoped hosted runtime-role trial with original-row/ledger reconciliation. Actual
LOGIN/pool behavior, browser/Data API exposure, full managed recovery, matched
frontend/backend flags and publication/review of the continuation remain open.
Keep merges held. Track 1 accounting remains independent of prep and sales.

Source review confirms concrete route gaps: `pg_delete_item` retires the store
item through UPDATE and preserves its identity, while recipe bulk/single deletion
still deletes `public.dishes` after `menu_contract.retain_operating_history`.
Roster deletion still deletes `public.staff_members` after assignment/reference
checks. This candidate currently grants neither of those table DELETE privileges.
The next route checks must cover successful allowed operations, retained-history
rejection, atomic rollback and store/manager boundaries before deciding whether
to add narrow DELETE grants or use deactivation. These are source findings, not
claims that those routes already pass under the candidate.
