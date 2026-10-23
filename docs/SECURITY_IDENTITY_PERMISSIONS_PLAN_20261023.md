# Coordinated security, identity and permissions plan — October 23, 2026

**Local planning only. No live action, account/grant/credential change, migration,
provider operation, deployment or message to coworkers has been performed.**
Inventory Build Main owns the queue; Companion is the source/history reference
and may receive only an explicitly assigned bounded task. One implementation
owner and one stock writer per slice; no parallel duplicate fixes.

For planning review, Jeff coordinates database/infrastructure and approval
packets; Rudd reviews identity/Operations integration; Jay reviews scheduling,
jobs/dayparts and staff experience. These follow the existing domain split and
do not appoint an identity reviewer, owner, administrator or recovery trustee.
Confirm the actual people and availability before any cross-person approval.
No separate chat is required for routine coordination; bounded specialist work
can be assigned explicitly without creating a second competing implementation.

## Baselines, completed work and actual remaining dependencies

Inventory: accepted PR59 `c3b429a2da8d1880ecdbcf34ccb5b28033978c6c`, tree
`52c3b07b494344fe8b09c270a9392576526b57ef`, separately green reviewed-head and
merged-main CI. Today's health and read-only calibration passed; neither is
personal-login, deployed security or operational acceptance.

Companion planning source: PR72 `b73a80d63adde989babee3c75c198e3148bf6ce9`.
Its source-only identity mapping originally used Inventory PR49 `6f1774a` paired
with Companion PR71 `104d8cd`. Local comparison to current accepted Inventory
finds changes in `backend/server.py`, `backend/staff_pin_security.py`,
`frontend/src/App.js` and `frontend/src/components/StaffSheet.js`; the referenced
public schema/migration files are unchanged across that comparison. The current
PIN/session fixes must replace the old review's unsafe-path description, while
its deployed acceptance, source-to-installed reconciliation and identity gaps
remain open. Do not repeat the old implementation or reintroduce session minting.

The earlier build-variable cleanup and its limits remain dated evidence.
Current key presence, consumers and deployment require the separately approved
S1 check. S2a's scope, affected credential and supporting evidence belong in the
owner-held record; public progress text carries package-level status only.
No secret values or private record addresses belong in this repository.

The calibration used a separate maintenance path and does not establish the
running API's current actor or consumer bindings. Keep those actual bindings in
the owner-held S1 record. The 30-migration runtime candidate excludes the par
table; that remains an O1 design input, not a new par-installer prerequisite.

## Approval packages and sequence

| Package | Concrete work | Ready for live approval? |
| --- | --- | --- |
| **S1 — security acceptance and current configuration inventory** | Bounded Inventory app checks, private evidence review and metadata-only deployment/role inventory below; no credential/grant/schema edits. | **Yes: exact bounded scope below.** A fresh execution start/deadline and user-handled personal sign-ins are still required. |
| **P1/P2/P3 — par rollout** | See the companion par proposal: new 60-minute window, fresh backup/restore/qualification; separate exact-hash DDL approval; later labelled acceptance. | P1 is reviewable. P2 needs its freshly generated executable plan. P3 needs exact fixture identities/baseline. |
| **R1 — restricted runtime candidate** | Locally reconcile the complete per-object inventory and auxiliary account candidates, add par dependencies, meaningful allow/deny tests and code review. | **No live grants/cutover yet.** Final SQL, actual role names, installed-object matrix and recovery evidence are required. |
| **S2a — targeted credential retirement** | Prepare after S1 consumer inventory, independently of R1 and outside P1. Scope, affected credential and evidence are held in the owner record. | **Not ready / not approved.** Exact consumers, pooler/old-login proof, recovery operator and separate window need a reviewed packet and owner decision. |
| **S2 — restricted connection cutover** | After R1, stage limited inventory/account connections, validate both bindings and retire superseded app credentials. | **Not ready / not approved.** Reviewed role/grant artifacts and consumer/recovery evidence remain required. |
| **I1 — first shared identity/feature slice** | Reconcile canonical identities privately, implement verified server actor resolution and port one integrated workflow. | **No shared DDL/account linking/provider cutover yet.** Decisions, local implementation, exact migration/row set and tests are required. |

Recommended sequence: amend/review these documents, separately approve S1,
then review a targeted S2a packet before the fresh P1/P2/P3 par sequence. This is
a recommendation, not approval or an automatic new installer gate. R1 and I1
local design can progress alongside it. Assess S2a priority from the owner-held
record rather than making its preparation wait for the full R1 redesign. Do not
combine credential rotation, PIN policy changes, grants or identity cutover into
the par window. R1's final policies must match the installed schema. No new PR is published without the requested push
prompt, and merge/automatic deployment remain separately approved.

## S1: exact proposed live scope — 15-minute bounded verification

Targets: existing Inventory build frontend `https://jaymax-concepts.onrender.com`
and API `https://jaymax-api.onrender.com`; only their known Render service pair
and the designated existing Supabase build project for metadata. Companion's
public entry points/ingress are not silently included.

### Prerequisites and access

- Owner handles normal personal authentication; no password/PIN/token is pasted
  in chat or exposed in a tool transcript. Use existing authorized accounts only.
- Privately select Bert's existing active roster entry, configured PIN and any
  already-existing owner/manager/staff personal test accounts. These identifiers
  are bound in the private execution checklist before requests. If a required
  account, owner_admin roster entry or PIN is absent, record the affected test as
  not evaluated; do not create/change it to make the test pass.
- Capture the deployed API/frontend commit and `AUTH_REQUIRED`/PostgreSQL/native
  feature configuration without displaying secret values. A changed source or
  unexpected target holds for comparison rather than automatic redeployment.
- Explicitly accept a short Bert's shared-PIN lockout during the rate-limit case.
  Personal manager/owner login is independent. No business-form submission occurs.

### Request budget and expected results

Use at most **18 programmatic application requests**, at most **six public
frontend-asset reads**, and at most **three normal human-handled personal sign-in
attempts**; no automatic retry or password guessing. Use only the exact existing
routes; missing actor/fixture prerequisites reduce the executed count and remain
unverified. Ordinary middleware audit entries and the temporary limiter counter
can change; no business/account/role records are intentionally modified.

Run PIN checks in isolated anonymous contexts with no Authorization header,
cookie or stored personal session; otherwise a signed-in actor could legitimately
bypass the PIN check and invalidate the limiter test. Personal-role checks use
separate authenticated contexts. Respect browser/security restrictions; if read-
only Render access is unavailable, request owner-supplied masked evidence and
label it as owner-reported, or return the affected check as unverified.

Twelve-request PIN/security sequence, using `/api/pg/staff/berts/verify` and
`/api/pg/staff/berts/identify`, outside any maintenance window:

1. After a clean limiter interval, valid configured PIN verify succeeds once.
2. Identify the privately selected active owner_admin roster entry once: response
   contains only `ok`, `name`, `role`; no token, authorization upgrade or stored
   manager session. The roster label is not verified personal identity.
3. Make five deliberately incorrect PIN requests across verify/identify. Derive
   the wrong value privately so it is guaranteed different; never guess a real PIN.
4. One further wrong request carries a deliberately different synthetic
   `X-Forwarded-For` value from steps 1–3 and returns 429 with bounded Retry-After.
   This re-tests the original changed-header G04 case within the same budget.
   Record proxy/header rewriting limits; a stripped header is not proof of every
   possible address-attribution path. Never use a real person's address.
5. One correct-PIN request is also temporarily blocked, consistent with the
   owner-selected store-wide budget; do not change limiter policy to hide this.
6. After the supplied interval expires, correct verify and tokenless identify
   succeed again (two requests). If deployment/instance/storage replacement or
   limiter state loss occurs between steps 5 and 6, record "restart observed" or
   "limiter state continuity unverified"; do not count this as expiry evidence.
   A process restart alone does not prove the SQLite file was lost.
7. One unauthenticated `GET /api/auth/users` is denied: no manager authority came
   from the PIN identity claim. This completes at most twelve requests.

Execution notes: the first request has a **90-second total client timeout**
to allow a possible cold start; no retry. Subsequent requests have bounded client
timeouts within the 15-minute overall deadline. No request is started if its
budget cannot fit. Capture deployment continuity from the already approved
metadata observations, without adding restart/provider requests. A security
failure or ambiguous request stops the sequence; counts are maxima, not a duty
to keep sending requests after a stop.

Six additional read-only role checks: `GET /api/auth/me` and
`GET /api/auth/users` under each existing owner, manager and staff personal
account. Confirm personal identity/store scope; owner-only user listing must
deny manager/staff. Minimize private user-directory output; publish only test
dispositions and counts. A missing personal account remains a named gap.

If Bert's PIN is unconfigured, verify disabled behavior only and leave valid-PIN
cases unevaluated. **No PIN is set or rotated in S1.** Revocation-after-role-change
and new shared-session lifecycle require later local/I1 work; S1 does not mutate
accounts or claim those tests passed.

The request budget tests the supported PostgreSQL path. Local tests cover the
retained legacy identify/verify implementations and old synthetic-token refusal.
If deployed routing exposes additional legacy entry points, document their
reachability and return a separately bounded acceptance extension; do not silently
add live requests or declare untested paths accepted. G04 closure is per evidence
item, not an automatic consequence of this checklist or a successful personal login.

### Metadata, prior activity and secrets inventory

- Read only current deployment commit, environment-key presence, flags, TLS route
  and configured primary/auxiliary database role/host/port. Re-mask all values;
  never display passwords, full DSNs, AUTH_SECRET, provider/vendor keys or cookies.
- At most **two dedicated read-only database connections, 120 seconds combined
  connected work**, for relevant catalog/role/grant/RLS/ledger metadata and the
  bounded minimized audit read below. No SET ROLE, DDL/DML, membership changes,
  backend termination or broad employee export.
- Privately review at most **200 existing manager/owner audit records** from
  **covering the period identified in the owner-held record**, through the
  approved check. Use minimized time/actor/action/status fields, without
  request bodies or credentials, inside the same connection/time budget. Record
  actual earliest/latest retained evidence, row cap, ordering and any uncovered
  required review interval. A capped sample is not an exhaustive investigation; missing
  older provider/database logs remain an explicit gap, not evidence of no misuse.
  No evidence deletion, retention change or incident-resolution claim is included.
- `public.activity_log` covers authenticated requests that reach its middleware
  hook; login/bootstrap, anonymous PIN requests and early authorization denials
  are not a complete part of that trail. Logging errors are caught after route
  execution. It is **not evidence about direct database sessions**, and an HTTP
  success does not prove an audit row exists. Direct-session/provider evidence
  needs separately accessible retained records; S1 does not enable new logging.
- Recheck presence/consumer ownership of the eight previously removed frontend
  variables: ANTHROPIC_API_KEY, AUTH_REQUIRED, AUTH_SECRET, BOOTSTRAP_TOKEN,
  DATABASE_URL, EMAIL_FROM_ADDRESS, PUBLIC_APP_URL, RESEND_API_KEY. Presence alone
  does not prove publication. No Save, Deploy, key deletion or rotation in S1.
- Inventory actual consumers for primary DB, auxiliary account DB, maintenance,
  Toast jobs/HTTP/RPC paths, signing/bootstrap secrets and vendor integrations.
  Do not call Toast replay, AI, email, supplier-order or other external side-effect
  endpoints as a credential test. Do not contact coworkers/providers automatically.

Stop at the first unexpected security result, unavailable personal access,
target/source drift or deadline; retain minimized evidence. S1 makes no repair.
Return a per-test pass/failed/not-evaluated matrix and an exact follow-up change
list. Cleanup browser test state, sign out only test sessions as approved and
let the limiter expire; no counter/database deletion or token-key rotation.

## R1: exact local permission design and future live delta boundary

Retain separate trusted server-only inventory and account connections. Neither
role owns objects, bypasses RLS, creates roles/databases, delegates privileges or
can write the migration ledger. Actual role identities must come from S1; no role
is invented, provisioned or disabled by this document.

| Area | Required proposed rights / boundary |
| --- | --- |
| Native inventory workflows | Retain only the reviewed per-object SELECT/INSERT and narrowly justified UPDATE/locking privileges, SELECT-only views and safe invoker function execution. Reconcile all trigger/sequence/catalog dependencies. Never replace the matrix with schema-wide ALL grants or security-definer wrappers. |
| New `purchasing.inventory_par_versions` | Explicit SELECT and INSERT for the intended trusted inventory role plus role-addressed RLS. No UPDATE, DELETE, TRUNCATE, ownership, grant option or browser role access. |
| Par trigger dependencies | Preserve required reads of `purchasing.unit_profiles` and `purchasing.item_bases`, `public.store_state` SELECT/INSERT/UPDATE, and existing catalog SHARE-lock ACLs. Do not remove locks or immutable-fact triggers to make permissions pass. |
| Primary activity log | Required INSERT to `public.activity_log` with explicit role-addressed INSERT policy where RLS is enabled. Existing candidate also requires SELECT; no product read route was found in this source review, so justify or remove it only in the separate R1 manifest/test change. No new right is granted here. |
| Account/notification connection | Explicit candidate access to `public.app_users` and `public.push_subscriptions` only, using reviewed SELECT/INSERT/UPDATE/DELETE policies and existing owner route authorization. No private inventory/accounting schema access, object ownership, ledger writes or browser exposure. |
| Browser/Data API | Deny direct private stock/purchasing/par access. No anon/authenticated grant as an identity workaround; retain server authorization and actual allowed/denied route tests. |
| Administrative connection | Remains separate for migration/recovery; no normal frontend or app request receives its credential. |

`db_auxiliary.pool()` falls back to the primary pool when its dedicated URL is
unset. **A limited primary-role cutover must therefore explicitly bind and test
`AUXILIARY_DATABASE_URL` alongside `DATABASE_URL`.** Otherwise personal login
and account routes could lose required access. Keep the existing pooler route
and TLS; no paid IPv4 add-on or hosting move is proposed.

The [non-executable permission delta](RUNTIME_PERMISSION_DELTA_PROPOSAL_20261023.json)
records dependency RLS and SHARE-lock decisions; it is not grant SQL. Source
expects purchasing.unit_profiles and purchasing.item_bases without RLS, and
public.store_state/public.activity_log with RLS. Actual installed flags, force-RLS
and applicable policies remain unverified until a separately approved read.
Do not create policies on RLS-disabled dependencies and claim they enforce access.
Test dependency SQL grants in all cases and policy removal only where RLS is
enabled and the caller actually reads/writes the table. Foreign-key integrity
checks bypass RLS; they are not a substitute for testing invoker reads.

For the six runtime SHARE-locked catalog tables (items, store_items, dishes,
dish_lines, prep_items, staff_members), preserve the candidate's existing
UPDATE-based lock permission for this design. Actual runtime write rights must
remain justified per table; retained metadata mutation triggers stay enforced.
MAINTAIN is not selected as a blanket substitute: on PostgreSQL 17 it also
permits VACUUM/ANALYZE/REINDEX/CLUSTER/REFRESH and broader lock modes. Par history
keeps MAINTAIN denied. A change to these privileges requires R1 candidate,
validator, catalog/security expectations and allowed/denied tests together.

### Future R1 audit-failure visibility — design only

Before a restricted-role cutover, implement a bounded, saturating in-process
audit-write failure counter (or equivalent monitored alert), surfaced only to an
authenticated authorized operator through readiness/monitoring. Keep anonymous
`/api/health` unchanged. Expose only a boolean/count and process epoch, never
actor IDs, credentials, SQL or request data. A zero count after restart is not
proof that earlier requests were audited; retain explicit reset/epoch context.
The final route/alert contract and tests belong in R1, not this docs-only PR.

Retain startup privilege/policy checks. After the cutover, one controlled
authenticated request must create **exactly one** attributable activity_log row.
The negative local case must make audit-write failure visible even if HTTP
succeeds, and cover restart/reset, bounded cardinality and unauthorized-read
denial. This is not a change to request success/failure policy or a claim that
the indicator already exists.

Required local R1 acceptance specifications (not tests run in this docs slice):

1. An authenticated allowed request under the restricted primary role succeeds
   and creates exactly one attributable activity_log row. Without INSERT or its
   required RLS policy, prove the write denial, absent row and sanitized logging
   failure. Current middleware catches that error; **do not expect the HTTP
   request to fail** or silently introduce fail-closed logging. Changing that
   product behavior requires a separate design/implementation decision.
   Test startup preflight refusal for a missing required privilege separately
   from the middleware error-handling case. A deliberately isolated local test
   is not authority to bypass the production permission inspector.
2. Par confirm/withdraw/replay pass with caller-rights dependency grants and
   required policies. Remove each applicable grant/policy separately, prove the
   expected refusal and rollback/no history or store-revision drift. Do not
   invent an RLS-policy-removal failure for an RLS-disabled table or FK-only check.
3. Every distinct SHARE-lock route family passes with its selected per-table
   permission and fails cleanly without all privileges capable of that lock.
   Preserve immutability and cross-store/actor denials; test actual write paths
   separately from lock permission.
4. A proposed cutover changing only DATABASE_URL while AUXILIARY_DATABASE_URL is
   unset is detected before activation: the account pool would fall back to the
   primary. Test both actual database actors, same-target checks, independent
   new authentication, login/notification operations, pool restart, explicit-empty
   or invalid auxiliary configuration and refusal without silent fallback.

Local tests must cover purchases/returns/corrections, explicit physical counts
and closures, prep/waste, orders/receiving, supplier data, par confirmation and
withdrawal/replay, shared catalog, personal account/notification routes, cross-
store/actor denials, immutable history and ledger denial, connection reuse and
pool restart. Freeze the final per-object SQL/RLS matrix and source hashes in a
separate reviewed PR. No live grants are approval-ready until those artifacts
and the actual target-role bindings exist.

## S2a: targeted credential retirement — after S1, independent of R1

Scope, affected credential, evidence, consumer bindings, review interval and
priority are held in the owner record. Prepare the exact packet after S1's
consumer inventory, independently of R1 and **outside P1**. Public documents
must not infer or publish a particular credential's security/rotation state.

The owner packet must name actual consumers and configuration targets, supported
pooler behavior, bounded stop conditions, recovery operator and validation that
the replacement works and the retired credential cannot open a **new connection**.
Existing pooled sessions are not that proof. Any pause, restart, provider action
or configuration mutation needs its own concrete approval. Do not rotate other
accounts, PINs or vendor keys by implication.

After an approved change, regenerate affected maintenance configuration and
P1/health/calibration/qualification packets against their new private bindings.
Prior receipts remain dated evidence; they do not authorize another run. If
consumer/recovery prerequisites are incomplete, return the exact gap and
alternative for owner decision. No S2a operation is authorized here.

## S2: restricted-role connection cutover — after reviewed R1

1. Freeze actual role names, reviewed grant/policy artifacts, private consumer
   bindings, supported pooler behavior and approved recovery access.
2. Under a separate exact approval, stage restricted inventory/account credentials
   and prove independent new authentication plus required allowed/denied work.
3. Under its separately approved window, change only the API's approved
   DATABASE_URL and AUXILIARY_DATABASE_URL together; retain current TLS/pooler,
   hosting and flags. Name restart/deployment effects explicitly. Verify personal
   login, core transactions, actor separation and preserved accounting baseline.
4. Retire superseded dedicated app-role logins only after every consumer and new
   pool passes. The separate S2a package is independent, not postponed until here.
5. Rotate signing/bootstrap/vendor secrets only if evidence identifies that exact
   affected key. Signing rotation has explicit reauthentication/recovery effects;
   it does not rewrite account IDs, saved request keys or history.

The live S2 prompt must name exact roles/key labels, SQL/artifact digests,
consumer targets, validation/stop rules, old-login retirement and recovery owner.
No credential value is published. Approving S1, P1 or local R1 work authorizes
none of these changes.

## I1: coordinated identity adoption, selected rules and pending decisions

Preserve the accepted Companion choices: one canonical person UUID; one durable
membership UUID per person/store; extra jobs separate; organization-wide owners;
owner-enabled administrators; multiple explicitly scoped store memberships;
personal sign-in and manager-issued setup first. Registered tablets/personal PIN
enrollment remain later. Source ingestion proposes employment/job data and never
grants sign-in or permissions. Owner additions/removals and independent account-
link review retain the accepted governance contract.

Map legacy types explicitly: Inventory app_users text IDs, people UUIDs,
staff_members roster UUIDs, store_roles composites; Companion D1 instance/member
IDs and local/browser principals; provider issuer/tenant/subject; Toast employee/
job identifiers. Reuse existing people UUIDs only after private reconciliation.
Preserve old actor keys, history, request fingerprints and FK references. No
email/name auto-merge, UUID cast or fictional principal grants real authority.

The live shared port needs these concrete local deliverables before its own
execution proposal:

- Reconcile actual installed source/catalog/ledger and the relevant legacy/D1
  consumer list against the current Inventory delta; retain one Inventory-owned
  ledger. Never concatenate or renumber Companion migrations 001–063.
- Implement one trusted actor resolver returning current person, optional acting
  membership, store/organization scope and separate access/lifecycle fences.
  Shared access changes must participate in a reviewed lock order; retain
  Inventory accounting locks and whole-transaction receipt/retry guarantees.
- Prove ingress strips/injects verified identity at every browser-link/workspace
  entry point and direct-origin path, or replace that assumption with verified
  provider tokens. Do not port caller-supplied oai-authenticated-user-id/email
  trust. Existing Inventory legacy tokens are not automatically new provider
  identities; source verification and current actor authority are separate.
- Recommended provider for feasibility review: Supabase Auth, given the chosen
  authoritative database platform. **Provider adoption remains a proposal.**
  Confirm issuer/audience/key verification, recovery and no-contact onboarding
  support before selection; no provider setting, invitation or password migration
  is executed. **If selected, live Supabase Auth adoption on this project follows
  S2a and the reviewed R1 permissions work.** This does not block local identity
  design or select the provider by implication. Keep existing login until an
  approved, tested replacement cutover.
- Privately prepare the first exact person/store/member alias row set with proof,
  reviewers and expected revisions. A different authorized canonical person must
  review an account link. No reviewer/owner/trustee appointment is inferred.
- Choose only slice-dependent remaining governance: initial verified owner/reviewer
  roster and bootstrap case; person creation/merge/rebind authority; privileged
  authentication/recovery policy. Preserve selected SEC10 M3 option A. Other SEC
  clock, retention, MFA and emergency-custody suggestions remain unselected;
  unrelated leave/employer policies need not block source/local design work.
- Produce the smallest receiving migration and adapter PR, local snapshot/
  concurrency/allow-deny/revocation/replay tests and a private alias reconciliation
  report. Present exact new tables/constraints/policies/functions, row mutations,
  provider operations, sole-writer routing and recovery before live approval.

First vertical slice: shared personal sign-in → restaurant selection → one
schedule draft/save/publish → authoritative Inventory count/prep reads → manager
handoff. Use labelled fixtures before any real employee adoption. Inventory keeps
catalog/item/recipe/unit identities and all food/stock/order effects; Track 1
remains explicit purchased-item count plus receipts minus closing count, with
tax/fees separate. Prep/waste and sales explain it only.

Do not copy Companion's Food stock writers or synthetic review fixtures into
production. Real roster/job/daypart/availability source certification, physical
phone acceptance, notifications, analytics expansion, full UI redesign and
operational release remain separately scoped. Retiring a legacy writer needs
history parity and a tested cutover; no D1/Supabase dual-write or history deletion.

## Sources and approval status

Source-only copies of the four accepted Companion handoff/design documents remain
in the original retained local planning bundle at Companion b73a80d; their byte
digests are carried forward in the documentation validation receipt. This does
not assert that the copies are files beside this new repository document. Current
Inventory code, staff-PIN security packet, O1 matrix and prior recovery records
were read locally; no old readiness text was promoted to a fresh live result.

Provider recommendations use primary guidance: [Supabase JWT verification](https://supabase.com/docs/guides/auth/jwts),
[server-side verified claims/user handling](https://supabase.com/docs/guides/auth/server-side/creating-a-client),
and [RLS/privileged-key boundaries](https://supabase.com/docs/guides/database/postgres/row-level-security).
PostgreSQL 17 documents [lock privileges](https://www.postgresql.org/docs/17/sql-lock.html),
[MAINTAIN](https://www.postgresql.org/docs/17/ddl-priv.html) and
[foreign-key/RLS boundaries](https://www.postgresql.org/docs/17/ddl-rowsecurity.html).
These sources establish capabilities and boundaries, not this project's current
configuration or selection of pending JMAX policies.

S1 live verification: **not approved**. R1 live grants/cutover: **not ready / not
approved**. S2a targeted rotation: **not ready / not approved**. S2 restricted
cutover: **not ready / not approved**. I1 shared implementation/
live cutover: **not approved**. All proposed live changes require the stated
concrete approval; local planning grants no authority by implication.
