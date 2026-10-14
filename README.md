# JayMax Restaurant Group — Inventory / Prep / Food-Costing App

## PR30 review amendments — October 14, 2026

Unexpected limit metadata no longer aborts backup export: valid observations
remain, unsupported ones are explicitly uncaptured, and `limitReadHeld` records
the diagnostic gap. Actual database/snapshot failures still stop export. Held
receipts identify retained private artifacts with boolean-only flags; they expose
no paths or key contents. PostgreSQL settings do not show the pooler's own limits.
The original PR30 head has four green CI checks (689 frontend tests, 695 offline
cases, 73 database cases). The amendments pass **700 offline cases**; fresh
published-head CI is required before the
owner-authorized merge. Hosted backup/restore and index application remain held.
See the [checkpoint](docs/HOSTED_SOURCE_INDEX_PREFLIGHT_CHECKPOINT.md).

## Backup artifact acceptance and diagnostic preparation — October 14, 2026

[PR29](https://github.com/jeffwelch0620-png/JayMax-Concepts-/pull/29) merged with
owner approval at **6f27edc**; all four
[merged-main checks pass](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/38640974919).
The next local follow-up publishes a final backup filename only after successful
verification/cleanup, rejects receipt fields in additive plans, and brings safe
SQLSTATE/cleanup categories plus phase timings to the standalone backup CLI.
Diagnostics observe effective limits without changing them. Local validation
passes **695 offline cases** and **3 targeted database cases across the initial
run and export rerun**; the checkpoint retains the initial parser failure and
its correction. The test server is stopped. This follow-up is ready for draft
review; no new hosted rehearsal or index application has occurred.
See the [current checkpoint](docs/HOSTED_SOURCE_INDEX_PREFLIGHT_CHECKPOINT.md).

## Read-only receipt and cleanup follow-up — October 14, 2026

[PR28](https://github.com/jeffwelch0620-png/JayMax-Concepts-/pull/28) merged with
owner approval at **c5cce2b**; all four
[merged-main checks pass](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/38630008470).
The next local follow-up records safe original/cleanup error categories in held
receipts and extends error preservation through read-only snapshots, advisory
unlock, connection close and partial-file cleanup. Cleanup failures still hold
the result and preserve known/unknown commit outcomes. Local validation passes
663 offline cases and 72 distinct database cases across the full run and a
targeted savepoint-fixture rerun; the initial fixture failure is retained in the
checkpoint. The owned local server is stopped. This follow-up is ready for draft
review; candidate CI has not run. The hosted backup/restore hold remains unchanged.
See the [current checkpoint](docs/HOSTED_SOURCE_INDEX_PREFLIGHT_CHECKPOINT.md)
for review scope, evidence and the timing-first diagnostic sequence.

## Hosted index preflight — merged adapter, backup hold, October 14, 2026

[PR27](https://github.com/jeffwelch0620-png/JayMax-Concepts-/pull/27) merged with
owner approval at **a39e46f**, and all four
[merged-main checks pass](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/38606086807).
Read-only hosted inspection verifies the original 29 deliveries and 25 historical
records, all 54 ledger rows, client denial and the absent source index. The two
recorded backend roles had no sessions in that observation; two active Toast
ingestion jobs remain part of the writer inventory. No hosted index or privilege
change, invoice import or hosting/connection change occurred.

The fresh backup/restore rehearsal is **held** by connection loss during extended
read-only inspection; no recovery or maintenance-window acceptance is claimed.
The next local follow-up preserves the original disconnect when transaction
cleanup also fails. It passes **242 offline methods plus 395 subtests (637)**,
with zero failures/errors/skips, and is prepared for independent draft review. This offline checkpoint
is distinct from PR27's earlier 637-case local offline/database checkpoint below.
See the [preflight and backup-hold checkpoint](docs/HOSTED_SOURCE_INDEX_PREFLIGHT_CHECKPOINT.md)
for evidence boundaries, scheduled-job review and the next approval sequence.

## Hosted source-index adapter - local preparation, October 14, 2026

[PR26](https://github.com/jeffwelch0620-png/JayMax-Concepts-/pull/26) is merged with
owner approval at **51b0f6d**. All four merged-main checks pass in
[run 38506067983](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/38506067983).
The next **codex/hosted-additive-index-adapter** branch prepares a manual adapter
outside Render's backend root, mandatory ordinary-client checks, full ledger
metadata preservation, backup/restore bindings and an explicit maintenance plan.
See the [hosted adapter runbook](docs/HOSTED_ADDITIVE_INDEX_RUNBOOK.md).
The pre-amendment source checkpoint **2e15b37** passes **635 reported cases**: 230 offline
methods plus 379 subtests (609), and 22 additive-core/hosted-wrapper database
methods plus 4 subtests (26), with zero failures, errors or skips. The fictional
$55 Food Cost report, all original rows and sequence states remain intact;
changed ledger defaults, column grants, missing uniqueness, active writers and
writes committed during a table-lock wait are refused before DDL. Lost commit
responses reconcile independently. Starting/ending local database and role
inventories match, the server is stopped and all nine tested source hashes remain
unchanged throughout the final run. The overnight interruption is retained in
the elapsed evidence; every final case passed without relaxing deadlines.
A separate earlier broad accounting/restore checkpoint passed 668 reported
cases (605 offline/63 database); those overlapping counts are not added to 635.
The candidate is published as [draft PR27](https://github.com/jeffwelch0620-png/JayMax-Concepts-/pull/27)
for independent review. The initial publication head **2e15b37** matches the
source-pinned local acceptance; the publication follow-up changes this note only.
Publication head **102283a** failed the Windows offline check in
[run 38567336949](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/38567336949):
229 methods/379 subtests passed, but generated-file ownership/ACL acceptance failed.
The 689 frontend tests/build and 55 database methods/11 subtests passed separately.
The PR27 amendment explicitly protects generated file ownership/ACLs without
relaxing input checks, declares Windows/PowerShell 7/Python 3.12+ and PostgreSQL
16+ (17 tested), and adds refreshed live writer observations before table locks
and inside the locked guards. The hosted review/plan envelope is now v2 with a
reviewed application LOGIN list; observations retain redacted counts and a
verified activity-visibility flag, and do not replace maintenance attestations.
The observer must be a superuser or have immediately available pg_read_all_stats
privileges; the tool refuses insufficient authority and never grants privileges.
Source head **aec7795** passes all four checks in
[run 38600775607](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/38600775607):
689 frontend tests/build, 236 offline methods plus 393 subtests (629), and 60
disposable-database methods plus 11 subtests (71), with no failures/errors/skips.
The lost-ack fixture targets the write commit, and the fictional LOGIN fixtures
authenticate explicitly without changing database authentication rules.
Current source-pinned local validation passes **637 reported cases**: 236 offline
methods plus 393 subtests (629), and eight hosted-adapter database regressions.
The exact fictional $55 Food Cost result is preserved, role/database inventories
match, all nine source hashes remain unchanged and the owned server stops.
The interrupted superseded run is not acceptance; counts from local/CI/historical
checkpoints overlap and are not summed. The PR
check panel remains the authority for documentation follow-up heads. Hosted acceptance
remains pending and the PR remains draft, with no merge or hosted installation approval.
The current Render/Supabase connections stay in place. Hosted execution and the
fictional $212/current-source acceptance require separate approval and evidence.

[PR25](https://github.com/jeffwelch0620-png/JayMax-Concepts-/pull/25) is merged at
**fbf06b7**, incorporating documentation refresh **53809e1**. All four checks pass
on the refreshed head and [merged main](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/38498944157).
Public app, bundle and API checks return HTTP 200; the API reports a connected
database. These public checks do not identify the Render deployment commit.
Migration 30 remains unapplied to Supabase.

The separate **codex/additive-source-index-install** follow-up adds a read-only
plan, atomic index/ledger application and independent uncertain-commit recovery.
Its CLI accepts only disposable local PostgreSQL. It preserves the original
29-file delivery mapping and complete earlier ledger, distinguishes raw file
and executed SQL-body checksums, and holds changed database baselines. Final local
validation passes **621 reported cases** with zero failures, errors or skips:
569 Windows offline cases and 52 disposable PostgreSQL cases, including all 12
incremental installer cases. The fictional **$55** actual Food Cost report is
preserved, successful-run role/database inventories match and the server is
stopped. Earlier corrected failures and the intermediate 30-case pass are
retained as separate evidence. The follow-up is published as
[merged PR26](https://github.com/jeffwelch0620-png/JayMax-Concepts-/pull/26).
[All four CI checks passed at initial source head e1144cb](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/38503716266),
including 689 frontend tests and the strict build, plus the 621 reported backend
cases. A publication cleanup removes only a trailing blank line from the test
file; its parsed code is identical. The PR check panel tracks the current head.
Review precedes a separately approved hosted adapter and rollout.
See [the incremental installation procedure and scope](docs/ADDITIVE_SOURCE_INDEX_INSTALL.md).

## Invoice-source lookup readiness - PR25 review, October 13, 2026

The **codex/purchase-source-lookup-index** candidate adds a version-first source
lookup index as migration 30 and verifies its definition and usable state through
the read-only deployment preflight. The original 29 migrations, public schema
snapshot, permission matrix and function/table contracts are preserved. Source
bytes, mappings, posting rules and Track 1 accounting remain unchanged. Local
validation passes **600 reported cases**: 549 offline, 40 disposable database,
10 fresh-install and one independent runtime catalog comparison. The successful
runs preserve their database/role inventories, and the local server is stopped.
[PR25](https://github.com/jeffwelch0620-png/JayMax-Concepts-/pull/25) is pushed at
**24dac66**. [All four Inventory CI checks pass](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/38496408661):
689 frontend tests across 67 suites and the strict production build, 40 reported
disposable PostgreSQL cases, 549 reported Windows offline cases and the required
aggregate check. These CI results are separate from the additional 11 local
installation/catalog cases. The owner-approved documentation revision passed all
four checks in [run 38498627229](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/38498627229)
before merge. Migration 30 has not been applied to Supabase. Next is the separately reviewed additive installer
for the existing 29-file installation, preserving older migration history and
handling uncertain commit outcomes before any approved hosted DDL.
See the [index contract, validation and later rollout boundary](docs/PURCHASE_SOURCE_LOOKUP_INDEX.md).

## Current source reopening acceptance - October 13, 2026

PR23 is merged at **4f93748** and deployed on the Render frontend. Its live
same-tab reload/sign-in recovery and competing-request discard trials passed.
The newer-source trial found a safe dead end: discard reopened revision 1's
original file even though revision 2 was captured in another file. Posting stayed
blocked, revision 2 remains unposted, and the closed **$212** Food Cost control
was preserved. The transport relay is stopped and normal app bundles are restored.

The reviewed **codex/latest-source-discard-reopen** follow-up adds a read-only
`currentSource` descriptor to purchase previews. Confirmed discard follows the
server's current invoice identity, version and captured file, validates that
source and checks status again before clearing the exact retained request.
Missing or changed pointers and failed or foreign reads preserve recovery.
There is no automatic posting, schema/migration change or hosted configuration
change. [PR24](https://github.com/jeffwelch0620-png/JayMax-Concepts-/pull/24)
is merged at **9b09da5**, with reviewed-head and main CI green and both Render
services verified Live. The fresh live trial preserved all 11 original values
through reload, blocked retry after a separately captured revision 2 and confirmed
that discard automatically reopened its newer file without posting. Browser
detachment required a fresh normal tab for the final explicit review and posting.
One fictional **October 13 / 1 each / $1** purchase saved on revision 2 using a new
key and survived reload, with original source versions and the earlier failed
fixture preserved. All 86 observed relations matched the verified post-commit
baseline and the complete **$184 + $173 - $145 = $212** control stayed unchanged.
The relay is stopped, its port closed and a normal reload has no marker. Override/
permission cleanup is user-reported; permission reset itself was not independently
inspected. The new purchase lies outside the original closed interval and does
not establish measured usage or a new Food Cost result. See the
[current-source recovery review](docs/LATEST_SOURCE_RECOVERY.md).

## Initial purchase recovery baseline - October 12, 2026

The [merged PR23 follow-up](https://github.com/jeffwelch0620-png/JayMax-Concepts-/pull/23)
on **codex/purchase-request-reload-recovery** retains a
submitted initial purchase's exact body and key across reload and same-user
sign-in in the same tab. It saves the scoped recovery record before the first
POST, restores frozen review values, and checks saved status before permitting
an explicit retry. No purchase is sent automatically. Storage failures stop
initial posting; another user or restaurant cannot inherit the review through
Invoice Master. Confirmed local discard checks status before and after
confirmation and refuses own saved outcomes. The separate-file newer-source
reopen gap found during live acceptance is addressed in merged PR24 above.
It does not cancel an earlier request. An already posted invoice follows the
saved-purchase/correction path, while late-commit conflicts retain the revised
command without an automatic resend. Capacity, size and storage errors have
specific messages; the API and journal share restaurant canonicalization, and
the review and journal share their unit vocabulary. All **674 frontend tests
across 67 suites** and the strict production build pass with the native feature
profile, ESLint enabled and a fictional backend URL.
See the [scope, validation and acceptance plan](docs/PENDING_PURCHASE_RELOAD_RECOVERY.md).

PR22 is merged at **cd29f22** and deployed on the Render frontend; the API remains
at **54975a0**. The real dropped-acknowledgement trial passed in the full Render
parent using temporary two-call browser routing to a loopback relay. Its exact
manual retry returned the original purchase with zero duplicate/updated rows,
and all 86 observed relations preserved the original **$212** Food Cost control.
The relay is stopped, the routing override is disabled and its temporary browser
permission was reset for that earlier trial. PR23's reload/sign-in and competing
discard cases pass live; the fresh newer-source trial also passes within the
segmented browser scope recorded above. Manual source capture and
correction command persistence remain separate follow-ups.

## Saved purchase comparison follow-up - October 12, 2026

PR21 is merged at `54975a0`. Both Render services were verified **Live** on that
commit through the dashboard, and all four [merge-commit CI checks](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/38196259722)
pass. The deployed comparison reads the existing fictional receipt's quantity,
conversion, received date and correction history without posting a command.

The walkthrough found one display mismatch: saved mapping decisions expose
`decision_note`, while the comparison read `note`. This local follow-up renders
and validates `decision_note`, preserving the competing user's frozen note and
request. Two regression cases failed before the correction and pass afterward;
all **619 frontend tests across 66 suites** and the strict production build pass.
The fix was merged under explicit approval in [PR22](https://github.com/jeffwelch0620-png/JayMax-Concepts-/pull/22)
at **cd29f22** and deployed on the frontend. No backend, schema, accounting or connection change was included.

A fresh read-only comparison at **1:08 PM EDT on October 12** preserved all
**86 observed relations**, the one fictional receipt and the original **$212**
report. An earlier read-only attempt lost its connection; the fresh retry passed
without changing connection settings. See the [recovery review](docs/PURCHASE_SAVED_OUTCOME_RECOVERY_REVIEW.md)
for the evidence and next steps. The new unresolved-request recovery scenarios
still require separate live acceptance; opening an already posted receipt does
not establish those paths.

## Local purchase saved-status follow-up - October 11, 2026

The [saved-outcome recovery review](docs/PURCHASE_SAVED_OUTCOME_RECOVERY_REVIEW.md)
records **Check saved status** and the PR21 review amendment. The existing scoped
GET now returns the original posting key. Recovery resolves only a matching
original version/key, including purchases corrected on the same version or a
supplier reissue. Another request's posting preserves the user's frozen values
for read-only comparison with the current purchase and correction history.
Held reads show their reasons and disable posting until a fresh read clears the
hold. Failed reads retain the original immutable request; status checks never
submit a POST. All **617 frontend tests across 66 suites**, including **39 purchase
component tests**, and the strict production build pass. All **41 local purchase
and PostgreSQL correction tests** and **211 Windows offline tests plus 323
subchecks** pass. Three new recovery cases are included in database CI.
No migration or write rule changes.
These changes were reviewed in [PR21](https://github.com/jeffwelch0620-png/JayMax-Concepts-/pull/21)
at **cc8072f**, then merged and deployed at **54975a0** under user approval.
The frontend requires the amended backend preview; absent request identity is
held as unconfirmed. Current hosting and Supabase connections remain unchanged.
The existing hosted parent now passes read-only reopening after normal owner
sign-in, navigation and a full reload: the retained receipt reads posted, has
one history row and offers no initial-post action. A fresh database check
preserves all 86 observed relations and the complete $212 original report.
These reads used the already acknowledged receipt; exact unresolved-command
continuity across reload or session expiry remains separate. The new status action is deployed; its unresolved-request scenarios remain
separate from the existing-receipt readback.

## Hosted recovery and deployed HTTP retry acceptance - October 11, 2026

PR20 is merged at `4855ba6`, and its Render frontend passed the
[hosted read-recovery walkthrough](docs/PR20_HOSTED_ACCEPTANCE_RESULTS.md).
Item and recipe drafts survived polling and stalled reads; timeouts released
recovery, initial Retry worked, and polling resumed. Both fictional drafts were
discarded without Save. Read-only comparisons preserved all 79 protected tables
and the complete **$212 Actual Food Cost** report. These controlled client-latency
checks do not establish a cold-start service-level guarantee.

The [deployed HTTP retry results](docs/DEPLOYED_POSTING_RETRY_RESULTS.md) now
confirm **eight exact retries returning the original batches** and **eight
changed-body/key retries refused with HTTP 409** through the existing Render
API. Fresh readback after every request and at completion preserved all
**79 protected tables**, migration identities and the complete **$212** report;
no new purchase outcome was created. Normal owner sign-in was used, with no
credentials stored in receipts or Git. The
[procedure](docs/DEPLOYED_POSTING_RETRY_PLAN.md) and
[read-only preflight](docs/DEPLOYED_POSTING_RETRY_PREFLIGHT.md) record the setup;
five offline runner controls remain separate from deployed evidence.
The [guarded hosted browser response-loss trial](docs/HOSTED_PURCHASE_BROWSER_RESPONSE_LOSS_RESULTS.md)
now also passes using the unchanged purchase-review component in a separate
local client. One labelled fictional October 11 receipt committed **+1 each /
$1** through the existing Render API. Independent database proof preceded the
deliberately truncated response; Chrome showed `ERR_NETWORK`, retained the
locked review and did not acknowledge success. One manual retry sent the
identical 438-byte body and key, acknowledged the original batch, and caused
**zero added or updated rows**. Exactly one batch, line and derived food fact
remain. All **86 observed relations** matched the post-commit baseline on final
readback; prior rows, migration identities and the complete **$212** original
report were preserved. The helper is stopped and its memory-only token discarded.
The new $1 purchase is outside the original closed interval and does not
establish $1 of actual usage. **28 offline guard tests** passed before execution.
The [trial plan](docs/BROWSER_POSTING_RESPONSE_LOSS_PLAN.md) and preceding
[local simulated test](docs/LOCAL_PURCHASE_REVIEW_RESPONSE_DROP_RESULTS.md)
record the method's progression. This accepts the same mounted review form;
the full hosted parent, reload/navigation/session-expiry recovery, concurrent
first posting and independent employee authorization remain separate.
Current hosting, Supabase connections, database roles and schema are unchanged.
This acceptance documentation is included in
[PR21](https://github.com/jeffwelch0620-png/JayMax-Concepts-/pull/21),
now merged and deployed; the note-display correction above remains local.

## Deployed walkthrough and item setup corrections - October 10, 2026

PR14–19 are merged into the existing Render test deployment. Both services are
verified Live at `b2f529f`; merge-commit Inventory CI passes. The approved
**Bert's fictional walkthrough** confirms **$212 Actual Food Cost**, preserved
close/reopen/reclose history, separate prep/waste explanation and the staff
quantity/manager acceptance workflow, including refusal of a stale review.
Independent employee authorization remains outstanding. Exact posting replay
against hosted PostgreSQL now passes through the reviewed API router; deployed
HTTP and lost-browser-response recovery remain separate acceptance checks.
The [live acceptance follow-up](docs/LIVE_ACCEPTANCE_CATALOG_EDITOR_FOLLOWUP.md)
records the results and a reproduced two-tab catalog overwrite. The amended
[PR19](https://github.com/jeffwelch0620-png/JayMax-Concepts-/pull/19) protects
both item and recipe editors, permits unrelated-refresh saves and new items,
and adds explicit recovery that preserves independent edits while holding
conflicts. The creation-receipt follow-up preserves a saved identity when typing
continues during creation, preventing another Save from appending a duplicate.
The [review response](docs/PR19_REVIEW_AMENDMENT.md) explains the boundaries.
All **562 frontend tests across 65 suites** pass locally with the native profile;
the strict production build also passes with `CI=true` and ESLint enabled. The preceding amendment
at `1ece856` passed its strict build and CI. The
[hosted acceptance results](docs/PR19_HOSTED_ACCEPTANCE_RESULTS.md) confirm item
and recipe conflict/recovery, unrelated saves, and single-record creation when
typing continues during confirmed saves. Original test fields are restored and
the final fresh Food Cost preview remains $212. Fresh-read reliability symptoms
and unexercised hosted cases are recorded separately. The
[posting retry results](docs/POSTING_RETRY_ACCEPTANCE_RESULTS.md) record 16 exact
replays returning the original batches, eight conflicting retries refused, and
unchanged rows across all 79 purchasing/count/prep/state tables checked. No new
purchase was imported or posted. A controlled local regression now confirms that
background polling can invalidate an explicit editor recovery read. The
[recovery-read follow-up](docs/EDITOR_RECOVERY_READ_INTEGRITY.md) prevents that
overlap while preserving stale-response and revision safeguards. The PR20 review
amendment also bounds the complete state load to **60 seconds**, cancelling
unfinished shared-state and PostgreSQL child reads so a stalled request cannot
pause polling indefinitely. Initial timeouts expose Retry; later timeouts retain
confirmed state and drafts. The deadline is scoped to reads and leaves mutation
and posting retry contracts unchanged. The amended follow-up passes **181 focused
tests across 11 suites**, all **588 frontend tests across 66 suites**, and the
strict production build. That review checkpoint was published in
[PR20](https://github.com/jeffwelch0620-png/JayMax-Concepts-/pull/20), subsequently
merged under user approval and deployed. The October 11 results above record
its completed hosted read acceptance; broader UI and authentication work remain
deferred.

The [item setup checkpoint](docs/DEPLOYED_ITEM_SETUP_CHECKPOINT.md) documents two
locally corrected blockers: duplicate count panels while typing, and unrelated
item saves blocked by a stored unknown supplier conversion. Unknown conversions
remain unknown; new UI supplier packs still require physical validation. These
fixes are merged in [PR18](https://github.com/jeffwelch0620-png/JayMax-Concepts-/pull/18)
and deployed at `85cf2b7`. Broad UI rework is a separate later
workflow. Existing hosting, Supabase connections and credentials are unchanged.
PR18 validation passed **522 frontend tests across 63 suites** with the native feature profile.
The [PR18 follow-up](docs/PR18_CONVERSION_CI_FOLLOWUP.md) adds a supplier-row link
to the existing verified conversion review, a non-blocking pack mismatch notice,
and complete shared component API mocks. Confirmations keep actor/time/evidence
in immutable native unit profiles; ordinary edits preserve null and positive
catalog factors. The two existing hook warnings were corrected for the strict
CI build, which passes in GitHub's fresh install. Build/database and GitHub check
results are recorded in that follow-up.

[Inventory CI](.github/workflows/ci.yml) checks pull requests and `main` with all
native frontend tests, a strict production build, and selected backend checks
against fictional fixtures in disposable PostgreSQL. Require its combined status
before merging; passing CI is separate from deployed workflow acceptance.

## Claude follow-up corrections - October 10, 2026

The [focused correction review](docs/CLAUDE_PR14_17_FOLLOWUP.md) preserves stored
physical count and supplier conversions, sends only changed item definitions
and explicit retirements, and reconciles confirmed saves after location changes
without clearing newer drafts. Missing prep progress and assignment records are
held for review. Initial location-load failures now show a retry and diagnosis.

[Repeatable review checks](docs/REVIEW_TESTING.md), the checked
[migration apply order](migrations/APPLY_ORDER.md), and a matched
[native testing feature profile](docs/BUILD_TEST_FEATURE_PROFILE.md) are included.
The feature profile is preparation, not verification of the live Render flags.
Frontend and backend for the partial-item route must be deployed together.
Current Supabase connections and private credentials remain unchanged; paid
IPv4 and connection changes are deferred. This review describes the correction
package before PR14–17 were merged on October 10; validation is retained below.

Validation for this correction: **211 selected backend tests and 323 subtests**,
**504 frontend tests across 62 suites in each of three configurations**, a passing
optimized build, and **24 selected disposable PostgreSQL cases plus 7 subtests**.
No selected checks were skipped. Two existing frontend hook warnings remain.
Local database/role inventory and the protected 40-path continuation were preserved.

## Current stack review and test-deployment merge path - October 9, 2026

The corrected PR14–16 stack and its local continuation now have combined source
acceptance: **205 backend tests with 309 subtests**, **494 frontend tests across
61 suites in each of three configurations**, a passing optimized build, and
**19 distinct disposable PostgreSQL acceptance cases**. These checks preserve
received-date purchases, explicit count values and Track 1 independence through
prep/waste corrections and whole recovery. Two existing frontend hook warnings
remain. Initial fixture/runner failures are retained alongside the passing repeats.

The [current merge checklist](docs/MERGE_READINESS_CHECKLIST.md) separates this
code-only build/test review from operational release. The owner confirmed Render
automatically deploys the repository, is unused, and contains no operational data.
An authorized merge will refresh that test deployment. Startup does not apply
migrations; the designated hosted build database's existing native installation
remains recorded in its checkpoint. Live Render flags were not inspected here.

Review order is **PR14 → PR15 → PR16 → the deployment/recovery continuation**,
retargeting and checking each dependent PR after its predecessor merges. Prefer
merge commits to preserve the reviewed stack. Publication of this continuation
is a draft PR; no merge or manual deployment is part of this checkpoint.
Authentication redesign, broader history/paging review, future modules and
operational recovery/credential-promotion gates remain separate tracked work.
Earlier local-only and merge-hold statements below describe their original
snapshots; this checklist governs the current build/test merge recommendation.

## Persistent supervisor checkpoints and client handoff review - October 9, 2026

Independent recovery checkpoints now survive supervising-process exits in a
separate metadata store. Conflicting writers and journal/checkpoint gaps hold
progress. The client handoff contract requires exact instance/source/revision
declarations and both database/pooler capacity measurements; declarations alone
never authorize promotion. **21 tests and 61 subtests pass.**

The [supervisor and handoff checkpoint](docs/LOCAL_SUPERVISOR_HANDOFF_CHECKPOINT.md)
records the process trials, credential-storage contract and remaining encrypted
credential/live-client/combined recovery requirements. PostgreSQL remains the
application data source; this store contains recovery metadata, no business data or
credentials. **Local only; no push, hosted change, merge or deployment.**

## Independent process recovery and populated accounting trial - October 9, 2026

The local recovery adapter now requires an independently pinned archive and
latest journal checkpoint, validates stage history before connecting, and uses
a fresh catalog to distinguish committed, rolled-back and ambiguous outcomes.
Verification through actual pools must be repeated after a process restart.
The [process recovery checkpoint](docs/LOCAL_INSTALL_PROCESS_RECOVERY_CHECKPOINT.md)
records the preserved $55.00 Food Cost result with $40.00 net food purchases,
genuine worker exits and remaining recovery/release limits. Eleven tests and 32
subtests pass, including the populated PostgreSQL case and exact cleanup.
This is local work; Supabase and active
configuration remain unchanged. **No push, merge or deployment.**

## Local installer and failure-recovery rehearsal - October 9, 2026

The guarded disposable installer now journals intent and expected catalog digests
before commit, holds uncertain outcomes for fresh-connection reconciliation, and
checks exact return to the original inventory/account connections before disabling
replacement test roles. It does not change Supabase or active configuration.

The [local installer checkpoint](docs/LOCAL_PARALLEL_INSTALL_CHECKPOINT.md) records
failure/cancellation, missing commit acknowledgement, catalog drift, pool cleanup
and local data/access preservation coverage. Validation passes: 41 cases and 110
subtests, including two real PostgreSQL cases and exact fixture/server cleanup.
Native accounting tables are empty in this fixture; a nonempty Food Cost report
regression remains required. The next requirement is recovery
from a separately restarted process with independently archived baseline pins.
Hosted capacity/client registration, secure credential staging and combined
recovery remain held. **Local only; no push, merge or deployment.**

## Explicit paired pool preparation and installer plan - October 9, 2026

Both actual pool constructors now support an independently verified, immutable
client revision with per-physical-connection identity and permission checks.
The paired preparer returns both owned pools or cleans up its partial attempt;
it never promotes pools or changes active configuration. Defaults remain intact.
The review-only installer plan renders the exact profile grants, 66 policy
additions/restorations, capacity holds and ordered rollback without password SQL
or an apply entrypoint. Inventory's catalog-reference receipt label is corrected.

Validation passes: 36 tests and 93 subtests, including both actual constructors,
physical reconnects and an original-singleton return on disposable PostgreSQL.
Fresh hosted checks pass for both unchanged original profiles/default pools and
metadata preservation. Pooler capacity and registered client count remain unmeasured.

The [paired startup and installer checkpoint](docs/PAIRED_STARTUP_INSTALL_PLAN_CHECKPOINT.md)
records what is implemented and the remaining local installer/journal rehearsal,
hosted pooler-capacity, client-registration and promotion gates. **Combined recovery,
merge and active-cutover gates remain held.** No hosted accounts or policies change;
local only, no push or deployment.

## Default-strict transition permission checker - October 9, 2026

The local diagnostic checker permits only independently recorded, same-profile
original/replacement role pairs. All effective privilege and inventory catalog
checks remain in place. Account policies now receive exact per-verb/cohort checks,
including rejection of extra PUBLIC/restrictive policies. Actual application
startup retains singleton policies and has no overlap environment toggle.

Validation passes: 29 tests and 91 subtests, including real disposable PostgreSQL
policy/privilege regressions. Both unchanged hosted credentials pass their
read-only default permission profiles; role/policy/membership metadata is preserved.

The [transition permission checkpoint](docs/TRANSITION_PERMISSION_CHECKPOINT.md)
documents record provenance, exact administrative membership pins, the tests and
remaining installer/startup/client-registry work. No hosted role, credential,
grant, policy or application configuration changes occur here. **Combined recovery,
merge and active-cutover gates remain held.** Local only; no push or deployment.

## Parallel-account rotation review and current pooler checks - October 9, 2026

Read-only review passes for both current permission profiles and all six original
session-pooler connection samples. Six direct connection samples time out; DNS
resolves the direct endpoint to IPv6 and the pooler to IPv4. All 58 inventory and
8 account policies match the reviewed contract, and role/policy/membership
metadata is unchanged. No credentials, roles, grants, policies or settings changed.

The [parallel rotation review](docs/PARALLEL_ROTATION_REVIEW_CHECKPOINT.md) recommends
keeping the current port-5432 pooler and private credentials while preparing
replacement accounts beside them. It identifies the strict singleton-policy
verifier prerequisite and the staged grant/policy/client/retirement process.
The review planner emits no SQL. Five guards and 20 subtests pass.

Follow-up: the [transition checker](docs/TRANSITION_PERMISSION_CHECKPOINT.md) now
implements the diagnostic prerequisite; journaled installation and explicit
startup/client integration remain to be prepared. **Combined rotation/recovery,
merge and active-cutover gates remain held.** Local only; no push or deployment.

## Combined rehearsal held; original pooled access and data verified - October 9, 2026

Temporary credentials authenticated, old passwords were rejected, both actual
application pools reconnected, and both controlled NOLOGIN comparisons passed.
The complete rehearsal then held on password-authentication/recovery verification.
Separate read-only checks verify both original application credentials, rejection
of temporary passwords and preservation of all 120 table/sequence fingerprints,
13 catalog groups, Track 1, the complete ledger and original role attributes.
Direct connections later timed out; the application session-pooler path is verified.

Original private configuration remains current. Temporary credentials are inactive.
Fifty-eight guards and 101 subtests pass. The
[combined rehearsal checkpoint](docs/COMBINED_ROTATION_REHEARSAL_CHECKPOINT.md)
preserves the held attempt, separate recovery evidence, exact hosted source and
locally tested recovery refinements. No further password rotations were run.

Next: review parallel new-role rotation and direct-path reliability before another
credential mutation, then finish the deployment/PR checklist. **Keep merges and
active cutover held.** Local only; nothing pushed, merged or deployed.

## Corroborated pooler denial verified for both roles - October 9, 2026

The controlled accounts and inventory comparisons pass under the new versioned
denial contract. Each exact role was confirmed NOLOGIN, rejected fresh direct
access, and rejected both fresh pooler requests after closing only its verified
owned test connection. The exact provider lookup response qualifies only with
independent witnesses; arbitrary internal errors remain held. The native-only
strict-pass flags and historical held receipts retain their original meaning.

Both unchanged original credentials and LOGINs are restored. All 120 table/sequence
fingerprints, 13 catalog groups, Track 1, the complete ledger and original role
attributes are preserved. Thirty-four guards and 73 subtests pass. The
[corroborated denial checkpoint](docs/CORROBORATED_POOLER_DENIAL_CHECKPOINT.md)
records the measured results, acceptance contract and limits.

Next: integrate this narrow qualification into the combined credential rotation,
pool-reconnect and recovery probe, then verify that workflow separately.
**Continue holding merges and active cutover.** Local only; no push or deployment.

## Controlled pooler drain and recovered hold - October 9, 2026

The owner confirmed inventory NOLOGIN, direct PostgreSQL returned the known 28000
denial, and only the verified owned pooler test connection was closed. Both fresh
pooler attempts then rejected access with the specific EAUTHQUERY lookup error.
The strict native-denial guard held; the accounts-role disable was not run.
LOGIN and unchanged original credentials are recovered on both paths, and all
120 table/sequence fingerprints, 13 catalog groups, Track 1, the complete ledger
and role attributes are preserved. Twenty-three guards and 18 subtests pass.

The [controlled drain checkpoint](docs/OWNED_POOLER_DRAIN_CHECKPOINT.md) records
the initial setup/data-comparison holds and the final recovered evidence.
Next: review the independently corroborated provider-denial contract and prove
the accounts-role case before changing combined rotation/recovery handling.
**Continue holding merges and active cutover.** Local only; no push or deployment.

## Verified owned-connection signal rehearsal - October 9, 2026

The owner successfully closed one newly created read-only test connection for
each retained build account. Both backends disappeared and unchanged original
credentials reconnected. No existing application connection was targeted.
Ten guard tests and 15 subtests pass. A separate read-only reconciliation verifies
original application records, Track 1, the complete ledger, catalog/access and
role attributes against the preserved recovered baseline.

The [signal checkpoint](docs/OWNED_SESSION_SIGNAL_CHECKPOINT.md) retains the
interrupted journal as held and records its passing reconciliation separately.
Next: compare a disabled login after draining only its explicitly owned pooler
test connection. Actual pooled-login retirement and the combined recovery
checkpoint remain unverified. **Continue holding merges and active cutover.**
This checkpoint is local only; nothing was pushed, merged or deployed.

## Verified encrypted application backup and local restore - October 9, 2026

The manual hosted export and isolated local restore pass: all 8,335 records, 120
table/sequence fingerprints and 13 catalog groups match across six application
and migration schemas. Thirty migration-file hashes are captured. Hosted data
and the baseline are preserved, restored access boundaries pass, and the disposable
database/role stubs were cleaned up. Ten local backup guards pass.

See the [backup verification checkpoint](docs/HOSTED_BACKUP_VERIFICATION_CHECKPOINT.md)
and [manual recovery workflow](docs/HOSTED_TO_LOCAL_BACKUP_WORKFLOW.md). Data and
the separate encryption key remain private. This verifies application-scope
recovery; managed services, credential retirement and remaining release checks
are still pending. Backups are not scheduled. **Merges and active cutover remain
held.** This checkpoint is local only; nothing was pushed, merged or deployed.

## Verified TLS and hosted-to-local recovery plan - October 9, 2026

Both reviewed application pools now require certificate and hostname verification
for remote PostgreSQL, use conservative two-connection caps, and safely hold failed
connections. Fifteen local tests and both hosted read-only pool checks pass. The
session pooler on 5432 remains the connection plan; no paid IPv4 add-on, credential
change, private configuration activation or deployment occurred.

The [TLS checkpoint](docs/TLS_AND_LOCAL_BACKUP_CHECKPOINT.md) records the evidence
and corrects the earlier pooler/backend SSL measurement. The
[local recovery workflow](docs/HOSTED_TO_LOCAL_BACKUP_WORKFLOW.md) covers all three
inventory tracks, original source fields, integration data and migration history.
The application export/restore subsequently passed, as recorded above.
**Merges and active cutover remain held** on the separate credential
retirement/recovery and release gates. This checkpoint is local only.

## Isolated LOGIN revocation hold - October 9, 2026

The owner confirmed inventory NOLOGIN and direct PostgreSQL rejected a fresh
client, but the session pooler accepted a fresh client as that role after 15
seconds. The role was restored immediately and both original accounts reconnected
on both paths. The test stopped before disabling the account role. Passwords,
business data, application settings and the strict combined probe are unchanged.
Four local classification guards pass. See the
[isolated comparison checkpoint](docs/ISOLATED_LOGIN_COMPARISON_CHECKPOINT.md).
**Continue holding merges and active cutover.** Review the intended direct/pooler
connection and exact-role retirement behavior before another combined rotation.

## Read-only pooler diagnosis - October 9, 2026

Both original retained LOGINs authenticate directly to PostgreSQL over IPv6.
The hosted pooler log identifies an EAUTHQUERY lookup failure during the held
disable interval, but its detail does not identify the role. The
[diagnostic checkpoint](docs/POOLER_DIAGNOSIS_CHECKPOINT.md) distinguishes observed
evidence from the likely lookup mechanism and specifies an isolated comparison
before another password rotation. No application connection path, credential,
role or business data changed. **Continue holding merges and active cutover.**

## Credential rotation checks and recovered hold - October 9, 2026

Replacement credential authentication, rejection of both old credentials and
reconnection of both pools passed. The combined hosted LOGIN-disable check held
on internal pooler errors, including its bounded retry. Both original passwords
and LOGIN ability were restored; fresh original-file connections and the full
application/native, Track 1, ledger, catalog/access and role baseline passed.
Replacement files remain inactive, and eight local guards pass.

The [credential recovery checkpoint](docs/BUILD_CREDENTIAL_RECOVERY_CHECKPOINT.md)
records all recovered holds and the isolated inventory authorization-denial test.
Next: read-only pooler-log/direct-connection diagnosis before another rotation.
Account-role disable and later checks remain unrun. **Continue holding merges**;
active application settings, schema/migrations and application routing are unchanged.


## Enabled hosted workflows with retained LOGINs - October 9, 2026

Selected account, manual-forecast and prep workflows now pass through the retained
inventory/account connections. Prep submission/acceptance retries create exactly
one measured batch; explicit completion and replay through a fresh connection
pass. Account cleanup, exact forecast cents, stale-save rejection and forecast
rollback pass. Six local probe guards also pass.

Independent verification preserves all global Track 1 rows, the complete ledger,
prior prep history and other locations' state rows. Only exact labelled new prep
records and the test location's revision/update time are allowed; its stable
fields are preserved. The [retained LOGIN workflow checkpoint](docs/RETAINED_LOGIN_WORKFLOW_CHECKPOINT.md)
records passing evidence and all reconciled probe holds. Active configuration,
application routing, schema/migrations and the permission matrix remain unchanged.
**Continue holding merges.** Next: credential rotation/reconnect and recovery,
then remaining browser, deployment and sequential PR checks.


## Retained build connections in private local configuration - October 9, 2026

Two retained build LOGINs and their reviewed grants/policies are now provisioned.
Their connection file is staged outside Git in an access-restricted local folder.
Eight simultaneous authenticated clients pass the inventory/account assessments
and deny prohibited cross-boundary reads; four local provisioning guards pass.
Independent verification confirms pre-existing permissions/policies and the
catalog, migration ledger and observed counts are preserved. No business rows
are written, and active application settings/feature flags are unchanged.

The [private build connection checkpoint](docs/PRIVATE_BUILD_CONNECTIONS_CHECKPOINT.md)
records safe evidence, the retained initial ACL-check hold and the next controlled
workflow/rotation/recovery steps. Credentials and owner configuration are excluded
from shared review artifacts. The inventory matrix, application routing/pools,
catalog references and all 29 migration hashes remain unchanged. **Continue
holding merges** until enabled-workflow, recovery and remaining deployment checks
are completed.

## Hosted two-pool verification - October 9, 2026

The hosted build trial passes with **16 authenticated clients** across two fresh
rounds of simultaneous inventory and account/notification pools. Both permission
assessments pass and prohibited cross-boundary reads are denied. Independent
verification confirms temporary roles/grants/policies are removed and the
catalog, effective object permissions, policies, migration ledger and observed
row counts match the starting snapshot. Three target-guard tests also pass.

The [hosted two-pool checkpoint](docs/HOSTED_TWO_POOL_CHECKPOINT.md) records the
passing evidence and an earlier interrupted attempt with verified recovery.
No business writes, permanent credentials or saved application configuration
changes occur. The next credential step will use private local configuration
for continued build/testing. **Continue holding merges** for permanent connection
and workflow validation, recovery, browser/Data API and sequential PR checks.

## Separate account/notification connection - October 9, 2026

The backend now supports an optional separately restricted connection for
accounts and push subscriptions in the same PostgreSQL database. Inventory
and staff PIN queries retain the primary pool. Seven connection unit tests,
two existing account compatibility tests and both local tests with independent
restricted LOGIN pools pass. Account/push changes leave native accounting
records and the physical-count Food Cost report unchanged; five excess-access
variants are rejected. External push delivery is mocked.

Configure both connection URLs before replacing the owner connection with the
restricted inventory role. When explicitly configured, an invalid or unavailable
auxiliary connection is held without falling back to inventory access. See the
[auxiliary connection checkpoint](docs/AUXILIARY_CONNECTION_CHECKPOINT.md) for
permissions, retained failures, test evidence and rollout limits. All 29 migration
hashes and both catalog/permission references remain unchanged. This checkpoint
is committed locally; saved credentials and hosted configuration are unchanged.
**Continue holding merges** pending hosted two-role validation, permanent
credentials/recovery and the remaining deployment checks.

## Restricted LOGIN workflows and permanent connection plan - October 8, 2026

**26 selected backend workflows pass through ordinary restricted database LOGIN**,
with seven passing subtests; four static safeguards and five tampering subtests
also pass. Each workflow checks five clients in a newly created pool. Wrong
passwords and attempts to assume the database owner are rejected. The disposable
local server's original authentication file is restored and the server stops.
Older retained test databases/roles remain intact; this run leaves no extra ones.

The saved owner connection cannot yet be replaced directly: account and push
queries currently share the inventory pool, but their tables are deliberately
excluded from its permission profile. The prepared recommendation is a separate,
narrow backend connection to those tables in the same PostgreSQL database.
See the [connection/workflow checkpoint](docs/RUNTIME_CONNECTION_WORKFLOW_CHECKPOINT.md)
for the exact coverage, access map, tradeoffs and remaining checks. The inventory
matrix, both catalog references and all 29 migration hashes remain unchanged.
No permanent credential, hosted data/configuration change, push or merge occurs
in this checkpoint. **Continue holding merges.**

## Hosted catalog and ordinary database login - October 8, 2026

The hosted catalog now matches an independent reconstruction from the retained
pre-native schema-only export and exact 29-file migration chain. Its extra Toast
groundwork and legacy price-history table are preserved. The original local
94-function/123-relation reference remains unchanged; a separately pinned hosted
variant contains 96 functions and 127 relations and requires explicit selection.

Three static checks and both local catalog-reader/nonowner assessments pass.
The hosted LOGIN/pool trial also passes: ten independently authenticated clients
across two fresh pools, with a complete restricted-role permission assessment.
The temporary roles and their grants are removed; an independent read-only check
confirms cleanup and the unchanged hosted catalog. Trial and cleanup
evidence are recorded in the
[hosted runtime checkpoint](docs/HOSTED_RUNTIME_LOGIN_CHECKPOINT.md). This work
does not deploy a permanent runtime account or change the app's connection,
feature flags, invoice data or integration activity. **Continue holding merges**
for the remaining workflow, browser/Data API, managed recovery, configuration
and sequential PR checks. Older sections preserve earlier checkpoint results.

## Forecast and AI history review - October 8, 2026

**Seven selected backend checks and all 494 frontend tests pass** across 61
frontend suites. Production compilation passes with existing warnings. Passing
case selection, retained failures and the interrupted broad test attempt are
recorded in the checkpoint notes.

Manual forecast saves now require a reviewed store/date version, preserve exact
amounts and reject stale replacements. Forecast dollars remain planning data;
they do not post purchases, physical usage or Food Cost. The editor retains drafts
on failed/unconfirmed saves and after navigation.

The proposed runtime role can read retained AI history but cannot insert or clear
it. The drawer shows that boundary, reports failed reads honestly, keeps history
after failed clears, and ignores late responses from another location. Storage
availability is checked before unavailable chat requests reach a provider.

The local matrix adds forecast SELECT/INSERT/UPDATE and AI-history SELECT only.
All 29 migration hashes, 94 function contracts, 123 relation contracts and the
protected original continuation remain intact. See the
[forecast/AI checkpoint](docs/FORECAST_AI_READINESS_CHECKPOINT.md) for the exact
concurrency, storage, compatibility and validation boundaries.

This checkpoint remains local. **Continue holding merges** until the approved
hosted catalog, ordinary LOGIN/pool, browser/Data API, managed recovery, matched
feature configuration and sequential PR stack checks are complete. No hosted
grant, invoice import, AI provider request, push or merge occurs in this step.
Older sections retain prior checkpoint evidence.

## Shared-state cutover and retained periods - October 8, 2026

**Five selected backend checks and all 481 frontend tests pass** across 60
frontend suites. The production build passes with existing warnings.
The proposed role can now load retained adjustments through
SELECT-only access. Legacy adjustment and reporting-period replacement is held
after native cutover, including owner connections with flags off, preserving
historical periods referenced by purchase guards. No historical data is remapped.

Server capabilities keep legacy adjustment editing, period closing, old accounting
views and incomplete app backup/restore unavailable after installed inventory cutover.
Explicitly retired prep balances load as unknown; malformed or unlabeled responses
remain held. Analytical sales
drafts and area settings remain editable with revision checks. Tested physical
reports and all eight accounting fact fingerprints remain unchanged.

Only the local permission matrix changes: add adjustment SELECT, without DML.
All 29 migration hashes, 94 function contracts, 123 relation contracts and the
protected original 40-path continuation remain intact. Read the
[shared-state checkpoint](docs/SHARED_STATE_CUTOVER_CHECKPOINT.md) for exact
boundaries, selected passing evidence, retained failures and remaining route gaps.

No Supabase query/grant change, real invoice import, flag-file change, push, merge
or publication occurred. Forecast/AI-history and minimum-grant review, hosted
catalog/LOGIN/pool testing, browser/Data API, managed recovery and matched flags
remain open. **Continue holding merges.** Older sections preserve earlier evidence.

## Unclassified prep-list history - October 8, 2026

**Four selected backend checks and all 469 frontend tests pass** across 57
frontend suites. The production build passes with existing warnings. A separate
read-only Prep History view preserves every stored
header/line field and exact decimal strings. Missing track values remain
Unclassified; other recorded count types remain distinct. No current recipe/price
joins or historical-to-current assignments are introduced. Tested Track 1 reports
and all eight accounting fact fingerprints remain unchanged.

No permissions or schema constraints change: all 29 migration hashes, 94 function
contracts, 123 relation contracts and the protected original 40-path continuation
remain intact. See the [prep-list history checkpoint](docs/PREP_LIST_ARCHIVE_CHECKPOINT.md)
for filtering, pagination, retained failed attempts, validation and limitations.
This closes the unclassified archive-access item recorded below.

No Supabase change, real invoice import, flag-file change, push, merge or
publication occurred. Remaining route/minimum-grant review, approved hosted catalog
reconciliation and runtime LOGIN/pool testing, browser/Data API, managed recovery
and matched flags remain open. **Continue holding merges.** Older sections retain
their checkpoint-specific evidence.

## Employee task cutover and archive permissions - October 8, 2026

**Thirteen selected backend checks and all 460 frontend tests pass** across
55 frontend suites. The production build passes with two existing hook warnings
and a Node deprecation warning. The old text-assigned count/prep queue now becomes
read-only history after native staff cutover, even with feature flags off.
Manager archive reads preserve entered names without inferring roster identities;
staff use reviewed count sheets and prep task plans for current work.

The local permission candidate adds SELECT only on `public.staff_tasks` and
`public.prep_lists`, and removes prep-item INSERT. UPDATE remains for native
SHARE locks; the retained-metadata trigger rejects DML. Failed task requests no
longer appear as confirmed empty queues, and late responses cannot replace another
location's tasks. Track 1 reports and accounting facts remain unchanged.

All 29 migration hashes, 94 function contracts, 123 relation contracts and the
protected original 40-path continuation are preserved. Read the
[task cutover checkpoint](docs/RUNTIME_TASK_CUTOVER_CHECKPOINT.md) for exact grants,
successful evidence, retained test-fixture failures and source helper references.
At that checkpoint unclassified legacy prep lists still needed archive-access
review. The subsequent prep-list history checkpoint above closes that item while
preserving NULL track values.

No Supabase query/grant change, real invoice import, flag-file change, push, merge
or publication occurred. Remaining route/minimum-grant review, hosted catalog
reconciliation and ordinary runtime LOGIN/pool validation, browser/Data API,
managed recovery and matched flags remain open. **Continue holding merges.**
Older sections below preserve earlier checkpoints.

## Manager workflows and retained history - October 8, 2026

**Twenty-two selected local checks pass**: eight manager workflow cases, seven
profile/fixture/verifier cases and seven inventory regressions.
Roster creation now honors `active=false`, and
malformed roster IDs are held by UUID validation. Candidate permissions add four
history-table reads and DELETE on unused recipe/roster definitions; native journal
deletion remains denied.

Manager tests cover all seven retained recipe-reference types, stale/concurrent
edits, late-failure rollback, store-specific supplier prices and item retirement,
roster history, and assignment/deletion races. Tested reports and accounting facts
remain unchanged: Track 1 is independent of prep and sales. The 94 function and
123 relation contracts, all 29 migration hashes and protected original 40-path
continuation remain intact. Read the
[manager checkpoint](docs/RUNTIME_MANAGER_WORKFLOW_CHECKPOINT.md) for the exact
permission delta, evidence, retained failures and limits.

This is a local candidate; unused privileges and remaining routes still need
review. Hosted catalog reconciliation and actual runtime LOGIN/pool behavior,
browser/Data API exposure, managed recovery and matched deployment flags remain
open. No Supabase permissions changed; no push, merge or publication occurred.
**Continue holding merges.** Older sections below are historical checkpoints.

## Read-only runtime permissions and drift checks - October 8, 2026

**Fourteen selected local checks pass**: six permission-verifier cases, seven
inventory workflows and one fixture-safety check. Preserved legacy planning,
count, container, day-list and supplier-contact captures now receive SELECT only;
reviewed mappings still create separate resolution records. Track 1 accounting
remains independent of prep and sales.

The read-only verifier compares effective privileges, column ACLs, role
memberships, grant options, ownership and backend RLS policies with the candidate.
Its independently installed reference pins **94 exact function contracts** and
**123 relation fingerprints**, including constraints, triggers, columns and RLS.
Strict checks caught SQL line-ending normalization in older fixtures; the runtime
tests now preserve the reviewed SQL bytes. Read the
[verifier checkpoint](docs/RUNTIME_PERMISSION_VERIFIER_CHECKPOINT.md) for the
matrix changes, evidence, retained diagnostics and limits.

This remains a local candidate. Other manager routes, unused grants and the
hosted catalog/runtime LOGIN need review before a hosted permissions trial.
Browser/Data API, managed recovery and matched deployment flags remain separate
gates. No Supabase permissions changed; no push, merge or publication occurred.
**Continue holding merges.** Older sections below are historical checkpoints.

## Nonowner runtime workflow candidate - October 8, 2026

**Seven selected local workflow cases passed** using a role with no ownership,
superuser, RLS bypass, database/role creation, private journal deletion or DDL
authority. The checks cover physical invoice/count corrections and period replay,
staff count/production review, order receiving/independence, supplier price/contact
history, paired waste corrections and saved prep analytics/reopening.

The candidate names individual objects across **78 native tables and seven views**.
Tests identified specific row-lock UPDATE rights and read-only access to existing
reporting periods; immutable invoice/count rewrites remain rejected. Read the
[runtime workflow checkpoint](docs/RUNTIME_PERMISSION_WORKFLOW_CHECKPOINT.md)
for the grant matrix, held diagnostics and evidence limits. This remains a local
candidate: unused rights, other routes and a read-only grants verifier still need
review before a hosted role trial. No Supabase permissions changed. No push,
merge or publication occurred; **continue holding merges**. Older sections below
are historical checkpoints.

## Hosted staff assignment and production - October 8, 2026

The retained synthetic hosted workflow now covers reviewed task assignment,
pending staff production, independent partial acceptance and a separate explicit
task finish. Original-key replay through a new pool retains one accepted batch
and the current completed task. Exact output **2.000000000001** survives;
all eight fixture Track 1 fact sets and the **$55 Food Cost** report remain intact.
All original **40-table projections** and **54 migration records** still match.

The hosted run reached its time budget after acceptance. Independent read-only
reconciliation proved the committed partial state and preserved all **41 physical
accounting/purchasing table fingerprints**. Completion resumed that same task;
the held attempt remains separately recorded. Read the
[production checkpoint](docs/HOSTED_STAFF_PRODUCTION_CHECKPOINT.md) for the evidence.

**Three selected local regression cases pass**, including a nonowner role with no
RLS bypass, ownership, DDL or journal-delete authority. The local prototype exposed
a roster row-lock policy requirement; Supabase grants were not changed. The
[runtime permission assessment](docs/RUNTIME_ROLE_PERMISSION_ASSESSMENT.md) explains
its scope and remaining design work. Hosted runtime-role, browser/Data API and
full managed recovery checks remain open. This continuation is local/unpublished;
keep holding merges. Earlier sections below are historical checkpoints.

## Hosted staff count and independent review - October 8, 2026

The staff prep-count workflow passed against the designated hosted build database
through the actual FastAPI routes and middleware, using synthetic signed identities.
Concurrent submission/approval retries and replay through a completely new pool
retained one measured revision and one accepted observation. Blank quantities,
stale requests, changed same-key bodies, unauthorized locations and self-approval
were held. Exact quantities survived; Track 1 Food Cost remained **$55**.

The checks caught and fixed a staff-response gap: reviewer and definition-author
audit identities now remain private in nested staff receipts. Stored manager audit
facts and review hashes remain unchanged. **Seven selected local regression cases
passed**, covering counts, task history, production history and response projection.
All original **40-table projections** and **54 migration records** still match;
20 synthetic activity-log rows and the invented count history remain as evidence.

Read the [staff review checkpoint](docs/HOSTED_STAFF_REVIEW_CHECKPOINT.md) for
evidence and the next work. This verifies locally executed app routes connected
to hosted PostgreSQL; deployed browser, login and ordinary backend-role readiness
remain open. Browser control failed before the Supabase dashboard could be read.
The current connection is the privileged `postgres` owner role; no grants changed.
This continuation remains local/unpublished. **PR14–16 remain draft/unmerged**;
continue holding merges until the remaining checks and continuation PR review.
Earlier sections below are historical checkpoints.

## Durable native Supabase installation - October 8, 2026

The owner-designated build database now has the **29 native migrations committed**,
verified through a fresh connection. Original values in **40 existing tables**
and all **25 historical migration records** were preserved. New delivery records
contain hashes matching the SQL actually executed; no historical replay or repair
was used. The pre-install private application backup restored locally with all
40 table fingerprints matching.

The committed hosted workflow also passed concurrent purchase/prep retries and
replay after closing/reopening the pool. Track 1 Food Cost remained **$55** through
prep, container waste and sales-context changes. Original records were preserved;
clearly labelled invented test locations remain as audit evidence. A new private
snapshot backup includes the installed schemas and all **54 migration records**.
That backup restored locally with all **118 application tables** and all 54
migration-record fingerprints matching. Full managed platform recovery remains open.

Read the [durable hosted checkpoint](docs/HOSTED_NATIVE_INSTALL_CHECKPOINT.md) for
the held first attempt, independent rollback reconciliation, committed retry,
connection diagnostics and remaining validation. This continuation is local and
unpublished. **PR14–16 remain draft/unmerged**, and GitHub currently reports no
checks on those branches; retained local evidence is separate from hosted CI.
Staff/runtime, browser/Data API and full managed recovery remain open. Application
flags and app publication are unchanged. Earlier sections describe their own
historical checkpoints, including the rollback-only state before installation.

## Hosted rollback trial - October 8, 2026

The existing connected Supabase project, explicitly designated by its owner as
a build/test database, passed the **29-migration hosted rollback trial** and
invented purchase/count/prep/container-waste API workflow. Explicit Track 1
Food Cost remained **$55** through prep and sales-context activity. PFG/US Foods
capture retained unknown fields and multiline bytes; posting used the received
date and separated taxes/fees.

After rollback, all **40 existing application/integration tables**, schema,
permissions and migration identities matched their original fingerprints.
No native schema or temporary location remains. A fresh application backup is
preserved privately. **20 selected local checks pass.** Read the
[hosted checkpoint](docs/HOSTED_ROLLBACK_TRIAL_CHECKPOINT.md) for evidence and
limits: durable installation, separate-connection workflows, managed restore
and browser/Data API validation remain pending. No app flags, push, merge or
publication changed. Older checkpoints below remain historical evidence.

## Local cutover/correction reconciliation - October 8, 2026

The preserved legacy retirement and correction-review workflows now build on the
latest integrity and deployment fixes. **19 distinct selected backend cases** pass,
including the combined restaurant day and whole SQL restore. Both frontend modes
pass **454 tests / 54 suites**. Track 1 stays unchanged while prep activity explains
usage; old ledgers remain retired after installed cutover even with flags off.
The production build passes with the same three existing hook warnings.

Read [the current cutover checkpoint](docs/CUTOVER_RECONCILIATION_CHECKPOINT.md) for
coverage, the corrected independent-counter fixture and remaining integration work.
This is local work, not pushed or deployed. The original continuation is preserved;
PR14-16 remain draft and unmerged. Earlier checkpoint text below is retained history.

## Local deployment reconciliation - October 8, 2026

The separate deployment branch reconciles the latest PR16 corrections with the
preserved readiness tooling, for a complete 29-migration native bundle with final
access hardening last. **14 selected local checks pass**, including whole SQL
restore and purchased-inventory transaction/replay checks under an ordinary
database-owning role without superuser or RLS-bypass privileges.

Read the [deployment reconciliation checkpoint](docs/DEPLOYMENT_RECONCILIATION_CHECKPOINT.md)
and [readiness process](docs/SUPABASE_DEPLOYMENT_READINESS.md) for the exact scope,
role model and remaining hosted checks. Example files select PostgreSQL with all
native features false. Actual environments and compiled frontend flags remain
unchanged. This local slice is not pushed; PR14-16 remain draft and unmerged.
The remaining 40-file continuation is preserved separately for reconciliation.
Earlier checkpoint text below records the state at its publication.

The October 7 correction pass is documented in
[`docs/PR_REVIEW_CORRECTIONS.md`](docs/PR_REVIEW_CORRECTIONS.md). It records save/retry,
session-expiry, catalog batching, supplier selection, targeted recipe saves,
order/staff review separation, workflow conflicts, limited paired waste corrections,
recipe history retention, staff audit-response boundaries, history read batching
and test-configuration fixes,
their validation, and remaining review work.
PRs 14–16 remain draft and unmerged; hosted development validation is still pending.

Current history-read changes batch container balances and staff count history,
preserving exact values, review hashes, unresolved work and historical evidence.
**18 distinct selected backend checks** pass across the 15-case regression run
and four-case boundary/profile recheck, with one repeated case.
Read [query budgets and migration/runtime-role review](docs/WORKFLOW_READ_PERFORMANCE_REVIEW.md)
for the implemented scope and remaining full-history/recipe setup work. The preserved
deployment plan needs the waste correction before final access hardening, for a
combined 29-migration bundle; combined runtime and hosted recovery validation remain
pending. This batch adds no SQL migration or frontend change.

Previous history/access evidence remains valid for the unchanged frontend:
**438 tests / 53 suites** in default and native configurations, with a production
build passing with three existing hook warnings. Its 16 selected backend cases and
PR15's complete 15 menu checks / 23 parameter subtests are recorded separately.
Checkpoint evidence below describes the original snapshots.

## Published staff workflow checkpoint — October 7, 2026

[Draft PR #16 — staff counts, containers, waste and production](https://github.com/jeffwelch0620-png/JayMax-Concepts-/pull/16)
publishes the verified continuation based on PR #15. It remains a draft and
unmerged. Read the [detailed checkpoint README](docs/STAFF_WORKFLOW_CHECKPOINT_README.md)
for the five workflow milestones, additive schema, validation evidence, remaining
limits and stacked review sequence (#14, then #15, then #16).

Original staff checkpoint evidence: **404 frontend tests / 49 suites**, **36 distinct backend checks**,
**23 offline checks**, production build and whole SQL restore. Track 1 Food Cost
remains independent. All fifteen native feature pairs remain false in examples;
no operational migration, enablement, real import or deployment occurred.
The verified pre-publication snapshot and prior review notes remain unchanged.

Next work continues locally on a separate branch: remaining legacy operating
endpoint and historical correction review, then combined cutover/recovery trial.

## Previous local checkpoint — staff production acceptance, October 7, 2026

Staff now submit measured production against current native assignments. Immutable
revisions, withdrawals and manager rejections record no inventory. Reviewed
acceptance creates one measured batch and task link atomically, with an optional
explicit finish event. Partial output does not automatically complete a task.
Track 1 purchased inventory and Food Cost remain independent.

Read [staff production integrity](docs/STAFF_PREP_PRODUCTION_INTEGRITY.md) for
measurement, claimed identity, source availability, correction, retry and SQL
recovery contracts. Reassignment, roster changes, source drift and stale reviews
are held. Shared PIN access and roster names remain claimed identities; PINs are
excluded from retained drafts and database snapshots. Accepted corrections use
the existing manager batch/reconciliation workflows. Independent new reports
still require manager review for overlapping physical work.

Current local evidence: **404 frontend tests / 49 suites**, **36 distinct
backend checks**, **23 offline checks**, whole SQL restore and production build
with three existing hook warnings. Backend coverage combines the passing regression
checks with the corrected authorization/retry recheck, without double counting. Review totals remain **seven fixed, 12 open,
one deferred**. All fifteen native feature pairs remain false in examples.
The prior container-waste snapshot is retained unchanged. PR #15 remains at its
published commit; no continuation commit, push, operational migration or enablement.

Next: remaining legacy operating endpoint and historical correction review, then
a combined cutover and recovery trial before operational publication.

## Previous local checkpoint — paired container waste, October 7, 2026

Measured storage/service discard now saves the contents reduction and matching
waste journal entry together. Exact frozen fill conversions, immutable links,
location serialization and request-key replay prevent partial saves and double
loss. The latest erroneous waste can be reversed only together with its matching
observation; later activity holds earlier corrections. Track 1 purchased-item
inventory values and Food Cost remain independent.

Read [container waste integrity](docs/CONTAINER_WASTE_INTEGRITY.md) for measurement,
source allocation, correction, retry, SQL seals and additive upgrade contracts.
The UI validates both saved effects and directs linked corrections to paired
reversal. Staff production submissions/acceptance, sales consumption and full
historical dependency correction remain future work. All fourteen native feature
pairs remain false in examples; application connections must be recycled after DDL.

Current local evidence: **390 frontend tests / 47 suites**, **44 selected backend
checks**, **23 offline checks**, whole SQL restore and production build with three
existing hook warnings. Review totals remain **seven fixed, 12 open, one deferred**.
The prior staff-task snapshot and earlier test attempts are preserved unchanged.
PR #15 remains at its published commit. No continuation commit, push, operational
migration, real import or feature enablement occurred.

Next: immutable staff production submissions and manager acceptance using the
native assignments, with accepted measured production recorded once.

## Previous local checkpoint — staff prep access and assignments, October 7, 2026

The unpublished continuation now adds manager-reviewed assignments, reassignment
and unassignment with immutable task/roster IDs and history. Staff read the
released native plan for an explicit date and daily/bulk track; there is no
fallback to an older list. Claimed roster names do not grant manager permissions.
Assigned staff identities are archived instead of deleted. Production recording,
completion review and Track 1 Food Cost remain independent of assignments.

Read [staff task integrity](docs/STAFF_PREP_TASK_INTEGRITY.md) for scope, identities,
SQL guards, retry and recovery contracts. Exact saved requests remain confirmable
after reassignment or replacement of the dated draft. The installed schema holds
legacy PostgreSQL staff prep reads/completions even with flags off. Native staff
roster selection does not invoke legacy shared-PIN elevation. Staff production
submissions, direct container waste and broader authentication/cutover remain open.
All fourteen native feature pairs remain false in examples.

Current local evidence: **378 frontend tests / 46 suites**, **14 selected backend
checks**, **23 offline checks**, whole SQL restore and production build with three
existing hook warnings. Prior 56-check container evidence is preserved separately;
these counts describe the checks actually run for each checkpoint. Review totals
remain **seven fixed, 12 open, one deferred**. PR #15 stays unchanged. No local
continuation commit, push, operational migration, real import or enablement.

Next: atomic direct container waste and reversals, then immutable staff production
submissions and manager decisions using these stable assignments.

## Previous local checkpoint — measured prep containers, October 7, 2026

The unpublished branch `codex/staff-prep-count-continuation` now adds measured
container capacity definitions, product-specific fill profiles and partial
storage/service movements. Actual contents reserve recorded native prep output;
send/return preserve it and unpack releases it to its original lot. Stated,
brimful and usable capacities remain distinct. Future unpacking cannot fund
backdated prep, waste or fills. No service transfer counts as consumption or
changes Track 1 accounting.

Read [container integrity](docs/PREP_CONTAINER_INTEGRITY.md) for conversion,
history, date, migration, retry and recovery contracts. Legacy PostgreSQL prep
stock/log writers are held after installation even with flags off. Direct
container waste/consumption and staff task access remain open. The new gates
remain false in examples.

Current local evidence: 363 frontend tests/44 suites, 56 distinct selected
backend checks, 23 offline checks, whole SQL restore and production build.
Review totals remain **seven fixed, 12 open, one deferred**. PR #15 stays unchanged;
this cumulative staff-count/container continuation is local and unpublished.
Next: staff task access/assignment and the remaining service/waste contracts.

## Previous local checkpoint — staff prep counts, October 7, 2026

The unpublished branch `codex/staff-prep-count-continuation` starts from PR #15's
publication commit `ae10c8cab319b7f1ed842711076bacd132653f43`. It adds manager-issued
full prepared-inventory sheets, immutable staff measurement revisions, exact retries
and reviewed acceptance into the native prep-count journal. Blank stays unknown;
zero means measured empty. Scope, units and physical dates are pinned. Original
legacy prep count fields are preserved and the old session/line writers are held
after the additive migration, even with the new feature flag off.

Read [staff prep count integrity](docs/STAFF_PREP_COUNT_INTEGRITY.md) for the data,
access, migration, save/retry and recovery contracts. Track 1 quantities, values,
purchases and Food Cost remain independent. Existing staff/PIN authorization is
reused with honest attribution; login redesign and verified task assignment remain
future work. The new backend/frontend gates remain false in example files.

Current local evidence: 348 frontend tests/42 suites, 25 distinct selected backend
checks across the main and final runs, 23 offline checks and whole SQL restore.
Earlier attempts and corrected fixture/configuration issues are retained. R16 is
now fixed within the native prep count scope: **seven fixed, 12 open, one deferred**.
The subsequent container milestone is documented above. No new PR, operational enablement or deployment is included.

## Published workflow checkpoint — October 7, 2026

[Draft PR #15 — supplier, order and prep execution workflows](https://github.com/jeffwelch0620-png/JayMax-Concepts-/pull/15)
publishes the continuation on `codex/inventory-workflow-continuation`. It is based on
`codex/postgres-invoice-capture`, the branch of
[draft PR #14 — PostgreSQL inventory foundation](https://github.com/jeffwelch0620-png/JayMax-Concepts-/pull/14),
so its diff contains only work added since that checkpoint. Both PRs remain unmerged.
When ready, review and merge #14 first, retarget #15 to `main`, and revalidate the combined result.
Merge, operational enablement and deployment remain separate decisions.

The [foundation checkpoint README](docs/INVENTORY_FOUNDATION_README.md) records the original
invoice capture, purchased-item accounting, prep analytical journals, shared catalog and recovery
work. The [machine-readable review](docs/INVENTORY_REVIEW_STATUS.json) retains all 20 findings,
source anchors, scoped fixes and acceptance criteria. At PR #15 publication, the status was
**six fixed within their stated local scope, 13 open and one deferred**. The local continuation
above records the subsequent assessment. Publishing a checkpoint does not close its remaining findings.

### Work completed since PR #14

| Area | Implemented and tested locally | Contract and evidence |
|---|---|---|
| Menu recipes | Canonical ingredient identities, strict definition validation and explicit incomplete/null planning costs. Missing mappings cannot silently become zero cost. | [Menu recipe integrity](docs/MENU_RECIPE_INTEGRITY.md) |
| Supplier prices | Immutable source observations and reviewed price adoption, retaining purchase provenance without rewriting original invoice facts. | [Supplier price history](docs/SUPPLIER_PRICE_HISTORY.md) |
| Orders | Versioned creation, edits, transitions and archive history; exact retries, current-state acknowledgements and retained uncertain drafts. | [Order command integrity](docs/ORDER_COMMAND_INTEGRITY.md) |
| Supplier contacts | Stable supplier relationships, reviewed legacy contact mapping, raw-field preservation and versioned saves. | [Supplier contact integrity](docs/SUPPLIER_CONTACT_INTEGRITY.md) |
| Standing prep | Immutable planning versions, explicit daily/bulk tracks, weekday/weekend pars, schedules and retirement history. | [Prep planning integrity](docs/PREP_PLANNING_INTEGRITY.md) |
| Dated prep drafts | Prior-day physical counts, explicit units/unknown stock, reviewed day overrides and sealed daily/bulk task sets. | [Dated prep drafts](docs/PREP_DAY_DRAFT_INTEGRITY.md) |
| Manager execution | Reviewed release/reopen commands and once-per-production-root links to measured production. | [Prep execution integrity](docs/PREP_EXECUTION_INTEGRITY.md) |
| Progress and corrections | Multiple whole batches per task, exact decimal totals, explicit finish and reviewed corrections/voids. | [Prep progress and reconciliation](docs/PREP_PROGRESS_INTEGRITY.md) |

For example, a task can accumulate multiple measured batches while remaining in progress.
Finishing requires an explicit reviewed decision, even if output exceeds its planned quantity.
A corrected batch is visible but requires renewed review; a void contributes zero and reopens
the task. Its production root remains reserved to the original task. Any linked production
history keeps the released list pinned. Fractional allocation and reassignment are future work.

### Inventory and accounting boundaries

- **Track 1 — actual purchased inventory:** opening physical count plus received purchases minus
  closing physical count determines actual usage. Counts include purchased items only, with
  explicit opening/closing count values for actual Food Cost. **Date received is the purchase
  date of record.** Taxes and fees remain separate and retained for future accounting modules.
- **Track 2 — prep and waste:** measured batches, physical prep counts, waste and expected usage
  explain the purchased-inventory baseline and support planning/variance analysis. They do not
  deduct or revalue Track 1.
- **Track 3 — sales:** future Toast portions provide theoretical usage and demand evidence.
  They do not change Track 1's accounting quantities or values.

All original invoice fields remain preserved by the foundation, including fields without a
current mapped output. No real invoices were imported for these checkpoints. Incomplete
analytics must disclose missing coverage before claiming an unexplained variance.

### Original workflow checkpoint verification and preserved snapshot

| Check | Recorded result and limit |
|---|---|
| Frontend | 329 tests passed across 40 suites with native paths enabled for testing; component tests, not a live browser walkthrough. |
| Selected backend | 30 distinct checks passed across the main run and two focused rechecks; not the full backend suite. |
| Offline contracts | 23 checks passed. |
| Recovery and upgrade | Whole SQL restore and an actual old-schema additive upgrade preserved immutable history, old request hashes and exact retries. |
| Production frontend build | Passed with three existing hook warnings in PurchaseOrdersTab, SchedulingTab and StaffTab. |
| Source checkpoint | Compilation/whitespace checks and all 70 prepublication source hashes verified; publication documentation updated separately. |

The backend main run passed 28 checks and encountered a connection timeout and a test-fixture
cached-statement error after DDL. Both cases passed focused rechecks. The upgrade fixture now
recycles connections after DDL, matching a stopped-app migration/restart rehearsal; the
application pool already disables statement caching. All attempts are retained.

The unchanged local prepublication archive is
`JayMax-prep-progress-2026-10-07-review-package.zip` (92 entries, 70 verified source paths),
SHA-256 `4687a6c254fb4eb4f9e3e1268788098a1e10db6002eb54c213c4f55acd9f33c5`.
It preserves the cumulative patch against foundation commit
`a472c8674a7e3f173e838907e1b9d13d7665a028`, review notes, source hashes, all test attempts and
earlier nested snapshots. Application implementation was published in commit
`d64dea4bbb4e42bb8f6e7c70acba7e516867c751`; this README records the subsequent publication update.
Local archives, runtime files and raw invoice samples are outside Git.

Tests used invented fixtures and disposable loopback PostgreSQL outside synced Documents/Drive.
These results are local evidence, not managed-platform or production acceptance proof. Earlier
milestone documents retain their original local/unpublished wording as historical records;
this README is the current publication and remaining-work guide.

### Schema and feature status

The continuation adds these migrations to the foundation dependency chain:

- `20261006_supplier_price_history.sql`
- `20261006_order_commands.sql`
- `20261006_supplier_contacts.sql`
- `20261007_prep_planning.sql`
- `20261007_prep_day_tasks.sql`
- `20261007_prep_execution.sql`
- `20261007_prep_progress.sql`

Consult each linked contract for prerequisites; this list is not a complete bootstrap command.
The progress migration follows execution and preserves old command serialization and retries.
All eleven native backend/frontend feature pairs remain false in repository examples, including
the new order, contact, planning, dated-task and execution gates. Price history uses the existing
purchase/accounting/catalog gates. Installed database guards continue holding covered legacy
writers even with a new flag off; flag toggles alone are not a rollback plan.

No operational migrations, feature enablement or deployment were performed. New execution
writes retain existing owner/manager authorization. Staff identity/assignment and login/PIN
redesign remain future work. Draft retention currently covers signed-in navigation; persistence
through browser reload or logout is not promised.

### Next build sequence and completion checks

1. **Native staff prep count submissions.** Define location/date/product/count scope and actor
   evidence; distinguish unknown from zero; preserve immutable submissions and manager review
   before counts feed dated planning. Complete when duplicates, concurrent conflicts, access
   boundaries and uncertain-save recovery are tested without changing Track 1.
2. **Verified container execution.** Normalize dimensions, units and capacity; distinguish
   stated, brimful and usable-fill measurements. Require reviewed recipe/output conversions.
   Complete when partial containers and service movements preserve exact identity/quantity
   without the legacy whole-group deletion behavior.
3. **Staff task access and assignment.** Connect verified identities to permitted stores and
   tasks. Complete when assignment, authorization, acknowledgements and retained drafts are
   tested; shared-PIN name selection alone must not confer elevated access.
4. **Finish the remaining integrity and operating cutover.** Close direct legacy API gaps,
   full canonical-unit/menu/price contracts, broader retirement and scope policy, invoice edge
   cases, durable recovery and supplier delivery/outbox behavior. Rehearse a supported baseline,
   ordered migrations, seeds/grants and native backup/restore before any enablement. The
   [foundation review](docs/INVENTORY_FOUNDATION_README.md) and machine-readable finding criteria
   remain the full acceptance list.
5. **Reserved integrations.** Add Toast, Scheduling, Operations and Analytics against stable
   identities and versioned contracts. Retain external event/revision IDs, date/unit/recipe
   evidence, corrections and completeness; compare common physical-count boundaries and avoid
   duplicate theoretical usage. Toast remains analytical evidence, separate from accounting.

Continue the next milestone on a separate local branch from this published checkpoint.
Keep #15 stable for review; publish the next draft PR only when authorized. If #15 changes,
reconcile those changes into the local continuation before its later publication.

The deployment overview below describes the earlier application configuration. It is not
evidence that these workflows are deployed or that a clean target reproduces them. Supported
managed-platform bootstrap and the broader operating cutover remain unfinished.

A multi-location restaurant operations platform for Bert's Hometown Grill & Pizzeria, Rudd's Pies
and Fries, and Papa Leoni's Pizza. It covers:

- inventory counts
- purchasing/par guidance
- recipe costing
- prep planning and measured production with separate analytical inventory evidence
- a purchase-order approval chain, with supplier email and PDF
- an ownership rollup dashboard
- an AI assistant ("Sous") and an AI par advisor

**Stack:**
- **Frontend:** React 19 (CRA + CRACO), Tailwind + shadcn/ui
- **Backend:** FastAPI
- **Database:** Supabase (Postgres, via asyncpg)
- **AI:** Claude, through the Anthropic API
- **Email:** Resend
- **Hosting:** Render, configured in `render.yaml`

**No secrets are in this repo.** See `backend/.env.example` and `frontend/.env.example` for placeholders.

---

## Live deployment

| Piece | Where |
|---|---|
| Web app (static site) | `https://jaymax-concepts.onrender.com` |
| API (Python web service) | `https://jaymax-api.onrender.com` — health check `GET /api/health` |
| Database | Supabase Postgres (37 tables, RLS enabled on all; see `supabase/`) |
| Deploy branch | `main` (Render redeploys on push) |

First-deploy steps (Render services, secrets, bootstrapping the owner) are in
[`docs/HOSTING_PROVIDERS.md`](docs/HOSTING_PROVIDERS.md).

---

## Repository layout

```
backend/
  server.py            # all routes: auth, inventory, costing, prep, PO chain, AI, email/PDF
  db_pg.py             # Postgres pool (connect timeout + background retry)
  requirements.txt     # pinned Python deps (public PyPI only)
  .env.example         # placeholders only
  tests/               # pytest suites (see Tests)
frontend/
  src/                 # App.js, components/, lib/ (api.js, calc.js), hooks/
  package.json, yarn.lock
  .env.example
supabase/
  schema.sql           # pg_dump of the live schema
  README.md            # applied migrations, RLS notes
migrations/            # earlier SQL plus new review-only native migrations; see checkpoint README
scripts/               # data import + Mongo->Postgres transforms (not used: no Mongo data was migrated)
sample-data/           # sanitized demo dataset (not operational data)
docs/                  # schema, access policies, hosting, migration plan, PRD
render.yaml            # Render Blueprint for both services
```

---

## How it's set up

- **Database:** Supabase Postgres only. `USE_PG=true` on the backend, so it never connects to MongoDB.
  - The legacy Mongo route families return `410` in this mode.
  - The frontend calls `/api/pg/*` by default. Only a build with `REACT_APP_USE_PG=false` uses the legacy routes.
- **Sign-in:** email + password accounts are stored in `app_users`.
  - Passwords are hashed with PBKDF2. Sessions are HMAC-signed tokens (`AUTH_SECRET`).
  - Roles: `owner`, `manager`, `staff`, `readonly`, each with per-store access.
- **Staff PIN portal:** cooks tap in with a shared per-store PIN and pick their name from the roster.
- **Managing access (owners):** the **Staff** tab has two parts:
  - **Email / Password Logins:** create, list, reset password, remove.
  - **PIN Roster:** the names people pick after entering the shared PIN.
- **AI (Sous chat + par advisor):** runs through the Anthropic Python SDK.
  - Model: `claude-opus-5-5` (override with `ANTHROPIC_MODEL`).
  - Server-side refusal fallback is turned on.
  - When Sous can't answer, the chat shows the cause: a missing or bad key, no credits, a key not tied to a workspace, or the model not being available.
- **Supplier email:** sent through the Resend API from `EMAIL_FROM_ADDRESS`, which must be on a domain verified in Resend.

---

## Environment variables

### Backend (`jaymax-api`)

| Variable | Required | Purpose |
|---|---|---|
| `USE_PG` | yes | `true` — Supabase mode |
| `DATABASE_URL` | yes | Supabase connection string (Connect → Shared pooler, transaction mode) |
| `PYTHON_VERSION` | Render | `3.11.9` |
| `AUTH_REQUIRED` | yes | `true` |
| `AUTH_SECRET` | yes | Random secret that signs session tokens (Render generates it) |
| `CORS_ORIGINS` | yes | The web app's exact https origin, no trailing slash |
| `PUBLIC_APP_URL` | yes | The API's own https URL (PO-PDF links in emails) |
| `ANTHROPIC_API_KEY` | for AI | Anthropic API key — create it **inside a workspace** |
| `ANTHROPIC_WORKSPACE_ID` | only if needed | Needed only for an organization-level key that isn't tied to a workspace |
| `ANTHROPIC_MODEL` | no | Override the AI model |
| `RESEND_API_KEY` | for email | Resend API key |
| `EMAIL_FROM_ADDRESS` | for email | Sender address on a Resend-verified domain |
| `EMAIL_FROM_NAME` | no | Sender display name (render.yaml sets "JayMax Restaurant Group") |
| `SESSION_TTL_SECONDS` | no | Session length (default 28800 = 8 h) |
| `RATE_LIMIT_PER_MINUTE` | no | AI chat / order email rate limit (default 60) |
| `BOOTSTRAP_TOKEN` | one time | Only to create the first owner; delete it afterwards |

### Frontend (`jaymax-concepts`)

These are read when the site is built, so redeploy the static site after changing them.

| Variable | Value |
|---|---|
| `REACT_APP_BACKEND_URL` | `https://jaymax-api.onrender.com` (no trailing slash) |
| `CI` | `false` (so existing lint warnings don't fail the build) |

Render static-site settings:
- Root directory: `frontend`
- Build command: `yarn install --frozen-lockfile && yarn build`
- Publish directory: `build`
- Rewrite: `/*` → `/index.html`

---

## Local development

Prerequisites: Python 3.11+, Node 18+ with **Yarn** (not npm), and a Postgres connection string
(Supabase, or a local Postgres loaded from `supabase/schema.sql`).

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # fill in real values; USE_PG=true
uvicorn server:app --host 0.0.0.0 --port 8001 --reload

# Frontend
cd frontend
yarn install
cp .env.example .env          # REACT_APP_BACKEND_URL=http://localhost:8001
yarn start                    # http://localhost:3000
```

All API routes are under `/api`; Postgres routes under `/api/pg`.

### First owner account

The first owner is created once, while `BOOTSTRAP_TOKEN` is set on the API, by calling
`POST /api/auth/bootstrap`. The exact request is in `docs/HOSTING_PROVIDERS.md`. After that:

1. Delete `BOOTSTRAP_TOKEN` from the API's environment.
2. Create every other login from **Staff → Email / Password Logins**.

---

## Tests

```bash
cd backend
# Offline unit tests (no database needed)
pytest --noconftest tests/test_pg_routes.py tests/test_pg_migrations.py -q
# Integration tests against a real Postgres loaded from supabase/schema.sql
TEST_PG_URL=postgresql://postgres@localhost:55432/jmax_test \
  pytest --noconftest tests/test_pg_local_integration.py -q
```

- The AI tests run the real Anthropic SDK against a mock HTTP transport, so they make no network calls and need no key.
- The other suites in `backend/tests/` target the legacy Mongo deployment through a running server, so they need its URL and credentials.

---

## Security

- Every API route requires a signed-in session. Roles and per-store access are enforced in the backend.
- The staff portal is the one exception by design: it uses a per-store PIN. **Set a custom PIN for every store.** A store without one accepts `1234`.
- RLS is enabled on every Supabase table with no policies, so the public `anon` key can't read or write anything. The backend connects as the database owner.
- Never commit keys or passwords, and never paste them into chat or tickets. Enter them only in Render or Supabase.

More detail: [`docs/ACCESS_POLICIES.md`](docs/ACCESS_POLICIES.md) and [`docs/KNOWN_GAPS.md`](docs/KNOWN_GAPS.md).
