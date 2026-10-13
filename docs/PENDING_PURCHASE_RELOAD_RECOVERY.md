# Pending initial purchase recovery across reload and sign-in

An initial purchase review previously held its submitted body and idempotency
key only in a mounted component. A reload or session-expiry return to sign-in
lost that command identity. Reading an already posted invoice after reload
proved persistence of the purchase, but not continuity of an unresolved request.

This follow-up retains submitted **initial purchase reviews** in this tab's
`sessionStorage`, under the signed-in user's stable ID and canonical restaurant
ID. It saves and reads back the record **before sending the first POST**. The
record contains the exact reviewed body/key, source/version identities and
selected original display fields. It excludes authentication credentials,
source-file contents and arbitrary server metadata. Values retain their original
types and decimal strings. A retry cannot overwrite a retained body or key.

## Restoration and reconciliation

Invoice Master lists this user's unresolved submitted reviews. **Restore
submitted review** reads the original version's saved status through the existing
authenticated GET. Reopening its retained file also reconciles the returned
version/key against the original command. Neither action submits a purchase.

| Fresh result | Result in the restored review |
| --- | --- |
| Own original version/key saved | Confirm the saved purchase and remove its local recovery record. |
| Own original version/key saved and later corrected | Confirm the original outcome and expose existing correction-history review; remove its local recovery record. |
| Still awaiting review | Preserve the original frozen fields and enable only an explicit retry with the original body/key. |
| Held, or posted by another request/version | Retain the original review and record; block another initial post. |
| Read failed, unauthorized, timed out or malformed | Keep the record and frozen review; require another successful check before retry. |

All write commands continue through the existing server validation, authority
and idempotency checks. Browser persistence is recovery evidence, not authority
or a transaction guarantee. Records are cleared after a matching saved outcome
or an explicitly confirmed discard, never by sign-out, an unsuccessful read or
an automatic age cutoff.

**Discard retained review** first reads the original version's status. Only a
validated held, awaiting-review or competing-request result opens confirmation.
Own saved/corrected outcomes refuse discard and direct the user to restore.
Confirmation explains that removing this tab's review **does not cancel the
earlier request** or delete source, purchase or history. Keeping the review makes
no change. Confirmation fetches the source and reads status again before
clearing the exact original version/key; failed or contradictory reads, foreign
identities, storage failure or a user/location change preserve the record.

The October 13 live test found that PR23 reopened the original file when a newer
revision was captured in a separate file. It stayed held and created no purchase,
but did not reopen the latest revision. The local
[current-source follow-up](LATEST_SOURCE_RECOVERY.md) corrects that read path;
its deployed acceptance remains pending.

Reopening uses current server fields and requires a new explicit review, rather
than unfreezing the old submitted body. An already posted document exposes its
saved purchase/correction path. A still-held document remains blocked until its
source issue is resolved, sometimes by reviewing a newer source version.
No discard action creates a posting or correction.

An awaiting-review read only establishes that no batch was visible then. An
earlier command may commit later. Before posting a revised review in this
workspace, the client checks again; a newly visible batch or hold blocks that
POST and opens the current document. A conflict after that check triggers a
status read, retains the revised command and blocks retry for a competing batch.
The server still locks the document identity, rechecks the command and permits
one initial batch per document. These checks prevent a duplicate but do not
guarantee which request wins. Correcting an already saved purchase remains a
separate explicit workflow.

Unavailable, corrupt, oversized or full recovery storage blocks initial posting
rather than silently dropping a record or creating a replacement key. Storage
has a 32-record and 2 MiB envelope limit per user/restaurant. A confirmed purchase
whose local-record cleanup fails remains confirmed; further initial posting is
held until recovery storage can be read and retained safely. The 32-record,
2 MiB, invalid-record and unavailable-browser-storage errors have distinct
messages. Discard targets the exact original version/key. Reopening independently
reconciles any other retained reviews in that source; unresolved reviews retain
their original frozen commands.

The journal and API share restaurant canonicalization (including
`papa_leonis` to `papa`); syntactically valid new location IDs no longer depend
on a second client allowlist. Server access checks are unchanged. The review
form and journal use the same client base-unit constant.

The App passes the stable user ID into Invoice Master and remounts its workspace
when that user or restaurant changes. Late status/file reads cannot populate the
replacement user's workspace. A late matching acknowledgement may reconcile its
original user's record without exposing that review in the new workspace.

## Local validation and limits

The complete native-feature profile passes **674 frontend tests in 67 suites**,
including 24 additional cases in the PR23 review amendment.
Coverage includes persist-before-send, exact retries after remount, own saved and
corrected receipts, held and competing outcomes, failed restored reads, user and
restaurant isolation, late responses, corrupt/full/unavailable storage, retained
decimal types, source/token exclusion and the actual client expiry/sign-out
functions. Amendment coverage also includes both discard reads, cancellation,
own saved/corrected refusal, held and competing reopening, foreign/malformed or
failed status reads, source/storage failure, preservation of another invoice
in the same file, superseded source versions, late user changes, original-commit
races, explicit capacity messages, new location IDs and manual-captured
initial-post restoration.
The strict `CI=true` production build passes with ESLint enabled, the same
native profile and a fictional backend URL. The initial strict build caught a
lifecycle memo dependency warning; the identity-bearing scope was corrected
without disabling lint, and the affected tests and final full suite passed.
The amended output is `main.2a2c6bf8.js` and remains local.

PR23 was merged at `4f93748` and deployed on the Render frontend. The October 13
live trial passed a pre-forward transport failure, same-tab reload and normal
same-user sign-in, one exact manual retry, a real truncated acknowledgement after
verified commit, and own-saved recovery after another reload. The competing-request
trial passed frozen original fields, blocked retry, cancelled discard and confirmed
discard into the saved-purchase comparison with one initial batch. The newer-source
trial failed to reopen revision 2 across separate captured files and remains held
with zero purchases for that invoice. The prior real acknowledgement-drop
test passed in the full Render parent under controlled fixture-specific browser
routing: **1 of 3,831 response bytes** after independently verified commit; exact
manual retry returned the original batch with no added or updated rows. Its
all-86-relation comparison preserved the original **$212** Food Cost control.
Those earlier transport results retain their original scope. The current-source
follow-up has local regression coverage and still requires separate deployed proof.

This recovery copy is scoped to the current tab and logical user/restaurant
identity; it is not encrypted browser storage or a separate authorization
boundary. Signing out deliberately leaves this tab's notes and quantities in
plain text for the same user's later recovery. Another user cannot see them
through Invoice Master, but someone with browser developer-tool access on a
shared device can read browser storage. Keep the tab open until saved status is
confirmed. Recovery in a new tab, after closing the tab or after browser restart
is not guaranteed. Automatic
expiry/deletion would lose unresolved command identity and is deliberately absent.

Manual source-capture commands, binary source capture and correction submissions
still retain their pending commands in memory; their durable recovery is a separate
step. An initial inventory posting from an already captured manual document uses
this journal and has a capture → posting → remount → exact retry test. No login
policy, credential, server command, schema, migration, hosting or Supabase
connection change is included. Track 1 accounting remains independent
of prep and sales.

## Remaining acceptance

1. Review the local current-source follow-up as a draft PR and its required Inventory CI.
2. Obtain separate merge approval before the automatic Render test deployment.
3. Re-run the newer-source hold and confirmed-discard case using distinct captured
   files. Confirm the reopened revision, source identity and line IDs, an explicit
   new review/key, and exactly one purchase of the latest version. Preserve the
   failed fixture's two captured versions unposted; its local review was already
   discarded. A fresh labelled fixture is needed to recreate that complete
   unresolved-request sequence through normal controls. Do not count manual file
   selection as proof of automatic current-source reopening.
4. Preserve all existing fixtures and the closed **$212** control; finish with an
   independent complete database comparison. Concurrent first posting,
   independent employee authority and reviewed fictional-data cleanup remain
   separate. Broad UI, Toast and connection architecture remain later workflows.
