# Hosted purchase response loss and exact browser retry

On October 11, 2026, the unchanged purchase-review component recovered from a
lost first response after the existing Render API committed a fictional receipt
to hosted PostgreSQL. One manual retry returned the original batch, with no
additional database changes. This accepts recovery in the same mounted review
form, using a separate local client; it does not accept the entire hosted
frontend or recovery after navigation, reload, sign-out or session expiry.

## Scope and identities

The user-approved Bert's fictional scope created one source and one purchase:

| Field | Verified value |
| --- | --- |
| Supplier / document | PFG / `TEST-ONLY-BROWSER-RETRY-20261011-07` |
| Existing inventory item | `berts_SH-003`, TEST ONLY Appetizer - UI 20261010 |
| Received date | October 11, 2026 |
| Quantity / verified conversion | 1 each / 1 inventory each per received each |
| Food purchase cost | $1.00 |
| Source tax / fees / discount | Explicit $0.00 each |
| Source file | `129bfadb-bfb7-4607-96a5-0b243e0342b2` |
| Document identity | `ca3a8c05-caa3-49cd-86bf-1236e83758e4` |
| Version | `25d7bbdf-0adf-4505-897c-e85bcc04230c` |
| Source line | `3234e69f-9119-4d98-9b40-c58706245856` |
| Saved purchase batch | `f40b3514-5cf5-41db-a5ed-7ed594249bc7` |

The source contains invented supplier/customer identifiers, the extra field
`Test purpose = Fictional browser lost-response acceptance`, and an explicit
fictional-evidence note. No real invoice export or attachment was imported.
The receipt remains persisted as a labelled test fixture. No deletion, reversal,
additional count, prep, waste, sale or period closure was performed.

## Method and observed results

Before execution, native Chrome read back Render's live API revision
`b2f529fc59f2c10eb62376884ebc3a7a5fe22601` and deployment
`dep-db5eob5ckfvc739v2dc0`. Pinned backend sources match that revision after
CRLF normalization only. The accepted frontend remains `4855ba6`.

The separate loopback client imported the unchanged `ManualPurchaseEntry` and a
literal unchanged `PurchaseDocumentReview` segment with existing form controls.
Its parent wrapper retained the production acknowledgement condition. The human
signed in through the normal owner login in a private local prompt; credentials
and the token stayed in process memory. Native Chrome entered and confirmed the
source, received date, USD currency, item, quantity, conversion and review note.

The relay admitted only the exact prepared source and captured version/line,
used normal verified TLS to the existing API, disabled automatic transport
retry and redirects, and serialized the guarded commands. No browser proxy,
certificate, hosted API URL or deployment setting changed.

1. **Source capture:** one actual API request returned HTTP 200, 4,082 bytes.
   A fresh independent read-only database observation verified eight expected
   source rows, retained source content, and zero purchase movements before the
   complete response was delivered to Chrome.
2. **First posting:** the actual API returned a complete HTTP 200 response of
   3,759 bytes. A separate read-only connection verified the committed batch,
   request fingerprint, one posting line and one derived food fact. Only then
   did the relay declare 3,759 bytes while delivering 1 byte and closing the
   browser connection. Chrome reported `ERR_NETWORK`, status 0 and no
   acknowledgement. The actual review component retained its date, item,
   quantity, units, conversion and note, disabled edits and offered
   **Retry same purchase posting**.
3. **Manual retry:** native Chrome clicked that control once. The second command
   had the identical 438-byte body, SHA-256
   `17d52ad3b19632658845c8d5ce8413d8703f4797d40460562f07dd721dc33fd2`,
   and browser-generated key `ea3960a2-87eb-464d-9601-ce98284e679c`.
   The actual API returned the same batch and complete 3,759-byte acknowledgement.
   Independent comparison found **zero added rows and zero updated rows**.
   Chrome acknowledged HTTP 200 and rendered the document as posted.
4. **Final check:** after the helper stopped, a new read-only connection again
   verified exactly one batch, one line and one food fact. All 86 observed
   relations matched the post-commit baseline. The loopback port was closed and
   the in-memory token was discarded.

There were **one source-capture request and two purchase-posting requests**:
first command plus one deliberate manual retry. The initial command's expected
changes are eight source rows, four posting/audit rows, one derived food-fact
row, and Bert's store revision/timestamp advancing once with its payload intact.
The 86-relation observation covers the existing 79 protected tables, six
additional catalog/legacy/reporting tables and the derived purchase-fact view.
Prior rows, catalog identity and migration identities were preserved in every
phase; this is not a claim that first posting left every relation unchanged.

## Accounting preservation and limits

The full original October 1-8 report remains exactly unchanged:
**$184 opening + $173 net received food purchases - $145 closing = $212 Actual
Food Cost**, report hash
`e85c53b4edb66eb34f0ffa5c52f40bbdbbc72557e8d05f212d5b70e703321d66`.
October 11 is outside that interval. The new $1 purchase is not $1 of measured
actual usage or a new Food Cost calculation; that requires the next physical
count and explicit inventory value.

This trial covers normal owner authority, one first command and exact retry in
the same mounted form. Independent employee authorization, concurrent first
posting, the complete hosted parent, and recovery after remount or session
expiry remain separate. Broad UI rework, connection architecture, Toast and
reviewed fixture cleanup remain later workflows. Current Render hosting,
Supabase connections, application source, schema and database roles are unchanged.

## Retained evidence

Receipts, helper sources, private test build and native browser evidence stay
outside Git. The local runner's **28 offline guard tests** passed before
execution, including real loopback refusals; these are separate from hosted
acceptance. No application source changed and no new GitHub CI run is claimed.

| Local evidence | SHA-256 |
| --- | --- |
| `hosted-purchase-browser-execution-20261011T234334380894Z.json` | `75ab19d4d8d3bbe04daab4fe8c1f69986fba7f49674c0fa753e02fff351b93f7` |
| `hosted-purchase-browser-final-verification-20261012.json` | `15054290c3b6e30c2cddbcd26bd42e0faca8da29b1c7761ef6e44a0f3d6c2737` |
| Separate browser `client.js` | `680847e29dbdd936d83ba4a58e3ef531456aa849b88af88cc6cc64e81403a2ff` |

Execution completed about 8:03 PM EDT on October 11. The final read-only check
completed at 8:04 PM EDT (October 12, 00:04 UTC, hence its filename). Native
review, network-error/frozen-form and acknowledged-posted readbacks, plus
screenshots and the Render revision readback, are retained in the private build
directory. This documentation checkpoint is local and has not been pushed.

Next, inventory the remaining acceptance gaps and review recovery across remount
and session boundaries before extending this evidence to those cases. Preserve
the existing test identities and avoid another first-post fixture for the
already accepted same-form case.
