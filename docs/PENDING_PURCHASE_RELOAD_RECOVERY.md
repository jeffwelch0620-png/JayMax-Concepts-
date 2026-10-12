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
or a transaction guarantee. Records are cleared only after a matching saved
outcome, never by sign-out, an unsuccessful read or an automatic age cutoff.

Unavailable, corrupt, oversized or full recovery storage blocks initial posting
rather than silently dropping a record or creating a replacement key. Storage
has a 32-record and 2 MiB envelope limit per user/restaurant. A confirmed purchase
whose local-record cleanup fails remains confirmed; further initial posting is
held until recovery storage can be read and retained safely.

The App passes the stable user ID into Invoice Master and remounts its workspace
when that user or restaurant changes. Late status/file reads cannot populate the
replacement user's workspace. A late matching acknowledgement may reconcile its
original user's record without exposing that review in the new workspace.

## Local validation and limits

The complete native-feature profile passes **650 frontend tests in 67 suites**.
Coverage includes persist-before-send, exact retries after remount, own saved and
corrected receipts, held and competing outcomes, failed restored reads, user and
restaurant isolation, late responses, corrupt/full/unavailable storage, retained
decimal types, source/token exclusion and the actual client expiry/sign-out
functions. The strict `CI=true` production build passes with ESLint enabled, the same
native profile and a fictional backend URL. The initial strict build caught a
lifecycle memo dependency warning; the identity-bearing scope was corrected
without disabling lint, and the affected tests and final full suite passed.
The output is `main.704b31e2.js` and remains local.

This implementation is prepared locally from main `cd29f22`. It is not a deployed
reload or session-expiry acceptance result. The prior real acknowledgement-drop
test passed in the full Render parent under controlled fixture-specific browser
routing: **1 of 3,831 response bytes** after independently verified commit; exact
manual retry returned the original batch with no added or updated rows. Its
all-86-relation comparison preserved the original **$212** Food Cost control.
Those transport results apply to the deployed baseline, not this new local code.

This recovery copy is scoped to the current tab and logical user/restaurant
identity; it is not encrypted browser storage or a separate authorization
boundary. Keep the tab open until saved status is confirmed. Recovery in a new
tab, after closing the tab or after browser restart is not guaranteed. Automatic
expiry/deletion would lose unresolved command identity and is deliberately absent.

Manual source entry, binary source capture and correction submissions still
retain their pending commands in memory; their durable recovery is a separate
step. No login policy, credential, server command, schema, migration, hosting or
Supabase connection change is included. Track 1 accounting remains independent
of prep and sales.

## Next acceptance

1. Review this local follow-up as a draft PR and its required Inventory CI.
2. Obtain separate merge approval before the automatic Render test deployment.
3. Rehearse a labelled fictional unresolved **initial purchase** across reload
   and normal same-user reauthentication. Confirm the original key/body, fresh
   reads, no automatic POST, exact manual retry and one committed purchase.
4. Preserve all existing fixtures and the closed **$212** control; finish with an
   independent complete database comparison. Concurrent first posting,
   independent employee authority and reviewed fictional-data cleanup remain
   separate. Broad UI, Toast and connection architecture remain later workflows.
