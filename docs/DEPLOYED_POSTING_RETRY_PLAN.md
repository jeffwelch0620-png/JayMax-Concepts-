# Deployed invoice and credit retry procedure

The core deployed test [passed on October 11, 2026](DEPLOYED_POSTING_RETRY_RESULTS.md):
eight exact retries returned the original outcomes and eight conflicting retries
were refused, with all 79 protected tables and the complete **$212 Actual Food
Cost** report unchanged. The procedure below records its preparation and
execution controls; the optional concurrent extension and separate browser
lost-response trial have not run.

Read-only preparation verified the four original fictional Bert's postings,
their request fingerprints and the accounting control, sending zero posting
requests. Execution then used the existing Render API and normal owner
authentication to return the same saved outcomes over HTTP.

The [earlier replay results](POSTING_RETRY_ACCEPTANCE_RESULTS.md) established
16 exact retries and eight 409 refusals through an in-process FastAPI harness
against hosted PostgreSQL, with rollback guards. Deployed HTTP requests cannot
use those outer transaction guards. Immediate independent readback is therefore
required after each request, and a whole-table comparison closes the run.

## Prepared originals

| Document | Original batch | Posting lines | Food effect |
| --- | --- | --- | --- |
| TEST-ONLY-PFG-20261010-03 | 255d8fda-d967-4ba6-91d8-9e0465fc4cd9 | 2 | 40 lb protein / $140; 100 each appetizers / $25 |
| TEST-ONLY-USFOODS-20261010-04 | 6dfd17b8-b5b7-4bf5-9014-ac6ac5ba9c78 | 1 | 20 lb produce / $50 |
| TEST-ONLY-PFG-RETURN-20261010-05 | c95fe8cf-de7c-4013-ac5f-355fd509a1ad | 1 | -10 lb / -$35 physical return |
| TEST-ONLY-PFG-PRICECREDIT-20261010-06 | a1bb1165-ac62-4602-b22c-a05892393fa8 | 1 | Zero quantity / -$7 linked price credit |

Read-only preparation confirms one persisted batch per document and the expected
2/1/1/1 line graph. Each reconstructed `PostDocument` reproduces the stored
request fingerprint, including a serialize/parse/model-validation round trip.
Stored command keys, document versions and batch identities are unchanged.
Mapping notes retain their TEST ONLY labels.

The local preparation helper `prepare_deployed_posting_retry.py` has no HTTP
execution path. It writes request material outside Git, without authentication
credentials, and a separate shareable receipt:

- `deployed-replay-preparation-20261011T162527770892Z.json`
- `deployed-replay-requests-20261011T162527770892Z.json`

The preparation receipt records source and request-file hashes, four fingerprint
checks, **79 unchanged protected tables**, unchanged migration identities and
the full accounting report. The route source hashes match the earlier executed
API/database replay. The request material is local execution input, not a
replacement source import or a new invoice review.

## Preflight immediately before execution

1. Verify the actual HTTPS API origin from the existing deployed frontend's
   normal request configuration and its current Render deployment record. Do
   not infer it from the frontend URL. Pin the deployed backend revision and
   confirm the purchase routes match the prepared source hashes. An unchanged
   backend may legitimately have a different commit from the frontend.
2. Use the existing owner or authorized Bert's manager session. The production
   route rechecks normal application authorization for each request. Keep bearer
   tokens private and out of plans, receipts, command arguments, Git and logs.
   Do not copy database credentials into an HTTP client or change authentication.
3. Arrange a quiet test window with no other fixture edits or postings. Run fresh
   read-only observation against the same designated build database, comparing
   the migration identities, all 79 protected tables, original batch/line graph,
   and the complete accounting report with the prepared control. A changed
   baseline requires reconciliation before execution.
4. Independently read all four documents through the deployed API. Require the
   expected version, posted status and original batch identity. Revalidate each
   request file hash, original key and model-normalized fingerprint against the
   persisted posting. A missing posting or mismatched fingerprint holds the run;
   do not use POST to reconstruct a missing outcome.

## Exact retries

The local execution helper is `run_deployed_posting_retry.py`, retained outside
Git. Its default mode performs read-only preflight and sends no posting request.
The explicit execution mode requires the operator to sign in through a masked
local prompt using the existing Inventory owner account. It calls only the
normal `https://jaymax-api.onrender.com/api/auth/login` endpoint and keeps the
password and token in memory. Closing the prompt stops execution before posting.
Each HTTP command is followed by a fresh read-only database transaction, checking
all 79 protected tables, migration identities, the full report and all four
original batch/line/fact graphs, plus a deployed document read.

Current preflight confirms the API is Live at `b2f529f` in Render and the frontend
serves the accepted `main.7e3cd424.js` asset pointing to that API. The prepared
Windows source hashes differ from the deployed commit blobs because of CRLF;
the source is byte-for-byte identical after CRLF-to-LF normalization only. Both
raw hashes and the comparison method are retained in the preflight receipt.
Five offline transport tests pass: original command identity/results, stopping
after a lost response, stopping after changed rows, cancelled sign-in, and the
default mode's zero-posting behavior. These controls validate the test runner,
not deployed replay results.

Use the actual API origin with the prepared path:

```text
POST /api/pg/purchases/berts/documents/{original_version_id}/post
Content-Type: application/json
Idempotency-Key: {original_stored_key}
Authorization: Bearer {private_current_session_token}
Body: {unchanged_prepared_PostDocument}
```

1. Send one exact retry per original document, sequentially. Require HTTP 200,
   the original `batchId`, and the original document ID with status `posted`.
   Read back that document and its persisted batch/line graph after each request.
2. Repeat one exact retry per document through a new HTTP client connection,
   retaining the same body and original key. This totals **eight exact responses**
   in the core deployed test. A new client connection is not evidence of a new
   database login or session renewal.
3. After the sequential core and whole-table comparison pass, a separate
   extension may send two concurrent exact retries per document. Record those
   eight responses separately. It tests concurrent replay of an existing outcome,
   not concurrent first posting.

Do not generate a new key for an exact retry, change decimals or notes, rebuild
the review from current item conversions, import source files, or use correction
routes. Closed-period history must remain closed and unchanged: an exact retry
returns the prior outcome before the new-posting validation path.

## Conflicting retry refusals

After exact retries and their preservation checks pass, use each original posted
document for two refusal probes:

1. Keep its original key and body except for a clearly labelled appended test
   note. Require **409**, with no saved mapping, batch, revision or accounting
   change.
2. Keep the exact body but use a distinct valid UUID key. Require **409**, with
   the same preservation checks. This is an intentional refusal probe, not an
   alternative retry strategy.

There are **eight refusal responses** for the four documents. Read back after
each probe. A 401/403 is an authentication hold, 422 is a payload/setup hold,
and 429 is a rate-limit hold; none counts as the expected idempotency refusal.
Do not modify permissions or regenerate the original command to bypass a hold.

## Preservation and stop conditions

After each HTTP command, compare the guarded purchasing batch/line/mapping/
reconciliation/item-base and store-state tables, plus the original document's
one-batch identity and line/fact cardinality. At phase boundaries and completion,
compare all 79 protected tables, migration identities and the complete report:

**$184 opening + $173 net received food purchases - $145 closing = $212.**

Retain the same received dates, return and price-credit links, explicit physical
values, separate tax/fees and prep/count/history records. No new outcome is
expected. Catalog/authentication tables outside the protected set are not covered
by its hash claim.

Stop on a changed batch, duplicate line/fact, row/hash/revision change, incomplete
readback, unexpected response, deployment drift or accounting difference.
Preserve the evidence and reconcile it; do not delete records, issue a compensating
credit, reopen periods or continue probes to hide a discrepancy. Changes caused
by another editor make the preservation result inconclusive until explained.

For a transport timeout, treat the outcome as unknown: read the persisted
document and protected baseline first. Keep the original body and key. Do not
automatically retry, interrupt a request, or continue if readback cannot confirm
the original outcome. Never log bearer tokens or raw authorization headers.

The result receipt must distinguish requested cases, actual responses, original
identities, per-request readbacks, table/report comparisons and held cases.
Only claim deployed HTTP acceptance after those checks pass.

## Separate browser lost-response trial

Already-posted documents cannot exercise the review form's initial uncertain
submission because the form disables posting once status is `posted`. A browser
response-loss trial therefore needs a separately reviewed fictional unposted
fixture, its own accounting expectations, and controlled transport behavior.
It must demonstrate the frozen body/key, retained review, same-command retry and
one saved outcome after reconnection. Do not reopen or repurpose these four
original controls for that trial. First-post concurrency, expired-session recovery
and independent employee authorization also remain separate acceptance cases.

Current Render hosting, Supabase connections, database roles and schema stay in
place during these build checks. Broad UI and connection decisions remain deferred.
