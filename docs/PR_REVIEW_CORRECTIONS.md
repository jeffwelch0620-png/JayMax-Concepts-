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
3. Review separation covering authors and subsequent editors, safe conflict responses,
   staff production identity collisions, and container-waste correction dependencies.
4. Cross-module idempotency, history/access boundaries, and migration/runtime-role checks.
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
