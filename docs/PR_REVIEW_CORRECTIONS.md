# October 7–8 review corrections

This records correction batches following independent review of the external
PR14–16 fix package. All three pull requests remain draft and unmerged. This document
supplements the original inventory review; it does not close its remaining findings.
The newer local deployment/recovery continuation is preserved separately.

## Changes in PR14

| External finding | Correction and boundary |
|---|---|
| A3: sales drafts cannot retry after another save | Explicit retry refreshes saved sales and reconciles baseline, draft, and latest data before saving with the returned revision. Independent field edits survive; same-field conflicts and remotely changed period dates block the write and retain the draft. Normal debounce never silently adopts an external revision. |
| A4: prep settings need clearer save feedback | Prep settings show an unsaved indicator. App-level browser unload protection also checks drafts cached on other tabs, and voluntary sign-out asks before discarding them. Explicit per-recipe confirmation remains required. |
| A5: expiry and repeated load errors | Local token expiry emits the session-expired event once, removing the stale session. Polling reports the first failure in a streak; successful reads reset it. Superseded reads cannot report stale errors. |
| A7: adapter checks depended on shell flags | Item adapter tests select and restore their own configuration. Added explicit native-flags-off cases preserve legacy portion conversion behavior. |

Drafts remain scoped to the signed-in App instance and restaurant. Tab navigation retains
them in memory; reload and logout do not. Browser unload prompts depend on browser support
and prior interaction. No write is started blindly during unmount, location change, or
logout. A pending acknowledgement cannot erase typing performed after submission.

## Validation

PR14: 247 frontend tests across 31 suites passed with all `REACT_APP_*` variables unset,
and all 247 passed again with the native configuration below. The final production build
passed with the three existing hook-dependency warnings in PurchaseOrdersTab,
SchedulingTab, and StaffTab. Earlier build attempts preceded the last draft-warning
changes; the final build uses the final tested source.
The expired-session test initially failed because the test runner cleared the interceptor
registration mock before the test; loading the module within the test corrected the
fixture, and the full suite passed afterward.

Commands use the repository's existing frontend dependencies:

```text
node node_modules/react-scripts/bin/react-scripts.js test --watchAll=false --runInBand
node node_modules/@craco/craco/dist/bin/craco.js build
```

Native-mode validation sets `REACT_APP_USE_PG`, `REACT_APP_NATIVE_PURCHASES`,
`REACT_APP_ACTUAL_INVENTORY`, and `REACT_APP_CATALOG_MAPPING` to `true`.
This test configuration does not change deployment settings.

These are component and source checks, not a live browser walkthrough, hosted database
validation, operational rollout, or proof that every reviewed workflow is corrected.
Earlier checkpoint counts and hash manifests describe their original snapshots.

## Remaining correction sequence

1. Catalog query batching and deterministic supplier selection are implemented for the
   documented catalog/profile paths, preserving SKU history. Remaining setup/history
   paths still require review.
   Retirement must preserve physically present purchased stock and its count/value;
   a removed supplier option must not silently reassign historical purchases.
2. PR15 adds recipe validation scoped to changed recipes, dependents and their inputs,
   named errors, canonical save acknowledgement and unknown-cost sorting/display.
   Partial-cost display and wider legacy history deletion paths remain under review.
3. Known-identity review separation, production root collisions and selected coupled
   request-key conflicts are corrected below. Wider identity/authentication and
   quantity-dependency corrections remain separate work.
4. Recipe deletion and staff audit-response boundaries are corrected below. Broader
   cross-module idempotency, other legacy history/access paths, and migration/runtime-role
   checks remain open. Setup/history paging and batching also remain separate work.
5. Repeat stack-level acceptance and finish isolated hosted-development validation once
   the separate Supabase development target is available. Never apply test migrations
   or fixture data to the operational project.

The external suggestions are evaluated individually. Removing revision checks, deleting
retired inventory value, freeing historical supplier identity, converting exact decimal
API values to floating-point numbers, and re-enabling legacy writers after native schema
installation are not accepted shortcuts. Accounting Track 1 remains independent of prep,
waste, and sales explanations. Login redesign is deferred; the existing shared-PIN role
elevation still prevents treating claimed employee identity as verified review separation.

Merge readiness remains pending. The intended merge order is PR14, then PR15, then PR16,
after their applicable integrity and deployment checks pass. Merging and enabling native
features are separate decisions.

## Catalog correction batch

Catalog list and owner catalog reads now use one request-local, repeatable-read snapshot.
Schema checks, supplier rows, location aliases, and shared-location counts are batched.
Unit-profile validation reads the same source fields as the single-profile contract in
three queries rather than querying each item/SKU separately. No process-wide cache can
retain a removed schema, changed pack, or old planning price.

Supplier order is deterministic: available choices, then preferred choices, then stable
supplier/SKU identities. Current planning selection ignores unavailable rows, including
an unavailable row still marked preferred. Historical rows, original prices, product
links, and exact decimal API strings remain present. With no available supplier, there
is no selected supplier; the later recipe contract preserves unknown costs. Choosing a
different available supplier affects planning only, never received purchase facts or
explicit physical-count values.

A6 is corrected for these catalog/profile reads; other setup/history query paths remain
subject to review. A2's stale-price selection is corrected, but arbitrary SKU reassignment
remains deliberately held. Reassignment needs a reviewed identity/history contract.
Retired purchased items retain physical count participation and stock; retirement does
not prove the stock has disappeared.

Validation: 36 distinct selected backend checks passed across the initial 35-pass run and
one corrected-fixture recheck. The initial failure assumed `999.0000` rather than the
equivalent exact decimal returned as `999`; its original output is retained. Five query
budget/source-contract checks cover one and 300 items/profiles. Disposable PostgreSQL
regressions also cover shared store settings, retirement, source staleness, received-date
accounting, receiving, and whole synthetic restore. No hosted database was changed.
PR14's full frontend suite passes 251 tests across 32 suites with both default flags and
the four foundation native flags enabled. The native-configured production
build passes with the same three existing hook warnings.

## Recipe correction batch in PR15

Targeted recipe changes now require the caller's current `If-Match` revision and send only
changed definitions plus explicit deleted IDs. A comparison read never silently adopts a
new revision. Changed recipes, all retained dependents, and their dependencies are checked
before committing; unrelated incomplete legacy definitions remain untouched. Whole-graph
replacement remains strict. Retained errors include the recipe name and canonical ID.
Headers, ingredients, deletes and revision commit together, and retained prep-log references
hold deletion. This does not close every legacy cascading-history deletion finding.

The acknowledgement returns the full saved collection and temporary-to-canonical ID map.
The editor uses the confirmed canonical ID on its next edit, preventing duplicate creation.
Missing yields/units stay unknown, and unknown profitability sorts after verified values,
including real zero cost. Available alternate suppliers can be selected for planning while
unavailable historical rows remain present. These changes never value counts or deduct
purchases; Track 1 remains the independent accounting baseline.

PR15 validation: all 359 frontend tests across 44 suites passed with default configuration
and with the four foundation native flags enabled. No controlled-input warnings remained.
The selected local PostgreSQL run passed 28 checks plus 21 parameter subtests: affected
graphs, canonical IDs, stale/missing revisions, incompatible yield rollback, retained history,
supplier-source staleness, query budgets, original recipe contracts, and synthetic restore.
A final read-only recipe snapshot was added after that run; all four affected-recipe
checks passed again against the final backend source. The native-configured production
build passed with the same three existing hook warnings.
No new migration, hosted SQL, real invoice import, or live-browser acceptance occurred.

## Carry-forward validation in PR16

The catalog and targeted recipe corrections are inherited in the staff continuation.
All 434 frontend tests across 53 suites passed with default flags and with the four
foundation native flags enabled. The production build passed with the same three
existing hook warnings. Twenty selected backend checks and 21 parameter subtests passed
against this checkout, including original/scoped menu contracts, catalog/profile query
budgets and staff legacy reads/completion holds when feature flags are off.

The first frontend attempt passed 433 checks and failed a date-switch fixture that selected
today's date, so no switch occurred. The fixture now always selects another date and verifies
the new request before resolving the older response. Both complete suites passed afterward;
the application response guard was unchanged. These results do not complete the remaining
staff review-separation, identity collision, waste-dependency or hosted-readiness work.

## Recipe history retention and direct deletion corrections in PR15

Direct recipe deletion now requires the current `If-Match` revision and a recipe
belonging to that restaurant. Before direct deletion, targeted removal or collection
replacement, the transaction locks the parent against concurrent FK references and
checks retained counts, prep definitions/list lines, logs, recipe stock, overrides
and par recommendations. Even zero stock or a zero recommendation does not establish
that its evidence may be erased. Referenced identities return 422 before cascades or
history-preservation triggers run; revisions and any coupled edits roll back.
Unused definitions can still be explicitly deleted. No history migration is required.

All 15 menu backend checks and 23 parameter subtests passed on disposable PostgreSQL,
including unchanged recipe validation, location/revision enforcement, retained stock
and planning references, and original physical-accounting independence. Frontend
application code is unchanged from the prior 359-test/44-suite checkpoint. These
API guards are not a database-wide deletion policy for every legacy SQL writer;
rollback to older code still requires the documented history-preserving cutover.

## Order review separation and mapping corrections in PR15

Approval now checks the authenticated actor against the retained creator and every
create/edit/reorder journal author. An earlier editor remains ineligible after another
editor replaces the content. Valid independent approval still follows the current
version and canonical-line checks. No actor identity is fabricated for legacy orders.
Incomplete retained line mappings return 422 on submit, approve, send and reorder;
no partial command, new order or version change remains. Unique workflow identity or
request-key conflicts return 409 only after the transaction has rolled back.

Eleven selected disposable PostgreSQL order checks passed, including both new cases
and the existing retry/race, receiving and whole-restore contracts. PR15 frontend code
is unchanged from the prior 359-test/44-suite default/native and production-build
checkpoint. This does not prove the externally alleged cross-store key race; that
specific race was not reproduced and the existing global serialization remains.
Known session-ID separation is an API guard. Shared-PIN identity and the login redesign
remain deferred; this does not establish individual identity or SQL-role approval policy.

## Staff review, workflow conflicts and waste correction in PR16

Count acceptance checks every retained sheet revision author. Production acceptance
checks every retained root revision author plus a matching canonical claimed roster ID.
Rejection and exact retained retries remain available. These are known-ID API checks;
shared PINs and typed names do not prove independent employees. No login redesign or
new SQL-role permission policy is claimed.

Production previews and commits reject roots occupied by another store or by an existing
revision ID with 409. Selected order, count, production and container transactions
translate unique identity/request-key conflicts to 409 after rollback. Real production
batch/acceptance and container/waste journal key collisions exercise rollback of the
coupled effects. This is not a universal global namespace for all module request keys.

The additive `20261008_container_waste_corrections.sql` migration permits paired reversal
of an erroneous older loss after storage/service transfers or reversals of those transfers.
Later waste, unpacking, quantity corrections and source changes still hold the correction.
The target, original timestamp, compartment and exact quantity remain pinned; no restored
total can exceed the original fill. Both journals retain the loss and append its reversal.
The client offers older targets only when the new database capability is installed.
Track 1 purchased counts, received purchase facts, explicit count values and Food Cost
remain independent of these analytical corrections.

Migration installation follows `20261007_container_waste.sql`; connection pools must be
recycled after DDL. The private invoker function is not granted to PUBLIC/anon/authenticated.
The preserved newer local 28-migration deployment bundle needs the new migration included
and ordered migration/recovery validation repeated before hosted use. No hosted SQL or
operational data has been changed.

Validation: 14 distinct selected local PostgreSQL staff/waste checks passed across the
first attempt (9 pass) and final rerun (10 pass, overlapping earlier cases). The first
five failures were test fixtures missing token email fields or calling a nonexistent
helper; those fixtures were corrected and all final selected cases passed. The final
root test exercises both preview and direct POST collisions, and restore verifies the
new function's private ACL. Existing retry races, actual-report independence, paired
latest reversal and late-reversal holds remain covered by these selected checks.
All 437 frontend tests across 53 suites pass with default and foundation native flags;
the production build passes with the three existing hook warnings. The first new
frontend run used the wrong refresh button label; the corrected test passes in both
complete suites. Prior attempts and final output are retained. These are scoped local
checks, not full backend coverage, live-browser acceptance or hosted-platform proof.

## History and staff response corrections in PR16

The PR15 recipe-history preflight is carried forward. Installed container legacy stock/
log hold triggers no longer turn supported recipe removal into a server error. Direct,
targeted and collection deletion preserve the recipe, child lines, stock and captured
raw history and return 422, including when the container feature flag is off. Missing
or foreign recipe identities cannot be used to silently advance another store revision.
Existing roster assignment-history deletion already returns 409 and suggests deactivation;
its covered behavior is retained, rather than introducing deletion of historical staff.

Staff count lists and submission/retry receipts, staff production setup/preview/submission
receipts, and task plans recursively omit private audit identity fields. This includes
copies in nested review snapshots, decisions, lots and assignment evidence. Stored
facts, manager responses, request hashes and fingerprints retain the original evidence.
Counter names, roster selections and free-text notes remain claimed operational data;
this does not introduce individual authentication or restrict recipe/lot measurements
required for the current staff production workflow. Privacy of other routes remains
separate work.

The staff production client compares projected receipts with both old and newly filtered
pending previews. Original request keys/body/hashes remain pinned, and quantity, assignment,
location and immutable history checks remain enforced. Manager receipt comparisons keep
their audit identity checks. Missing progress or assignment state in staff plans now returns
409 with a review instruction instead of raising StopIteration.

No new migration is required for this batch. No historical row, actor or financial fact
is rewritten. Installed immutable schema holds still apply after older-code rollback;
the code-first recovery plan must retain that evidence. These API corrections are not
a universal SQL deletion policy or proof of hosted deployment readiness. The separate
newer local continuation remains preserved.

Validation: 16 selected history/access backend cases passed across the first 13-pass
run and final three-case rerun (including inherited cases), with two parameter subtests.
The first container deletion fixture used the purchase-only router and received 404;
the corrected full-app fixture proves the installed hold with the flag off. The final
rerun also passes staff production permissions and whole SQL production recovery.
Original roster deletion/deactivation holds, private manager history, count retry races,
and both count/production author separation remain covered. PR15 separately passes its
complete 15-check menu suite and 23 subtests. All 438 frontend tests across 53 suites
pass in default and foundation-native configurations, including old pending-preview
compatibility and retained measurement/hash checks. The final production build passes
with the same three hook warnings. Source/probe and selected local runtime evidence
are distinguished from full backend, browser and hosted Supabase acceptance.

## History read batching and deployment source review

Staff count setup reads only its current product/unit definitions. Sheet histories,
decisions, boundary conflicts and definition holds are loaded in batches. Container
contents load all fills, movements and paired waste observations in batches, keeping
exact Decimal values, timestamps, original hashes and immutable retry receipts. Current
profile checks reuse the loaded definition snapshot; lot totals group complete balances.

The retained-history helpers use five queries for nonempty container history with the
waste schema and seven for pending sheets with definitions supplied. Both query budgets
hold for one and 300 roots. They do not make whole setup constant-cost: full response
size and shared recipe/source validation remain open. No cutoff hides pending work or
older stock; coordinated API/UI paging remains next work.

Validation: 18 distinct selected backend checks passed in a 15-case regression run and
four-case boundary/profile recheck, with one overlap. Batched results match the previous
individual reads for loss pairs, old pending hashes, physical-boundary and scope errors,
superseded units, final rejection history and current profile review flags. Existing
author, immutability, paired reversal, migration upgrade and whole restore checks pass.
The initial attempt's composite/domain driver failures and unsuitable timezone fixture
are retained alongside passing final evidence. Frontend source is unchanged; its previous
438-test/53-suite results and build remain checkpoint evidence, without fresh reruns.

Source reconciliation verified that all 27 shared native SQL files match the preserved
continuation after line-ending normalization. That continuation's 28-file readiness plan
omits the existing waste correction. The combined 29-file plan must put the correction
immediately before final native access hardening. Runtime-role, combined recovery and
hosted checks are still pending. No protected continuation source or hosted configuration
was changed. See [the scoped performance and deployment review](WORKFLOW_READ_PERFORMANCE_REVIEW.md)
for role ownership limits, paging requirements and validation boundaries.

## Subsequent local deployment reconciliation

A separate local branch based on PR16 correction head `91b028d` brings forward
the readiness tool, final private-access migration and exact-newline restore fix.
All 29 native migrations are ordered once, with access hardening last. Fourteen
selected checks pass, including full chain/restore, client-denial and an ordinary
owner-role Track 1 transaction/replay test without superuser or RLS-bypass privileges.
Example PostgreSQL modes align with all native features held. The broader original
40-file continuation remains unchanged and snapshotted separately. This local
checkpoint is not pushed and performs no hosted SQL, deployment or operational
import. See [the current deployment scope and remaining work](DEPLOYMENT_RECONCILIATION_CHECKPOINT.md).
