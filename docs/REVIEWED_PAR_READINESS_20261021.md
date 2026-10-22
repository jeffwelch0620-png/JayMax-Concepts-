# Reviewed-par readiness review — October 21, 2026

**Subsequent accepted work:** the owner separately authorized the
[bounded submitted par recovery fix](PAR_SAVE_RELOAD_RECOVERY.md), its reviewed
local-discard amendment and PR53 merge `46461e5`; reviewed-head and merged-main
CI passed. The limitation below describes the earlier PR51 baseline. The
[current installation and acceptance proposal](REVIEWED_PAR_INSTALL_ACCEPTANCE_PLAN_20261021.md)
preserves this dated artifact inspection, unchanged install SQL and separate
hosted approval boundaries. No installation or live acceptance is implied.

## Decision and scope

**Recovery qualification passed; full installation and operational readiness are
not established.** Keep hosted work, credentials, grants and schema changes on
owner hold. Par editing stays frozen and ordering manual. This review creates
no executable migration plan, delivery version, permission candidate or rollout
approval. It neither opens a database connection nor starts a local server.

Accepted source is PR51 merge `07daa299b4bc99e33a1b959c201e0801458f9e62`,
tree-identical to reviewed `b331d31`. The accepted PR52 store-wide PIN controls
are included. Reviewed-head CI [39674794412](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/39674794412)
and merged-main CI [39686163775](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/39686163775)
each passed four checks: 1,034 frontend tests / 82 suites plus strict build,
1,176 Windows offline cases and 238 backend/disposable PostgreSQL cases.
These are earlier CI results, not fresh tests of this documentation review;
the profiles overlap and must not be added as unique coverage.

## Completed evidence, with boundaries

| Evidence | Verified result | Limit |
| --- | --- | --- |
| October 21 role observation | All 16 scoped checks passed: six backend checks for each of two reviewed logins plus four independent ledger denials; no supplemental findings. | Not a complete client-private-schema audit, installer readiness pass, runtime RLS cutover or successful personal-login test. No new hosted check was made for this review. |
| Fresh maintenance | Owner approved 7:45:47–8:30:47 p.m. Eastern; two strict drain observations at 7:51:47 and 7:52:43, with another pre-export guard. | Producer pause and owner no-other-writes commitment applied to that window only. |
| Fresh application backup | Authenticated encrypted archive created at 7:55:48 p.m. Eastern; export took 147.078 seconds. | Six application schemas only: public, purchasing, actual_inventory, prep_inventory, integrations and supabase_migrations. |
| Disposable restore | 120 tables, 45,638 rows and 13 catalog groups matched in 25.750 seconds; nonempty-target refusal and both selected restored-access guards passed. | PostgreSQL 17.6 source / 17.11 local: major matches, patch differs. Restored identities are NOLOGIN stubs; password and role-membership recovery was not demonstrated. |
| Recovery | Database and 17 new role stubs removed; original local database/role inventory restored, owned local server stopped, no cleanup errors. Toast jobs 3/4 restored and verified enabled. Owner confirmed API Live at 07daa29. | API control/recovery evidence is the owner's manual Render observation, not automated UI or functional endpoint acceptance. |
| Window closure | Closed at 8:02:45 p.m. Eastern, within the deadline. Ordinary manual writes may resume. | No active maintenance permission or current drained-writer claim remains. |

The prior 7:21–7:34 p.m. attempt closed without pausing producers or taking a
backup. It is not counted as a successful backup attempt or reused approval.
The successful backup is dated recovery evidence after producers resume; a later
schema window requires a fresh approved pause/drain and fresh backup/restore.
Managed Supabase Auth/Storage/Vault/cron recovery, closed-period runtime replay,
full recovery retention/monitoring and operational release remain unverified.

## This offline inspection

An external local audit authenticated the retained encrypted bundle, checked its
archive digest and source bindings, and inspected its archive table of contents.
`pg_restore --list` and selected ledger text output were captured in memory;
no DSN, restore target or SQL execution was used. Network connection calls were
disabled inside that audit process. No credentials or role names are published.

| Saved-artifact check | Result |
| --- | --- |
| Installer source bindings | All 49 recorded installer-source hashes match accepted source. |
| Migration source bindings | All 31 native migration hashes match; the bundle captures 32 migration files across the native and Supabase folders. These counts are different scopes. |
| Pending SQL / reference | Raw SQL `84814517f75bb58940a36facdbf5a7934036ff5b388e97a820038e837416506e`; executed-body reference `3a189a8b2a352cbd560cea88194dbde1940f160a54e7bcd4616d719c47b88c48`; catalog reference `8a18effb17929604c76817ed7478b112033df4886e4434c0c1e6a4cce01e8e17` all match. No SQL was executed by this inspection. |
| Archived ledger | 55 unique versions; maximum archived version `20261015175921`. Full original-delivery/index name/body/fingerprint reconciliation was not rerun. No new delivery version was allocated. |
| Par absence / names | `purchasing.inventory_par_versions` is absent from the snapshot; zero matches for its reviewed table/index/guard names in the archive TOC. This is snapshot evidence, not a fresh live collision check. |
| Existing dependencies | Unit profiles, item bases, store items/state, count snapshots, period closures and purchasing posting batches are present in the saved table inventory. Presence does not prove effective privilege, row policy, trigger or unit-profile validity. |
| Source index | Its name appears once in the TOC. Exact current definition, valid/ready/live flags and installed ledger-body reconciliation remain installer checks. |

The offline audit first refused its ledger parser because Windows text output
used CRLF. Only the audit's in-memory text parser was corrected; the retained
archive and source SQL were unchanged. The corrected audit passed. The initial
refusal is not described as a database, backup or installer failure.

## Findings and recommendations

| Finding | Meaning and recommendation |
| --- | --- |
| Installation checks remain unrun | The narrow role result and successful restore do not cover full browser/client private-table and column denial, installed ledger/name/body reconciliation, readiness warnings, trigger/constraint states, exact index flags or current backup/baseline equality. Preserve every existing guard. When hosted work is separately authorized, the full preparer must pass; do not label an unvisited check failed or passed. |
| O1 is a separate runtime gate | The frozen 30-migration permission candidate excludes par history. The par SQL enables RLS but creates no runtime policies or grants. A future restricted deployment needs explicit SELECT/INSERT, trusted-backend RLS, invoker profile/base reads, store-state revision writes and existing SHARE-lock dependencies. No history UPDATE/DELETE/TRUNCATE or browser access. This is not a finding that O1 must be applied to the existing owner-connected build before owner installation; do not silently turn a runtime-cutover gate into a different installer predicate. |
| Security acceptance remains open (G04) | The accepted store-budget fix has source/CI evidence. Successful personal login, configured-PIN flows, old-token rejection and limiter/recovery behavior still require separately authorized acceptance. Keep this an Inventory security track, independent of Companion adoption. No credential change or live test is included here. |
| Par request recovery is bounded | The current contract retains uncertain commands within the signed-in app instance; it does not promise durable reload/sign-in recovery. Post-install acceptance must distinguish saved-value persistence from retained unsaved/pending commands. Recommend a separate local design review of that limitation before operational use; do not bundle a new recovery implementation into documentation work. |
| Current summaries had drifted | README and some JMAX status/remaining-work entries still said PR51 was awaiting merge, deployment was unverified or the new backup was pending. Reconcile current summaries, retain earlier dated evidence and distinguish owner deployment evidence from functional acceptance. |

No new implementation defect was demonstrated by this artifact-only review.
The findings identify explicit remaining evidence and release requirements;
they are not permission repairs or reasons to repeat an already completed backup
before there is a new, approved installation activity.

## Rollout and recovery checklist — for a later separately approved workflow

1. Reconfirm accepted source and all writers, including Companion/manual scripts.
   Obtain new explicit hosted preparation/window permission; record the actual
   deadline and recovery reserve. Do not reuse October 21 controls or approval.
2. Verify local process readiness, record exact producer original states, pause
   approved writers, prove strict drain, and take a fresh encrypted application
   backup with matching disposable restore. Preserve current timeout budgets.
3. Run the existing read-only par preparer only when authorized. Reconcile the
   original delivery plus source index, all installed ledger versions, explicit
   role classifications, complete readiness and exact current catalog/baseline.
   Any hold stops the workflow; no role/grant repair, guard relaxation or timeout
   increase is implicit. If no application approval is available, restore the
   writers and close the window.
4. Present the concrete plan/hash, target, allowed additive delta, receipts,
   timeouts and recovery route. Obtain separate owner approval before applying.
   Application code merge alone never applies the table or authorizes SQL.
5. After known commit, independently reconcile the exact empty par table/catalog
   delta plus one ledger entry and unchanged old data/security. If commit outcome
   is uncertain, retain the exact plan and evidence, never retry DDL automatically
   or kill unrelated sessions, and use the existing reconciler. Do not restore
   writers into an unknown migration outcome without reviewed recovery handling.
6. Restore original producers within the approved window. Keep par editing
   unavailable on installation, permission or route failure; ordering remains
   manual. Additive history is retained after a known install; destructive repair,
   backup restoration or application rollback needs its own approval.
7. Run separately approved fictional acceptance below. O1, G04 and operational
   release remain their own gates; do not adopt Companion services/schema here.

## Required par acceptance matrix — proposed, not newly run

| Case | Expected result |
| --- | --- |
| Storage unavailable / legacy references | Explicit unavailable/unconfirmed state; no auto-backfill, inferred unit or confirmation of an old/default zero; manual ordering stays available. |
| Confirm / zero / exact units | Current verified physical count profile, explicit quantity including confirmed zero, exact derived base quantity, actor/time/note retained together. |
| Save / fresh page / history | Saved values and immutable versions persist exactly after a fresh read; supplier changes never reinterpret the physical target or fill order quantities. This does not claim pending-command reload recovery. |
| Profile changes / withdrawal | Old target becomes Needs review; reconfirmation uses the current count profile. Withdrawal appends history while retaining predecessor quantities. |
| Retry / conflict / failed read | Same-body retry adds no duplicate; changed body/key conflicts and stale revisions preserve draft data. Confirmed save followed by failed refresh remains a read error, not permission to post again. |
| Actor/location / restricted role | Personal manager authority and location checks enforced; future restricted-role reads, writes and invoker dependencies pass with negative cross-location/browser/history-mutation checks. |
| Accounting independence | Purchased-item count and received purchases, explicit opening/closing values, separate taxes/fees and the agreed dated Food Cost control remain unchanged. Prep/waste/sales and pars do not rewrite Track 1. No new Food Cost runtime comparison was performed by this review. |

## Evidence handling and validation

Retained backup/restore receipt SHA-256:
`69858f220f8a636ee263f8b6d1bc8bd43e700b35bebfd5eaf4116d6ed973b3fa`.
Window closure receipt SHA-256:
`28b78cf48fe8725663514b2d001e0b0e9e96f1bbd3d56d0f70d5b8c6c181a7f0`.
Encrypted artifact SHA-256:
`f38d332e3e14ed472f00b5522dc9bc844737cbfc44299fef6de4bfba60866c6a`.
Real archive/key locations, identities, receipt paths and row values remain in
protected local operator storage outside Git/Pages/Drive.

The corrected offline artifact audit passed. Generated review guides matched
source, all 10 added relative Markdown links resolved, and `git diff --check`
passed. This slice runs no frontend/backend/database suite,
Supabase/Render request or live acceptance test. Historical CI and the completed
backup/restore are reported separately. No GitHub push, PR, merge or deployment
is authorized by this documentation review.

References: [installer](HOSTED_REVIEWED_PAR_INSTALLER.md),
[hosted plan](HOSTED_REVIEWED_PAR_MIGRATION_PLAN.md),
[par contract](REVIEWED_INVENTORY_PARS.md),
[role preflight scope](PAR_ROLE_PREFLIGHT_PACKET.md),
[runtime dependencies](RUNTIME_ROLE_PERMISSION_ASSESSMENT.md),
[staff security acceptance](STAFF_PIN_STORE_BUDGET.md).
