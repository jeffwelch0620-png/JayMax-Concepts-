# Staff PIN authority boundary

**Current local follow-up:** the owner approved a separate mandatory store-wide
attempt budget and local testing on October 21, 2026. See the
[store-budget review packet](STAFF_PIN_STORE_BUDGET.md). It is not pushed, merged
or deployed; prompt before draft publication. Hosted work and credential changes
remain on hold. G04 remains open pending review and separately approved deployed
acceptance. The historical PR50 validation below does not establish that outcome.

The PR50 authority fix is merged as
`cf0f127e3a5f8247e43746c269a47b75d2e58d1a`, matching reviewed `b22734a`.
[Reviewed-head CI](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/39635235513)
and [merged-main CI](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/39638706456)
passed. Later separately approved hosted checks stopped on an unresolved limiter
result; they did not complete security acceptance. Publication, merge and hosted
acceptance for the new store-budget follow-up remain separate owner decisions.
This work changes no credentials,
deployed settings, application database schema or stored operational records.

## Personal authority and claimed roster names

Both PostgreSQL and retained Mongo identify routes return only `ok`, `name` and
`role` for the active, store-scoped roster entry. `owner_admin` is a roster label,
not authorization. Neither route mints an application session. Shared-PIN work
continues to use claimed identity; this does not verify a unique employee or
adopt Companion identity, membership or provider-session contracts.

The prior frontend used `StaffSheet`'s `onElevate` callback in two `App` locations
to store the identify response as a session. These paths are removed. The portal
offers **Manager / owner sign in**, returning anonymous users to the existing
personal email/password form. An already personally signed-in user returns to
their existing workspace. The roster screen and Staff settings explain this
boundary. Owners provision personal accounts through the existing owner-only
Logins panel; no account, password, PIN or key is provisioned by this patch.

Previously minted PIN sessions carried the reserved `email: staff:<roster-id>`
namespace. Token validation now refuses that namespace, and token issuance
refuses it too. Therefore an unexpired old PIN token cannot retain management
authority on the updated backend. Personal tokens, password hashes, signing
keys, historical actor strings and saved request fingerprints are unchanged.
Historical attribution is not rewritten. This is targeted retirement of the
old synthetic token format, not general account/session revocation or the
future shared identity implementation. Old tokens can remain in browser storage
until normal rejection/sign-out; stored tokens are not server authority.

## Explicit PIN configuration

There is no implicit PIN. Missing, empty or malformed configuration disables
unauthenticated PIN access. Stored PINs must be four to eight ASCII digits.
Manager read responses return blank `staffPin`, `custom: false`, `enabled: false`
when disabled; the existing manager settings show that state and allow an
explicit PIN to be set. A valid explicitly stored value is preserved, even if it
equals the former default. This patch never silently deletes or rotates it.

All direct PIN consumers use the same check: verify, identify, prep sheets and
completion, counts, tasks, notification subscriptions, and native count/prep
credentials. Personal-login access retains its existing authorization rules.
Legacy workflow retirement guards remain in force; this fix does not reactivate
old stock/count/task writers or grant private schemas to browser roles.

## Attempt limit and deployment boundary

The local follow-up admits at most five failed or unresolved checks per canonical
store in a fixed 60-second window, across all clients. Verify, identify and direct consumers
share that budget, including the `papa_leonis`/`papa` alias. Admission is reserved
atomically before reading the PIN. A successful check refunds only its own
reservation, not previous failures; expired reservations cannot refund a newer
window. Blocked attempts return 429 with `Retry-After` and do not extend the
window. Disabled-PIN attempts also consume the budget. Infrastructure read
failures refund their reservation without authenticating the caller.
PR50 used per-store/client attribution. On October 21, the owner first accepted
temporary shared throttling and later approved implementing the recommended
store-wide budget as separate local work. The new budget deliberately groups
every staff device at that store: failures or unresolved checks by one caller
can temporarily block other callers, including correct PIN checks. Personal
manager/owner authorization remains independent. This local approval is not
deployment approval or operational acceptance. Review availability, thresholds
and the supported strong per-store PIN policy before operational use. No PIN is
rotated or silently rejected to enforce a newly selected strength rule.

Counters use Python's standard-library SQLite in the instance's local temporary
directory, outside the repository and application database. Threads and workers
sharing that filesystem use atomic transactions. No Redis/service, Supabase
table, migration, grant, signing secret or new environment variable is required.
The state contains namespaced hashed store keys, expiry and counts, never PINs,
tokens, passwords or roster records. Expired entries are removed on admission;
10,000 active keys is a hard bound. Saturation refuses new keys. State/storage
errors return 503 and never bypass verification. SQLite busy waits are bounded
to 250 ms and run off the event loop.

**This is a single-instance limit, not a distributed security guarantee.** Workers
must share the same OS temporary filesystem. Independent replicas, rolling
instances and separate hosts do not coordinate; ephemeral filesystem replacement
resets counters. Before scaling, adopt a separately reviewed centralized limiter.
Do not claim a deployment-wide durable limit merely from these local tests.

The mandatory budget uses only the canonical store supplied by the common
PostgreSQL/Mongo wrappers. It does not use request headers, ASGI client address,
session identity or proxy peer to create additional budgets. The new namespace
does not reinterpret old per-client entries as store-wide counts. On first use
of the new namespace a fresh window begins; old entries expire normally. This
is not a durable migration of earlier counters. No per-client attribution is
asserted trustworthy by this fix.

The tracked start command supplies no explicit proxy allow list. Pinned Uvicorn
0.25.0 uses `FORWARDED_ALLOW_IPS` or defaults to `127.0.0.1`; Render's documented
[native Python runtime default](https://render.com/docs/environment-variables)
sets that variable to `*`. A dashboard without an explicit override is therefore
not proof of loopback-only proxy trust. The earlier proxy assessment missed this
provider default. Uvicorn's
[configuration](https://github.com/encode/uvicorn/blob/0.25.0/uvicorn/config.py)
and [proxy middleware](https://github.com/encode/uvicorn/blob/0.25.0/uvicorn/middleware/proxy_headers.py)
use exact trusted-address matching, not CIDR network matching. Do not assume
that configuring a proxy range works with this pinned version, or trust `*`
without verified ingress and direct-origin boundaries. The store-wide fix
does not change proxy trust, URL scheme handling or deployment configuration.
Effective hosted ingress sanitization and instance attribution remain unverified;
local reproduction does not conclusively identify the cause of the prior live
result. Future per-client isolation requires separately verified provenance.
Under separate owner authorization, verify the actual proxy chain and test
trusted/untrusted peers before changing trust settings. No such setting change
is authorized by this local implementation.

## Validation and release gates

Use fictional offline route tests with fake Mongo/PostgreSQL pools; SQLite is real
and cross-thread/cross-process coordination is tested. The new module is included
in the explicit offline CI selection. Never run the old external HTTP nightly
suite against the hosted application as a local test: it writes application data.
Its default-PIN assertion is updated to explicitly configure a fictional PIN for
a separately authorized fictional environment; that suite is not part of this
offline validation.

Required evidence includes no token/session on identify, old synthetic-token
refusal, preserved personal login, unset/malformed PIN refusal, shared failure
budget across different clients, expiry/store isolation, bounded/error states, and configured-PIN
prep/count/task compatibility. Frontend coverage includes ignored old response
sessions, personal-login navigation, disabled/limited errors and native portal
compatibility. Record final test attempts/results in the review packet before
requesting draft publication; local tests do not prove hosted acceptance.

### Pre-merge checklist and owner acceptance

Merging into `main` automatically deploys the Render test application. Before
merge approval, record each decision independently:

- **Accepted October 21, 2026:** temporary shared throttling in the build
  deployment, including possible grouping of staff devices behind a proxy/NAT.
- **Accepted October 21, 2026:** staff portals without a valid explicitly
  configured PIN remain disabled until a manager sets one through the authorized
  personal-login interface. This acceptance replaces a requirement to inspect or
  provision every store PIN before this build release; it does not claim that
  store configuration has been verified or authorize any PIN change.
- Confirm personal manager/owner login is available before relying on it for
  access or PIN configuration. This documentation amendment does not verify live
  accounts. Old synthetic PIN sessions will be rejected by the updated backend.
- Obtain separate approval to merge, with the automatic deployment consequence
  understood. The owner authorized this documentation push only; PR50 remains
  draft and unmerged. Hosted work and credential changes remain on hold.

Before any hosted inspection or fictional live acceptance: obtain separate owner
approval, verify the accepted deployment/head and single-instance/proxy boundary,
and use approved private handling for any account/PIN configuration checks.
Do not create accounts, set PINs, rotate secrets or alter service settings without
that approval. Reverting the
backend can restore the old vulnerability and must not be treated as a routine
security rollback. A separately approved fictional live acceptance can follow.

Reviewed-par installation, runtime-role/RLS work and Companion adoption remain
separate. Track 1 accounting, par-editing hold and manual ordering are unchanged.

## Historical PR50 local validation

- Full frontend: **1,034/1,034 tests across 82 suites**, using the reviewed native
  feature profile. Includes the real App-to-personal-login navigation test.
- Strict production build: **passed** with `CI=true` and the same public native
  profile. Local source-map generation was disabled to limit memory usage;
  no deployment/build configuration was edited. The existing Node `fs.F_OK`
  deprecation notice remains; compilation and lint completed successfully.
- Full offline profile: **1,134 reported cases** (397 selected tests plus 737
  subtests), zero failures/errors/skips. Both Windows ACL cases passed; five
  existing dependency/lifespan deprecation warnings remain. This includes 49
  new parametrized PIN-security cases. PostgreSQL/Mongo route tests use fake
  pools/collections and HTTP ASGI transport without startup; SQLite counter
  isolation, real thread/process coordination and fail-closed states are tested.
  No PostgreSQL server, hosted application or real account was contacted.
- Earlier focused backend runs passed 46 and then 54 cases as coverage expanded;
  frontend selection passed 34 cases. These overlap the final profiles and are
  not additional unique coverage. The final full profile covers later additions.
- The first full frontend attempt passed 1,033/1,034: the new disabled-PIN test
  queried settings before opening Planning. Only test navigation was corrected;
  the full rerun passed. The external evidence wrapper also needed UTF-8 console
  output to display that failure; original log evidence is retained unchanged.
- Static review: application SQL strings and protected migrations, snapshot,
  catalog/permission inputs, installer and hosting/CI configuration remain
  unchanged from accepted PR49. Python syntax, generated guides, documentation
  links and whitespace pass. Source remains on a separate local branch.

Evidence stems outside Git: `staff-pin-offline-20261021T023646499531Z`,
`staff-pin-frontend-20261021T023525305435Z`, and
`staff-pin-build-20261021T023835487571Z`. Published draft
[PR50](https://github.com/jeffwelch0620-png/JayMax-Concepts-/pull/50) at
`3b37fba3f8b76942eaa581be1127df73f8936d81` passed all four checks in
[CI run 39632624195](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/39632624195):
1,034 frontend tests in 82 suites, strict production build, 1,134 Windows offline
cases and 228 backend/disposable PostgreSQL cases. Profiles overlap; counts are
not additional unique coverage. This documentation-only follow-up records owner
acceptance and corrects release/proxy guidance; fresh exact-head CI is required
after its push. The existing eight-thread reservation test already verifies five
admissions plus three 429 responses without 503, and another-process coordination
is covered. No observed contention failure justifies changing the 250 ms timeout
in this amendment. No live/deployment acceptance, credential change, session
revocation on a running server, or mitigation of Companion ingress-header trust
is claimed. Merge and hosted work remain separately gated.
