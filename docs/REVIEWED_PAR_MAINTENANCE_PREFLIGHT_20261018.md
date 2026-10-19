# Reviewed-par maintenance preflight - October 18, 2026

Status: **PR46 merged and verified; local maintenance inputs prepared. No active
window, fresh hosted backup, executable plan hash or schema-application approval.**
This checkpoint does not authorize pausing writers, taking a hosted backup or
applying SQL. The owner reconfirmed the writer inventory below; a new bounded
window and no-manual-writes commitment are the next approval.

## Accepted implementation and CI

- Owner-approved [PR46](https://github.com/jeffwelch0620-png/JayMax-Concepts-/pull/46)
  merged from tested head `31f65c346a1abee3990fb19c0e955778d45b7e07` as
  **`f762808b22bae680c40026af01a69c0226f5d2c7`**, October 18 at 7:53:28 p.m. Eastern.
- The accepted merge has exactly the tested head's file tree. Both
  [reviewed-head CI 39177342587](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/39177342587)
  and [merged-main CI 39178376304](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/39178376304)
  passed all four checks: 1,026 frontend tests/80 suites and strict build;
  121 backend methods plus 60 subtests (181 reported cases); 328 Windows
  methods plus 617 subtests (945 cases); aggregate Inventory CI.
- The [installer runbook](HOSTED_REVIEWED_PAR_INSTALLER.md) retains the separate
  69-case local selection/corrected restore evidence and earlier failed attempts.
  Overlapping local and CI results are not added as unique coverage.

## Read-only deployment evidence

Render's API deployment `dep-dbalnujm8hqs73bi9s3g` is **Live on `f762808`**,
auto-deployed at 7:53:30 p.m. Eastern, duration 2m18s. Service:
`srv-dauimuugekts73ek9lr0` (`jaymax-api`). No manual deployment, suspension,
environment change or job control was used.

The frontend remains **Live on PR45 `9dac63e`**, deployment
`dep-dbaj6gpsrm7s73ahimtg`. Its observed Render root directory is `frontend/`;
the settings explain that changes outside the root do not trigger auto-deploy.
The entire `frontend/` tree is identical between PR45 and PR46. This is an
unchanged frontend, not evidence of a new frontend deployment on `f762808`.
No manual redeploy or hosting change is needed for the tooling-only slice.

Deployment status is not proof of authenticated par behavior or a fresh hosted
database comparison. The accepted temporary par-editing freeze and manual
ordering remain in place.

## Owner-confirmed writer scope

The owner reconfirmed: **only `jaymax-api` and the two Toast jobs write to this
Supabase project; Companion remains local-only.** Before starting any window,
also obtain a commitment to stop manual SQL/scripts and reconfirm this if the
work resumes later or circumstances change.

| Control | Last recorded identity; refresh before mutation |
| --- | --- |
| Render API | `srv-dauimuugekts73ek9lr0`, `jaymax-api`, now Live on `f762808` |
| Bert's/Rudd's Toast job | Job 3, `jmax-toast-berts-rudds-daily`, schedule `15 10 * * *` |
| Papa Leoni's Toast job | Job 4, `jmax-toast-papa-daily`, schedule `20 10 * * *` |

Cron IDs, schedules, command hashes, activity and enabled states above are still
historical until read from the live database in the newly approved window.
Record actual original states and refuse changed identities or additional
writers. Do not assume all jobs are enabled, terminate unknown sessions, or
reuse the historical PR34 controller's expired dates/approval bookkeeping.

## Completed local-only input checks

The local preparation made **no database connection** and no service/job,
schema, credential, grant or connection-setting change. Database connection/pool
entry points were guarded against use during this preparation.

- ACL-checked retained original installation receipt, source-index review,
  descriptor and executable source-index envelope agree by their recorded hashes.
  The new par core validates the original 29-file delivery and retained index
  evidence against unchanged accepted sources.
- The retained index envelope's unchanged `core` was copied into a **new**
  protected private file. Original evidence was preserved. Extracted core SHA-256:
  `6401ef41401caa04fd006f57cd5b19aae02c0a5c899087ff605bee0a3e5c2aa2`.
- The private administrative target shape matches the retained designated
  project/endpoint/actor and requires certificate/hostname verification. This
  constructs the TLS policy locally; **no live handshake or login was tested**.
- The pending review includes four denied-client roles and three reviewed writer
  login roles, retaining the two private local backend credentials in the checks.
  No credential values, full URLs or private artifact paths belong in Git/Pages.
- New artifacts under ACL-protected `%LOCALAPPDATA%/JayMaxBuild/backups` were
  read back through the same private-file guards. The pending review deliberately
  has placeholder dates/backup/delivery version, `allWritersStopped: false` and
  `inFlightDrained: false`; the adapter refuses it as non-executable.
- Local evidence: `reviewed-par-maintenance-local-preflight-20261018T235916964980Z.json`.
  Private preflight SHA-256:
  `4adc5f989a61fdb98a27ea206ff9624454f718c7f7ed4951006f674442f1f2e8`.

The retained history expects 55 ledger entries, as recorded in the completed
October 15 window. **This is historical evidence, not a fresh hosted ledger
read.** Unexpected history, existing/partial par objects or other drift must hold
the new operation; do not repair history or replay the original installer.

## Exact schema boundary remains unchanged

Only migration 31, `20261018_reviewed_inventory_pars.sql`, is eligible:

- Raw SHA-256 `84814517f75bb58940a36facdbf5a7934036ff5b388e97a820038e837416506e`.
- Body SHA-256 `3a189a8b2a352cbd560cea88194dbde1940f160a54e7bcd4616d719c47b88c48`.
- PostgreSQL 17 catalog reference SHA-256
  `8a18effb17929604c76817ed7478b112033df4886e4434c0c1e6a4cce01e8e17`.

It permits the reviewed empty `purchasing.inventory_par_versions` table and
exact catalog delta plus one correctly named/body-bound ledger entry. Existing
rows, sequences, catalog/security, role attributes/memberships, column/default
privileges and history must match. No old pars are backfilled or confirmed.
Restricted-role grants/RLS, credential cutover, login/UI redesign and broader
integration remain separate workflows. The SQL remains unapplied by this workflow.

## Proposed next window - separate approval required

Propose a **new 45-minute window**, with actual start/deadline recorded only after
owner approval. Approval covers temporary suspension of the exact API and two
named jobs, fresh writer-drain checks, encrypted application backup and disposable
local restore. It must also include no other manual writes during the window.
It does **not** authorize the schema application.

1. Verify the accepted source/configuration and administrative connection, exact
   API/job identities, original states and ability to restore them. If these
   cannot be established, stop before pausing anything.
2. Pause only approved producers; verify full session visibility, known-login
   drain, absence of unknown write transactions and downstream Toast completion.
   A quiet API or empty HTTP queue alone is insufficient. Do not kill sessions.
3. Take a fresh authenticated encrypted application backup after drain, bind it to
   current sources, and verify a disposable PostgreSQL restore including ledger,
   rows/sequences/catalog/security. Preserve original private archives and keys.
4. Generate the new par adapter's read-only concrete plan. Choose a new delivery
   version only after live ledger verification; validate all current sources,
   retained history, fresh backup, allowed delta and remaining deadline.
5. **Prompt the owner with the exact executable plan SHA-256 before application.**
   Keep application held if approval is absent. At least 660 seconds must remain
   before apply: 600-second operation budget plus one-minute recovery reserve.
   If review consumes the safe budget, restore writers and arrange another window.
6. Apply only after that later approval; independently reconcile any outcome before
   restoring writers. Restore each producer to its recorded original state and
   close the window within the deadline, or report a recovery hold immediately.

Use the [hosted plan's failure/recovery policy](HOSTED_REVIEWED_PAR_MIGRATION_PLAN.md)
and [manual adapter contract](HOSTED_REVIEWED_PAR_INSTALLER.md). No window is
scheduled, no executable plan is asserted, and silence is not approval.

## Validation of this preparation

The continuation changes documentation only. Generated review guides, 193
relative documentation links and whitespace pass; application, tooling, SQL,
workflow and runtime-permission sources match accepted merge `f762808`.
The fresh local private-input preparation passed its guarded readback and
non-executable-template checks. Full application/database suites are not rerun
for prose-only edits; the reviewed-head/merged-main CI above is separate exact
accepted-source evidence. No new implementation PR is required for a maintenance
window that uses the already accepted tooling.
