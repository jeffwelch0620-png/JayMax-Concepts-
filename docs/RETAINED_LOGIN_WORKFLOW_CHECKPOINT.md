# Enabled workflows through retained build LOGINs â€” October 9, 2026

**Selected hosted workflow milestone passed.** The final independent comparison
confirms global Track 1 and the complete migration ledger unchanged, all prior
prep history preserved, other locations' state rows preserved, and stable fields
of the labelled test location preserved. Its revision/update time advances as
expected. Account cleanup and forecast rollback are verified. Six local guards
pass. This does not clear deployment or merge holds.

This follows the [private build connection setup](PRIVATE_BUILD_CONNECTIONS_CHECKPOINT.md).
The selected hosted checks use the retained inventory/account roles, the unchanged
application routes and the previously labelled invented location. Native feature
flags are enabled only inside this probe process. Active app settings and staged
disk flags remain held; no browser deployment or real invoice import occurs.

## Data-integrity checks

Before writes, the probe saves original-column fingerprints for the existing
application tables, full migration-ledger row fingerprints and whole-row hashes
for all eight Track 1 fact tables across all locations. It requires an unambiguous
pair of the existing synthetic physical-count boundaries. Later account,
forecast and prep activity must preserve that exact actual Food Cost report.

The account connection creates/logs in/deletes one uniquely named invented
manager account. The email is checked absent before creation; its exact identity
is journalled for cleanup after an uncertain acknowledgment. This exercises the
separate connection, not a redesign or full acceptance test of authentication.
The probe signs invented actor tokens to exercise application role/location
authorization and independent-review rules. This does not verify a human staff
identity or change the previously deferred sign-in/PIN work.

Manual sales forecasts are written through the actual reviewed API with real
inventory-role permissions inside an outer rollback transaction. Exact cents,
the explicit nonaccounting basis and stale-save rejection are checked. Review
uses the route's own read-only transaction before the write rollback wrapper. The
forecast row and nested API writes must disappear on rollback. This is planning
input; it does not establish Toast portion sales, complete recipe depletion,
theoretical sales consumption or operational pars. Toast remains future work.

The prep scenario reuses the established staff-production workflow: reviewed
planning, a new synthetic service day, release, roster assignment, concurrent
retry, staff measurement, independent acceptance, partial progress and explicit
finish. Pending submissions must create no batch. Acceptance must create exactly
one measured prep batch, with exact output `2.000000000001`, despite concurrent
retries. Original idempotency keys are replayed through a fresh authenticated pool
after completion, with private staff projections and current task status checked.

The native prep audit fixtures remain labelled and retained. No previous record
is deleted. Postflight compares pre-existing application values while excluding
only this run's newly generated wrapper/prep activity actors and roster IDs,
plus the exact linked new prep graph. No complete prep location is excluded.
All previous prep rows must reproduce their original full-row fingerprints.
Other locations' state rows retain their full-row baselines. For this labelled
fixture alone, revision/update time may advance; all remaining state fields must
match a separately captured baseline. All Track 1 rows and all migration-ledger rows must remain
unchanged. The invented account is removed; forecast mutations are rolled back.

## Connection and evidence boundary

Every primary pool acquisition, including the workflow's fresh pool, checks
`session_user` and `current_user` against the recorded retained inventory role.
The auxiliary pool uses its actual startup permission gate. The complete hosted
inventory contract is reassessed before workflow writes. There is no SET ROLE
substitution, owner-backed application pool or owner fallback. Owner connections
are used only for read-only baselines and independent postflight comparisons.

The probe journals safe stages and mutation identities before continuing. A held
or interrupted case requires reconciliation before another run; blindly repeating
it could create another synthetic batch or service day. Credentials, generated
test passwords and returned tokens are never written into the safe evidence.
External push delivery is disabled; no email, Toast or AI service is invoked.

Six local guard tests cover recorded role identity/held disk flags,
operational-store/cross-project rejection, invalid-overlay rejection before
connection, bounded journal replacement retries, exact nested nonaccounting
forecast responses, and operational-state/mismatched-prep exclusion rejection
before SQL. One existing Starlette deprecation warning remains. These are
selected API/SQL checks, not a full backend suite, new frontend build or browser
acceptance run. Earlier full frontend results remain historical.

## Interrupted attempt and reconciliation

The first attempt stopped on a Windows journal replacement permission error
following test-account creation. Cleanup verified that account absent, and no
forecast or prep writes had begun. The initial independent comparison held on
two new middleware audit records. Read-only reconciliation verified their exact
test actor, routes and statuses; excluding only those two records restored the
original application fingerprints. Global Track 1 and the complete ledger stayed
unchanged. Both held receipts and the verified reconciliation are retained.

Journal replacement now retries a transient file lock for a bounded interval and
stops if the journal remains unavailable. Forecast-save middleware audit writes share
the rollback connection; review audit entries remain identifiable. These changes are covered by the selected local guards;
they do not identify what caused the original Windows file lock.

A second attempt passed account create/login/delete but held when the test's
outer transaction conflicted with the forecast review's read-only isolation.
The outer transaction rolled back before forecast writes; no prep work began.
Independent reconciliation verified the three account/report audit rows, exact
account absence and unchanged original application, global Track 1 and ledger
fingerprints. The wrapper now performs the real review before entering the
rollback transaction used for saves. Both reconciled attempts remain in evidence.

The repository-wide test fixture expects `/app/frontend/.env`, which is absent
on this Windows workspace. The selected standalone guards run with that unrelated
conftest disabled: six pass, with one existing Starlette warning. This is not a
claim that the full backend suite passed.

A third attempt reached a successful forecast save but held on a probe response
mapping error: the saved amount belongs inside `projection`, not at the top level.
The outer transaction rolled the save and its audit write back. A new guard
checks the nested exact amount and nonaccounting fields, including rejecting
missing/flat responses, fractional cents and an accounting basis. Read-only
reconciliation verified the four retained account/report/review audit rows,
account absence and unchanged original application, global Track 1 and ledger
fingerprints. No prep work had begun. All three held attempts remain in evidence.

The fourth attempt passed the selected account, forecast and complete prep/replay
scenario. Its broad preservation comparison correctly held because the probe
had counted expected prep appends and the synthetic location's save-conflict
revision change as unexpected edits. Track 1 and the ledger passed independently.
Read-only reconciliation checks exact new batch/task/submission links against
all prior prep-row fingerprints. The old receipt lacks separate baselines for
non-fixture state rows and the fixture's stable fields, so full state preservation
cannot be claimed retroactively. The corrected probe captures those baselines
before writes and compares them afterward; only the labelled fixture's revision
and update time may advance. A fresh controlled scenario subsequently passed
that corrected comparison. Previous immutable fixtures remain retained.

## Remaining steps

Next, test credential rotation,
reconnect and owner-assisted recovery with the private overlay. Browser/Data API
exposure, matched compiled/server flags, managed Auth/Storage/Vault recovery,
broader enabled workflows and sequential PR-stack validation remain open.
Continue holding merges. Keep the active app connection unchanged until the
remaining controlled checks support cutover. Source, safe evidence and a chained
snapshot can be reviewed; private configuration remains outside Git and shared
artifacts. No PR is pushed/merged or application published by this checkpoint.

## Final evidence

The passing receipt is `jaymax-retained-login-enabled-workflows-v1`: `retained-workflows-20261009T1436145940648Z.json`. It covers 118 existing application/native
tables and 54 complete migration-ledger rows. The new synthetic prep graph
contains 14 exact linked records across 10 tables. Receipt flags distinguish
expected prep appends and synthetic state revision changes from preserved
accounting facts, earlier prep history and other locations' state values.
Safe receipts, all reconciled holds and the six-test XML are included in the
chained local review package. Private configuration remains excluded.
