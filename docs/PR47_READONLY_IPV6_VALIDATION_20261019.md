# Read-only direct IPv6 validation October 19 2026

Status: **passed within the separately approved read-only scope** on accepted
PR47 merge `a7270ca`. No API/Toast pause, backup, schema/data write, grant change,
credential rotation or app/Render configuration change occurred. The next gate
is approval of a new maintenance window. The owner reconfirmed the three writers
and their controls were refreshed read-only after the validation.

## Observed result

The owner approved the [prepared two-client check](PR47_DIRECT_MAINTENANCE_PREFLIGHT.md).
At approximately 12:03 a.m. Eastern on October 19, two sequential connections
through accepted `maintenance_connection.connect(..., readonly=True)` passed
native IPv6, certificate/hostname-verified TLS and effective session validation.
The explicit read-only probes verified the designated postgres actor/database,
PostgreSQL 17 and full activity visibility. No pooler fallback or retry was used.

| Check | Result and scope |
| --- | --- |
| Private configuration | A new separate ACL-checked maintenance file was created under private local storage using the existing owner credential. It contains only MAINTENANCE_DATABASE_URL, with interpolation disabled; no credential value or path is included here. |
| First connection cleanup | Its owned client closed. The second direct read-only observer confirmed that the exact first backend identity, PID plus backend start, was absent. |
| Observer cleanup | Its owned client closed successfully. No third database client was opened, so independent server-side disappearance of the observer is not claimed. |
| Limits | Exactly two connection attempts; 3.859 seconds of observation within the 120-second budget. Existing 20-second connect/probe and five-second owned cleanup bounds remained in effect. No cleanup hold. |
| Dump routing | Accepted IPv6-only DNS/PGHOSTADDR settings retained canonical PGHOST, verify-full and read-only options. No pg_dump or backup was performed. |
| Dated presence/count | Par table absent; ledger count 55. This is not a full fingerprint, accounting comparison, strict writer-drain proof or permission to reuse an earlier baseline. |
| Preservation | Original owner/preflight input hashes unchanged. No SQL backend signals, writer controls, role changes, operational writes or configuration cutover. |

Protected receipt/config readback verified ACLs, exact target shape, accepted
source hashes and the two-client result without another database connection.
The safe local evidence is `pr47-readonly-ipv6-20261019T040326940281Z.json`.
Private receipt SHA-256:
`f62aff9610f33e0ae8fad192db40e4ddbbdef32557a48b00d127e6c2ae81ac77`.
The one-use orchestration script SHA-256 is
`aeaab03c5c78bfc8a01677b515149fba112e5d53a4e56adeb9097c7d945f8139`.
Credentials and full connection strings remain outside Git and shared Pages.

## Fresh writer controls and proposed window

The owner reconfirmed on October 19 that only `jaymax-api` and the two Toast jobs
write to this project; Companion remains local-only. Render's read-only dashboard
shows API `srv-dauimuugekts73ek9lr0` Live on `a7270ca`, automatic deployment
`dep-dbap7km7bikc73esuat0` (1m51s). No manual deployment or setting changed.

A separate read-only preparation connection, after that owner confirmation,
refreshed these exact jobs and then closed. This is separate from the earlier
two-client validation; it does not change that test's connection count.

| Producer | Observed original state | Identity pin |
| --- | --- | --- |
| jaymax-api | Live on a7270ca | srv-dauimuugekts73ek9lr0 |
| Bert's/Rudd's Toast | Enabled | Job 3, jmax-toast-berts-rudds-daily, stored schedule 15 10 * * * |
| Papa Leoni's Toast | Enabled | Job 4, jmax-toast-papa-daily, stored schedule 20 10 * * * |

The two command hashes match the prior reviewed definitions:
`fdb988cb4d9268fb68a45bbde2f9c757283dedd5e2d316d9bda495d6e8c1c7f3`
and `85f1d8764080da7243744ae08e1e631afb29b19353fc2584acc60e46db1481fb`.
No other active cron job was observed. HTTP queue, active cron runs and unfinished
Toast runs were zero at that snapshot; the producers remain active, so this is
not writer-drain proof. Safe evidence:
`pr47-writer-control-inventory-20261019T040809681028Z.json`.
Local `pg_dump` and `pg_restore` report PostgreSQL 17.11.

Propose a **new 45-minute window starting only when owner approval is
acknowledged**, with its actual timezone-aware deadline recorded then. Approval
must include no other manual SQL/script writes. Recheck source, controls and
original states before pausing only this API and these two jobs. Use the accepted
direct maintenance helper for all operator observations; retain strict writer
visibility, session, queue and downstream-completion guards.

After drain, take a fresh encrypted application backup and verify a disposable
local restore. Prepare a new source/baseline-bound par plan and prompt separately
for its exact SHA-256 before application. Keep at least 660 seconds before any
later approved apply; otherwise restore the writers and leave DDL held. Restore
the API to Live and both jobs to their recorded original enabled states before
the window deadline. Refresh changed/stale evidence; never reuse the closed
October 18 window, its controllers, dates or approvals. No new window is active.

## What this closes and what remains

This validates the accepted helper's read-only IPv6/TLS/session path against
the designated build database and verifies the first backend's disappearance.
It does not validate a fresh hosted encrypted export/restore, apply-mode session,
schema installation, par routes or complete accounting preservation.

Writer confirmation and the control snapshot above qualify preparation, not a
pause. Reconfirm changed circumstances, manual SQL/scripts and recovery states
when the new window starts. Keep strict writer exclusion: retained unidentified
or reassigned sessions still hold.

Only after that new approval may the producers be paused and drain proven,
followed by a fresh encrypted backup and disposable restore. Present the new
executable par plan's exact SHA-256 for separate application approval. No window,
backup, delivery version or plan approval is created by this result. The October
18 window remains closed. Par editing stays held and ordering remains manual.

## Code and documentation validation

Reviewed-head and merged-main CI for PR47 remain green with an identical source
tree: 1,026 frontend tests/strict build, 182 backend cases and 1,013 Windows cases.
These counts overlap previous local tests and are not added as unique coverage.
This continuation changes documentation only; code, SQL/snapshot, grants, app
connections and Render settings match accepted merge `a7270ca`. Documentation
links, generated guides and whitespace are checked before the local commit.
