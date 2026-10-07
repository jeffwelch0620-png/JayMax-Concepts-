# Native staff prep count submissions — October 7, 2026

Publication note: this document preserves its pre-publication local milestone.
The verified continuation is now published in [draft PR #16](https://github.com/jeffwelch0620-png/JayMax-Concepts-/pull/16);
see the [checkpoint README](STAFF_WORKFLOW_CHECKPOINT_README.md). No operational
migration or enablement occurred. Historical local-status statements below refer
to the original snapshot, which is preserved unchanged.

This is a local continuation from published draft PR #15, on
`codex/staff-prep-count-continuation`. No new PR, operational migration, feature
enablement, real data import or deployment is included.

## Measurement and review contract

A manager issues a full prepared-inventory sheet for a declared physical instant,
location calendar date and IANA timezone. The manager selects one current verified
count profile for every prepared identity, previews its scope/conversions and
explicitly confirms it. The sheet pins product version, count profile, displayed
name, count/base units, conversion factor, date/time, instructions and issuer.
Purchased inventory is excluded. There is one active issued sheet per physical
boundary; a rejected sheet remains in history and permits a new issue.

Staff submit quantities for every issued identity, with a counter name and
measurement note. A blank quantity is retained as unknown; an explicit zero means
physically measured empty. Missing individual evidence may be retained in a draft,
but acceptance requires every quantity and its measurement evidence. Unsupported
extra identities, duplicates, negative/nonfinite numbers, invented values or unit
overrides are rejected. Quantities retain up to 16 whole and 12 fractional digits,
without floating-point conversion. Scope is currently full prepared inventory,
limited to 500 identities; arbitrary partial-scope counts are separate work.

Every successful submission appends an immutable revision. Concurrent submissions
against one reviewed state cannot both silently replace it. An exact retry returns
the original submission alongside current sheet/history evidence; a different
payload or actor cannot reuse that request key. No submission changes a stock
balance or automatically becomes a planning count.

A manager previews acceptance or rejection with a reason and explicitly confirms
the decision. Acceptance requires the latest complete submission, unchanged
prepared scope/profiles, the issued physical boundary and a freshly reviewed
native observation hash. It atomically creates one full `prep_inventory`
physical-count observation and one immutable decision referencing that submission.
Rejection creates no physical observation. An observation already at that instant,
a newer submission, a definition/unit change or an already decided sheet holds
acceptance. A stale or unused sheet can still be explicitly reviewed and rejected.

Accepted counts feed the existing dated-prep draft and analytical period paths.
Both daily and bulk plans can use the same full prepared-inventory count; the
count is not duplicated by track. Existing planning rules select the latest current
count from the previous location calendar day. Later corrections or voids append
through the existing manager observation journal, preserving the original staff
submission, acceptance and physical boundary. Dependent-opening restrictions still
apply. Overnight service-date policy remains separate from this calendar-day model.

## Identity and access boundary

The existing account or shared-PIN authorization callback is reused. Issuance and
decisions require owner/manager write access; staff can list open issued sheets and
submit quantities only at allowed locations. Readonly, cross-location and invalid
PIN requests are held, and staff cannot issue or accept sheets.

`submitted_by` records the server-derived bearer identity or `shared-pin` credential
class. The separate counter name is claimed attribution, including when the portal
prefills it from the roster. A shared PIN/roster choice does not verify an employee
identity or provide elevated authority. Neither the PIN nor a PIN-derived audit
digest is retained in the submission. Login/PIN redesign and verified staff
assignment remain future work; this milestone does not claim those fixes.

## Migration, retained legacy records and recovery

`20261007_staff_prep_counts.sql` requires the native prep definition, batch and
observation migrations. The covered rehearsal includes reviewed planning and dated
draft dependencies. It adds immutable `staff_sheets`, `staff_submissions` and
`staff_decisions` in `prep_inventory`, with scoped foreign keys and request identities.

The migration locks legacy count tables while preserving every original field of
prep/commissary sessions and their lines in `legacy_count_sources`. It freezes those
legacy session/line writes, including changes that would move a row out of the held
scope. Other count types are not frozen by this migration. Original rows stay in
place; raw snapshots do not become native measurements or guessed unit mappings.
The legacy GET-that-created-a-session, entry save and submit handlers now return
an explicit hold once the schema is installed, including with the feature flag off.
Historical legacy reads remain historical, separate from accepted native counts.

Database guards enforce full current scope/profiles, one active physical boundary,
continuous submission revisions, exact membership and retained request-body fields.
Acceptance must reference the latest immutable submission and a matching new count
created in the same transaction, with pinned units, submitted quantities, evidence,
actor and reviewed observation. Altered staff quantities cannot be accepted by
fabricating a decision. Failure rolls back the observation, decision, initial
calendar policy and revision change together. Tables and private functions are
withheld from anonymous/public client roles.

`STAFF_PREP_COUNTS_ENABLED` and `REACT_APP_STAFF_PREP_COUNTS` remain false in example
files. They require native prep observation dependencies; no separate accounting
gate is relaxed. Installed guards remain active when flags are off. Disabling a
flag is not a rollback plan. Whole native SQL backup/restore includes the new
tables, guards, legacy snapshots and exact acceptance retries. A complete managed
platform bootstrap, migration/grant recipe and operational restore remain pending.

## UI save integrity

The manager Prep/Evening Count view issues and reviews native sheets; the staff
Counts view displays a separate prep section alongside purchased-item count sheets.
Uncertain issue/submission/decision responses retain the exact body and UUID key.
Fields are held until the same request is confirmed or the user explicitly starts
a revised review after a rejected request. Preview edits invalidate confirmation.
Acknowledgements validate location, immutable sheet/submission/decision identity,
request key, submitted body, reviewed hashes and native observation evidence.

Staff and manager drafts survive navigation in the current App instance. An
uncertain staff request stays visible for retry even if a subsequent open-sheet
read omits the now-decided sheet. Saved older revisions are distinguished from
the returned latest revision. Late location/unmount responses and older pending
refreshes cannot replace a confirmed result. Clearing the portal/session draft
scope cannot be undone by an old response. PINs are excluded from retained prep
drafts. Draft persistence across logout, portal lock or browser reload is not
promised; durable recovery remains future work.

## Accounting independence, verification and next step

Issuance, measurement revisions and acceptance create no purchased-item counts,
purchase facts, inventory values, tax/fee entries, prep movements or Food Cost
changes. Track 1 remains the purchased-count/received-purchase accounting baseline.
Accepted Track 2 observations explain and plan that baseline. Future Toast sales
remain Track 3 theoretical evidence.

Final frontend verification passed 348 tests across 42 suites. Backend verification
passed 25 distinct selected checks across a 23-check main run and a 13-check final
run with two additional database cases; repeated cases are not counted twice.
Twenty-three offline route/migration checks also passed. Whole SQL restore retained
submissions/decisions and replayed the exact accepted request. Source compilation
and whitespace checks passed. Production build passed with three existing hook warnings in
PurchaseOrdersTab, SchedulingTab and StaffTab.

Earlier attempts are preserved: an invalid restore target from a fixture variable
collision, one unchanged catalog test timeout, an offline invocation with a missing
test path, and a Mongo-fake revision test invoked with PostgreSQL mode enabled.
The fixture was corrected; the final frontend run used a 15-second test timeout;
offline contracts were rerun with their expected default mode. Application database
behavior was not changed to bypass those safeguards or fixture errors. Tests used
invented data and a disposable loopback database outside synced Documents/Drive;
they are not live-browser, managed-platform or production acceptance proof.

R16's original prep count history/concurrent creation finding is fixed locally for
this native PostgreSQL workflow and the installed legacy hold. Broader task/staff
access, containers and operating cutover remain open under their separate findings.
Next: verified container identity/capacity/conversion and partial service movements,
then verified staff task access/assignment and the remaining integration contracts.
