# Local purchase review response-loss acceptance

On October 11, 2026, the existing `PurchaseDocumentReview` component passed a
real HTTP response-truncation test in Chrome. The first response failed with
Axios `ERR_NETWORK`; the reviewed values remained frozen. Manual retry sent
the identical body and idempotency key and acknowledged the complete response.

This is **actual component and local transport evidence**, not a hosted first
posting or database commit test. The local server supplied a clearly labelled
synthetic acknowledgement. It has no hosted API, authentication or database
capability. No hosted invoice was captured or posted.

## Build and test scope

The external test build includes a literal, unchanged source segment containing
the review component and its `units`, `empty` and `errorText` helpers. It imports
the repository's existing `Field` and styling constants from `common.js`.
Its separate parent wrapper uses the production parent's acknowledgement
condition: require a batch ID and a document with status `posted`. That condition
was checked against the source before building. The wrapper also restricts the
local response to its fictional document and local batch identities.

The wrapper is not the full `PurchaseImportsTab` parent or deployed frontend.
It uses installed React **19.0.0** and Axios **1.18.0**, with Axios's XHR adapter
explicitly selected. No packages were installed. The build and test helper are
outside the repository; app source and deployment artifacts were not changed.

| Identity | SHA-256 |
| --- | --- |
| `PurchaseImportsTab.js` source | `1e83f9e6600ae307b771317aa44aede2cdb0d2594d82e51c9c92c9f04333fc1b` |
| Literal included component/helper segment | `43a0eaa1efc5409fdc9e3e21db7d6bc80bbace9527c43ee85834be3bf065492b` |
| `common.js` source | `b2fc5d8c35533e0e10d60699f82a5bfea44b68be751619e1d34d5aafd32ddf4e` |
| Separate test wrapper | `22b71a5f6f9ff2a7706dee79cc74726e1d6278d43e26e3c55c8c0899e363db7f` |
| Compiled local client | `3f7cb2f8478ea70cc4dc1699aa7da94fb61bea300fb23fb6f7c413cb529707a4` |

The fixture was `TEST-ONLY-LOCAL-COMPONENT-20261011`, with locally generated
document, line and batch UUIDs. Its form represented one fictional `each` at $1
and zero tax/fees, using the existing test item's code as a label. Those values
were never sent to Render or Supabase. The received date, USD confirmation,
review note and line verification were entered through the native browser UI.

## Results

Seven route checks passed before any accepted submission: wrong route, wrong
origin, supplied credentials, unsupported method, missing key, invalid key and
unlisted read. They created no accepted posting attempt. The helper listened
only on `127.0.0.1:8768`, served its own assets, and allowed only the exact local
document route and fictional review body. It supported at most two accepted
requests, had a 20-minute maximum lifetime and no automatic retry.

| Check | Result |
| --- | --- |
| First local response | Declared 828 bytes; delivered 1 byte and closed the connection |
| Browser outcome | `ERR_NETWORK`, status 0, acknowledgement false; `Network Error` shown |
| Retained review | Received date, item, quantity, unit, factor and note retained; fields disabled |
| Retry action | Existing `Retry same purchase posting` button remained available |
| Manual retry | Same 432-byte request body and same browser-generated key |
| Second local response | All 828 bytes delivered; HTTP 200 acknowledged; document rendered `posted` |
| Hosted requests / new hosted records | 0 / 0 |
| Cleanup | Exact helper process stopped; loopback port verified closed |

Both request body hashes were
`b5bcd150c4c12911b74e5578c13c08c8d8ab30458397dbc5aec82917ae5ca91a`.
The first request was recorded at **21:46:50 UTC**. The server's two-request
receipt and the observed frozen/confirmed browser states were independently
checked before acceptance. Screenshot and observation artifacts contain only
the isolated fictional test page. A receipt-validation script initially read
UTF-8 text using Windows's default encoding; explicitly reading UTF-8 corrected
that validation error without rerunning either request.

Local acceptance artifact `purchase-review-local-trial/acceptance-results.json`
has SHA-256
`e56eb119bc1847764783188f582595a2f924f8b881f50b53f592a0090e91a44a`.
Its raw transport receipt is
`local-purchase-review-drop-20261011T213956539946Z.json`, SHA-256
`c4644eb34aa30d81b2329728e4f6f4d97dc702c09e66abf7c2fbd2902149376d`.
The build manifest, route-check results, UI observations and two screenshots
remain outside Git with recorded hashes and sizes.

A subsequent fresh read-only hosted preflight,
`deployed-http-replay-20261011T214955230989Z.json`, passed preservation of all
**79 protected tables**, migration identities, the original four purchase
outcomes and the complete **$212 Actual Food Cost** report. It attempted zero
posting requests. That check is separate from the local component trial.

## Remaining hosted acceptance

The local test accepts retry within the same mounted review form. It does not
accept recovery after reload, navigation, sign-out or session expiry, the full
hosted parent workflow, independent employee authority or concurrent first
posting.

The [hosted response-loss plan](BROWSER_POSTING_RESPONSE_LOSS_PLAN.md) now uses
deterministic downstream truncation instead of the unsuccessful DevTools
Offline approach. Before creating its new fictional receipt, the command relay
and phase-aware read-only observer must be implemented and reviewed with exact
version/line/body/key guards. The relay must receive the real upstream outcome
and independently confirm its single committed purchase before withholding
acknowledgement from the browser. The retry must return that same batch and
produce zero further database changes.

The proposed hosted receipt remains uncaptured and unposted. The hosted
frontend API origin, Render configuration, Supabase connections, schema and
roles remain unchanged. This documentation checkpoint is local and not pushed.
