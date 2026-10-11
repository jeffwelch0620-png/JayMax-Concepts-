# Browser recovery after a lost posting response

This proposed trial uses one new clearly labelled fictional Bert's manual
purchase. It must demonstrate that the server saved the purchase while the
browser did not receive a complete acknowledgement, then that the existing
**Retry same purchase posting** action returns that single saved outcome.
Preparation is read-only: **no source was captured and no purchase was posted**.
**Execution is held: read-only calibration did not demonstrate response loss.**

The [completed deployed retry test](DEPLOYED_POSTING_RETRY_RESULTS.md) established
eight exact responses and eight conflict refusals for existing outcomes. Its
four original invoices/credits remain intact. A new unposted document is needed
because the browser hides posting actions for an already-posted document.

## Prepared fictional source and accounting effect

| Field | Proposed value |
| --- | --- |
| Location | Bert's / `berts` |
| Document | `TEST-ONLY-BROWSER-RETRY-20261011-07` |
| Supplier | Existing active PFG supplier; fictional branch/customer `TEST-ONLY-BROWSER` |
| Item | `berts_SH-003`, TEST ONLY Appetizer - UI 20261010 |
| Supplier SKU | `TEST-ONLY-BROWSER-RETRY` |
| Supplier date | October 11, 2026 |
| Received date, inventory date of record | October 11, 2026 |
| Quantity and fixed base unit | 1 each; 1 each per received each |
| Food line extension / total | $1.00 / $1.00 |
| Additional tax / fees / discount | Explicit $0.00 / $0.00 / $0.00 |
| Evidence | TEST ONLY invented source; no real delivery or vendor invoice |
| Expected saved outcome | One document version, one posting batch, one line and one food fact: +1 each / +$1.00 |

Use the existing **Manual purchases / other suppliers** form and normal purchase
review. Do not import either real vendor CSV, create a new item or supplier,
change verified conversion profiles, or reopen any period. Source capture should
retain the invented source fields and create no inventory movement. Its real
version and line IDs must come from the capture receipt; preparation's line-ID
placeholder is not an executable command. The browser generates its normal
posting key on first submission and must retain that same key and body for retry.

Fresh read-only preparation confirms the proposed document is absent, the item
is labelled TEST ONLY with fixed base `each`, and the PFG supplier is active.
The current manual-source model and projection accept the invented source with
balanced totals, and the posting model accepts the proposed review shape.
All 79 protected tables, migration identities and the complete original report
still match the accepted control:

**$184 opening + $173 net received food purchases - $145 closing = $212.**

The new receipt is outside that original report interval, so the complete
original report and its $212 result must stay unchanged. It adds one $1 purchase
fact dated October 11; it does not establish $1 of actual usage or a new Food
Cost result. A later physical closing count would be needed for another actual
usage period. Do not create a count, prep batch, waste entry, sales record or
period close during this trial.

## Response-loss method and calibration

Use the unmodified hosted frontend and API. Chrome DevTools supports custom
download/upload throttling and Offline through its normal Network panel
([Chrome Network reference](https://developer.chrome.com/docs/devtools/network/reference)).
The proposed method is a very slow download, fast upload and zero added latency,
followed by Offline **only after an independent database read confirms commit**.
The saved profile was verified at **1 kbit/s download, 100 Mbit/s upload and
0 ms added latency**. Chrome accepted 0.1 in the editor but did not retain it;
the integer profile was saved and selected instead. A selected profile is not
evidence that a response was lost.

Before creating the fixture, calibrate using a read of an existing fictional
document. Confirm the profile holds the response pending long enough for a
read-only commit observer and native browser controls to act. Return to
**No throttling** and confirm successful reads. Native Chrome controls completed
three read-only trials of the existing fictional price-credit source. The first
read returned 200 in 49.36 seconds before Offline was selected at 61.85 seconds.
The second returned 200 in 29.19 seconds before Offline was selected at 29.36
seconds. In the third, the source response was pending in the observation before
interruption, but completion was observed when Offline was selected at about
25.28 seconds; Network recorded 200 and 25.27 seconds. None produced a failed
source request or a lost acknowledgement. The third observation does not prove
whether switching profiles released buffered data or completion happened just
before the switch.

Normal networking was restored and the same source returned 200 in 2.78 seconds.
DevTools was closed and the original window size restored. A fresh read-only
post-calibration check passed for all 79 protected tables, migration identities
and the complete $212 report. There were zero posting requests and no new
fixture records. The browser-extension control connection timed out; these
results came from native Chrome controls.

The latency-only 70-second read tests do not prove this method. Do not use
request blocking before submission, fabricated JSON responses or local response
overrides as proof that the real server committed. Chrome's
[override documentation](https://developer.chrome.com/docs/devtools/overrides#how-it-works)
describes serving local content instead of the network resource; independent
real-commit evidence remains essential.

**The slow-download/Offline method is not accepted for a first-post trial.** Hold
the fixture before capture and review a deterministic alternative. An alternative
must first demonstrate a failed acknowledgement on a read-only request, then
support independent commit observation and the same mounted review's retry.
Changing the actual server or replacing its response with invented data would
not establish that deployed recovery works. No backend delay hook, browser extension,
proxy, TLS interception, hosting change or connection change is included here.

## Execution and evidence

The following is an execution contract for a later accepted method, not
instructions to post with the failed calibration method.

1. Confirm a quiet test window, the same approved deployment and database target,
   a normal owner session, the original four outcome identities and unchanged
   original accounting report. Capture a fresh complete pre-capture baseline.
2. Retain exactly the prepared invented manual source through the normal UI.
   Read it back, require one version and one source line with no posting batch,
   and verify no food purchase fact or accounting change. Capture a separate
   post-capture baseline; it now includes the intended source records.
3. Complete the received-date, USD and line reviews using the values above. Hold
   the same mounted review form throughout submission and retry. Record the
   intended body and its model-normalized fingerprint without credentials.
4. Start an independent read-only observer restricted to this exact store,
   document number and fictional supplier identity. It must use fresh
   transactions, not an older held snapshot. Select the calibrated slow-download
   profile and submit **Confirm and post purchase** once.
5. Require commit proof from that observer: exactly one batch and line/fact for
   the captured version, +1 each / +$1, October 11 received date, and a stored
   fingerprint matching the submitted review. Record the original command key
   and batch privately in the local test receipt. The UI must still be awaiting
   its acknowledgement when the observer confirms commit.
6. Select Offline in the same Inventory tab. Require the original request to
   fail and the retained review to show its error and **Retry same purchase
   posting**. Confirm its inputs remain frozen and no success has been announced.
   An Offline setting alone does not prove the response was lost.
7. Independently confirm the one saved outcome and the expected first-post
   changes. Restore **No throttling**, then click the existing retry once. Require
   HTTP 200 with the same batch/version, posted UI confirmation and the same
   original body/key. Compare protected-table rows/hashes immediately before
   and after retry: **zero additional changes are expected from retry**.
8. Read back all original and new outcome graphs, original full report, count,
   prep and period history. Only after confirmation, reload normally and verify
   the new document appears once in history. Restore **No throttling**, close
   DevTools and retain the labelled fixture for reviewed cleanup.

Record request/commit/error/retry ordering, response statuses, canonical
fingerprints, batch/line cardinality, independent comparisons and relevant
screenshots. Never retain a bearer token, login credentials or an unredacted HAR.

## Allowed changes and failure outcomes

Source capture may add this fixture's import file, upload attempt, parse run,
raw/source row, document identity, version and source line. There are no address
or attachment rows in the prepared source. First posting may add its single
mapping, reconciliation, batch and posting line, with one derived food fact,
and advance Bert's store-state revision. Its fixed item base already exists.
Record actual per-table deltas and verify rows belong to this fixture; an
allowlist is not permission for unrelated edits in those tables.

Original invoice/credit identities and rows must remain unchanged. Actual
Inventory count/period/history and every prep table must be unchanged.
No mapping-profile or catalog edit, supplier change, tax/fee movement or
deduction from Track 2/3 is expected. Capture and first posting necessarily
change the protected baseline; compare each phase with its own fresh baseline
and preserve the prior rows, rather than claiming all 79 tables are unchanged
across the first posting.

If the request completed normally before interruption, record a normal first
posting and hold the response-loss case; do not delete, reverse or re-post that
outcome to manufacture a test. If the observer cannot confirm commit, an offline
failure is inconclusive. Read back first and hold further commands. If the
review remounts, loses its key/body, returns an unexpected status or changes any
unrelated rows, preserve the evidence and stop. No automatic compensation or
second fixture is included.

`PurchaseDocumentReview` retains the command in a component `useRef`; the current
local failed-post test covers same-mounted-form retry. This trial therefore
does not accept unknown-outcome recovery across reload, navigation, sign-out
or session expiry. Those cases need separate review and acceptance. It also
does not exercise concurrent first posting or independent employee authority.

## Prepared artifacts and review checkpoint

Local preparation receipt: `browser-response-loss-preparation-20261011.json`,
SHA-256 `00bfa3b863a0532d56f08cbc9a7dcc690472151a3e0b73968f9d75acd550efc7`.
It contains the invented source, review template, validation flags and unchanged
original controls, with zero HTTP requests and zero records created. Its helper
`prepare_browser_response_loss_trial.py` has only a read-only database path;
neither file is in Git. The plan is saved locally for review before fixture
creation and posting. The current build deployment and Supabase connections
stay in place.

Local calibration receipt: `browser-response-loss-read-calibration-20261011.json`,
SHA-256 `c7dfe437b6653903d66d58b0d5e270306f3a8d4c37109c3e10935849a96bb141`.
It records the three successful source reads, failed response-loss calibration,
normal-read recovery and zero posting requests. Screenshot evidence remains
outside Git. Post-calibration preservation receipt:
`deployed-http-replay-20261011T175527589976Z.json`, status
`passed_read_only_http_preflight`; it is a new read-only check, not another
execution of the sixteen completed posting probes.

Next: select and review another fault method before any hosted fixture creation.
The existing sixteen deployed HTTP outcomes remain accepted; browser
lost-first-post-response acceptance remains open. The proposed fictional receipt
would create a new persistent +1 each / $1 purchase and needs its own reviewed
execution checkpoint once the method is usable.
