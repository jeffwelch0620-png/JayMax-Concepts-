# JayMax Restaurant Group â€” Inventory / Prep / Food Costing

## Now

Inventory serves Bert's, Rudd's and Papa Leoni's. PostgreSQL is authoritative
for catalog/units, purchases, counts, prep/production and stock effects.
**Actual purchased-item counts + received purchases âˆ’ closing count** determine
Track 1 usage; count values are explicit. Prep/waste and sales explain variances
without rewriting that accounting baseline. Taxes/fees stay separate.

The accepted baseline is [merged PR71](https://github.com/jeffwelch0620-png/JayMax-Concepts-/pull/71)
**a67aa375**, tree-identical to approved **c5f063c**. The four
[approved-head checks](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/40214920647)
and [merged-main checks](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/40215493932)
passed separately. Merge and automatic Render test deployment were approved;
deployment completion and live acceptance were not inspected. PR70's earlier
[head](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/40206917665)
and [main](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/40208642033)
receipts remain historical source evidence.

The first merged integration slice is a distinct personal-owner/manager
**Manager overview** tab, with purchased-item count context and dated prep
progress/review flags. It uses two existing authorized GET readers, isolates
unconfirmed sections and stale scope responses, and opens the native Prep
workflow with the same restaurant/date/track. Existing dashboards, Operations
archive access and retained drafts remain. That merged read-only slice included
no backend, schema or business-write commands; the local extension below adds
note-only persistence.

Owner-selected fictional starting scope: **Bert's / October 25, 2026 / Bulk Prep**.
The owner confirmed Supabase is still a development database with no operational
data. Tests and the separate local preview use clearly labelled fictional data;
no fixtures are inserted into Supabase or substituted into production screens.
PR71's original head passed **1,150 frontend tests in 87 suites**, the strict
production build and all four CI checks. The M1 review amendment clears the
overview's one-time prep context on manual tab selection, preserving retained
drafts. Its four real-component App navigation cases reproduce the old failure
and verify ordinary Today/Daily entry, original dated-draft recovery and
restaurant/session isolation. The amended full frontend run passed **1,154 tests
in 88 suites** and the strict production build passed. Approved-head and
merged-main CI separately passed all four checks. These are PR71 receipts,
not the follow-on handoff-note validation receipts below. The fictional desktop preview was inspected and its exact prep
navigation context verified. Initial test-setup failures and the corrected strict
build warning are recorded in the
[receiving contract, acceptance and coverage matrix](docs/INTEGRATION_MANAGER_OVERVIEW_20261025.md).

Inventory Build Main remains the sole coordinating chat; Companion PR72
**b73a80d** is the source baseline. This read-only milestone does not adopt its
D1 workspace service, candidate migrations, persistent operations or scheduling.
The approved local receiving extension implements one **manager production-shift summary
and next-shift note**: draft, submit, reload and correct with history. It uses
existing personal Inventory accounts with a fresh server-side role/store lookup,
one shared note per store/date/track and exact-request recovery. Full named
responsibility-transfer handoffs depend on real leadership/people mappings and
remain separate. The [canonical coverage and proposed receiving contract](docs/INTEGRATION_MANAGER_OVERVIEW_20261025.md#proposed-persistent-manager-handoff-note)
lists the logical tables, permission rows, default-off capability and fictional
acceptance plan. The implementation includes a default-off Manager handoff tab, revisioned API,
separate receiving migration and fictional schema/role/recovery tests. Its
[local acceptance record](docs/MANAGER_HANDOFF_LOCAL_ACCEPTANCE_20261025.md)
distinguishes tests from future CI/live acceptance. Existing sealed native/par
installers and their source pins are unchanged; the new migration, reviewed
timezone rows, permissions and capability activation need a separate plan.
No hosted SQL, grant, credential or configuration change has been performed.
Local validation passed **1,188 frontend tests in 92 suites**, the strict build and
**10 disposable PostgreSQL methods**, including real fictional dump/restore.
The broad offline run passed 1,947/1,953 reported cases; all six local dependency
failures cleared in the corrected, overlapping 155-case focused rerun. Full details
and initial corrections are in the acceptance record; fresh CI is still pending.
Prompt before each new draft publication and merge.
Hosted work, service controls and
credential, grant and schema changes remain held. S1 remains partial; optional
harness work is parked while local integration proceeds. Ordering stays manual
and Track 1 remains independent.

## Historical PR69 diagnostic checkpoint

The following preserves the earlier pre-PR70 local receipt and S1 context.
Accepted baseline at that checkpoint was [merged PR69](https://github.com/jeffwelch0620-png/JayMax-Concepts-/pull/69)
**6740590**, tree-identical to reviewed **13c4e53**. All four
[reviewed-head checks](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/40160234719)
and [merged-main checks](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/40160847615)
passed separately: 1,079 frontend tests/strict build, 1,904 offline cases and
344 backend/disposable PostgreSQL cases. Those are accepted-baseline receipts,
not fresh CI for the local follow-up below.

The separately approved October 25 S1 attempt confirmed that commit Live, then
closed held after one P01 intent and zero validated completed results, with
`probe_shape` at response validation. Owner login and the deliberate lockout
sequence did not run. Its consumed claims and cleanup evidence remain intact.
Memory stayed above the selected 1-GiB/15% start and 512-MiB/10% running guards;
the separate 1,536-MiB quiet evidence target missed. No security acceptance.

The owner-authorized LOCAL
[first-verification diagnostic distinction](docs/S1_PIN_VERIFICATION_DIAGNOSTICS_20261025.md)
reports only an exact P01 `{"ok": false}` as `pin_verification_rejected`.
Malformed responses retain `probe_shape`; both hold without retry or login.
No response contents or secret inputs are saved. All **298 selected local cases**
passed across the initial **296/298** run and corrected **2/2** TLS rerun; the
initial two failures were missing local `cryptography`, resolved by using an
existing test dependency path without source changes or installation. All
**14 new cases** passed initially. The selection covers six S1 safety modules;
no broad offline, frontend or PostgreSQL run is claimed. Prompt before draft
publication; CI, merge and any fresh live
attempt remain separate approvals. Hosted execution and credential, grant and
schema changes stay held. No app endpoint or protection threshold changed.

Historical PR68 baseline was [merged PR68](https://github.com/jeffwelch0620-png/JayMax-Concepts-/pull/68)
**15d7f1f**, tree-identical to reviewed **b1053a0**. All four
[reviewed-head CI checks](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/40155278817)
and [merged-main CI checks](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/40156278013)
passed separately. The owner-approved local
[F1/G1/G2/G3 follow-up](docs/S1_POST_CLAIM_ACTIVATION_GATES_20261024.md)
separates post-claim setup in version-2 resource evidence, adds the optional
raise-only pre-claim operator floor, and requires a same-shape/session real-time
rehearsal with >=1536 MiB quiet-wait minima before requesting live approval.
It changes no app endpoint, PIN policy, credential, grant or database schema.
Original-head local validation passed **1,889 offline cases** and the overlapping
**121-case focused selection**. The final actual-clock/resource loopback run
passed thirteen fictional requests in **139.047 seconds**, with
all seven phases, source hashes and cleanup verified. Numeric quiet-wait G2
gate **passed** with a selected 1536 MiB operator floor; fresh accepted-source
same-session G1 qualification is still required. Those receipts are preserved
as historical evidence after the owner-approved PR69 P1/P2 amendment: the
controller now retains a durably claimed journal before enforcing the
post-claim guard, and prepare supports explicit roles/roster/PIN shape flags
with a safe summary. Genuine storage/callback failures still report uncertainty.
This pre-merge checkpoint is historical; PR69 was subsequently accepted as
recorded above. No new live packet or hosted execution is authorized.

PR69 amendment validation: the corrected focused selection passed **56 cases**.
The broad local offline run passed **1,903/1,904 cases**; one unchanged Windows
callback-start timing test failed, then the complete **10-case process suite**
passed on rerun without code changes. PR69's later full CI passed; profiles
overlap. The amended CLI's actual-clock/resource loopback run passed thirteen
fictional requests in **139.453 seconds**, with source hashes, journal closure
and cleanup verified. Numeric **G2 failed** at **1386.793 MiB** on both sides
against 1536 MiB. Functional completion does not qualify a live attempt; the
original-head receipts above are historical. Details and initial/corrected
test results are in the linked qualification runbook.

Earlier accepted baseline was [merged PR67](https://github.com/jeffwelch0620-png/JayMax-Concepts-/pull/67)
**e0adc3b**, tree-identical to reviewed **dedeb82**. All four
[reviewed-head CI checks](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/40149826393)
and [merged-main CI checks](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/40153362211)
passed separately. Its fixed failure stages and independent cleanup diagnostics
are accepted tooling, not proof of the original S1 cause or live acceptance.
The accepted PR68 [N1/R1 follow-up](docs/S1_REAL_RESOURCE_REHEARSAL_20261024.md)
adds subclass categories and a digest-bound real-clock/resource rehearsal with
numeric per-phase minima. It changes no app endpoint, PIN policy, credential,
grant or schema. Final local validation passed **1,849 offline cases** and
the overlapping **80-case focused selection**. The real-clock loopback rehearsal
passed all thirteen fictional requests in **148.828 seconds**, with source hashes
and cleanup verified. Minimum free memory was about **1,149 MiB**, above guards
but below the suggested 1.5 GiB headroom target; live acceptance remains open.
Failed/corrected exploratory runs are retained in the follow-up notes. Prompt
before publishing the next draft; hosted and credential/grant/schema work stays held.

Earlier PR66 baseline **42a78b8**: the separately approved
October 24 owner-only S1 attempt confirmed that deployment, accepted protected
inputs locally, then held before its first request intent. It sent **zero API
requests**; no owner login/session or PIN lockout occurred. Both claims are
consumed and owned cleanup passed. The subsequent seven-case fictional review
did not reproduce the hold; its cause remains unknown.

The accepted [safe failure-attribution change](docs/S1_SAFE_FAILURE_ATTRIBUTION_20261024.md)
adds fixed worker/controller stages and allowlisted reasons, with primary and
cleanup failures reported separately. It never records raw exception text or
secret inputs. It preserves approval, source/resource/time, claim and request
guards. This is a diagnostic improvement, not a proven fix for the original hold.
PR67 local validation passed **1,809 offline cases**, including 39 new
diagnostic cases; the 41-case focused profile overlaps. Initial local dependency
selection failures and corrected reruns are documented in the follow-up notes.
Draft publication, CI, merge and any fresh live attempt remain separate gates;
hosted work and credential/grant/schema changes are held.

Earlier transport baseline: PR65 **1db9797**, tree-identical to tested 2898c77. All four
[reviewed-head checks](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/40103720101)
and [merged-main checks](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/40104331749)
passed separately. The October 24 approved S1 v3 attempt observed API PR64 and
frontend PR53 Live with finite service source proofs. Its two-connection read-only
collector completed in 11.391 seconds: 13 scoped relations, ledger 55 and 17,468
recorded owner/manager audit entries with a retained 200-row sample. Aggregate
coverage was complete; the sample was truncated and is not exhaustive security
review. Both owned database clients closed. PIN/role probes remained NOT EVALUATED:
the attempt stopped before any controlled API/PIN request because the required
protected-input request transport was unavailable. That window is closed and
its approval consumed. Existing app/service/credential settings remained unchanged.

The authorized [local transport design and rehearsal](docs/S1_PROTECTED_REQUEST_TRANSPORT_20261024.md)
now uses isolated anonymous/personal contexts, legitimate fictional logins,
strict route/response/time limits, one-use request slots and minimized receipts.
The [PR65](https://github.com/jeffwelch0620-png/JayMax-Concepts-/pull/65) review
amendment enforces P09 recovery waits before P10/P11, requires successful P10
before P11, and binds separate absolute stop-checks/cleanup deadlines. Receipt
metadata documents unavailable server revocation and the configurable eight-hour
session default; local session cleanup does not revoke issued tokens.
PR65's amended local validation passed 1,687 offline cases and the overlapping
67-test transport profile; its reviewed-head/main CI is linked above.
Its LocalTransport entry point deliberately has **no hosted mode**. The authorized
[activation-adapter implementation](docs/S1_ACTIVATION_ADAPTER_20261024.md) adds a
separate approval-bound HTTPS factory, durable request journal and supervised
private console worker, tested only with fictional/local targets. The real
fictional console milestone passed. No actual hosted execution or secret input
was performed. Original follow-up validation passed all 1,736 offline cases, including
the new process, TLS, identity, protocol and storage-failure coverage. Local
validation, independent review, hosted activation and a fresh
live approval remain separate gates. The
[collector history](docs/S1_VISIBILITY_SESSION_FOLLOWUP_20261023.md) remains dated
evidence; this slice does not change collector or application behavior.
The owner-authorized [PR66](https://github.com/jeffwelch0620-png/JayMax-Concepts-/pull/66)
review amendments validate protected input before claiming an attempt, permit
two local corrections per field and require at least 397 seconds to the existing
stop-checks cutoff before claiming. The disabled-PIN variant sends an empty
non-candidate while preserving server throttling. Full per-request integrity
hashes remain, with measured timing; preflight facts are labeled owner-reported.
Account holders enter their own credentials or use approved dedicated test
accounts; credentials are never relayed to the operator. No hosted attempt or
real credential input is included in these amendments.
Amended local validation passed **1,770 offline cases** (698 tests plus 1,072
subtests), with no failures/errors/skips. The initial fixture failure and corrected
rerun are preserved in the [review amendment notes](docs/PR66_REVIEW_AMENDMENTS_20261024.md),
alongside the final 21-request loopback timing: 17.377 seconds combined integrity
checks. Full hashing remains; hosted timing is unproven. Fresh amended-head CI
and separate merge/automatic-deployment approval remain required.

## Next

- Finish local F1/G1/G2/G3 validation and JMax updates, then prompt before the
  next draft PR push. New live proposals require fresh accepted-source evidence
  from the same operator-machine session and matching roles/roster/PIN/floor
  shape, receipt digest and >=1536 MiB minima in the quiet wait on both sides.
  Preserve consumed attempts and the unresolved original cause. All hosted work
  and credential/grant/schema changes remain held.
- Review the [coordinated approval index](docs/PAR_SECURITY_APPROVAL_INDEX_20261023.md)
  and [security/identity/permissions plan](docs/SECURITY_IDENTITY_PERMISSIONS_PLAN_20261023.md).
  S1 verification comes first; a targeted S2a rotation packet no longer waits for
  the entire restricted-role redesign. All live approvals remain separate.
- The [par installation proposal](docs/PAR_INSTALLATION_PROPOSAL_20261023.md)
  owns the proposed 60-minute P1 schedule. A [pre-built P2 checklist](docs/P2_EXACT_PLAN_DECISION_CHECKLIST.md)
  binds the later fresh executable plan; no plan SHA/version is allocated here.
- R1 permission/dual-pool tests and shared-identity implementation are future
  local slices. This chat coordinates the queue; Companion is a bounded source
  reference. Supabase Auth is conditional, not selected or configured.

## Held

All hosted work/service pauses and credential, grant, schema, connection and
provider changes stay held. No draft PR is pushed before the owner's prompt.
Merge and automatic Render test deployment need separate approval. Ordering
remains manual, par editing frozen and operational release unapproved.

Personal owner/manager authority uses personal login. Shared-PIN identification
does not mint a session; a store without a configured PIN has its portal disabled.
The shared attempt budget can temporarily block all staff devices at that store.
These source fixes do not by themselves close deployed G04/security acceptance.

## Project references

| Area | Entry point |
| --- | --- |
| Current par status and historical provenance | [Hosted par plan](docs/HOSTED_REVIEWED_PAR_MIGRATION_PLAN.md) |
| Installation/recovery controls | [Runbook entry](docs/REVIEWED_PAR_INSTALLATION_RUNBOOK_20261022.md) |
| Non-executable permission design | [Delta](docs/RUNTIME_PERMISSION_DELTA_PROPOSAL_20261023.json) |
| Foundation, mappings and accounting relationships | [Foundation checkpoint](docs/INVENTORY_FOUNDATION_README.md) |
| Staff PIN security and limitations | [PIN security](docs/STAFF_PIN_SECURITY.md) |
| Current collaborator workflow | [JMAX workflow](https://chatgpt.com/space/page_1e9f0baababc8191a6f628ce4799af7a) |
| Dated implementation/deployment/test/setup record | [Verbatim README archive](README_HISTORY_20261023.md) |

The archive preserves all earlier milestones and setup text unchanged, including
obsolete PIN defaults, deployment claims and pending gates. It is dated evidence,
not a current setup/run command. Do not infer current hosting tier, source
coverage, permissions or table counts from it. Existing hosting is unchanged;
no paid IPv4 add-on is proposed. No secret values belong in Git or shared docs.
