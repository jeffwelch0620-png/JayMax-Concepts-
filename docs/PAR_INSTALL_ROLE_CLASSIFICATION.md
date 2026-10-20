# Reviewed par installer: explicit browser and backend role checks

**Accepted PR48:** owner-approved merge `cbe8e88` matches reviewed `12dba79`;
reviewed-head and merged-main CI passed. The local
[diagnostic/preflight follow-up](PAR_BACKEND_HOLD_DIAGNOSTICS.md) addresses N1/N2.
It needs its own publication/review gate; hosted validation remains unrun.

Local follow-up to the [October 19 held plan](REVIEWED_PAR_WINDOW_20261019.md).
Supabase, Render, app connections and runtime grants are unchanged. Par editing
remains held and ordering manual. This work neither applies the par schema nor
approves operational release, and it does not reuse the closed maintenance window.

## Cause and bounded correction

The retained review included the trusted Inventory backend in `clientRoles`.
That list was used both for migration-ledger denial and for readiness checks that
require no private Inventory access. The backend's existing Inventory permissions
therefore caused a legitimate refusal under the wrong role classification.

The par-specific v2 review separates `clientRoles` (private access denied) from
explicit `backendRoles` (existing access preserved). It does not infer trust from
names, remove backend logins from writer drain, change the historical index tool,
or weaken the shared `deployment_readiness.inspect` contract. Both groups remain
denied table- and column-level migration-ledger access. The generated core plan
stores both groups, and the hosted envelope binds them to the exact review hash.

Every non-maintenance writer must be classified in exactly one group. Only the
existing administrative `postgres` actor can remain outside the permission-denial
groups; it remains in the writer inventory when it is also an application writer.
The ordinary browser roles `anon` and `authenticated` are always mandatory clients.
Changing a classification or writer inventory invalidates the reviewed plan.

## Backend preservation contract

An explicit backend must exist as an unprivileged LOGIN, with no superuser,
BYPASSRLS, CREATEDB, CREATEROLE or replication authority, unreviewed role membership,
database ownership, application/ledger schema ownership (even with CREATE
revoked), application/ledger DDL authority or relation/function ownership. Future private/ledger
default grants to it are refused. The new par table's table/column access and
the new guard function's execute permission remain denied, even to this backend.
An existing incoming membership for the administrative catalog reader is retained;
all other incoming memberships and every backend membership in another role are
refused, including NOINHERIT memberships that still allow SET ROLE. Column-only
private grants to browser clients are explicitly refused as well.

Existing role attributes/memberships, schemas, relation/function ACLs, column
ACLs, default privileges and catalog definitions remain frozen in the baseline.
The migration's allowed new catalog delta is unchanged. A changed grant after
planning holds application; an unexpected new-table grant cannot be accepted by
reconciliation. Exact source hashes, prior ledger history, restore-verified backup,
writer visibility/drain, locks, timeouts, rollback and independent reconciliation
remain required.

This is a **preservation-only installation contract**. It does not establish that
every old backend permission is appropriate, replace the separate runtime/RLS
assessment, or grant the deferred new par routes access. Those remain later O1
work. The migration still creates an empty table and one ledger entry only after
fresh exact-plan owner approval; it never backfills pars or changes Food Cost.

## Private review shape and old artifacts

The new formats are `jaymax-hosted-reviewed-par-review-v2`,
`jaymax-hosted-reviewed-par-plan-v2` and
`jaymax-additive-reviewed-par-plan-v2`. V1 reviews/plans are refused, with no
automatic conversion, role-name inference or approval transfer. Historical
original-install and source-index evidence retain their original formats/bytes.

Example classification fragment only, not an executable review:

```json
{
  "format": "jaymax-hosted-reviewed-par-review-v2",
  "clientRoles": ["anon", "authenticated", "<accounts-login-denied-private-access>"],
  "backendRoles": ["<reviewed-inventory-backend-login>"],
  "writerLoginRoles": ["postgres", "<accounts-login-denied-private-access>", "<reviewed-inventory-backend-login>"]
}
```

Real role names, backup/key paths and credentials stay in protected local inputs.
`backendRoles` must be explicit even when empty. Each backend must also be a
reviewed writer. Do not update the old private review or retained approval in
place. After local review, fresh CI and owner merge approval, a newly approved
window must recheck all writers, capture a new backup/disposable restore and create
a new source/baseline-bound v2 plan. Prompt separately with that exact plan SHA-256
before applying anything to Supabase.

The actual hosted role configuration has not been validated against this new
contract. After review and acceptance, a separately scoped read-only role
preflight should precede another outage. It may still hold on unsafe privileges;
correcting the classification does not approve all existing backend permissions.

Managed-project memberships, CREATE on `public` or `extensions`, and global
default ACLs can be preflight findings. `public` is checked directly today;
`extensions` is outside the explicit schema check. The default-ACL predicate is
global/private/ledger scoped, not every namespace. Record a dated per-rule
read-only result before any window, marking unvisited checks `not_evaluated`.
Resolve holds as separate reviewed permission work, never installer exceptions;
see the [exact scope and record requirements](PAR_BACKEND_HOLD_DIAGNOSTICS.md).

## PR48 CI fixture correction

The initial [PR48 CI run](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/39206935839)
at `91d5f7f` passed all 1,026 frontend tests/80 suites, the strict build and
1,025 Windows offline cases. Its database job passed 128 methods and 91 subtests
but failed two new login methods: the fictional backend had no password and
inherited the owner DSN's password on connect. The owned local server used trust
authentication, so the earlier local pass did not cover that CI requirement.
This initial CI run is **failed**, not an acceptance result.

The fixture now creates its UUID-scoped backend LOGIN with a public TEST_ONLY
password and explicitly supplies that role's password in both new connections.
No production credential, runtime grant, CI authentication policy or installer
guard changes. The targeted local rerun uses an alternate startup-only HBA file:
non-owner loopback connections require SCRAM, an independent probe must reject a
wrong password and accept the correct one, and the saved cluster HBA is preserved.
The owner DSN intentionally carries a different synthetic password to verify the
role override. Both affected methods passed in
`reviewed-par-password-auth-20261019T060031844776Z` (two cases, no failures or
skips). Its receipt verifies the negative/positive SCRAM probe, unchanged saved
HBA, exact database/role cleanup, stopped server and no hosted connections.
The corrected-fixture full offline rerun
`reviewed-par-role-v2-offline-20261019T060456000855Z` passed all 1,025 cases
(346 methods plus 679 subtests), with no failures, errors or skips.
The earlier complete local selections below retain their own scope and overlap
this corrected-fixture rerun; they are not added as unique coverage. Fresh-head
CI remains required before independent-review readiness.

## Validation

Regression work uses fictional data, sanitized environment variables and an owned
loopback PostgreSQL 17 instance only. Hosted connection inputs are not loaded.
All final selections use the strengthened database/schema ownership and
column-only guards. Counts below are disjoint within the five database batches;
earlier attempts and overlapping offline guards are not added as unique coverage.

| Final completed evidence | Methods | Reported cases including subtests |
| --- | --- | --- |
| `maintenance-ipv6-database-20261019T052352745658Z` | 3 | 20 passed |
| `maintenance-ipv6-database-20261019T052644500228Z` | 5 | 19 passed |
| `maintenance-ipv6-database-20261019T053004628539Z` | 3 | 6 passed |
| `maintenance-ipv6-database-20261019T053226358675Z` | 5 | 14 passed |
| `maintenance-ipv6-database-20261019T053752223109Z` | 5 | 10 passed |
| **Database total** | **21** | **69 passed; no errors, failures or skips** |
| Full offline profile, `reviewed-par-role-v2-offline-20261019T054628555079Z` | 346 | 1,025 passed (679 subtests); no errors, failures or skips |

Both unchanged Windows ACL cases passed in the final offline profile. Five
existing deprecation warnings remain. Frontend tests/build were not rerun because
frontend code is unchanged. Fresh-head CI is required after the fixture amendment.

Each completed database receipt proves identical starting/final database and role
inventories, owned-server shutdown and no hosted connections. Real encrypted
export/restore preserved immutable par history and the exact $55.00 fictional
Food Cost report. Source/role changes, browser and backend ledger exposure,
column-only grants, unsafe authority/default grants, live/hidden writers,
rollback/commit ambiguity, concurrent writes and postcommit tampering remain held.

The earlier broad attempt `maintenance-ipv6-database-20261019T045840312860Z`
hit its 1,200-second runner limit during Windows memory pressure, after 18 methods
reported passing. It has no final XML report and is **not a passing run**. Its
exact two added databases and three added roles were removed only after comparing
the retained before/after inventories; all pre-existing objects were preserved,
the original inventory was restored and the owned server stopped. Windows also
reported a paging-file/process-start failure. The owner freed memory twice;
the five completed serial batches above replace that incomplete attempt.
Earlier seven-method and focused offline runs overlap and are not added here.

External evidence and receipt hashes are retained in `pr48-local-validation.json`
under the local work folder, outside the repository. Static checks verify Python
syntax, generated review guides, relative Markdown links and whitespace. Against
accepted PR47 `a7270ca`, application code, migrations/snapshot, pinned catalog,
runtime permission candidate/implementation and historical index tools remain
unchanged. No Supabase/Render connection or permission changes were made.

The JMAX workflow, progress hub, hosted plan and root are synchronized through
11 guarded block updates and full 184-block readback; unrelated content and the
Companion boundary were preserved. Owner-approved draft PR48 is published;
the fixture amendment requires fresh-head CI. Independent review, owner merge,
hosted preflight, a new window
and exact-plan application remain distinct later gates. This local rehearsal
does not establish hosted par acceptance or managed Auth/Storage/Vault recovery.
