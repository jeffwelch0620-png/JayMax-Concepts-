# Purchase saved outcome recovery review and local follow-up

[PR21](https://github.com/jeffwelch0620-png/JayMax-Concepts-/pull/21), merged and
deployed at `54975a0` under user approval, adds **Check saved status** to a frozen purchase review. The October 11 review
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

## Reviewed PR21 validation and hosted evidence

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

## Deployment and comparison follow-up

Both Render services were independently read as **Live** at merge commit
`54975a0bd1787595a73195e3964c94562cb02bfc` on October 11. Both deployments were
automatic; no manual deploy, setting, role or connection change was made.
All four [merge-commit CI checks](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/38196259722)
pass. The public bundle contains the amended recovery controls. After a cache
refresh, the signed-in owner reopened the existing fictional Bert's receipt
and used **Show saved purchase and correction history**. The read-only table
showed `berts_SH-003`, 1 each, conversion 1 and inventory date October 11, with
no corrections recorded. The initial posting/retry actions were absent. No
capture, purchase-posting or correction command was submitted in this check.

The saved review note displayed as a dash. `document_preview` returns mapping
rows with their canonical **decision_note** field; the client read **note**.
An independent read-only query confirms the persisted decision note exactly
matches the original review, so the source data did not need correction.
The local follow-up changes only the comparison's rendering and shape check to
`decision_note`. Its fixtures now use the real response field. Two regressions
reproduced the missing note and missed malformed-note rejection before the fix;
afterward all **619 frontend tests across 66 suites** pass, including **41
purchase component cases**. The strict `CI=true` production build also passes
with the native profile and fictional backend URL. This follow-up was merged under explicit approval in [PR22](https://github.com/jeffwelch0620-png/JayMax-Concepts-/pull/22)
at **cd29f22** on October 12 and deployed on the frontend; its live saved-note
readback passed. The API remains at **54975a0**.

A fresh independent read-only comparison at **1:08 PM EDT on October 12**
confirmed unchanged rows/hashes across all **86 observed relations**, migration
identities, one original receipt batch/line/food fact and the complete original
**$212** report. An earlier comparison lost its connection; the fresh retry
passed without a configuration change. The verifier's source-capture/posting
counts describe the earlier execution receipt, not commands submitted by this
read-only follow-up. The new comparison and this verifier made no such command.

Private evidence remains outside Git:

- Render readback: `pr21-render-deployment-verification-20261012T025357934480Z.json`, SHA-256 `7980ea2ebf57b221389f5417b9d6aa1271a28abf5e3b502f3d38e82f17c7a15d`.
- Stored-note proof: `pr21-comparison-note-readback-20261012T030650921600Z.json`, SHA-256 `8a711f70db35ec445fb2fe45ef848c7b917d006210f682edc6b56e8fbc6185fe`.
- Latest full comparison: `hosted-purchase-browser-final-verification-20261012T170802141851Z.json`, SHA-256 `a3a8aa7798f357e32c2e442bd643647e07e573d780366da4b6da62417854c636`.

This validates deployed read-only comparison of an already posted receipt and
finds a small display defect. It does not establish the new **Check saved
status** path from an unresolved request, corrected/competing request recovery
or held-read recovery in the deployed parent. The pending key/body cannot be
reconstructed after reload. Those runtime cases remain distinct from local and
CI regression proof. The historical hosted observations below retain their
original pinned scope.

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

## Current sequence after the October 12 acceptance

PR22 is merged and its saved-note display is accepted live. Deployed unposted,
failed-read, held, competing, own-saved and own-saved/corrected cases are recorded
in the JMax reference pages and private acceptance receipts. A real response drop
in the full Render parent, using fixture-specific browser routing to a loopback
relay, verified commit before delivering 1 of 3,831 acknowledgement bytes. The
exact manual retry returned the original batch without adding or updating rows;
the final comparison preserved all 86 relations and the original $212 report.
The earlier observations above retain their historical scope.

Merged PR23 at `4f93748` retains initial submitted purchase body/key across
reload and same-user reauthentication in the same tab. See the
[pending initial purchase recovery review](PENDING_PURCHASE_RELOAD_RECOVERY.md)
for its local validation, boundaries and separate deployment acceptance plan.
Its review amendment adds confirmed local discard after fresh status checks,
handles late original commits without a new
automatic POST. Held sources stay held; saved invoices require correction review.
The October 13 live reload/sign-in and competing-discard trials passed. The
newer-source trial exposed a separate-file reopening gap and stayed safely held
with zero purchases for that fixture. The local
[current-source follow-up](LATEST_SOURCE_RECOVERY.md) addresses that lookup and
still requires review, separately approved deployment and live acceptance.
Manual source-capture and correction persistence, independent employee authority,
concurrent first posting and reviewed fictional-data cleanup remain separate.
Broad UI work, hosted connection architecture and Toast remain later workflows.

No new hosted record, role, schema or connection change is included. Track 1
continues to use purchased physical inventory, received-date purchases and
explicit count values; prep and sales remain explanatory tracks.
