# Submitted source-capture recovery

## Current hosted checkpoint

The owner-approved PR35 merge is **edbf2321769ce9a6343d28483af8dbcee903a885**,
from amended head **7ae28dabb589075902d22d171baff910d1d12db4**. Amended-head
and merged-main CI passed; both Render services are verified Live on the merge.
Normal fictional CSV capture/status/reload and the manual-source loss/reload/exact
retry/lost-acknowledgement recovery case passed, with no accounting changes.
The file before-save/sign-in/exact-reselection case and after-save/lost-status/
reload case also passed. The final identity-conflict/discard case passed both
failed-read retention and fresh-conflict local clearing, preserving an unrelated
manual draft. Final independent checks confirm five single-attempt sources,
zero purchase postings, unchanged pre-existing protected data and $212.00 Food
Cost. The relay is stopped, owner-reported permission cleanup is complete, and
normal browser reload has no test banner or pending request. These are scoped
CSV/manual results; raw/PDF transport remains untested. The
[live checkpoint](PR35_HOSTED_CAPTURE_CHECKPOINT.md) distinguishes completed
observations from prepared tests. Older unmerged/undeployed wording below is
historical and superseded by this checkpoint; no new maintenance window is open.

October 15, 2026. Local follow-up from `5be2c20`, after PR34's hosted recovery
acceptance and the completed backup/index maintenance window. Implementation and
local validation are recorded at `278863e`; the owner subsequently approved
publishing a draft PR for independent review. It remains unmerged and undeployed;
GitHub CI is a separate check from the local results below. No hosted writes,
connection changes, role changes or schema migrations accompany this slice.

## Independent-review amendment

The owner authorized amending draft [PR35](https://github.com/jeffwelch0620-png/JayMax-Concepts-/pull/35)
after review of published head `3c327ae`. The original-head CI passed all four
jobs; amended-head CI remains a separate check.

- Retain the raw filename for display, exact reselection and compatibility with
  existing tab records. Only the server's file-status comparison applies HTML
  multipart filename escaping: double quote becomes `%22`, LF `%0A`, CR `%0D`.
  No percent decoding is performed, so literal `%22`/`%0A` filenames stay literal.
  Source bytes, digests, request keys and the strict command replay guard are
  unchanged. The fix applies to both CSV and raw-source capture; see the
  [HTML multipart filename rules](https://html.spec.whatwg.org/multipage/form-control-infrastructure.html#multipart-form-data).
- A recognized status identity conflict now exposes confirmed local discard,
  with a warning that a source may already be saved. The server returns a typed
  `capture_identity_mismatch` conflict; the client also recognizes the exact
  original status message during staggered service deployment. Arbitrary 409s,
  authentication errors, failed reads and malformed saved evidence do not grant
  discard or retry permission.
- Discard confirmation always checks again: fresh mismatch or `retry_available`
  clears only the exact tab record; fresh `saved` opens the validated source;
  timeout/authorization failure/malformed evidence leaves recovery intact. A
  conflict never enables retry or claims that no source was saved. File discard
  clears the selected file and preserves unrelated unsubmitted manual fields.
- The status routes require the same owner/manager authorization as capture
  commands while retaining read-only database transactions. SQL lookup filters
  by store before inspecting an attempt: a foreign-location key is
  indistinguishable from an absent key, and no foreign file details are returned.
  Same-store actor/source mismatches retain the strict conflict response.
- Unsupported filenames fail before hashing or submission with an explicit
  rename/reselect instruction. Slashes/backslashes remain disallowed because
  server basename handling differs between Windows and Linux. The journal schema
  is unchanged; existing submitted records are neither rewritten nor given new keys.

The route-kind column remains deferred. No schema/migration or login redesign
is needed. Amendment local results are below; the older validation later in
this document is historical. Merge and live acceptance remain separate owner
decisions. Check the current head's [PR35 CI results](https://github.com/jeffwelch0620-png/JayMax-Concepts-/pull/35/checks),
not a green run from the original reviewed head.

### Amendment local validation

| Check | Result |
| --- | --- |
| Full frontend | 789/789 tests, 71/71 suites |
| Strict production build | Passed, CI=true and ESLint enabled |
| Offline review checks | 741/741 cases: 285 methods + 456 subtests; zero skipped |
| Full manual-source/native-purchase suite | 38/38: 34 PostgreSQL integration tests + 4 parser tests |
| Focused frontend | 208/208, overlapping the full suite |
| Focused database recovery | 5/5, overlapping the full suite |
| Local database/role inventories | Unchanged before/after both database runs; owned PostgreSQL 17 stopped |

All fixtures are fictional and no hosted connection was used. The two added
database methods cover twelve actual multipart filename combinations across
CSV/raw routes, stored name assertions, literal-percent preservation, read-only
saved lookup, exact replay, strict changed-name refusal, and the real app's
owner/manager/readonly/staff/location/anonymous authorization for both routes.
Purchasing-table snapshots around status reads remain exactly equal. Component
cases cover the mismatch exit, fresh saved/negative reads, timeout/401/403/
unrelated conflict/malformed evidence, raw quoted-name capture, and preservation
of an unrelated manual draft. All five recovery database methods are selected
by the repository's CI runner.

Amendment receipts under the build workspace's `work` directory:

- `source-capture-amend-frontend-20261015T190143340935Z.json`.
- `source-capture-amend-build-20261015T190143180368Z.log`.
- `source-capture-amend-offline-20261015T190143268177Z.xml`.
- `source-capture-focused-20261015T190023698137Z.json`.
- `source-capture-tests-20261015T190014473442Z/receipt.json` (focused database).
- `source-capture-amend-tests-20261015T190219088745Z/receipt.json` and `database.xml` (full database).

## Behavior

Invoice Master now retains a submitted manual source or file-capture request
before its first POST. Recovery is scoped to the signed-in user and canonical
restaurant in this browser tab's `sessionStorage`. An unavailable, corrupt, full
or unverifiable recovery store blocks submission. Limits are 32 requests and
2 MiB per user/location; earlier records are preserved when a limit is reached.

- Manual entries retain their exact submitted source fields, blanks, leading
  zeroes, repeated additional labels, attachment references and original key.
  Attachment IDs are normalized to the same sorted unique set the server uses.
- File captures retain the route kind, filename, byte count, SHA-256 and original
  key. Original file bytes are not copied into recovery storage. After reload,
  retry requires reselecting the same filename and exact bytes. PDF/photo/raw
  retention and vendor CSV parsing remain separate capture choices.
- Reload and sign-in restore the requests without sending them. A read-only
  status check is required before an explicit retry. A negative read is only a
  point-in-time observation: the original command can still complete later.
- A dropped or malformed command response cannot itself confirm success. After
  a send, status is checked and the saved file is read and matched before the
  exact recovery record is cleared and purchase review opens. Reads time out
  after the existing 60-second read budget and leave the request retained.
- Late responses cannot populate a different user/location's workspace or clear
  the old user's request. New source capture controls are disabled for a capture
  of the same category while its outcome remains unresolved.
- Confirmed local discard performs another fresh status read. If already saved,
  it opens the source instead. Otherwise it removes only that exact tab record;
  it neither deletes a source nor cancels an earlier command. The UI tells the
  operator to inspect captured files before creating a replacement.

Ordinary unsubmitted drafts are not persisted by this feature. Closing the tab,
clearing browser data or restarting the browser can remove recovery evidence.
A new tab is not a guaranteed shared recovery surface. Browser recovery is not
server authority or a replacement for the retained source and purchase history.

## Server contract

Two POST endpoints carry lookup input but perform read-only database work:

- `/api/pg/purchases/{store}/capture-status`: CSV/raw-file hash, byte count,
  filename and requested kind, with the original `Idempotency-Key` header.
- `/api/pg/purchases/{store}/manual-records/status`: exact original manual body
  with that header; uses the command's shared canonical source serializer.

The lookup first scopes the attempt to the store, then checks actor, multipart
filename, digest and byte count. An in-store mismatch returns a typed generic
conflict without foreign file details. An absent or foreign-store attempt returns
`retry_available`, never an invented file ID.
Lookups use a consistent read-only transaction.

Raw-source completion needs retained bytes. CSV completion additionally needs
the current parser's committed parse run. Manual completion needs its committed
manual parse run and the exact attachment-link set. Source retention, projection
and linking are separate command transactions; partial completion therefore
remains `retry_available`. A completed capture can still contain parsing or
document-review holds: capture success never means approved inventory posting.
The stored attempt predates this feature and has no route-kind column; completeness
is evaluated for the requested capture kind, not a newly asserted historical
route identity. No schema field is invented to imply otherwise.

Normal command replay now also requires the original actor and supplied filename,
alongside the original file identity. Its transaction rolls back a conflicting
attempt. New keys may still retain identical bytes under the existing per-store
content deduplication; this slice does not change invoice revision rules.

Status recovery cannot approve quantities, conversions, received dates or costs.
The normal capture and purchase commands retain their authorization and validation.
Actual inventory remains the accounting baseline; prep/sales are explanatory,
and taxes/fees remain separate from food amounts.

## Original-head validation and remaining gates

Local frontend validation passes **776 tests in 71 suites**, including 11 capture
component cases, seven capture-journal cases and bounded status-read coverage.
The production build passes with `CI=true` and ESLint enabled. Offline checks
pass **741 cases** (285 methods plus 456 subtests), with zero failures/skips.
The full manual-source/native-purchase suite passes **36 cases**: 32 PostgreSQL
integration tests and four parser tests. Its database/role inventories match
before/after and the owned loopback PostgreSQL 17 server is stopped. Final focused
reruns pass 195 frontend tests and all three new database recovery cases after
the last changes. These overlap the full runs and are not added to their unique
test counts. Both final database runs also match the initial pre-failure inventory.

Fixtures are fictional. The database suite snapshots all purchasing tables around
status reads, covers bytes-only and projection-without-links partial stages,
exact retry, foreign actor/location/key content, and verifies zero actual purchase
facts from source capture alone. Existing manual-source and native-purchase
integration tests are rerun alongside the new cases. New cases are included in
the repository's database CI profile.

Local evidence under the build workspace's `work` directory:

- `source-capture-frontend-20261015T183754993906Z.json`: 776/776, 71/71 suites.
- `source-capture-build-20261015T184010038733Z.log`: strict production build passed.
- `source-capture-offline-20261015T183441545145Z.xml`: 741/741 reported cases.
- `source-capture-tests-20261015T183546461500Z/receipt.json` and `database.xml`:
  full 36-case pass, zero skips, unchanged inventories, server stopped.
- `source-capture-focused-20261015T184312576785Z.json`: final 195/195 focused pass.
- `source-capture-tests-20261015T184313455457Z/receipt.json`: final three-case
  database recovery rerun passed, unchanged inventories, server stopped.

An initial database run failed during setup because the readiness helper was
local to the older route installer. The helper is now shared, the three databases
created by that failed setup were removed by their exact run-owned identities,
and the original inventory was restored before the successful full run. The
cleanup receipt is preserved with the failed run; existing test databases and
roles were left intact. Initial test-fixture and strict hook-lint failures were
also corrected before the successful runs above. No hosted connection was used.

The owner approved the requested draft-PR push after local validation.
Remaining: independent review and CI;
separate owner merge approval (main auto-deploys to the Render test app); then a
scoped fictional live reload/sign-in and dropped-response acceptance test. Local
mocked transport results are not live transport proof. UI redesign, product
Backup/Restore buttons, deployment architecture, runtime-role cutover and credential
rotation remain later workflows. The previous maintenance window remains closed.
