# October 7 review corrections — first batch

This records the first correction batch following independent review of the external
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

1. Catalog query batching and deterministic supplier selection, preserving SKU history.
   Retirement must preserve physically present purchased stock and its count/value;
   a removed supplier option must not silently reassign historical purchases.
2. Recipe validation scoped to changed recipes and dependents; actionable identity in
   errors; unknown-cost sorting and display. Do not price an unknown recipe as zero.
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
