# Planning-cost refusal and chart formatting follow-up

## Merged checkpoint

PR40 merged with owner approval as `f33db6e` from `4abf76e`. All four PR checks
and merged-main CI passed, including Windows ACL checks. API and frontend are
Live on the exact merge. The local wording below preserves the pre-publication
record; the [next checkpoint](SINGLE_ITEM_PREP_ARITHMETIC.md) records deployment
smoke coverage and the separately gated arithmetic follow-up.

October 16, 2026. Local continuation from owner-approved PR39 merge `fafa95e`.
The owner authorized proceeding after the merge. Publication of a new draft PR
still requires the owner's requested prompt; merge/deployment remain separate.

## Resulting behavior

The four legacy prep completion helpers share one preflight error formatter.
An unknown supplier planning price names the item (falling back to its control
number/code) and asks the operator to enter or confirm the price before recording
prep. It states that no prep write was made. A real calculation-range failure
keeps the previous range message. Known zero still passes this cost check.
Existing feature/schema holds, authority checks, transactions and validation
order remain unchanged. This changes refusal wording, not native prep valuation.

The ownership chart uses `fmtPlanningCost` for its tooltip formatter, keeping
null/undefined distinct from genuine zero. This is defensive formatting: the
installed Recharts implementation filters null payloads by default, and native
mode omits the inventory-value bar. A visible null-as-zero tooltip was not
reproduced in the current deployment. The component test captures the supplied
formatter and tests its null/zero contract; it does not claim a real hover test.

No SQL, credentials, permissions, hosting/connection changes or Track 1 accounting
changes are included. The legacy pathways remain retired in the current native
build. No migration, native prep-cost writer or historical rewrite is introduced.

## Local validation

- **880 frontend tests across 75 suites passed**, including the null/zero
  owner-tooltip formatter regression. Strict production build passed with CI
  and ESLint enabled; asset `main.cfa1b3a5.js` is local, not deployed.
- **70 focused backend cases passed** (13 methods plus 57 subtests). Tests
  distinguish missing-price/range messages and exercise both Mongo helper
  entrypoints with fictional mocks and no write calls.
- Full selected offline profile: **814/816 reported cases passed**. The same
  two unchanged Windows ACL tests timed out starting PowerShell. There were
  no skips. This is not an all-green local run; no permission bypass or mocked
  success was added. Focused cases overlap this broader run.
- **34 disposable PostgreSQL cases passed** (21 methods plus 13 subtests),
  including both batch/task missing-later-price tripwires, direct-item refusal,
  real range errors, valid completion/rollback, native accounting isolation and
  location-alias pricing. A 45-second diagnostic stack appeared during a slow
  accounting case; the test subsequently passed and the run completed with no
  failures/skips. Original database/role inventory is unchanged, and the owned
  local server is stopped.
- Generated review contracts match source and whitespace checks passed.

External evidence uses the `planning-feedback-` prefix for focused/full offline,
full frontend/build and database reports. Fresh exact-head GitHub CI remains a
publication/merge gate. The green PR39 checks do not validate this new candidate.

## Remaining gates

PR39's [scoped live acceptance](PR39_LIVE_BACKEND_ACCEPTANCE.md) is complete:
blank, zero and restoration passed, with the original fictional price restored
and historical Food Cost unchanged at $212.00.

1. Commit the local fixes/docs and prompt before pushing a new draft PR.
2. Independent review and new-head CI, then separate owner merge approval.
3. Continue the field/unit and missing-reference audit, followed by coordinated
   runtime-role deployment before operational use. UI redesign, authentication
   and shared module integrations remain separate workflows.
