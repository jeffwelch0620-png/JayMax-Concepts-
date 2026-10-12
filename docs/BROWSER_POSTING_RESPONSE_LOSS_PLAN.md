# Browser recovery after a lost posting response

This proposed trial uses one new clearly labelled fictional Bert's manual
purchase. It must demonstrate that the server saved the purchase while the
browser did not receive a complete acknowledgement, then that the existing
**Retry same purchase posting** action returns that single saved outcome.
Preparation is read-only: **no source was captured and no purchase was posted**.
**Hosted purchase execution is held. Response truncation and same-mounted-form
retry now pass in a separate local client using the actual review component.
The hosted first-commit trial remains open.**

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

## Earlier unsuccessful DevTools calibration

The earlier candidate used the unmodified hosted frontend and API. Chrome DevTools supports custom
download/upload throttling and Offline through its normal Network panel
([Chrome Network reference](https://developer.chrome.com/docs/devtools/network/reference)).
That candidate used a very slow download, fast upload and zero added latency,
followed by Offline **only after an independent database read confirms commit**.
The saved profile was verified at **1 kbit/s download, 100 Mbit/s upload and
0 ms added latency**. Chrome accepted 0.1 in the editor but did not retain it;
the integer profile was saved and selected instead. A selected profile is not
evidence that a response was lost.

The candidate was calibrated using reads of an existing fictional document
before any new fixture creation. Native Chrome controls completed
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
not establish that deployed recovery works. The replacement uses a separate
loopback test client and narrowly scoped delivery relay, without a backend delay
hook, browser extension, TLS interception or deployed connection change.

## Successful isolated response-drop calibration

On October 11, a separate loopback-only helper forwarded exactly two public
**GET https://jaymax-api.onrender.com/api/health** requests. It received and
validated each real upstream HTTP 200 response, then deliberately closed the
first downstream response after delivering **1 of its declared 38 bytes**.
Native Chrome observed Axios's XHR adapter report **ERR_NETWORK**, status 0,
with no acknowledged result. Clicking **Retry same health read** made the
second GET; all 38 bytes were delivered and the browser acknowledged HTTP 200.
The calibration page's local text draft stayed intact after both requests.

This proves a transport failure in a separate local calibration page, not
`PurchaseDocumentReview`, first posting, persistence of an idempotency key or
database commit. Both upstream body hashes match
`e37598d8934bd69807a0db0358bd093ac20ef7aedbbd46caeca49c9c3b894b67`.
The relay received real responses; it did not substitute invented health JSON.
The existing installed Axios browser bundle was used with its XHR adapter.

The helper bound only **127.0.0.1**. It supported no purchase route or upstream
POST and rejected credentials. Five route/credential checks passed with zero
upstream requests before the browser trial. Browser observations were submitted
only to the local helper and were never forwarded. No login, operational source,
invoice, credential, TLS certificate, browser proxy setting, deployed build,
hosting configuration or Supabase connection was changed. The helper was stopped
after acceptance. A JavaScript string-escaping defect in the initial local page
was corrected and syntax-checked before the successful trial; that initial page
made no upstream request.

Receipt `read-only-response-drop-relay-20261011T201041555127Z.json` has SHA-256
`d682289293f830b4641402341627676ce9f70f5547ebc8089cdac3caf8bd66eb`.
Error/retry screenshots and the helper remain outside Git. An earlier public
preflight failed with ConnectError before posting; the subsequent fresh
`deployed-http-replay-20261011T210536200632Z.json` passed read-only validation of
all **79 protected tables**, migration identities and the complete **$212**
report. Neither preflight executed a posting request.

The actual purchase-review component has since passed the
[local transport trial](LOCAL_PURCHASE_REVIEW_RESPONSE_DROP_RESULTS.md):
`ERR_NETWORK` left its reviewed values frozen; manual retry sent the identical
432-byte body and key and acknowledged the complete local response. Seven
local route guards passed and the helper was stopped. The local acknowledgement
was simulated and no hosted request was made. A fresh hosted read-only preflight
`deployed-http-replay-20261011T214955230989Z.json` preserved all 79 protected
tables and the complete $212 report, with zero posting requests.

**Next: implement and review the guarded hosted command relay and phase-aware
observer for the separate test client.** The existing hosted frontend is not routed
through the helper, and the helper cannot currently forward a purchase command.
A later command-capable relay needs exact document/method guards, memory-only
authentication handling, no automatic POST retry, independent commit proof
before truncation, and recorded body/key equality on manual retry. A separate
test client must be clearly distinguished from the hosted frontend. Review that
concrete setup and its +1 each / $1 fictional first-post effect before creating
the hosted fixture. Do not change the deployed frontend's API connection to
make the test work. The original failed Offline method stays unaccepted.

## Execution and evidence

The following is the revised execution contract for deterministic downstream
truncation. It is not an executable hosted runner or permission to create the
fixture before the command relay and observer are prepared and reviewed.

1. Confirm a quiet test window, the same approved deployment and database target,
   a normal owner session, the original four outcome identities and unchanged
   original accounting report. Capture a fresh complete pre-capture baseline.
2. Retain exactly the prepared invented manual source through the normal UI.
   Read it back, require one version and one source line with no posting batch,
   and verify no food purchase fact or accounting change. Capture a separate
   post-capture baseline; it now includes the intended source records.
3. Initialize the separate local client with the real captured version/line IDs
   and read-back source data. Use the literal existing review component and the
   production parent's batch-ID/posted-status acknowledgement check. Obtain a
   normal owner session through a private human sign-in prompt; retain its token
   only in server memory. Complete the received-date, USD and line reviews using
   the values above. Hold the same mounted form throughout submission and retry.
   Record the intended body and model-normalized fingerprint without credentials.
4. Start an independent read-only observer restricted to this exact store,
   document number and fictional supplier identity. It must use fresh
   transactions, not an older held snapshot. Arm only the exact captured version's
   normal POST route at the existing Render API. Submit **Confirm and post
   purchase** once. The relay must perform one upstream request, with normal TLS
   verification, no automatic retry and no redirects, and retain the complete
   real upstream response before sending any downstream acknowledgement.
5. Require commit proof from that observer: exactly one batch and line/fact for
   the captured version, +1 each / +$1, October 11 received date, and a stored
   fingerprint matching the submitted review. Record the original command key
   and batch privately in the local test receipt. The UI must still be awaiting
   its acknowledgement when the observer confirms commit.
6. Only after independent commit proof and response identity validation, declare
   the full real response length and deliver one byte before closing the local
   browser connection. Require Axios `ERR_NETWORK`, no acknowledged result and
   the existing **Retry same purchase posting** action. Confirm that the reviewed
   values remain frozen and no success has been announced. Record the actual
   real response size and delivered size; do not substitute fictional JSON.
7. Independently confirm the one saved outcome and the expected first-post
   changes. Capture a fresh post-commit baseline, then click the existing retry once. Require
   HTTP 200 with the same batch/version, posted UI confirmation and the same
   original body/key. Compare protected-table rows/hashes immediately before
   and after retry: **zero additional changes are expected from retry**.
8. Read back all original and new outcome graphs, original full report, count,
   prep and period history. Only after confirmation, reload normally and verify
   the new document appears once in the hosted history. Stop the relay, discard
   the memory-only session token, verify its loopback port is closed and retain
   the labelled fixture for reviewed cleanup. No DevTools throttling is required.

## Hosted relay guards to implement before capture

| Boundary | Required guard |
| --- | --- |
| Network target | Fixed `https://jaymax-api.onrender.com`; normal HTTPS verification; no caller-provided target or redirect |
| Browser interface | Loopback-only unique trial path; exact Host and Origin; no incoming cookie or bearer token; own assets only |
| Command scope | One store (`berts`), one real captured version, one line, the prepared item/SKU/date/amount; only its normal posting route |
| Review admission | Exact expected field set and values; valid browser-generated key; backend-model normalized fingerprint matches intended review |
| Retry admission | One manual retry only; original raw body bytes and key retained; a changed body/key or a third request is refused locally |
| Authentication | Human owner login through the normal API; token only in helper memory; no token from browser storage, logs or files |
| Ordering | Complete real upstream acknowledgement, then fresh independent commit proof, then truncated browser delivery |
| Source preservation | Pre-capture baseline; post-capture baseline; verify permitted additions belong only to this fixture and preserve every prior row |
| First-post preservation | Verify exactly one batch/line/food fact and the intended state revision; verify all unrelated rows and original full report |
| Retry preservation | Compare all 79 protected tables, migration identities and original full report against the fresh post-commit baseline; zero further changes |
| Held outcomes | Any uncertain response, commit, identity, baseline or concurrent edit holds further commands; no compensation or automatic fixture replacement |
| Lifetime | Bounded test window; stop helper and clear its token after acceptance or hold |

The local component helper intentionally implements no hosted forwarding or
authentication. These guards define the remaining command-capable setup; passing
the local trial does not prove they already exist in a hosted runner.

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

If the browser received a complete acknowledgement before truncation, record a normal first
posting and hold the response-loss case; do not delete, reverse or re-post that
outcome to manufacture a test. If the observer cannot confirm commit, a truncated-response
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

The guarded relay and phase-aware observer were implemented and reviewed with
28 passing offline tests. The [hosted execution results](HOSTED_PURCHASE_BROWSER_RESPONSE_LOSS_RESULTS.md)
now record a successful first commit followed by response truncation and an exact
manual browser retry. The fictional receipt is persisted as **+1 each / $1**
dated October 11; the original complete **$212** report remains unchanged.
Source capture added no movement, first posting created exactly one outcome,
and retry added or changed no observed rows. The helper is stopped and its
memory-only token discarded. This plan's preceding preparation and calibration
descriptions are historical checkpoints, not the fixture's current state.
Acceptance covers the same mounted component in the separate local client;
full hosted-parent, remount/session-expiry and independent employee acceptance
remain open. This plan and its execution results are now included in
[draft PR21](https://github.com/jeffwelch0620-png/JayMax-Concepts-/pull/21);
no merge or new deployment is included.
