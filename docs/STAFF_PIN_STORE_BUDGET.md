# Mandatory store-wide PIN attempt budget

## Scope and approvals

On October 21, 2026 the owner authorized this separate local security fix and
testing, with a prompt before draft publication. The branch starts from accepted
PR50 main `cf0f127e3a5f8247e43746c269a47b75d2e58d1a`; it does not include or modify
the separate [draft PR51](https://github.com/jeffwelch0620-png/JayMax-Concepts-/pull/51)
par-role packet at `7fd4ce4`. No hosted requests, credential/account/PIN changes,
proxy configuration, migrations, database permissions or deployment are part of
this package. G04 remains open. Personal-login acceptance remains incomplete.

The owner subsequently approved publication. [Draft PR52](https://github.com/jeffwelch0620-png/JayMax-Concepts-/pull/52)
opened from tested `e262c9f5eb3adb7aea6c8832a649955f70d10f90`. This publication
update changes README/runbooks only; the implementation and tests retain the
locally tested bytes. The PR remains draft and unmerged. Current-head CI and
independent review must precede any separate owner merge decision. Publication
does not release the hosted-work or credential holds.

## Behavior

All anonymous PIN checks for one canonical store now share a mandatory five-check
failure/unresolved budget in a fixed 60-second window. Request headers, client
addresses and proxy peers cannot partition it. All existing PostgreSQL and
retained Mongo consumers still pass through the same check; restaurant aliases
resolve to the existing canonical store before keying. Other stores have their
own budget. Successful checks refund only their own reservation. Disabled or
malformed PIN checks consume a reservation; infrastructure read errors refund
their own reservation. Exhaustion returns the existing 429/Retry-After contract
without another PIN read, and storage failures remain closed with 503.

This intentionally shares availability: one caller can exhaust PIN access for
other devices at that store, including correct PIN attempts. Correct personal
manager/owner authorization does not consume the PIN budget and keeps its
existing role/location checks. Shared roster selection still issues no session,
old synthetic staff tokens remain refused, and unconfigured portals stay disabled.
No password normalization, fallback credentials or account repair is introduced.

## Staff response to a temporary lockout

"Too many staff PIN attempts. Try again later." (HTTP 429) means the shared
store budget is exhausted by failed or unresolved checks. It does not establish
which employee made the attempts or that a personal account password is wrong.
Pause PIN retries and wait until the indicated `Retry-After` interval expires
before trying again. Continued attempts can exhaust a later window too, so this
is not a promise that access will recover after one wait.

If the message recurs or blocks work, report it to the on-duty manager through
the existing support/reporting channel. Give the store, time, affected screen and
error text; never send the PIN, password or session token. An authorized manager
may use **Manager / owner sign in** with their own personal account, subject to
the existing permissions. That path is independent in source, but successful
deployed personal login remains unverified: do not describe it as a demonstrated
fallback. No credential reset, PIN change, account provisioning or service change
is authorized by this guidance or by the current documentation amendment.

## Pre-operational mitigation decision

Before operational use, record an owner-reviewed plan for sustained store-wide
lockouts and counter continuity. The review must evaluate a centralized durable
limiter with verified client attribution, a mandatory store ceiling and secondary
client controls; review any proposed threshold/backoff changes for both guessing
resistance and legitimate staff access. A stronger/longer PIN policy may reduce
guessing risk, but does not by itself prevent someone exhausting the store budget.
Backoff or a higher ceiling alone does not establish trusted client isolation.

The release record must name the selected mitigation, accountable owner, staff
escalation path and acceptance evidence for legitimate concurrent use, repeated
lockout, personal-authority access, instance replacement and supported scaling.
Unselected alternatives remain proposals. The current five-check/60-second build
policy, SQLite implementation and credential/hosted holds remain unchanged.
G04 is not closed by this documentation or by an eventual source merge.

## Counter continuity

The existing SQLite transaction implementation and 250 ms busy wait are unchanged.
Counters coordinate only workers sharing one filesystem. Independent instances,
rolling replacements or temporary-storage reset can each have a new budget.
Centralized/durable enforcement is a separate design gate before operational
scaling. Store keys use a new namespace: previous client counters are not summed
or treated as store counters. The new namespace begins a fresh window; retained
old entries expire normally. The existing 10,000-active-key bound still fails
closed if saturated. No application database schema is involved.

## Proxy boundary and evidence

The earlier proxy review missed Render's documented
[Python runtime default](https://render.com/docs/environment-variables).
Pinned [Uvicorn 0.25 configuration](https://github.com/encode/uvicorn/blob/0.25.0/uvicorn/config.py)
can apply provider environment defaults before the app reads ASGI client
attribution. The mandatory store budget removes that attribution dependency.
The fix changes no proxy or hosting settings. The prior unexpected hosted result
remains unresolved; local causal reproduction is not proof of the effective
hosted ingress chain or instance/counter continuity. Private reproduction
receipts stay outside Git and collaborator Pages.

## Local validation

The final full offline profile passed **1,145 reported cases**: 408 selected tests
and 737 subtests, zero failures/errors/skips. This includes all **60 PIN-security
cases**, both Windows ACL cases, pinned Uvicorn 0.25 middleware controls and the
existing real thread/process checks. The profile is based on PR50, not the
separate PR51 additions; totals are not directly interchangeable. Tests use
fictional records, fake PostgreSQL/Mongo
pools, in-process HTTP ASGI transport with startup disabled, and disposable SQLite
files. The middleware selection exercises the actual pinned Uvicorn package and
synthetic provider settings, without starting an HTTP server or contacting the app.

Coverage includes changed forwarding attribution and proxy peers, duplicate and
malformed headers, IPv6, unchanged/changed/unchanged controls, canonical aliases,
other-store isolation, concurrent reservations before PIN reads, correct-check
refund preserving earlier failures, expiry, disabled portals, storage refusal,
old-token rejection and personal-authority access when PIN attempts are exhausted.
Existing real thread/process coordination is retained. No SQL, frontend, workflow
runner, dependency pin or hosting configuration change is required; the existing
offline CI profile already selects this test module. CI had not run at the local
source checkpoint; current PR52 checks must be evaluated separately for its
reviewed head. Prior PR50/PR51 CI is not this branch's CI evidence.

An initial focused run passed 60 cases and the initial full profile passed 1,145.
After adding explicit assertions that middleware changes the delivered ASGI
address, a focused run passed 58/60: the test incorrectly expected an exact-proxy
profile to select the leftmost address rather than the rightmost untrusted one.
Only the expected attribution was corrected. The final full run passed all
1,145 cases with those stronger assertions; the limiter returned 429 throughout
both earlier fixture failures. Five existing dependency/lifespan warnings remain.
All totals overlap and must not be added. Evidence logs/JUnit reports are private,
outside Git, under stems `store-pin-focused-20261021T184205907799Z`,
`store-pin-offline-20261021T184241622505Z`,
`store-pin-focused-20261021T184511164654Z` and the final
`store-pin-offline-20261021T184543663264Z`.

The bundled local dependency directory had Uvicorn 0.54. A separate private
test-only directory supplied the actual locked Uvicorn 0.25 package; the regression
asserts its imported version matches `backend/requirements.txt`. No dependency
pin, environment file or running application setting changed. No PostgreSQL
server was needed or started. Frontend/source/SQL remain unchanged, so no new
frontend/build or database-server acceptance is claimed. Generated review guides
and final whitespace checks pass. Application connections and credential files
were not opened by this work.

## Next gates

1. **Completed:** local checks, repository/JMAX checkpoint and owner-approved
   draft PR52 publication. This documentation-only update records that status;
   independent review and current-head CI remain pending gates.
2. Obtain separate merge approval after exact-head CI/review. Merging main
   automatically deploys the Render test app; current local approval does not
   authorize that deployment or changing any service settings.
3. Obtain a new, explicitly bounded hosted verification approval, including
   effective runtime provenance and owner-led personal-login prerequisites.
   Keep request details private, use fictional scope, and stop on unexpected
   results. Do not guess credentials, rotate them or silently repair accounts.
4. Keep the separate PR51/par permissions/migration workflow on its own review
   and hosted gates. Recommended merge order is PR52 first; after its separately
   approved merge, normally merge accepted main into PR51, preserve the store-wide
   security guidance, resolve README/runbook conflicts and obtain fresh CI before
   PR51's own merge approval. Its proposed missing-role diagnostic remains separate
   work. No PR51 amendment or merge is authorized by this PR52 documentation task.
5. Complete the pre-operational mitigation decision and demonstrate the staff
   escalation/personal-login path under separate approval before operational use.
   Ordering remains manual; Track 1 accounting is unchanged.
