# Purchase saved outcome recovery review and local follow-up

Draft [PR21](https://github.com/jeffwelch0620-png/JayMax-Concepts-/pull/21)
adds **Check saved status** to a frozen purchase review. The October 11 review
amendment addresses F1, F2 and F3 together: recovery distinguishes this original
request from a competing posting, recognizes later corrections, and explains
held outcomes without suggesting a retry that cannot resolve the hold.

## Recovery decisions

| Read or exact retry result | Display and behavior |
| --- | --- |
| Requested original version and posting key match; no correction | Your purchase was saved and confirmed. Close the initial review and refresh purchase history independently. |
| Requested original version and posting key match; a correction exists | Your original purchase was saved and has since been corrected. Resolve the initial outcome, retain the server's real status, and expose read-only current purchase details and correction history. |
| Another original version or posting key owns the saved batch | Identify a different request/version. Preserve this user's received date, quantity, units, conversion, note, body and key; disable another initial-post attempt and provide read-only comparison. |
| Unposted document is held | Show the returned reasons. Keep the review frozen and disable posting; a later fresh read may clear the hold. |
| Awaiting review with no saved batch | A read can race an in-flight commit. Keep the original review/body/key frozen; permit only an exact retry or another status check. |
| Failed, timed-out, unauthorized or malformed read | Do not resolve the outcome or reconstruct a command. Retain the existing frozen review and any previously established hold. |

A correction on the same source version is recognized as well as a correction
using a supplier reissue. The client never relabels a held server document as
posted: saved-and-corrected is a separate recovery result. A posting response
must also match its returned batch ID to the document's original batch.

The authenticated, location-scoped preview now includes **posted_request_key**,
read from the existing original posting batch's idempotency key. Corrections do
not replace that identity. There is no migration, new table or changed write
rule. Existing authorization and location checks remain in force. The server
still checks the complete original version, key and canonical reviewed-body
fingerprint on every exact retry; the client comparison is not a substitute.

The comparison reads the current posted version and correction history through
existing scoped GET routes. It verifies the document identity, original batch,
current version and correction generation before rendering the saved mappings.
It does not copy those mappings into the frozen request or submit a correction.
A failed comparison leaves the frozen review visible. Purchase history refresh
failure does not undo a confirmed saved outcome. No status check submits a POST.

The status GET retains its 60-second deadline and cancellation. Pending checks
disable posting and checking; failed reads release the check without releasing
the original review. Late timed-out or unmounted-location results cannot supply
a new saved outcome. Existing receiving reads retain their original behavior.

## Local validation and hosted evidence

All **617 frontend tests across 66 suites** pass with the native feature profile.
The focused purchase suite passes **39 tests**, including both correction paths
through status reads and exact retries, independent clients with competing dates
and quantities, read-only comparison, held reasons and later hold release,
missing/malformed request identity, and the existing deadline/location guards.
The strict production build passes with **CI=true**, ESLint enabled and the same
profile. Its backend URL is the fictional `https://backend.invalid`; the build
was not deployed.

Three new real PostgreSQL regression cases cover original posting identity
through same-version and reissued-version corrections, unchanged ledger facts
on exact replay, competing reviews refused with 409, and unauthorized/wrong-store
reads. All **41 tests** in the native purchase and posted-invoice correction
modules pass against the dedicated disposable loopback PostgreSQL 17 server,
with no skips. These three new cases are included in the database CI selection.
The local Windows offline profile passes **211 tests and 323 subchecks** with
no failures or skips. Its first collection attempt lacked the pinned cryptography
dependency; installing the repository-pinned dependency in an isolated local test
folder resolved that environment issue without changing source or lockfiles.
The generated review guides match source; migrations and the schema snapshot
are byte-identical to the pre-amendment head. The dedicated test server stopped
after completion. Local test receipts remain outside Git.

The amendment is local review evidence until separately approved and deployed.
It requires the amended backend preview alongside the frontend; an older server
without the request identity fails closed rather than claiming this request was
saved. Current Render deployment, hosted data, connections, roles and migration
identities are unchanged. The earlier hosted observations below apply to their
pinned deployed source and do not validate this amendment's new status action.

A fresh independent read-only observation at **8:21 PM EDT on October 11**
preserved all **86 observed relations** against the prior post-commit baseline,
one fictional receipt batch/line/food fact, migration identities and the complete
original **$212** accounting report. It made no source-capture or posting request.
Follow-up receipt `hosted-purchase-browser-final-verification-20261012T002133885726Z.json`
has SHA-256 `8ca5995d3b702df095750744d2dc26b099534b29515307608a7295f73df2d115`.
The original receipt remains byte-identical to its recorded hash. The verifier
now saves future readbacks under exclusive timestamped filenames.

The human completed normal owner sign-in in Chrome; no credentials were
extracted or submitted by automation. The existing acknowledged receipt was
reopened in the deployed Invoice Master, then reopened again after Dashboard
navigation and after a full app reload. Each fresh file read showed the invoice
as **posted**, with **no initial-post/retry button**. Its history contained one
October 11 entry for **1 each / $1.00**. After reload, the owner selected Bert's
again from the Ownership dashboard. No capture, posting or correction control
was submitted. Native readback evidence is retained outside Git.

A final independent read-only comparison at **8:43 PM EDT on October 11**
confirmed the same one batch/line/food fact, unchanged rows and hashes across all
86 observed relations, unchanged migration identities and the full **$212**
original report. Receipt
`hosted-purchase-browser-final-verification-20261012T004339755060Z.json` has SHA-256
`31c5b9115deca9bc098f63988823da98edab7081275711e883ecbee6fdc56d09`.
Browser receipt `saved-outcome-reopen-evidence/browser-results.json` has SHA-256
`43d1b8bb8c579b28ccd586e9274e4522de14c81c195ef7d233f263311cc7c893`.

This accepts **saved-outcome readback** in the existing deployed parent after
normal sign-in, navigation and reload. The original trial had already
acknowledged its exact retry before these reads. It does not prove continuity
of an unresolved body/key across remount, session-expiry recovery, or the new
local status action itself. That action has not been deployed or tested live.
Initial capability reads briefly displayed the existing awaiting-enablement
message before normal loading completed; that presentation remains part of the
deferred UI workflow.

## Remaining sequence

1. Saved-outcome reopening in the deployed parent is now complete within the
   scope above. Preserve the same labelled receipt and original control.
2. Draft PR21 is published for review. Verify its current-head CI and obtain
   separate approval before a merge/deployment. Rehearse the new status
   action against saved and unavailable outcomes without another first-post
   fixture for the already accepted same-form case.
3. Separately decide whether exact pending-command continuity is required across
   browser reload or sign-in. If so, design a scoped pending-command receipt
   with immutable body/key, authenticated owner/location boundaries, expiry and
   explicit read-before-retry reconciliation. Do not treat browser persistence
   alone as a transaction guarantee or automatically resend after login.
4. Retain independent employee authority and concurrent first-posting acceptance
   as separate checks. Broad UI work, hosted connection architecture, Toast and
   reviewed fixture cleanup remain later workflows.

No new hosted record, role, schema or connection change is included. Track 1
continues to use purchased physical inventory, received-date purchases and
explicit count values; prep and sales remain explanatory tracks.
