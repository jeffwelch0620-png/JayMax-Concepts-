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
The test server was stopped after each run. This branch is not
pushed, merged or deployed. Review and required GitHub CI come before separate
merge approval and the automatic Render test deployment. Then validate the
newer-source path live, with an independent database comparison and the original
$212 control. Preserve the failed fixture's two unposted versions; a fresh
labelled fixture is needed to recreate the unresolved original review through
normal controls because that review was already discarded. Manual selection of
revision 2 is not automatic-reopen acceptance.

Browser restart, independent employee authority, concurrent first posting,
source-capture/correction command persistence and reviewed fictional-data cleanup
remain separate. Broad UI, Toast and hosted connection architecture remain later
workflows. Purchase accounting uses received dates and explicit counts; prep and
sales remain explanatory tracks.
