# Hosted source-index maintenance plan — October 14, 2026

## Current follow-up and pre-operations gate

PR32 merged with owner approval at **7b61620**, refreshed documentation head
**3d1eacc**, after [all four exact-head checks passed](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/38674779748).
The next local follow-up adds allowlisted export diagnostic counts for completed
server aggregation, size-triggered cursor fallback and cursor-only relations.
Counts contain no table names; failed/incomplete relations are not counted.
They do not change archived fingerprints, command timeouts or hosted settings.
The 60-second client command budget applies to each aggregate statement; retain
the current budgets until a separately approved hosted rehearsal supplies evidence.
For that rehearsal, record fingerprint-phase duration, path counts, relation/row
counts and effective client/server limits. Compare with the earlier 158.9/181.0 s
observations only with their differing source and environment limits recorded;
local equivalence tests do not establish a speed improvement or the earlier cause.

For a completed default current-format export, expect `cursorOnlyRelations`
to equal the manifest's sequence count and all three completed counts to sum
to the manifest relation count. Zero fallbacks is expected for the previously
measured small dataset, not a permanent size invariant or a validity gate.
A nonzero fallback count identifies a safe full-cursor path to investigate for
timing, not corruption. Legacy or explicitly cursor-selected exports have
different expected cursor-only counts.

PR31 merged at **cb63129** after owner approval, with exact-head and merged-main
CI green. The old window remains closed. The
[bounded fingerprint follow-up](BOUNDED_FINGERPRINT_CHECKPOINT.md) is PR32, with
full reviewed-head CI green and owner approval to merge after documentation
refresh and current-head CI. No private operator runner with historical
commit pins is an approved execution path for a new window.

**OPEN — restricted deployed runtime credentials before operational use.** The
recorded live API owner connection is not protected by the inventory/account
role separation tested locally. Retain the current build configuration while
the owner coordinates with coworkers. A separate approved deployment workflow
must select the connection/pooler capacity, stage the two restricted connections
privately, update the actual deployed inventory/account pools, run positive and
negative permission/workflow smoke tests, and retain a verified configuration
rollback. Application permission checks and integrity constraints still apply;
this gate concerns the missing database-level restriction on the owner pool.
No connection cutover, role/grant change or paid add-on is approved by this note.

**Future hosted cancellation acceptance:** record the export reference from its
safe progress/result and verify the exact `jaymax-backup-<reference>` and
`jaymax-backup-<reference>-tool` sessions are absent after cancellation. Combine
this with the full writer/activity visibility guard; a pooled/reset label alone
cannot establish drain. If a session remains or visibility is insufficient,
hold and investigate ownership, backend start/identity and downstream activity.
Do not terminate by role or broad application-name prefix. This is a future
read-only acceptance step inside a newly approved rehearsal, not proof supplied
by local direct-PostgreSQL cancellation tests.

Retained backup/key artifacts now have an ACL-verified private metadata inventory,
including the known cancelled recapture key. No key contents or business rows
were read, and nothing was deleted. Counts, inventory hash and review limits are
in the [follow-up checkpoint](BOUNDED_FINGERPRINT_CHECKPOINT.md). Any later cleanup
must resolve provenance/retention deliberately; key-only presence is not proof
that a key is safe to discard.

**Local follow-up:** see the
[backup reliability review](BACKUP_EXPORT_RELIABILITY_REVIEW.md). A future fresh
export must use canonical migration names and an explicit budget that leaves
time for cleanup, restore, plan review and recovery. The helper's 600-second
default is not permission to exceed a window. Verify the uniquely labelled
export connection and tool have drained after cancellation; do not terminate
other postgres/platform sessions to make a guard pass. Review/merge and a new
window approval remain pending separately from these local changes.

**Execution update:** the owner approved 7:32:32–8:17:32 p.m. EDT. The API/jobs
were paused, reviewed writers drained, and a fresh encrypted backup/restore
passed. Plan qualification rejected Windows migration-path labels; a corrected
recapture stalled and was cancelled. API/jobs were restored and verified, the
window was closed early at 8:09:20 p.m. EDT, and no index or ledger change was
attempted. See the [current checkpoint](HOSTED_SOURCE_INDEX_PREFLIGHT_CHECKPOINT.md)
for evidence and offline prerequisites before a new window. The proposal below
is retained as historical planning context; it is not an active approval.

Status: **planning only; no writer pause, job change, plan approval or hosted DDL**.
Proposed duration: **45 minutes**, with actual timezone-aware start/end still
requiring owner approval. The private planning draft is deliberately not an
executable hosted v2 plan and has no delivery version or application authorization.

## Verified baseline and evidence

- Inventory PR30 merge: `6e08ba7fca10d640ce311d0a9a10e75aa3838dfc`, exact-head and
  merged-main CI green. Local documentation baseline before this plan: `4b8254e`.
- Fresh rehearsal: 369.219-second encrypted export and 41.297-second disposable
  restore; 27,271 rows, 120 relation fingerprints and 13 catalog groups matched.
  Protected archive/key and receipts were reverified. Local cleanup passed.
- Backup creation: October 14 at **7:07:51 p.m. EDT**. This proves the rehearsal,
  but cannot substitute for a backup created inside a later maintenance window:
  `load_evidence` in `tools/ops/hosted_additive_index.py` explicitly requires that
  ordering. Recapture and restore after the approved writer stop/drain.
- Refreshed database observation at **7:21:08 p.m. EDT**: original 54 ledger rows;
  source index absent; anon/authenticated ledger denial preserved; complete
  activity visibility; no observed application write transaction. These are
  point-in-time observations, not a claim that writers are stopped.
- Private writer receipt SHA-256:
  `d3e62c2e3d50dd43445d1fcf3a87770edac2e15f9f4ed2ce73b2d29af700c78f`.
- Private non-executable planning packet SHA-256:
  `1da42fcc3401b1a52d78003cd4c3b2949a972c1725cdc5c378aff4470b970ee1`.
- Separately extracted rehearsal restore-receipt SHA-256:
  `c8cb01e57c6c777fe1e2974261b91fbcb422b8de8108d3b47f244ed9d8f24f50`.
  Its verified archive binding is historical rehearsal evidence, not permission
  to reuse it for a future window.

## Writer inventory and proposed controls

| Writer or entry point | Verified state | Proposed control, only after approval |
| --- | --- | --- |
| Render `jaymax-api`, `srv-dauimuugekts73ek9lr0` | Live at PR30 merge; main auto-deploy; Python/uvicorn; Free instance | Suspend this exact web service; prevent concurrent deployments and manual restarts; resume after reconciliation |
| Deployed API database role | Render DATABASE_URL identity is `postgres` for the designated project, pooler port 6543 | Include `postgres` in writer observations; do not change saved connections or roles in this maintenance slice |
| Two restricted local runtime credentials | Both roles exist and were quiet, but they are not the deployed Render identity | Keep local app/script instances disconnected; preserve credentials unchanged |
| Cron job 3: `jmax-toast-berts-rudds-daily` | Active; `15 10 * * *`; database `postgres`; HTTP request | Record exact configuration/hash, temporarily set this job inactive, drain downstream work, restore original active state |
| Cron job 4: `jmax-toast-papa-daily` | Active; `20 10 * * *`; database `postgres`; HTTP request | Same control, limited to this exact job |
| Companion | Owner says it will write in future and believes it is not doing so yet; current candidate/Git workflow documents keep hosted application and Inventory adoption separate | Treat as potential; confirm no connected worker, local script, preview or migration is writing during the window; no Companion edits or integration |
| Frontend/static site and existing browser tabs | User-facing request entry points to the API | Leave static hosting unchanged; avoid submissions during outage; backend suspension blocks this route but not direct Supabase clients |
| SQL editor, direct clients, Edge Functions and other integrations | Completeness not proven by process/session snapshots | Confirm no manual writes, migration jobs or independently triggered imports; identify any additional producer before execution |

The Render environment was inspected without recording the URL/password. The
credential was re-hidden immediately; no environment value was changed. No
separate AUXILIARY_DATABASE_URL or linked environment group was listed on the
observed service. Do not infer deployed privilege separation from the local pair.
Keep the current hosting/connection standard; credential cutover is a later
coordinated decision.

The refreshed writer guard includes the deployed `postgres` role plus the two
local roles. It sees **two idle `postgres` sessions with a Supavisor label** and
holds. Six other idle sessions use platform roles (`authenticator`, `pgbouncer`,
`supabase_admin`); labels and addresses are excluded from public evidence except
for safe classifications. Pooler server sessions are not proof of live Render
client ownership. Suspension must be followed by another refreshed guard; do not
kill platform sessions or weaken the guard if pooled sessions remain. Hold and
resolve attribution/drain behavior instead.

`cron.timezone` is **GMT**, observed live. On October 14, 2026, the jobs' 10:15 and
10:20 GMT times correspond to **6:15 and 6:20 a.m. EDT**. Preserve the cron strings
and timezone; these local equivalents change with daylight saving time.

At observation, no recent cron run was in progress and `net.http_request_queue`
contained zero requests. The commands dispatch HTTP work: pg_net removes queued
requests when execution begins, so queue emptiness alone cannot prove a remote
Edge Function or import has finished. Check the relevant run/completion evidence
and live write/session guards after pausing the producers; do not trigger jobs to
test this. [Supabase pg_net documentation](https://supabase.com/docs/guides/database/extensions/pg_net).

The service's Free settings expose **Suspend Web Service**. Paid maintenance mode
is unavailable here and would leave the process running even if purchased.
Use the existing suspend/resume mechanism after approval; no paid upgrade is
part of this plan. [Render maintenance mode](https://render.com/docs/maintenance-mode),
[suspend API](https://api-docs.render.com/reference/suspend-service-1).

## Proposed 45-minute sequence

The rehearsal establishes an approximately seven-minute backup/restore stage;
planning, fresh fingerprint comparisons and coordination add time. The estimates
below are planning allowances, not measured guarantees for the whole operation.

1. **Minutes 0–5: start and drain.** Record approved start/end/reference and exact
   original service/job states. Confirm Companion/other producers disconnected.
   Suspend the exact API service and temporarily disable only jobs 3 and 4 after
   confirming their IDs, schedules, usernames and command hashes still match.
   Wait for HTTP/import completion and refresh activity/write guards. No table
   locks or application DDL while drain is unresolved.
2. **Minutes 5–14: fresh backup and restore.** Capture a new encrypted export and
   isolated restore inside the approved window. Reverify all hashes, fingerprints,
   private ACLs and cleanup; retain the new standalone restore receipt. A failed
   or partial archive cannot qualify. Do not reuse the pre-window rehearsal.
3. **Minutes 14–24: read-only hosted dry-run and owner review.** Prepare the actual
   v2 plan from the new backup/receipt, original 29-file installation evidence,
   current 54-row ledger, exact target, reviewed login list and current migration
   hashes. Record its exact SHA-256. Present that concrete plan for owner approval;
   window approval alone does not authorize applying it.
4. **Minutes 24–36: one additive change and reconciliation, if approved.** Apply
   only the reviewed source-lookup index and one ledger entry with the guarded
   adapter. Retain original installation/history; never replay the fresh installer.
   Use independent reconciliation and confirm backed-up business rows/sequences,
   permissions and unrelated metadata are preserved. Keep the fictional accounting
   control separate from real operational data.
5. **Minutes 36–45: resume and verify.** Once the outcome is known and verified,
   restore only the previously active jobs and resume the API to its recorded
   configuration. Check health plus an ordinary authenticated read; do not use a
   successful health response alone as proof of connected data routes. Record
   original/final states, source/index/ledger evidence and writer resumption.

The adapter enforces a 10–60-minute active window, reviewed stop/drain assertions,
and bounded probes/locks/DDL/operations. Do not invent true stop/drain flags to
generate a plan. Do not squeeze a new apply into an expiring window; if owner
review or drain consumes the budget, hold before DDL and reschedule.

On any uncertain COMMIT or connection loss during application, keep writers
paused and independently reconcile the pinned plan; never retry DDL blindly or
drop/replay history to repair an ambiguous outcome. Report any interruption to
the owner and follow the existing recovery protocol before resumption. A clean
pre-apply abort can restore recorded writer states without changing the index.

## Window selection and remaining decisions

Render's dashboard currently advertises critical-infrastructure maintenance on
**October 14 at 9:00 p.m. EDT**. Its linked status incident could not be retrieved
through the web tool; the dashboard notice is the observed evidence. Recheck the
provider status before execution. Do not overlap that event: if starting tonight,
start a 45-minute window no later than **8:00 p.m. EDT** and leave at least
15 minutes afterward. Otherwise use a later owner-selected window after vendor
status is clear. Nothing here schedules or starts maintenance automatically.

Before execution, the owner still needs to confirm writer completeness, including
Companion, approve exact timestamps and the listed temporary stop/resume actions,
and then separately approve the generated v2 plan's exact hash. No permission,
credential, network, paid hosting, schema-integration or permanent configuration
change is included. This plan and its private packet are ready for review; all
execution flags remain false.
