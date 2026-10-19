# Reviewed-par maintenance window - October 18, 2026

Subsequent work is tracked in the [maintenance-only IPv6 runbook](MAINTENANCE_DIRECT_IPV6.md).
This execution record remains the dated closed-window outcome.

**Closed at 8:35:28 p.m. Eastern without schema application.** The approved
window began at 8:15:16 p.m. and had a 9:00:16 p.m. deadline. Render's API is
restored Live on accepted PR46 merge `f762808`; `/api/health` reports
`{"status":"ok","database":"connected"}`. Both Toast jobs are independently
verified restored to their original enabled states, schedules and command hashes.

The writer-drain prerequisite did not pass. Fresh encrypted backup, disposable
restore, executable par-plan generation and schema application **were not started**.
There is no application plan hash to approve. The window is closed and must not
be reused even before its original deadline. Par editing remains held and ordering
stays manual.

## Approval and exact scope

The owner confirmed that only `jaymax-api` and the two Toast jobs write to this
Supabase project; Companion remains local-only. The owner approved a new
45-minute pause/drain/backup/restore window and committed to no other manual
SQL/script writes. Schema application was explicitly reserved for a separate
exact-plan prompt. No schema-application approval was requested or received.

Accepted executable source remains PR46 `f762808b22bae680c40026af01a69c0226f5d2c7`.
The local documentation continuation was pinned at `d4e3857` during preparation;
application, tools, SQL, CI and runtime-permission sources matched the accepted
merge. Existing reviewed-head and merged-main CI results remain the dated code
validation; the held hosted check is not a passing migration rehearsal.

## Observed controls and drain

| Control | Original state | Maintenance action | Recovered state |
| --- | --- | --- | --- |
| Render `jaymax-api`, `srv-dauimuugekts73ek9lr0` | Live, `f762808` | Temporarily suspended | Live, same deployment `dep-dbalnujm8hqs73bi9s3g`; database health connected |
| Job 3, `jmax-toast-berts-rudds-daily` | Enabled, `15 10 * * *` | Temporarily disabled | Enabled; identity, schedule and command hash match |
| Job 4, `jmax-toast-papa-daily` | Enabled, `20 10 * * *` | Temporarily disabled | Enabled; identity, schedule and command hash match |

Five saved drain observations verified complete activity visibility and all three
reviewed LOGIN roles. Each found zero write transactions, zero queued HTTP
requests, zero running cron records and zero unfinished downstream Toast syncs.
The latest Toast sync records reported successful completion. One or two other
reviewed-login sessions remained connected, so no observation qualified as fully
drained; two consecutive qualifying observations were required.

Read-only session metadata showed `postgres` connections reported as `Supavisor`.
An observed idle connection began at 8:21:04 p.m. and last changed state at
8:22:50 p.m. Those times overlap this workflow's administrative checks, making
retained operator/pool connections a plausible explanation. **Ownership and pool
lifecycle are not proven by that timing or by the application name.** The check
did not establish an additional business writer, and it did not prove those
sessions harmless. No session was terminated or excluded to pass the guard.

The bounded drain ended at its 300-second limit. Original producer states were
then restored rather than retrying the backup or relaxing the session rule.

## Failures and recovery evidence

- The initial read-only preflight connection was lost before any pause. A fresh
  preflight succeeded and recorded the exact original job states.
- The first pause helper stalled before producing a pause-intent receipt. Only
  that workflow-owned local process was stopped. Independent reads confirmed both
  jobs remained enabled before a new bounded pause command; no mutation was
  blindly resent against an unknown job state.
- Browser screenshots were returned as JPEG bytes despite the requested local
  PNG filename. Original bytes were preserved and converted to actual PNG before
  proof hashing; the bookkeeping check was not weakened.
- The bounded pause and independent readback verified both named jobs disabled.
  After the held drain, a bounded resume and fresh readback verified their exact
  original enabled states. Render Resume restored the same API deployment; its
  free-instance wake-up completed and database health returned connected.
- Available Inventory tabs were at the sign-in screen. An authenticated app read
  remains pending; database health is not presented as authenticated acceptance.
  No credentials were entered or changed.

A fresh final read confirmed `purchasing.inventory_par_versions` absent, zero
ledger entries named `reviewed_inventory_pars`, and 55 installed ledger entries.
This is presence/count evidence, **not** a full current ledger-fingerprint,
accounting-row or Food Cost comparison. The historical $212.00 hosted accounting
control and $55.00 local fixture retain their earlier dated scope.

Private control journals and receipts remain in protected local JayMaxBuild
storage. Safe external evidence: `pr46-maintenance-closure-20261018.json`, restored
Render/API-health screenshots and five drain observations. Archives and keys from
earlier windows were preserved; none is relabeled as a fresh backup for this run.

## Next step

Investigate the administrative session's ownership and lifecycle read-only before
another outage. Establish whether closed operator connections remain visible
through Supavisor and how to distinguish them from application/manual writers.
Do not weaken the accepted guard, terminate unknown sessions, alter pool settings
or switch saved database endpoints to force progress. Any guard correction needs
local regression coverage, independent review and the usual PR approval process.

After resolving that prerequisite, request a **new** bounded window and fresh
writer confirmation; repeat drain, encrypted backup and disposable restore;
prepare a new exact plan and prompt separately before applying migration 31.
No current hosting, credentials, grants, connection settings or Companion
integration changes are authorized by this held window.
