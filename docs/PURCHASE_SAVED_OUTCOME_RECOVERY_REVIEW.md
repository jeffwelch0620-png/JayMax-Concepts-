# Purchase saved outcome recovery review and local follow-up

The existing database prevents a second initial posting for the same invoice.
The remaining recovery gap is in the client: its exact submitted review and
idempotency key live in a component ref and disappear after remount, reload or
session exit. Reopening the retained file queries its saved status and can show
an already posted invoice without another command. An unsuccessful or negative
read cannot establish that an earlier command failed to commit.

This follow-up adds a read-only **Check saved status** action to a frozen purchase
review. It preserves the existing body and key when status is unavailable,
unposted or held, and resolves the displayed outcome only after the requested
version is positively read as posted with its batch identity. It also requires
a posting acknowledgement to identify the requested document and the batch
recorded on that document before announcing success. The changes are local and
not deployed; the accepted hosted test remains evidence for its pinned source.

## Source findings and selected approach

| Finding | Consequence and response |
| --- | --- |
| `PurchaseDocumentReview` stores its pending command in `useRef` | Exact retry survives in the mounted form; its key and reviewed values are not durable across reload or session exit. Keep that limit explicit. |
| Invoice Master and its review are remounted on navigation/location changes and file reopening | Read saved state before considering any further write. Do not automatically reconstruct and resubmit a command. |
| `post_review` locks the document identity/version and checks its existing batch first | Matching original version, key and fingerprint return the original batch; a different review or key for a posted identity is refused. This protects the ledger independently of the screen. |
| `file_preview` reads each document's current posted version and batch | Reopening is an existing read-only recovery path. Verify it in the deployed parent using the retained fictional receipt. |
| The old client accepted a truthy batch and `status: posted` without matching document/batch identities | The local follow-up now checks the requested version ID and equality between the response batch and the document's posted batch. |
| A saved-status read may stall or race an earlier commit | The new GET has a 60-second deadline with cancellation. A negative/failed read preserves the frozen original request; it never enables an edited replacement command. |

The status action uses the existing scoped document GET. It does not submit a
posting, correction, capture or migration. A positive read displays **Saved
purchase found** rather than attributing that posting to the unresolved local
review; the user should inspect history before a correction. History refresh
failure does not undo a confirmed saved outcome. While checking, retry and the
check button are disabled. Late responses to an unmounted location cannot
populate a new location's panel.

The shared read-deadline helper accepts an optional diagnosis; its existing
state-read budget, default message and mutation semantics remain intact. The
purchase-status adapter uses a purchase-specific diagnosis. Existing document
reads used by receiving retain their original behavior.

## Local validation and hosted evidence

All **606 frontend tests across 66 suites** pass with the reviewed native feature
profile. This includes 18 new cases for positive and negative saved reads,
authorization/read failure, malformed or mismatched results, pending/timeout
release, unchanged retry identity, remount, location isolation, and matching
posting receipts with independent history refresh. These controlled local cases
are separate from hosted runtime proof. The strict production build also passes
with `CI=true`, ESLint enabled and the same native feature profile.

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
2. Review the local candidate, push a draft PR when authorized, verify CI, and
   obtain separate approval before a merge/deployment. Rehearse the new status
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
