# Staff production submissions and manager acceptance — October 7, 2026

Publication note: this document preserves its pre-publication local milestone.
The verified continuation is now published in [draft PR #16](https://github.com/jeffwelch0620-png/JayMax-Concepts-/pull/16);
see the [checkpoint README](STAFF_WORKFLOW_CHECKPOINT_README.md). No operational
migration or enablement occurred. Historical local-status statements below refer
to the original snapshot, which is preserved unchanged.

This continues locally from PR #15's publication commit
`ae10c8cab319b7f1ed842711076bacd132653f43` on
`codex/staff-prep-count-continuation`. Published PRs and previous snapshots remain
unchanged. This milestone applies no operational migration, imports no real data,
enables no operational feature and makes no commit or push.

## Measurements before production posting

An active roster identity submits against its current manager-issued native task
assignment, explicit location calendar date and daily/bulk track. The task must
be released, included, positive, open and free of changed production requiring
reconciliation. Roster changes, reassignment, reopening, replacement of the dated
draft and recipe/unit/source drift hold submissions or acceptance for review.
Staff cannot choose a different recipe or turn a plan quantity into actual output.

Each submission contains the full measured batch: actual usable output, recipe
batch multiplier, every gross ingredient quantity, explicit measurement basis,
approved units/conversions, prepared source lots, physical timestamp, confirmed
location timezone/calendar date, single-output confirmation and evidence. Blank
is unknown. Output must be positive; an empty/failed batch is not fabricated as
production. Included trim/loss explains the gross input and does not create a
second waste withdrawal. Recipe-estimated inputs are identified as estimates;
measured usable output remains explicit. Costs remain uncalculated.

Saving or revising a submission records no batch, ingredient withdrawal, stock,
task completion, waste or accounting movement. It does not reserve prepared
ingredients. Available lots are checked again at acceptance; another accepted
use can hold a pending submission with insufficient sources. Pending physical
production is evidence awaiting manager reconciliation, not available recorded
output for further allocation.

## Immutable revisions and decisions

A generated stable submission root identifies this physical production report.
Each revision keeps its original task and claimed staff identity, follows the
exact current revision and retains the previous quantities. Pending submissions
can be revised or withdrawn. Rejected submissions can be revised and reviewed
again. Withdrawal retains the original assignment and history and creates no
production. Withdrawn or accepted roots cannot be edited by staff.

New roots cannot reuse an occupied root or revision ID, including another store's
identity. Preview and commit return 409 without partial submission history. Real
cross-module request-key collisions likewise roll back batch/link/finish/decision
effects before returning 409; the caller must refresh and review a new request.

Managers inspect submitted usable output, gross inputs, source lots and evidence.
Acceptance rejects any recorded revision author and an actor whose canonical ID
matches the claimed roster ID. Shared-PIN identity remains unverified; these known-ID
guards do not replace the planned login work or prove individual review independence.
Acceptance rechecks the current assignment, active roster, recipe mapping,
allocation availability and task progress. One transaction records exactly one
measured batch, links its production root to the native task and saves its
immutable acceptance. A manager explicitly chooses whether to finish the task;
if chosen, a separate finish event follows the link in the same transaction.
Partial batches accumulate without automatic completion from planned quantities.

Rejection saves a reason and posts no production. A stale but current undecided
submission can still be rejected after reassignment or draft replacement, allowing
review of stranded reports. Each submitted revision can receive only one decision;
superseded, withdrawn or decided revisions cannot be accepted. Competing decisions
serialize by location and only one wins.

Acceptance never creates a second purchased-inventory withdrawal or Food Cost
expense. Track 1 continues to use purchased-item physical counts, received-date
purchases and explicit count values. Track 2 measured production and its input
bases explain usage. Future Toast Track 3 evidence remains separate.

Accepted measurement corrections use the existing manager batch replacement/void
workflow, followed by task reconciliation. Original acceptance and linked batch
remain visible. Allocated output still holds corrections until its dependencies
are resolved. These routes do not create a historical dependency solver.

## Identity, retries and atomic safeguards

Existing staff/location authorization is reused. Shared PIN access and a selected
roster name are explicitly claimed identity; they are not proof of employee
identity and do not grant manager authority. Both the credential actor/basis and
the stable claimed roster identity are retained. Employee account mapping and
login/PIN redesign remain deferred. PINs are omitted from database snapshots,
fingerprints and retained form drafts; the current credential is sent separately.

Same-key retries return the original immutable submission/decision and original
accepted batch/link/finish, together with current history/progress. Keys bind the
store, date, track, submitted body, credential actor/basis or manager actor. Another
payload or actor cannot reuse them. A new key cannot reuse a stale root revision
or decide an already decided submission. Independent new roots are explicitly new
reports; software cannot prove that two reports describe different physical work.
Managers must check overlapping reports before acceptance.

The UI confirms the matching revision and all accepted effects before success.
Wrong/missing acknowledgements hold the exact request for retry. Drafts survive
component/date/location navigation in the current app cache; reload or logout is
not durable storage. Logout clears staff submission cache entries, and late
responses cannot recreate cleared scopes or change a different selected date.
Definitive conflicts require explicit revision and fresh review.

Private SQL guards enforce local task/assignment/roster scope, exact revision
chains, immutable snapshots and one decision per revision. Batch and execution
effects carry the submitted revision ID; deferred seals require their matching
acceptance in the same transaction. Any failed batch, movement, link, finish or
decision rolls back the entire transaction. Acceptance cannot attach previously
recorded production or add facts to sealed history.

## Additive installation and evidence boundary

`20261007_staff_prep_production.sql` follows the native task assignment and
execution/progress migrations, preserving the existing measured batch foundation.
It adds private submission/decision tables and an internal transaction marker on
execution events. Existing marker values stay NULL; internal metadata is omitted
from public execution JSON, preserving old pending reviews and retry snapshots.
Recycle application connections after DDL to avoid stale row/statement caches.

New backend `STAFF_PREP_PRODUCTION_ENABLED` and frontend
`REACT_APP_STAFF_PREP_PRODUCTION` depend on native staff task access. All fifteen
native feature pairs remain false in examples. This document is not authorization
to apply migrations or enable features operationally.

Current validation counts and the final snapshot are recorded in the repository
README and machine-readable review. Evidence covers synthetic UI/API behavior,
disposable PostgreSQL guards, atomic failure/retry/concurrency, additive upgrade,
whole SQL restore and private ACL checks. The dedicated test database is outside
synced folders. Initial failed fixtures and the caught staff bearer-route allowlist
gap are retained with their corrected results. Backend coverage combines passing
regression cases with the corrected authorization/retry recheck, counting each
test once. Both shared-PIN and bearer submissions are verified; manager decisions
remain restricted.
There is no live-browser, operational or managed-platform runtime proof.

Next: review the remaining legacy operating endpoints and historical dependency
correction contracts, then prepare a combined operating cutover and recovery trial.
Scheduling, Operations, analytics and Toast can build on these stable identities
and journals after their remaining boundaries are reviewed.
