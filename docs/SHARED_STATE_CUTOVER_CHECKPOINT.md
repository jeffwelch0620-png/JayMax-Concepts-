# Retained adjustments and reporting periods at native cutover

The subsequent local [forecast and AI-history checkpoint](FORECAST_AI_READINESS_CHECKPOINT.md)
extends the candidate's planning/history access and records its own validation.
The results and matrix pin below remain the evidence for this earlier checkpoint.

October 8, 2026. Extends local commit
`3966e864ab01b496de3a0bab14f607eea1ebab73`. This checkpoint is local; it does not
query/change Supabase, import real invoices, edit flag files, push, merge or publish.
Track 1 remains explicit purchased-item physical counts and received-date purchases.

## Reproduced gaps

The frontend starts its PostgreSQL state load with `GET /api/state/{restaurant}`.
That route reads legacy adjustments before fetching the other collections.
The proposed runtime role had no adjustment SELECT grant. An invented full-native
database reproduction raised `InsufficientPrivilegeError` on that table, so the
main state load could fail before reaching otherwise working native screens.

The old reporting-period writer deletes/replaces a store's complete period list.
An owner-backed request returned 200 for an empty list after native installation,
even with feature flags off. Its old revision check does not establish that the
legacy workflow remains valid after cutover. Closed legacy periods are still
referenced by native invoice posting/correction guards; rewriting that history
could change which received dates are protected. The reproduction used only an
invented disposable database. It does not establish that hosted history was lost.

The related adjustment writer also deletes/replaces its entire list. Waste now
belongs to reviewed prep explanations, independently of actual Food Cost. Restarting
the old writer would maintain another parallel explanation with different units
and review rules. Both legacy lists remain retained, not mapped automatically into
native facts or erased to make the application load.

## Selected boundary

`legacy_shared_state.py` treats purchased inventory as retired when
`PURCHASE_IMPORT_ENABLED` or `ACTUAL_INVENTORY_ENABLED` is requested, or
`purchasing.posting_batches` or `actual_inventory.count_snapshots` is installed.
Installed schema remains a boundary with flags off. Prep reporting cutover also
retires legacy adjustments, without independently retiring legacy physical periods.

After the corresponding cutover, adjustment/reporting-period replacement requests
return 409 before validation, revision changes or writes. The low-level replacement
helpers also enforce the boundary. This protects API paths under both owner and
candidate connections; it is not universal immutability against arbitrary owner SQL.
Before requested/installed cutover, owner-backed legacy replacements remain available.

State reads retain the compatible arrays, add `legacyStateCapabilities` and
`legacyStateBasis`, and serialize adjustment quantities as exact decimal strings.
Archived arrays are explicitly nonoperational. These adapters are not complete raw
database exports or a reconstruction of historical recipe values. Sales entries
in `store_state.sales_period` remain analytical drafts; area settings remain editable.
Both use the existing transactional revision checks. They do not create physical
counts, close accounting periods or change received purchase facts.

The frontend honors server retirement status independently of the client flag.
Historical adjustments show a retention notice with no add/delete/current-price
valuation controls. Sales Tracking uses expected-usage mode and hides the old period
close action. App JSON backup/restore remains unavailable for installed native
inventory, including guards on the actual handlers before file processing or writes.
The historical adjustment rows remain available to authorized state consumers;
a detailed raw adjustment archive screen is not implemented in this step.

The shared-state hook previously rejected the explicitly unavailable prep response
(`prepStock=null`, `prepLogs=null`, `available=false`, `basis=legacy_prep_retired`).
A targeted local reproduction confirms that prevented a load. The hook now accepts
that complete contract and preserves both nulls. Unlabeled nulls, wrong status/basis,
mixed arrays/nulls and fabricated empty arrays under a retirement label remain held.
Null means unavailable, not zero. The app also holds old dashboard/count/history
views, suppresses legacy low-stock alerts and removes the restore file input when
the server has retired inventory but corresponding native client features are off.
Native screens still require their reviewed feature configuration; server retirement
does not silently enable features.

## Permission and schema review

Add only SELECT on `public.adjustments`: 28 individually named public tables now
appear in the local candidate. No adjustment or reporting-period INSERT, UPDATE or
DELETE grant is added. These are trusted backend-role policies, not employee,
database PUBLIC or browser/Data API grants. Existing store gates still matter.

All 29 migration hashes, 94 function contracts and 123 relation contracts remain
unchanged. No new trigger or migration is introduced. Only the matrix pin changes:

- Previous: `0e2ad01e3806853f7c1f71e57f3970e7034791af1c369bac6825191e02d745fa`
- Current: `3476ac48ea1278b41a26260b820ab0f8672d92420563bde1c758133d02fd2a84`

`verify_shared_state_inputs.py` checks this exact delta, unchanged native privilege
sets/catalog contracts/SQL, the preceding archive package, and the protected
original continuation's 40 pending paths and every captured byte/hash. It does not
connect to a database. The target database is not accepted as its own reference.

## Validation and preserved evidence

Five unique selected backend checks pass across retained runs:

- `shared-state-final.xml`: select the passing public-only compatibility and
  read-only permission verifier cases (two cases from the 105.17-second run).
- `shared-state-final-v2.xml`: select the passing labeled-history/Track 1 and
  owner/candidate replacement-hold cases (two cases from the 57.39-second run).
- `shared-state-final-v3.xml`: the allowed-settings/sales-draft case passes
  (one case, 32.00 seconds).

There are no failures, errors or skips in the selected successful cases. Failed
cases in the earlier runs are retained and excluded from successful evidence.
The verifier passes for the catalog reader and the nonowner role, preserves rows
and ledger/catalog fingerprints, and keeps the independent owner deployment gate
held. The role is NOLOGIN, selected with SET ROLE on pool acquisition. Owner-backed
connections are confined to the explicit bypass probe and public-only compatibility.

State tests retain the large decimal `123456789012345.000000000001`, closed legacy
periods and raw underlying rows; verify flags-off installed-schema retirement;
deny adjustment/period table DML; reject replacements through routes and helpers
without changing revision; and preserve a populated physical report plus all eight
accounting fact fingerprints. Area/sales draft saves advance the actual current
revision, stale saves fail without replacing data, and manager-location/staff/
readonly/anonymous restrictions apply. A million-unit analytical `itemCounts` draft
does not change any physical accounting fact or the report.

All 481 frontend tests in 60 suites pass in `shared-state-frontend-v6.txt`
(50.299 seconds). Twelve new cases cover retained adjustment controls, server-based
cutover with client flags off, the separate prep-only capability, exact quantities
and metadata through the real PostgreSQL state adapter, failed state reads, the
strict unavailable prep contract and the main app's actual routing with client
flags off. Earlier complete frontend runs are retained as intermediate evidence.
Final production compilation passes in `shared-state-build-v2.txt` with the existing
PurchaseOrdersTab/StaffTab hook warnings and Node `fs.F_OK` deprecation warning.
This is selected backend validation and full local frontend validation, not GitHub
CI, the complete backend suite, a live browser test or hosted recovery proof.

Diagnostics remain retained: `shared-state-reproduction` confirms the two original
gaps. The first final run has a new-test helper collision with inherited
`self.retained`; the helper is renamed. The next run passes two state cases and
holds an allowed save because its test assumed revision zero after physical-count
setup. The corrected case reads the current revision; no concurrency check is
relaxed. Frontend attempts retain a JSX fixture typo and an empty-item fixture that
incorrectly expected the sales screen instead of its empty state. A tracked invented
item now exercises the actual expected-usage screen. The second frontend helper
also encounters a Windows terminal Unicode encoding error while printing its
already-written failure log; the next run uses UTF-8 console output.

`shared-state-hook-reproduction.txt` confirms the hook's unavailable-response gap
(one failure, four passing malformed-response checks; unrelated tests deselected).
The subsequent full frontend run validates the corrected contract. The app routing
test's first attempt used the wrong existing navigation label; it is corrected to
“Price History,” with the original failure retained. The first production build
precedes the hook/app integration corrections; final compilation uses separate
`shared-state-build-v2.txt` evidence.

The local test server is stopped after validation. The chained package records
the commit/delta, all passing and failed attempts, previous package hash and
protected original continuation checks. No credentials or private backup are included.

## Remaining gates

Further route review is required. Source inspection identifies `store_sales_projections`
and `ai_chat_messages` reads/writes outside this candidate's grants. Forecasts are
planning inputs; they are not received purchases or physical consumption. AI history,
account/bootstrap and push delivery need separately scoped permissions/availability
decisions, not blanket access to fix runtime errors. No external AI request, email,
push message, hosted forecast or operational entry is used in this checkpoint.

Approved hosted catalog reconciliation and actual ordinary runtime LOGIN/pool
validation remain pending. The candidate's NOLOGIN/SET ROLE tests do not prove
hosted authentication or pool behavior. Browser/Data API exposure, full managed
recovery, matched flags and sequential PR stack revalidation remain open.
**Continue holding merges.**
