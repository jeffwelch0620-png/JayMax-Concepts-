# Reopening the latest captured invoice after retained review discard

The PR23 live recovery trial on October 13 found that revision 2 of a fictional
invoice was captured in a different file. Confirmed discard removed only the
original local recovery copy, but fetched revision 1's original file and reopened
the superseded, held review. No purchase was posted for that invoice. Its newer
revision remains unposted; the closed $212 Food Cost control stayed unchanged.

This local follow-up resolves the source through the invoice identity rather
than assuming later revisions belong to the original file.

## Read contract and confirmation

The existing authenticated purchase document/file preview adds `currentSource`:

```json
{
  "documentId": "the location-scoped invoice identity",
  "versionId": "the latest document version",
  "fileId": "the current captured file, or null when unavailable",
  "revision": 2
}
```

The server selects the greatest revision of the same invoice identity within
the requested restaurant. It finds a linked captured file through immutable
source rows and parse runs, restricted to that restaurant. If more than one
captured file links to the version, the newest capture is selected with file ID
as a deterministic tie breaker. The original file preview still contains its
original source versions; it is not rewritten to contain later captures.
This descriptor is response metadata, not posting authority or a new stored record.

For an unposted review, the initial discard-status read must return a valid
current-source descriptor. Confirmation fetches that file and validates the exact
invoice identity, version, revision and current-source descriptor. A second fresh
read must still identify the same source before the exact original local version/key
is cleared. A missing descriptor, unavailable file, foreign/malformed source,
duplicate candidate or newly captured revision preserves the retained request.
Cancel and check again when the source changes during confirmation.

Another request's already posted outcome retains the existing saved-purchase and
correction path. Own saved/corrected outcomes refuse discard. The user must review
and verify the reopened lines, quantities, conversion, received date and note again.
Discard never posts automatically, cancels an earlier in-flight request or deletes
source/purchase history. Late-commit preflight, server identity locks and the
one-initial-batch rule remain unchanged.

The new client with an older API fails closed for unposted discard because the
descriptor is missing. Both backend and frontend need the reviewed follow-up
deployment for this path. Other saved-status/retry behavior is unchanged. No
schema, migration, permission, connection or hosting-setting change is required.

## Validation and release

The separate-file client regression leaves only revision 1 in the original file,
returns revision 2 through its own file, and verifies the target line ID and a new
explicit posting key. Refusal tests cover malformed/missing pointers, wrong file,
version, identity or revision, duplicate candidates, failed reopening, changed
source metadata and a revision changing in the final read. Existing own-saved,
competing, cancellation, storage and late-commit tests remain in the suite.

The disposable PostgreSQL regression captures two distinct fictional files for
one invoice identity. It verifies the original-file preview stays on revision 1,
both previews identify the current revision/file, original bytes are preserved,
foreign-restaurant reads are refused, and all purchasing-table rows remain equal
across the reads with zero batches or food facts. It is selected by the existing
database CI runner; it does not run against hosted Supabase.

All **689 frontend tests across 67 suites**, including the **90-test Invoice
Master suite**, and the strict `CI=true` production build pass with the native
feature profile, ESLint enabled and a fictional backend URL. The output is
`main.2f343853.js`. The broad disposable database run passed **51 existing checks**
across native purchases, posted-invoice corrections and manual captures. Its new
regression initially failed because the test snapshot incorrectly assumed an
`id` column on source-row links. The snapshot was corrected to compare every
purchasing table, and the new separate-file regression passed in a focused rerun
(one passed, 21 deselected). These are **52 distinct backend checks** accepted
across the broad run and focused rerun, not a claimed clean 52-test single run.
The test server was stopped after each run. These counts describe the historical
local validation; the current live acceptance is below.

[PR24](https://github.com/jeffwelch0620-png/JayMax-Concepts-/pull/24) is merged at
**9b09da529af1b3ed557718fa75351690e3c6d47c**, with all reviewed-head and main CI
checks green. Both Render services were verified Live at that commit.

The fresh **TEST-ONLY-PR24-LATEST-20261013-15** live trial passed. Its original
421-byte request was dropped before API forwarding; all 11 original values
survived reload unchanged and frozen. Capturing revision 2 in a different file
produced the newer-source hold and blocked retry. Cancelling discard preserved
the retained review. Confirmed discard automatically reopened the revision-2
file and SKU with fresh editable fields and no automatic posting. This was
observed through the original tab's DOM; browser detachment interrupted its
separate screenshot export.

After temporary test cleanup, the final explicit review and posting resumed in
a fresh normal app tab. Automated date entry was refused without database
changes. Its local review was discarded through normal confirmation; the user
entered the date manually before a new review was posted. Exactly one initial
batch **0c075457-2a9c-4f80-bee1-5674bb5c08a2** saved on revision 2 with new key
**f6d81aa9-d94e-4769-92f2-69ebc7a0966c**, distinct from the original dropped key
**86732db0-6769-45d9-8af0-edbc5e3254a4**. Its saved values are **berts_SH-003 /
1 each / conversion 1 / $1 food / October 13**, separate zero tax/fees, and note
**TEST ONLY PR24 latest revision 2: verified 1 each at $1.** Full reload retained
the exact comparison, one history row, no corrections and no initial-post/retry
controls. Revision 1 and the earlier failed fixture remain unposted.

The final independent comparison preserves all **86 observed relations** against
the verified post-commit baseline, migration identities and the entire closed
**$184 + $173 - $145 = $212** report. The trial added exactly 15 capture/audit
rows, four posting/audit rows, one food fact and one store revision/timestamp
advance; the store payload is unchanged. The October 13 fictional purchase lies
outside the original closed interval and is not measured usage or a new Food
Cost result. The first final observer attempt exposed a local row-envelope
KeyError; its helper was corrected and the fresh rerun passed.

Private acceptance **pr24-live-newer-source-recovery-acceptance-20261014T001258966559Z.json**,
SHA-256 **44dfe29c093a4c0a08bf0412ebecc243d5bfddefcb97d55b4996b6d45a0a36e3**,
retains the receipts, wire identity, browser observations, final screenshot and
limitations outside Git. The relay is stopped and its port independently closed.
The user reports disabling overrides and resetting temporary device permission;
a fresh normal reload has no test marker. The permission reset itself was not
independently inspected. This is segmented browser acceptance, with automatic
reopen in the original tab and final explicit posting/reload in the fresh normal
tab. It does not claim uninterrupted completion in one tab.

The supporting [invoice-source lookup index](PURCHASE_SOURCE_LOOKUP_INDEX.md) is
a separate local schema proposal before bulk imports. It has not been applied
to Supabase and is not a requirement for the PR24 accounting/recovery result.

Browser restart, independent employee authority, concurrent first posting,
source-capture/correction command persistence and reviewed fictional-data cleanup
remain separate. Broad UI, Toast and hosted connection architecture remain later
workflows. Purchase accounting uses received dates and explicit counts; prep and
sales remain explanatory tracks.
