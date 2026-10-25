# Manager production handoff note: local implementation

October 25, 2026. Owner-approved local implementation on the accepted PR71 baseline
`a67aa375`, with Companion PR72 `b73a80d` used as the source reference. Inventory
Build Main remains the sole coordinator. This is the first persistent receiving
operations slice, not completion of the Companion merge or scheduling adoption.

## Result and boundaries

One shared note per restaurant/business date/prep track. Current personal managers
of that restaurant and owners can save drafts, submit the saved draft, correct a
submitted note with a reason, and read immutable history. The selected starting
fixture is **TEST ONLY Bert's / October 25, 2026 / Bulk Prep**. Earlier submitted
notes are found across missing days; later drafts do not imply readiness and are
not the previous submitted note. Corrections remain visible as currently recorded,
not an as-known-at-the-time reconstruction.

The summary and next-shift text are reports. No action transfers responsibility,
accepts a named receiver, resolves a task, completes prep, sends notifications or
writes stock. Track 1 accounting, purchases, counts, prep and sales commands remain
separate. Existing dashboards, Prep and the Operations archive remain available.
Named handoffs need actual dated leadership/recipient mappings in a later slice.

## Receiving surface

- `ManagerHandoffTab` is reached from its own manager tab or the dated Manager
  overview link. Explicit navigation carries restaurant/date/track; manual tab or
  restaurant/session changes clear that navigation focus. It can load independently
  of legacy aggregate state. The overview itself gains no new automatic GETs.
- `GET /api/pg/operations/{store}/handoff-notes/days/{day}?track=bulk` returns the
  current note, previous submitted note and reviewed timezone/settings revision.
- `GET .../notes/{note_id}/history?after=0` returns at most 50 immutable revisions,
  the current revision and an explicit continuation cursor. Changed snapshot
  revisions cannot be combined into a claimed complete history.
- `POST .../commands` accepts `create_draft`, `save_draft`, `submit` or `correct`,
  with `If-Match` and `Idempotency-Key`. Optimistic revision checks plus a
  store-scoped transaction lock prevent competing creates and lost updates.
- `POST .../status` is read-only. It returns a matching receipt with its accepted
  revision and current note, or `unconfirmed`. A negative snapshot is not proof
  that an original in-flight write cannot still commit.

Summary/next note/reason limits are 6,000/4,000/2,000 Unicode code points. Invalid
Unicode, NUL, extra body fields, invalid dates and unsafe revisions are refused.
Browser/backend normalization and SHA-256 request identities agree. Errors do not
echo malformed note inputs or database diagnostics.

## Authority and storage

Every route checks a signed personal subject against the current `public.app_users`
ID, role and location list through the separate auxiliary account pool. Token role,
email, claimed roster selection, shared PIN and identity headers cannot grant this
surface. Disabled development authentication does not bypass its signing/account
checks. Deleted/downgraded/moved accounts cannot read or replay receipts. This is
current authority at dispatch, not global session revocation or instant removal of
already-read information. Existing middleware may require normal personal
re-login before newly granted roles/locations can be used; it is not bypassed here.

`20261025_manager_handoff_notes.sql` creates only `operations.store_settings`,
`handoff_notes`, `handoff_note_revisions` and `handoff_command_receipts`, with
immutable-context/append-only guards, scoped FKs, RLS and revoked public/client
access. It seeds no timezone, account or note, and grants no runtime access.
The generated `supabase/manager_handoff.schema.sql` is a fictional structure
reference, not an installer or grant proof. Its companion manifest binds source,
structure and the proposed per-object privilege matrix.

The operational fixture role can SELECT settings, SELECT/INSERT/UPDATE note
projections, and SELECT/INSERT revisions/receipts. It cannot delete evidence or
rewrite history. Applicable RLS and the existing visible-store reader are required.
The auxiliary fixture reads only account ID/role/locations for this adapter and has
no operational schema access. Browser roles receive none. The real auxiliary login
retains its existing login/notification duties; no real privilege is reduced here.
Trigger functions are invoker functions, not security-definer wrappers.

The new extension does not join `deployment_readiness.MIGRATIONS` or rewrite the
sealed 31-file reviewed-par packet. Apply-order documentation lists it separately.
`manager_handoff_schema.configuration` reviews its feature pair independently.
`runtime_permissions.catalog_contracts(..., schemas=('operations',))` captures its
reference explicitly; the default historical namespace set/profile is unchanged.
Auxiliary permission inspection adds the new namespace to its denial checks.

Both `MANAGER_HANDOFF_NOTES_ENABLED` and `REACT_APP_MANAGER_HANDOFF_NOTES` default
off. The fictional CI profile enables the browser flag for tests only. Missing
storage, disabled guards, missing/invalid timezone or inactive store holds the
feature. Business-day validation uses the reviewed store timezone; saved note
context preserves its original timezone/revision. No UTC/browser fallback is used.
The runtime cannot UPDATE settings. Any future settings writer must coordinate
with the same store advisory lock or a drained maintenance window; this module
provides no configuration-writing route.

## Personal-browser recovery

Unsent edits stay in the App draft map by person/store/date/track. Before a command
is sent, its exact body, UUID key, expected revision and hash must be readably saved
in actor/store-scoped sessionStorage. Blocked/full/corrupt storage prevents a POST.
Uncertain requests freeze editing and offer explicit status, exact retry or discard.
There is no automatic retry, new key or optimistic success. Mutation/status
transports have a 60-second timeout; GETs use the existing cancellable read budget.
An acknowledged older command displays the returned newer current version rather
than rolling it back. Acknowledgement is fenced to the still-active account/form.

Reload and same-account sign-in can recover the original request. Retained text
and editing wait for a successful current authorized day read; a refused read hides
the form and text. A status receipt may clear recovery even if the day read is
unavailable, but cannot invent missing settings or open a new editor. Discard only
removes browser recovery and forces a fresh read; it does not undo a committed note.
SessionStorage is not encryption or a shared-device confidentiality boundary.
The approved personal-manager browser convention is not employee/shared-tablet
rollout policy; retention, shared-device erasure and wider identity work remain open.

## Validation receipts

Serial local receipts are retained outside the checkout in the owned
`manager-handoff-local-20261025` evidence directory. Local tests do not establish CI, deployment,
live timezone configuration, actual role grants or hosted acceptance.

- Final disposable PostgreSQL selection: **10/10 methods passed**, including
  shared editing, submission/correction history, earlier-note lookup, same-key
  before/after-commit status/replay, competing creates/edits, current-account
  revocation, malformed fields, missing schema/guards/timezone, role allow/deny,
  manifest/catalog equality and real fictional dump/restore with original-key
  replay. The owned server was stopped and verified after each run.
- Final full frontend selection: **1,188/1,188 tests in 92 suites passed**.
  The strict CI-mode production build compiled successfully after the handler
  rename. Its test-profile bundle is not a deployed or production-approved build.
- Complete broad offline selection: **1,953 reported cases; 1,947 passed and six
  failed on the local Uvicorn-version assertion** (0.54 loaded instead of the
  repository-pinned 0.25). The corrected focused rerun used the cached pinned
  dependency and passed **155 reported cases (49 tests + 106 subtests)**,
  including all six proxy cases, the latest note authority/version checks,
  frozen-par packet and runtime-profile checks. Selections overlap; do not add
  these totals or call the original broad run wholly green. Merging XML results
  by parent test key leaves no unresolved failed parent cases.
- Earlier focused frontend/navigation selection: **43/43 passed**. These overlap
  the later full frontend run and are not additional independent cases.
- Generated guides match their source. The sealed native/par source pins,
  proposal and `deployment_readiness.py` remain byte-equivalent to their accepted
  versions after newline normalization. Historical SQL files were not rewritten.
  The new SQL/reference/manifest have explicit LF attributes so their raw-byte
  hashes survive Windows and Linux checkouts; prior byte rules are preserved.

Corrections and limits: an initial expected-digest typo was corrected and the
canonical Unicode vector now agrees between browser and Python. The first local
database run lacked timezone data in its test-library path; the already-declared
dependency was loaded from the bundled runtime. The role fixture initially needed
its explicit visible-store RLS policy. More importantly, a settings `FOR SHARE`
lock required UPDATE privileges, so the implementation removed that lock rather
than widen the approved SELECT-only matrix. A malformed-Unicode HTTP test was
changed to send escaped JSON so it reaches the API instead of failing in the test
client encoder. A transient broad run started during installer isolation was
stopped and superseded by the complete broad/focused receipts above. The first
strict build flagged a plain `useCurrent` handler as a Hook; it was renamed.
These initial failures are retained in evidence, not counted as passes.

The UI checks are automated component/App tests. No manual browser layout or
hosted transport/deployment acceptance is claimed. The raw fictional dump/restore
checks this journal's persistence; it is not a new operational encrypted-backup
or hosted recovery rehearsal.

## Next gates

1. Finish local validation, source review and JMax readback; prompt before draft push.
2. Independent review and fresh CI; come back for merge/automatic test deployment
   approval. No merge approval is inferred from this implementation request.
3. Prepare a separate exact hosted installation/permission/configuration and
   fictional acceptance plan. Prompt before any hosted work or real credential,
   grant or schema change. Existing holds remain in place.
4. Continue the selective operations/scheduling receiving map and resolve actual
   responsibility/leadership identities before named handoff acceptance. Optional
   S1 harness investigation remains separate from this integration milestone.
