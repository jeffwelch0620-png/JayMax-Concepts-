# Submitted par save/reload recovery

## Scope and authority

Local follow-up to accepted PR51 `07daa29` and the
[October 21 readiness review](REVIEWED_PAR_READINESS_20261021.md). The owner
authorized a bounded recovery implementation and local testing, with a prompt
before any draft PR push. **Hosted work, credentials, grants and schema changes
remain on hold.** No migration, hosted connection, credential file or permission
candidate is changed. Existing fictional test fixtures use only disposable local
databases; application and hosted schemas are untouched.

This slice retains submitted confirm/withdraw requests. Ordinary unsubmitted
typing remains in the existing signed-in draft cache. It does not add cross-tab,
closed-tab, browser-restart or cross-device recovery, offline posting, automatic
retry, automatic ordering or accounting writes. The accepted hosted par-editing
freeze remains until separate installation and live acceptance.

## Retention before sending

`pendingPars.js` uses a versioned `sessionStorage` journal scoped to the stable
signed-in actor and canonical restaurant. Each product has at most one retained
request, with a unique UUID key, original expected revision, exact body, and the
selected physical profile or withdrawal predecessor snapshot. Decimal strings
are not converted through Number for storage or request replay. Withdrawal
acknowledgement verifies predecessor identity, quantities, conversion and units.

Only explicit display/evidence fields are retained. Tokens, passwords, raw files
and arbitrary metadata are excluded. The journal has a 32-request / 128 KiB
limit and validates exact keys, identities and bounds on read/write/clear.
Writing includes immediate readback before the initial PUT. Storage failure,
quota refusal or invalid records block a new write without silently deleting
the old evidence. Cleanup matches the complete retained record.

Reload and same-account sign-in in the same tab can reconstruct the recovery
cards without the old App draft Map. Other users/locations do not receive those
records, and old asynchronous responses cannot acknowledge the current scope.
Sign-out guidance distinguishes unsent drafts from submitted recovery evidence.
Retained browser data is evidence, never authority: all requests use normal
personal authentication and location/manager checks.

## Read-only saved-status contract

The new authenticated `POST /api/pg/purchases/{store}/inventory-pars/{item}/status`
accepts the exact retained body, `If-Match` expected revision and
`Idempotency-Key`. It requires normal write-level manager/owner authorization
but executes only a bounded, repeatable-read, read-only transaction. It does not
call the store-lock helper, which can insert a store-state row.

The status reader and PUT share request fingerprint construction and new-review
validation. The existing writer still owns its original transaction, locks,
idempotency check, expected revision, conversions and immutable history guards.
Status checks do not bypass or replace any command-time authority check.

| Outcome | Meaning / control |
| --- | --- |
| `saved_current` | Exact actor/store/item/body/revision/key fingerprint matches a saved review, which is still current. Resolve only that retained request. |
| `saved_superseded` | The exact request saved, and a later review is current. Show the later-review notice and refresh current state; never resubmit the old target as a new review. |
| `retry_available` | No saved key was visible and the exact retained command passes the snapshot's current validation. Offer an explicit retry with the same body/key/revision. This does not assert cancellation or prevent the original from completing later. |
| `not_saved_superseded` | The key is absent and the immutable current revision is greater than the retained expected revision. The old expected revision can no longer append. An explicit compare/review action checks status again and refreshes the current head before returning retained values to an unconfirmed draft. |
| `held` | Key/actor/body mismatch, storage unavailability, changed conversion, inactive/invalid item or other validation hold. Keep the record. Do not expose another request's record, generate a replacement key or offer an unknown-outcome discard. |

An exact saved-key lookup precedes mutable profile eligibility: a later profile
change does not make the original committed review disappear. Response validation
checks the actor, store, product, expected revision and request key, original save
receipt, current immutable identity and declared outcome. Contradictory evidence
holds. Authentication failures, 4xx/5xx responses, timeouts and malformed results
never erase the unresolved journal simply because of an HTTP status category.

## UI flow and recovery

1. Verify the journal and current form, persist/read back the frozen request, then
   send the initial save. Concurrent clicks share an immediate sending guard.
2. Reload/sign-in shows retained cards. It never sends a PUT or status request
   automatically. Use **Check saved par status** to inspect one exact request.
3. **Retry same par review** is enabled only after `retry_available`, and performs
   another fresh status check on click. A late commit discovered then resolves
   the saved result without another PUT. Otherwise only the original command is
   sent; the writer rechecks its guards.
4. For an absent, revision-fenced request, **Review current par and retained
   values** rechecks and reads the current head before releasing the record.
   Preserve quantity/unit/note for explicit comparison; confirmation resets and
   the next command needs a new human review. Held/unknown requests cannot use
   this path. Closing a view does not cancel a server request.
5. A verified save remains saved if journal cleanup, par readback or catalog
   refresh fails. Cleanup failure blocks new commands; a later status check can
   resolve the same evidence. Read failures are reported as refresh problems,
   never used to manufacture another review or repeat a confirmed write.

The par form is paused while its location has retained requests or recovery
storage is unavailable. Other application workflows and manual ordering retain
their existing contracts. Unknown supplier prices, physical count units and
explicit-zero rules are unchanged.

## Local validation and separate gates

The selected and full frontend runs cover journal validation, exact decimals,
write-before-send/readback, reload with a fresh draft cache, authentication/HTTP
refusals, account/location changes, exact retry and delayed commit, later reviews,
withdrawal, invalid proof, corruption/quota refusal, and confirmed-save cleanup
failure. Disposable PostgreSQL checks cover the actual read-only transaction,
shared validation, original-key replay, revision fencing, identity/profile holds,
withdrawal and authorization, plus unchanged fictional Food Cost and existing
history/backup coverage. New database methods are included in the CI selection.

Final local evidence (October 21 Eastern / October 22 UTC):

| Check | Result | Evidence prefix outside Git |
| --- | --- | --- |
| Full frontend, native feature profile | **1,062/1,062 tests, 83 suites**, no failures/skips | `par-recovery-front-all-20261022T012213191995Z` |
| Final strict CI/ESLint production build | **Passed**, `main.7a97b966.js` | `par-recovery-build-20261022T012309283490Z` |
| Broad offline backend | **1,180/1,180 reported cases**: 420 methods plus 760 subtests, including both Windows permission checks | `par-recovery-offline-20261022T011649068119Z` |
| Disposable PostgreSQL 17 | **28/28 reported cases**: 16 methods plus 12 subtests, including real status authorization/read-only checks and unchanged accounting | `par-recovery-database-20261022T011806260115Z` |

Earlier focused/full selections overlap these totals and are not additional
unique coverage. The initial strict build found unnecessary hook dependencies;
the scope object was corrected and the strict rerun passed without suppressing
warnings. The final compatibility check preserves nonblank catalog codes up to
200 characters, including Unicode and spaces. Existing dependency deprecation
notices remain outside the strict compiler. The database receipt verifies the
original database/role inventory restored and the owned server stopped, with
fictional fixtures only and no hosted access.

Local fixture results are not hosted acceptance. Fresh CI, independent review,
merge approval, any automatic Render
deployment consequence, hosted schema installation and live acceptance remain
separate gates. O1 restricted-role ACL/RLS work and G04 acceptance stay open.
Track 1 actual accounting remains independent of these planning targets.
