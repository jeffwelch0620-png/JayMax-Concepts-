# PR20 hosted read recovery acceptance

On October 11, 2026, the deployed Render frontend at `4855ba6` passed the
scoped read-recovery walkthrough using the existing fictional Bert's item
`SB-003` and menu recipe `GR-001`. Neither draft was saved. The complete
accounting control remained **$184 + $173 - $145 = $212 Actual Food Cost**.

The reviewed head was `500d768`; the served asset was `main.7e3cd424.js`.
[Merge-commit Inventory CI](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/38109936656)
passed all four checks. Existing local validation is **181 focused tests across
11 suites**, **588 frontend tests across 66 suites**, and a strict production
build. This acceptance changed no application code and did not rerun those
code checks. Hosted observations below are separate evidence.

## Observed results

| Case | Hosted result |
| --- | --- |
| Item recovery across polling | With applied 20-second client latency, recovery remained pending beyond the 15-second polling interval, then completed with HTTP 200 reads and the unsaved name retained. Polling resumed. |
| Item stalled read | Applied 70-second latency cancelled the request at 59.99 seconds. The retained-draft diagnosis appeared and recovery became available again. Normal-speed recovery cleared the error and retained the draft. |
| Recipe stalled read | Cancellation occurred at 59.99 seconds. The unsaved name and original ingredient remained; recovery became available and polling resumed. |
| Recipe recovery across polling | With applied 20-second latency, recovery remained pending at 25.4 seconds and completed by the 58.4-second observation. Initial and child reads returned 200, the error cleared, and the draft and ingredient remained. |
| Initial location load | Cancellation at 59.89 seconds displayed the connection diagnosis and **Retry loading location**. Automatic polling recovered after normal speed was restored. |
| Explicit initial Retry | A second trial cancelled at 59.99 seconds. Clicking Retry started a new request; restoring normal speed loaded the dashboard, with subsequent successful reads. |

Changing the settings of an already-active custom throttle profile did not apply
its new latency. An early purported stall therefore still used 20 seconds and
is excluded from timeout evidence. The actual stall trials applied the profile
after selecting **No throttling**. These controls changed browser latency only.
Observed response times include client scheduling and dependent reads; they are
not measurements of server execution or a cold-start service-level guarantee.

## Fixture and accounting preservation

The item draft was cancelled without Save. The original saved item remains
**TEST ONLY Editor Receipt - UI 20261010**, `SB-003`. Loading the saved recipe
discarded its unsaved trial change without Save and confirmed
**TEST ONLY Editor Acceptance - UI 20261010**, `GR-001`, ID
`79087291-095b-4083-b478-d58b25186e2a`, price **10**, note **TEST ONLY baseline**,
and one original `WI-003` portion. No new fixture was created.

Independent read-only before/after comparisons retained the rows and hashes of
all **79 protected purchasing/count/prep/store-state tables**, migration ledger
identities, and the complete October 1-8 accounting report. These observer runs
executed **zero posting requests**. Catalog restoration was additionally checked
through the UI; the 79-table comparison is not a hash claim about every catalog
or authentication table in the database.

The report hash remained
`e85c53b4edb66eb34f0ffa5c52f40bbdbbc72557e8d05f212d5b70e703321d66`.
Track 1 remains purchased inventory with explicit count values and received-date
purchases. Prep and future sales explain that baseline without deducting it again.

Evidence retained locally outside Git:

- `pr20-hosted-read-acceptance-receipt.json`: six cases and 13 screenshot hashes.
- `posting-retry-20261011T143027128714Z.json`: preflight accounting/table control.
- `posting-retry-20261011T150110930136Z.json`: matching postflight control.

The browser was returned to **No throttling**, with DevTools closed. No hosted
data, schema, credentials, Render configuration or Supabase connections changed.

## Remaining acceptance

Prepare and execute the separate
[deployed HTTP posting replay procedure](DEPLOYED_POSTING_RETRY_PLAN.md).
The prior API/database replay results do not establish deployed transport or
lost-browser-response recovery. Independent employee authorization, UI rework,
connection architecture and reviewed fixture cleanup remain separate workflows.
Cold-start latency and other unexercised hosted timing cases remain distinct
from these successful controlled-read trials.
