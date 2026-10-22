# Reviewed par installation and acceptance proposal

## Decision and current authority

Prepare one additive installation of the already-reviewed par migration, then
separately accept its owner-facing workflow with labelled fictional data.
**This proposal is not an executable installer plan or permission to pause
services, apply SQL or test the hosted app.** The owner subsequently approved
the [bounded read-only hosted preflight](REVIEWED_PAR_HOSTED_PREFLIGHT_20261021.md),
which completed with the runtime API identity still unproven. Further hosted
work and credential, grant and schema changes remain on owner hold. No new application
code, migration, grant policy or connection change is proposed.

Accepted source is PR53 merge `46461e51ea8803b61c5b1d0a2cd7c5564d3a48dd`, tree
`00051925cd20183613586911ca6431fe594dad80`, identical to reviewed `5c8e3ea`.
[Reviewed-head CI](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/39707534584)
and [merged-main CI](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/39708326344)
each passed all four checks: 1,079 frontend tests / 83 suites and strict build,
1,180 Windows offline cases, and 242 backend/disposable PostgreSQL cases.
These profiles overlap. Automatic Render test deployment was owner-approved;
both services were subsequently observed Live at the accepted merge under the
separate read-only preflight. This does not establish functional acceptance.

The October 21 backup window closed at 8:02:45 p.m. Eastern with the original
writers restored. Its verified 120-table / 45,638-row / 13-catalog-group recovery
is dated evidence. No maintenance window or schema approval is active.

## Exact proposed database delta

Use only [migration 31](../migrations/20261018_reviewed_inventory_pars.sql),
`20261018_reviewed_inventory_pars.sql`, through the existing par-specific
[core](../tools/ops/apply_reviewed_par_migration.py) and
[hosted envelope](../tools/ops/hosted_reviewed_pars.py). Do not replay the original
29-file installation, the source-index SQL or filename-sorted migrations.

| Object | Proposed change |
| --- | --- |
| `purchasing.inventory_par_versions` | Create one empty, append-only table with the 17 columns below. No legacy-value backfill and no automatically confirmed zero. |
| Constraints | Add the 17 exact reference constraints: primary/unique identities, successive revision/predecessor structure, verified profile/base references, exact nonnegative quantities/conversion, note/actor requirements and 32-byte fingerprint. Definitions remain hash-pinned. |
| Indexes | Six unique indexes: `inventory_par_versions_pkey`, `inventory_par_versions_predecessor_id_key`, `inventory_par_versions_request_key_key`, `inventory_par_versions_id_store_id_item_code_key`, `inventory_par_versions_store_id_item_code_revision_key`, and partial root index `inventory_par_root`. |
| `purchasing.guard_inventory_par()` | Add one trigger function enforcing the current predecessor, current verified count profile and exact conversion; withdrawal preserves predecessor quantities. Later accepted app inserts advance the store revision. Installation itself does not. |
| User triggers | Add `valid_inventory_par` before INSERT, `immutable_inventory_par` before UPDATE/DELETE and `retained_inventory_par` before TRUNCATE. The latter two use existing `purchasing.reject_fact_change()`. The reference also accounts for 12 internal foreign-key triggers. |
| New-object security | Enable RLS on the new table. Revoke direct table/function privileges from PUBLIC and, where present, anon/authenticated. Add no policies or runtime grants. Existing role attributes, memberships, object/column/default grants and policies must remain unchanged. These new-object security statements belong in the later explicit schema approval; the current grant hold remains in force. |
| Migration ledger | Insert exactly one row named `reviewed_inventory_pars` containing the verified transaction-free body, with a newly selected 14-digit version greater than every actual installed version. Allocate no version in this local proposal. |

Table columns, in order:

`id uuid`, `store_id text`, `item_code text`, `revision integer`,
`predecessor_id uuid`, `unit_profile_id uuid`, `source_unit text`,
`quantity numeric`, `factor numeric`, `base_unit text`, `base_quantity numeric`,
`confirmed boolean`, `coverage_note text`, `actor text`,
`recorded_at timestamptz`, `request_key uuid`, `request_fingerprint bytea`.

The complete [catalog reference](REVIEWED_PAR_INSTALL_CATALOG.json) is normative,
including nullability, defaults, constraint bodies, index flags, trigger state,
RLS and definitions. It contains seven relation records (one table plus six
indexes), 28 column records including index attributes, and no new schema,
sequence, type, view, extension or policy.

Existing legacy pars, item/unit/price data, purchases, counts, prep/waste, sales,
period closures and original ledger rows are preserved. The expected installation
delta is an empty par table/catalog plus one ledger row; no store revision or
application business row changes. The archived ledger had 55 versions, maximum
`20261015175921`; 56 rows is expected only if a future complete live reconciliation
confirms that unchanged baseline. A different baseline holds for review.

## Source pins and what remains unbound

| Input | Verified local SHA-256 |
| --- | --- |
| Exact SQL bytes | `84814517f75bb58940a36facdbf5a7934036ff5b388e97a820038e837416506e` |
| Transaction-free body, 4,407 UTF-8 bytes | `3a189a8b2a352cbd560cea88194dbde1940f160a54e7bcd4616d719c47b88c48` |
| Installed catalog reference, PostgreSQL major 17 | `8a18effb17929604c76817ed7478b112033df4886e4434c0c1e6a4cce01e8e17` |

The [local source audit](REVIEWED_PAR_PROPOSAL_SOURCE_AUDIT_20261021.json)
records all 49 installer-source hashes, all 31 dependency-ordered migration
paths, exact column/object details and the accepted tree. It parses saved source
and the existing SQL lexer without importing the hosted runner, opening a
database or executing SQL. SQL/reference bytes match accepted PR53 exactly.

There is deliberately **no executable plan hash** yet. The real target/actor,
current ledger/catalog/security/rows/sequences, fresh writer inventory, approved
window, new encrypted archive/restore receipt and delivery version must bind the
future hosted plan. A hash of this proposal or source audit is not application
approval. Do not reuse the earlier source-index plan's approval or a par v1 plan.
The hosted/core v2 formats and all source/backup/window guards remain unchanged.

## Proposed authorization sequence

| Gate | Concrete scope to present for later approval |
| --- | --- |
| 1. Bounded read-only hosted preparation | Completed within the owner's approved two-connection scope: both Render services Live at 46461e5; 16 role checks passed; reviewed client private-access counts zero; existing source index valid; par table absent; Toast jobs 3/4 unchanged/enabled. Actual API runtime role/connection and exhaustive writer inventory remain unproven. Resolve those identity/inventory gaps before maintenance; the scoped result is not full preparer readiness. No service pause, new private config, grant, credential, feature flag or SQL change occurred. |
| 2. Fresh maintenance window | Reconfirm API plus Toast jobs 3/4, Companion's local-only status and every manual/script/other writer. Present exact producer controls, original states, owner availability for Render suspend/resume, measured local memory/process readiness, private storage and recovery route. Request a new 45-minute window plus no-other-writes commitment; no window starts from this proposal. |
| 3. Exact installation approval | After approved pause/drain, fresh encrypted backup/disposable restore and complete preparer checks, present the actual target, verified delta, next ledger version, artifact bindings and generated plan SHA-256. Obtain approval for that exact schema/new-object security plan before any DDL. |
| 4. Fictional live acceptance | After a known verified install and writer restoration, present the exact two labelled Bert's fixture identities, profile conversions, initial par/store revisions and scoped mutation list. Obtain separate permission for normal app writes and any transport-fault controls. |

The existing maintenance-only direct IPv6 configuration may be reused unchanged
after the relevant approval. App/Render connections stay as they are; no paid
IPv4 add-on, new secret, role cutover or provider move is included. If the saved
maintenance configuration no longer works, stop and present a separate choice.

O1 restricted-runtime ACL/RLS work remains separate. The installer deliberately
grants no new par access to reviewed backend logins. Installation is not proof
that a restricted API role can use the table. If the actual app identity lacks
needed authority, preserve the freeze and propose O1 separately; do not swap the
connection or add grants during this window. The current owner's build path is
not silently required to adopt O1 as an installer prerequisite.

## Proposed maintenance sequence and stop rules

Use existing budgets: lock 5 seconds, probes 20 seconds, DDL 30 seconds, idle
transaction 120 seconds and adapter operation 600 seconds. Shared installer lock
is `781340621`. Application requires at least 660 seconds remaining by the
existing guard. The proposed operating schedule reserves more time:

| Relative time in a later approved 45-minute window | Action and required outcome |
| --- | --- |
| 0–5 minutes | Capture original controls; pause only approved producers. Verify full writer visibility, reviewed login drain, no unowned transaction and completed downstream jobs. Quiet queries alone do not stop writers returning. Unknown sessions/hidden activity hold; do not terminate platform sessions. |
| 5–15 minutes | Fresh encrypted six-application-schema backup and disposable restore, including ledger. Verify archive/key ACLs and hashes, matching PostgreSQL major, rows/sequences/catalog/security and owned cleanup. Keep passwords/project details/real row values out of shared output. |
| 15–25 minutes | Run the approved read-only full preparer. Reconcile original delivery and source index, every ledger fingerprint/body/name, exact index flags, all 31 readiness dependencies, complete roles/column/default ACL checks and fresh backup equality. Present the concrete plan/hash. A hold or missing exact approval by minute 25 means no application: restore writers and close the window. |
| 25–35 minutes | After exact approval, recheck target, source, deadline, baseline and drain under locks; apply the verified body plus ledger row in one transaction. The runner performs precommit preservation checks and fresh-connection reconciliation. Never auto-retry DDL. |
| 35–45 minutes | Restore exact original producers after a known verified outcome, perform only window-approved health checks, record closure and retain receipts. If outcome/recovery is unresolved by minute 35, escalate to the owner with the remaining time and concrete options. An extension or different restoration action needs explicit authorization; neither a blind resume into unknown state nor an automatic window extension is included. |

This schedule is a proposal, not a promise that every later input will fit it.
Any fresh timing/resource problem changes the proposal before an outage. A failed
backup, restore, identity/role/source check, catalog collision, changed ledger,
late writer or timeout stops application; no guard is weakened to pass.

On acknowledged rollback, independently prove no delta before restoring writers.
On lost commit/rollback acknowledgement, retain the exact plan and progress
receipt, use an independent read-only reconciler and classify applied/not-applied/
unknown. Do not repeat SQL. After a known install, retain additive history rather
than dropping the table. Destructive restore, object repair, manual replay or
application rollback needs its own reviewed authorization. Once acceptance has
legitimately appended par rows, use a separate post-acceptance comparison; the
maintenance reconciler requires an empty new table and is not a health probe.

## Proposed fictional acceptance scope

Use Bert's only, with two explicitly approved purchased-item fixtures, A and B.
Prefer existing TEST ONLY records after identity/profile verification. Do not
assume a product name, old SKU or UI control number proves the current database
identity or unit. No fixture is selected or created in this preparation.

The later approval packet must list exact item/profile IDs and factors, initial
history revision `h`, store revision, request UUIDs and expected per-case changes.
If suitable fixtures do not exist, propose their full catalog/profile writes
separately before creating them. A profile or supplier-metadata change below is
an additional explicit fixture write, not an incidental schema change.

For a current physical conversion `f` base units per stocking unit, a confirmed
quantity `q` means exactly `q * f` base units. Keep decimal strings exact. Each
new accepted par command appends one version and advances the store revision
once; status checks, replays, reloads and local discard add no version/revision.
Capture `h` separately for each case instead of resetting immutable history.
Account for any separately approved catalog/profile mutation's store-revision
delta separately from the par command count. Retain the historical $212.00 Food
Cost control as dated evidence and compare a fresh report for its exact scope;
do not substitute an ownership-dashboard total or assume the amount is current.

| Case | Expected result and proposed delta |
| --- | --- |
| Unavailable/legacy references | Before installation, unavailable/unconfirmed state; no inferred unit or auto-confirmed zero; manual ordering usable. Read-only evidence only. |
| Confirm `6` stocking units | One new review at `h+1`, base quantity exactly `6*f`, actor/time/note/key retained, store revision +1. |
| Reload/sign-in and immutable history | Same accepted values/history and no new review. Owner performs normal personal sign-in; no credential reset or PIN-based elevated login. |
| Explicit zero; withdrawal | Separate confirmed-zero command appends one review. A later withdrawal appends one more, preserving its predecessor quantity/unit/conversion and clearing confirmation; no old row changes. |
| Tiny exact decimal | Confirm `0.000000000001` with the current verified profile: exact stored/displayed quantity and product; one append, not a rounded zero. |
| Same-key replay; stale revision | Exact replay adds zero reviews/store revisions. A changed body under the same key or stale expected revision is refused and retains recovery evidence. |
| Drop before forwarding | With separately approved scoped test transport, original causes zero server writes. Reload retains the request; explicit check/retry sends the same body/key/revision and causes exactly one append. |
| Drop after commit | One append survives the missing acknowledgement. Reload or same-account sign-in then explicit status resolves as saved, without a second PUT/append. |
| Later review; revision-fenced request | An older saved request resolves as superseded without restoring its value. An absent old key with a higher immutable head uses the compare/review path; no automatic write. |
| Held conversion; local discard | Separately approve a fixture-only profile change before the held command. Valid held status exposes confirmation; confirmation rechecks and refreshes before clearing only local tracking. Zero par writes from discard, form/confirmation reset, warning that the original may still complete remains visible. |
| Late commit during discard | If the fresh check sees saved/current or saved/superseded, resolve as saved. A commit after a negative check remains possible; local removal must not be labelled server cancellation or create a replacement write. |
| Failed read/cleanup; cancel | Network/401/403/invalid proof/current-read refusal keeps the record. Local cleanup refusal blocks new reviews. Cancel makes no fresh request/write/clear. Browser fault simulation and cleanup require separate test-control approval. |
| Two fixtures; actor/location isolation | A retained A record freezes the location, including B. Clearing A never clears B. Scope change prevents late acknowledgements from clearing another user's/location's evidence. No second-account creation or permission change is included. |
| Supplier pack independence | If separately approved, change only a labelled fixture's supplier metadata: its fixed physical par must not be reinterpreted and order quantities remain manual. Restore only reversible fixture metadata through normal revisioned routes. |
| Accounting and other workflows | Compare complete protected purchase/count/closure/prep/waste/sales rows and the dated Food Cost control before/after; zero changes outside approved fixture metadata/par history/store revisions. No purchase posting, count acceptance, waste/prep/sales import or period edit. |

Existing CI evidence covers immutable-history UPDATE/DELETE/TRUNCATE refusals.
This proposal does not include trying those statements against the hosted
database. Future restricted-role permissions, cross-role SQL probes and G04
PIN/personal-login acceptance keep their own scope and approvals.

Keep accepted fictional par history labelled and retained. Do not delete it to
make the database appear clean. Retained browser-request cleanup is local only.
Any temporary relay, override or browser permission used later must be separately
scoped and removed with verified cleanup; no such control is prepared or enabled
by this planning step.

## Completion evidence and next decision

Installation completes only with a known committed outcome, exact new empty
catalog/table plus one ledger entry, all original application rows/sequences/
security/history preserved, original writers restored and a closed window.
Acceptance completes only with the approved case results, exact append/revision
counts, accounting comparison and test-control cleanup recorded separately.
Neither means operational release, O1/G04 closure or Companion adoption.

Review the [completed bounded preflight findings](REVIEWED_PAR_HOSTED_PREFLIGHT_20261021.md)
before moving forward. The next proposed scope is read-only confirmation of the
actual API runtime binding and current potential writers. No maintenance window
or installation is authorized. All remaining holds stay in force.

Local validation passed all 49 source-hash checks, the 31-migration ordering and
exact object counts, accepted SQL/reference byte comparisons, all 187 relative
links across the amended/new Markdown, generated review guides and whitespace.
No frontend/backend suite was rerun for documentation-only changes.
That original local planning step opened no database/server or hosted request.
The later separately approved read-only preflight is recorded independently;
no backup, restore, schema/grant change or application test accompanied it.
Earlier CI and recovery results remain dated evidence.
