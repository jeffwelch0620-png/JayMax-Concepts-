# Reviewed purchased-inventory par units

**Local continuation:** [maintenance-only direct IPv6 tooling](MAINTENANCE_DIRECT_IPV6.md)
is being tested under owner authorization, with draft push approval pending.
It changes the operator path, not application connections or par semantics.
The hosted table remains absent at the last verified checkpoint; par editing
stays held and ordering manual until separately approved installation/acceptance.

**Current installation checkpoint:** guarded tooling is merged in owner-approved
PR46 `f762808`, with reviewed-head/merged-main CI green. The
[October 18 approved window](REVIEWED_PAR_WINDOW_20261018.md) closed early with
writer drain held and all API/Toast controls restored. No fresh backup, restore,
executable plan or schema application was started. The par table remains absent.
Next: read-only operator/pool session investigation, then a new approved window
and separate exact-plan application approval. Ordering stays manual and the
accepted par-editing freeze remains. Earlier draft-pending entries are history.

**Guarded-installer continuation:** a separately authorized local follow-up
implements the [par-specific additive installer](HOSTED_REVIEWED_PAR_INSTALLER.md)
and disposable rehearsal. Publication, independent review, a new maintenance
window/fresh backup and exact-plan approval remain distinct gates. No hosted
table, role/grant or connection change is included in local implementation.
The final local record covers 24 new methods plus 45 subtests across the selection
and corrected restore rerun, and all 945 offline-profile cases passed. The real
encrypted restore retained exact par history and the $55 fictional Food Cost
control. These are local results, not hosted par acceptance.

**October 18 merge checkpoint:** owner-approved PR45 merged as `9dac63e` from
reviewed head `93941d4`, whose four exact-head CI checks passed. The owner
authorized preparing the [hosted migration plan](HOSTED_REVIEWED_PAR_MIGRATION_PLAN.md)
and reserved SQL application for a separate prompt. The new table is unapplied
by this workflow; no maintenance window, grant or connection change is included.
The existing index-only adapter cannot install it; par-specific guarded tooling,
fresh backup/restore and exact-plan approval remain prerequisites. Earlier local
and amendment statuses below retain their historical dates and validation limits.

The owner authorized explicit par units/review status, aligned screens and manual
ordering, with local tests and a prompt before a draft PR push. Baseline is PR44
merge `1729ecf`, plus its locally committed live checkpoint `41f2a9f`.

## Contract

A par is a location's target stock level for a stated coverage period. It is
planning metadata, not a physical measurement, reorder trigger, Food Cost value
or automatically generated purchase quantity. Prep targets remain separate in
the existing versioned Track 2 planner. Sales expectations can inform later
recommendations; they do not independently deduct or revalue purchased stock.

The reviewer enters an explicit nonnegative decimal quantity, including zero,
and selects the item's current verified count-unit profile. The server derives
the fixed physical target with exact decimal arithmetic. The saved input
quantity, source unit, profile, factor, fixed base unit/quantity, coverage note,
actor and timestamp are retained together as one immutable review version.
Input quantities/factors are bounded below 10^16 with up to 12 decimal places;
the base product is not rounded through binary floating point. Insignificant
trailing zeros do not create an unsupported precision or a database failure.

For example, six verified 5-lb bags establish a 30-lb target. A different supplier
case changes the purchasing equivalent, not that target. This slice does not
calculate the purchasing equivalent or round an order. Supplier selection and
order quantities remain manually reviewed.

## Existing values and review states

`public.store_items.par` is retained unchanged. There is no automatic backfill,
unit inference or conversion of those numbers, including existing default zeros.
Native Item Setup shows the old value as a read-only, unit-unconfirmed reference.
The separate Purchased inventory targets panel requires a new quantity and
explicit review; it does not prefill an old ambiguous number.

- **Unconfirmed:** no explicit target has been reviewed, or its confirmation was
  withdrawn. A default zero never becomes a confirmed zero by itself.
- **Confirmed:** the saved target refers to the current, non-stale verified count
  profile for this product/location.
- **Needs review:** the count profile/source has changed. The former target and
  fixed physical quantity remain visible; there is no automatic reinterpretation.

The same reference renderer is used in Item Setup and Reviewed Order Planning.
Changing supplier does not replace a target or fill an order quantity. Review
can be withdrawn without deleting history or changing stock.

Each confirmation or withdrawal also advances the location-wide
`public.store_state.revision`. The successful Setup save refreshes that shared
revision. Other open catalog, sales or recipe drafts may then receive a stale
revision 409 on their next save; retain their entries, reload the latest state
and explicitly review before saving again. This coordination does not change
their business values or authorize retrying a different command automatically.

## Persistence and rollout

`20261018_reviewed_inventory_pars.sql` adds only
`purchasing.inventory_par_versions` and its history/security guards. It follows
the existing native chain in the generated [apply order](../migrations/APPLY_ORDER.md).
Its LF checkout format is pinned in `.gitattributes` so its raw checksum remains
stable across Windows and Linux, without changing historical SQL fingerprints.
The base reference `supabase/schema.sql` remains the historical public-schema
input, consistent with the repository's migration model.

The purchase API exposes authenticated, location-scoped read/history routes and
a revisioned, idempotent review command. The server obtains the actor from the
session and derives units/factors from the retained physical profile. Readers
use read-only transactions. Writes preserve the current predecessor and append
one version; the associated store revision changes atomically. Changed bodies,
actors, locations, stale revisions and stale/wrong-kind profiles are refused.

The new table is append-only (including a truncate guard), has RLS enabled and
revokes direct PUBLIC/anon/authenticated access. Runtime permissions remain the
separate operational-release workflow. No extra deployment feature toggle is
introduced: this capability inherits native catalog review, and writes also
require its migration. When storage is absent, reads explicitly return
`available:false`; both screens retain unconfirmed references and manual order
entry. Application startup never applies SQL.

The original 29-file installation receipt and the 30-file runtime candidate stay
pinned to their historical baselines. The index-only installer explicitly checks
the `source_index_v1` migration baseline; default readiness checks still require
the full current chain, including this new par table. The historical inspector
continues checking permissions, disabled triggers and constraints across all
present objects. Its report identifies the selected baseline. No old receipt or
grant profile silently gains the new table/function. Restricted runtime access
to the new capability requires a later, separately reviewed permission update.

The form retains an uncertain command and its exact retry key across navigation
within the current signed-in app instance. This slice does not add durable
reload/sign-in recovery for par drafts. On a stale revision, the typed quantity
is retained, and an explicit latest read plus reconfirmation is required.

No hosted migration, flag/credential change or deployment is authorized as part
of this local slice. Hosted schema application and acceptance follow independent
review and approval. Existing item saves cannot confirm the separate par record.
After a confirmed par save, Setup refreshes the shared location/catalog revision;
a failed refresh is reported as a read problem without retrying the saved write.
The existing source-index-only installer cannot apply this table migration. Its
eventual hosted installation needs its own reviewed additive plan, backup and
approval; merging application code alone leaves confirmations awaiting storage.

### Owner-approved deployment sequence (October 18, 2026)

The owner explicitly accepted the temporary par-editing freeze on the build
deployment. After a separately approved merge auto-deploys, native Setup keeps
the previous par read-only and new confirmations remain unavailable until this
table migration is separately reviewed, approved and installed. Read failures
do not unlock the old ambiguous field. Existing values remain unchanged and
manual ordering remains available. The legacy shortfall/dashboard calculators
are not the active native order/accounting screens; this change does not make
their old numbers verified targets.

This acceptance is not merge approval or permission to apply hosted SQL.
Prepare a separate additive installation plan, fresh backup/restore evidence,
post-flight checks and a labelled live par review after independent review.

### O1 restricted runtime-role cutover remains open

The current frozen candidate already includes UPDATE ACLs on `public.items` and
`public.store_items`; validate their SHARE locks under the eventual role rather
than adding broader write privileges. The par guard also reads verified unit
profiles/item bases and inserts or updates `public.store_state`. The future
per-object candidate must explicitly include SELECT/INSERT for the new history
table, explicit trusted-backend RLS policies, and validation of invoker-trigger
dependencies. Table ACLs alone do not enable an RLS-protected route. Do not grant
UPDATE/DELETE/TRUNCATE on par history or direct client access. Test list/history,
confirm/withdraw, stale profiles, location/actor denial, replay and Track 1
independence under the restricted role before hosted cutover. No runtime grant,
manifest or connection change is included in this amendment; see the
[runtime permission assessment](RUNTIME_ROLE_PERMISSION_ASSESSMENT.md).

Par response decimals use fixed notation across setup, save, replay and history,
including small values and scaled zero. Only response formatting changes;
database values, profile snapshots and request fingerprints retain their
original exact decimal representation.

## Validation

The original local validation is recorded below, with its Windows startup
limitation. Draft PR45 was pushed at `a239429`; its frontend/build and Windows
safety jobs passed, including the two locally timed-out ACL tests. Its database
job failed during the runtime fixture's server-address check (106 methods and
43 subtests passed, one setup failure). The disposable Docker service is reached
through localhost but reports its container-side address. The amendment proves
the same cluster/database/server identity through a fresh dedicated localhost
DSN rather than trusting private-network addresses. Remote/control-DSN drift,
non-disposable names and mismatched identities remain refused. New-head CI is
still required. Tests cover unconfirmed defaults, explicit zero,
exact conversion, supplier/count-profile changes, authorization, concurrent
edits, exact retries, failed-write rollback, immutable history, disposable
backup/restore, manual order entry and Track 1 independence. A retained uncertain
write remains retryable even if the reference read fails on navigation back to
the form. A confirmed save refreshes the shared catalog revision; a subsequent
read failure never turns that confirmed write into a new command.

Initial failures are retained as evidence:

- The first PostgreSQL run passed 17/19 reported cases. Two assertions compared
  decimal text `30` and `30.0`; corrected assertions compare exact decimal values.
  The strengthened rerun passed 20/20, including full backup/restore and a direct
  restored-pool accounting comparison.
- The initial offline run exposed older tools assuming their pinned migration
  chain would always be the complete current chain. Historical receipt/runtime
  baselines are now explicit and separate from current readiness; source/body
  checksum checks and full permission guards remain in place.
- The first strict build refused an effect-cleanup lint warning. The reader now
  retains the generation explicitly; the subsequent strict build passed. Later
  decimal/recovery/revision tests and final-build evidence follow below.
- The final broad offline run passed **884/886 reported cases** (311 methods plus
  573 subtests). Two unchanged Windows ACL tests timed out starting bundled
  PowerShell; neither is counted as passed. Fresh CI, including the Windows ACL
  job, is required after an approved push and before merge approval.
- The extended database run passed 107/145 reported cases, with 10 failures and
  28 setup errors. Nine failures and the 28 cascading fixture errors came from
  missing local IANA timezone data; the repository already pins `tzdata==2026.3`.
  The isolated runner now supplies that exact package. The remaining failure was
  a new test nesting a repeatable-read snapshot inside a read-committed fixture;
  its outer fixture now explicitly uses repeatable read. Production timezone
  validation and snapshot isolation were not weakened. The corrected run passed
  **62/62 reported cases** (49 methods and 13 subtests), including every failed
  case and the final par/runtime guards. It verifies exact boundary decimals and
  harmless trailing zeros, full par backup/restore, the historical runtime order
  flow, refusal to inherit old grants for the new table, and all local/hosted-
  adapter index guards. Inventories were unchanged and the owned server stopped.
- Windows reached 99% memory use during overlapping local checks. The superseded
  build and a later frontend/offline run were stopped, with logs preserved. That
  interrupted frontend run reported three 5-second timeouts in unchanged
  PreparedItemSetup cases; it is not a passing full run. The owner freed memory,
  and remaining heavy runs were serialized. The final full frontend run below
  supersedes those interrupted timing results.

Final evidence:

| Check | Result | Retained artifact |
| --- | --- | --- |
| Full frontend, native feature profile | **1,026/1,026**, 80 suites, no failures/skips | `inventory-par-full-20261018T045715933633Z.json` and frontend log |
| Strict CI/ESLint production build | Passed; `main.912099cf.js` | Same prefix, `-build.log` |
| Corrected PostgreSQL selection | **62/62**, 49 methods plus 13 subtests; all prior failed cases resolved | `inventory-par-corrected-db-20261018T043407636283Z` XML/log/receipt |
| Broad offline selection | **884/886**; two Windows ACL startup timeouts | `inventory-par-backend-offline-20261018T041100142392Z.xml` and log |
| Final offline guards, serialized | **37/39**, 10 methods plus 27 subtests; same two Windows ACL startup timeouts | `inventory-par-final-backend-targeted-20261018T050235874451Z.xml` and log |

These are separate executions, not additive unique test counts. Original broad
database evidence is retained in `inventory-par-full-db-20261018T040621168521Z`;
it is not labelled a passing full run. All 38 failed/error methods are included
in the passing corrected selection, alongside final par and runtime guards.
The known Node `fs.F_OK`, multipart and FastAPI lifespan deprecation notices are
outside the strict compiler and remain unchanged. Documentation links, Python
syntax, generated review contracts, SQL checkout attributes and whitespace are
checked before the local commit. Fresh exact-head CI remains a merge gate.

Migration raw SHA-256:
`84814517f75bb58940a36facdbf5a7934036ff5b388e97a820038e837416506e`.

Amendment focused offline checks passed **9 methods and 29 subtests**, including
fixed response notation without evidence/fingerprint mutation, localhost and
Docker-forwarded identity proof, remote/control-DSN refusal and mismatched
cluster/database/address/port refusal with probe cleanup. Evidence prefix:
`pr45-amend-targeted-20261018T052037880682Z`. Python syntax, documentation links,
generated contracts and whitespace checks pass; migration bytes remain unchanged.
The broader local database follow-up is retained under
`pr45-amend-db-20261018T052146412985Z`; it was still running at amendment push.
At `2e583de`, [GitHub CI](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/39101905424)
passed **1,026 frontend tests in 80 suites**, the strict build, **151 database
cases** (108 methods and 43 subtests), and **906 Windows offline cases** (317
methods and 589 subtests), with no failures/errors/skips. This includes the real
Docker runtime-fixture proof and the new decimal/history/replay regression.

The expanded local run reported failures and reached its 40-minute runner limit
before writing a complete JUnit result. It is not a passed run. Its selection
also collected standalone installer tests inherited by `RuntimePermissionTests`,
whose setup already installs the candidate; those fresh-install methods are
incompatible with that preinstalled fixture. Runtime tests now explicitly reuse
the fixture's setup, teardown and install helpers without inheriting its test
methods. Canonical installer tests remain in their original module.

After the timeout, the recorded inventory identified exactly one new invented
database and role. An owned-server cleanup verified the inventory against that
snapshot, refused other clients, removed only those two exact run-owned objects,
proved the original database/role inventory restored, and stopped its server.
Receipt: `pr45-amend-db-20261018T052146412985Z/owned-timeout-cleanup.json`.
No hosted connection was used. The corrected local par/runtime selection is
retained under `pr45-amend-runtime-corrected-20261018T060248399335Z` and passed
**48/48 reported cases** (23 methods and 25 subtests), with no failures, errors
or skips. It includes the full par module, the complete now-independent runtime
permission module, and the restricted-role order/receiving/Food Cost regression.
Its receipt verifies unchanged database/role inventories and a stopped owned
server. Fresh CI for the final test-discovery head remains required and is
recorded on PR45 before merge approval is requested. Counts from separate runs
are not added as unique coverage.

All database runs use fictional data and an owned, loopback-only PostgreSQL 17
server. Their receipts compare database/role inventories and stop that owned
server. No hosted connection, migration or live acceptance is claimed.

Remaining scope: delivery/calendar-specific target policies, reorder points,
current available-stock evidence, incoming-order coverage, supplier rounding and
automatic suggestions. Aliases (F05), versioned Toast evidence (F06), credential
rotation and the later UI rework retain their separate workflows.
