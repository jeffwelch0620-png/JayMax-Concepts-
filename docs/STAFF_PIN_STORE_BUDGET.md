# Mandatory store-wide PIN attempt budget

## Scope and approvals

On October 21, 2026 the owner authorized this separate local security fix and
testing, with a prompt before draft publication. The branch starts from accepted
PR50 main `cf0f127e3a5f8247e43746c269a47b75d2e58d1a`; it does not include or modify
the separate [draft PR51](https://github.com/jeffwelch0620-png/JayMax-Concepts-/pull/51)
par-role packet at `7fd4ce4`. No hosted requests, credential/account/PIN changes,
proxy configuration, migrations, database permissions or deployment are part of
this package. G04 remains open. Personal-login acceptance remains incomplete.

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
offline CI profile already selects this test module. CI is not yet run for this
unpublished branch, and prior PR50/PR51 CI is not this branch's CI evidence.

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

1. Complete local checks, reconcile repository/JMAX documentation and prompt the
   owner before publishing a new draft PR for independent review.
2. Obtain separate merge approval after exact-head CI/review. Merging main
   automatically deploys the Render test app; current local approval does not
   authorize that deployment or changing any service settings.
3. Obtain a new, explicitly bounded hosted verification approval, including
   effective runtime provenance and owner-led personal-login prerequisites.
   Keep request details private, use fictional scope, and stop on unexpected
   results. Do not guess credentials, rotate them or silently repair accounts.
4. Keep the separate PR51/par permissions/migration workflow on its own review
   and hosted gates. Ordering remains manual; Track 1 accounting is unchanged.
