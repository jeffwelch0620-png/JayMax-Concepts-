# Staff PIN authority boundary

Local security follow-up from accepted PR49 main
`6f1774a1a21073370ac006d9b48155123128d6bf`. Publication, merge and hosted
acceptance remain separate owner decisions. This work changes no credentials,
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

The proposed local limiter admits at most five failed or unresolved checks per canonical
store/client in a fixed 60-second window. Verify, identify and direct consumers
share that budget, including the `papa_leonis`/`papa` alias. Admission is reserved
atomically before reading the PIN. A successful check refunds only its own
reservation, not previous failures; expired reservations cannot refund a newer
window. Blocked attempts return 429 with `Retry-After` and do not extend the
window. Disabled-PIN attempts also consume the budget. Infrastructure read
failures refund their reservation without authenticating the caller.
The five-attempt/60-second values are a reviewable proposal, not an owner-selected
deployed policy. Confirm thresholds and the supported strong per-store PIN policy
before release. This patch does not rotate or silently reject an otherwise valid
explicitly stored PIN to enforce a newly selected strength rule.

Counters use Python's standard-library SQLite in the instance's local temporary
directory, outside the repository and application database. Threads and workers
sharing that filesystem use atomic transactions. No Redis/service, Supabase
table, migration, grant, signing secret or new environment variable is required.
The state contains hashed store/client keys, expiry and counts, never PINs,
tokens, passwords or roster records. Expired entries are removed on admission;
10,000 active keys is a hard bound. Saturation refuses new keys. State/storage
errors return 503 and never bypass verification. SQLite busy waits are bounded
to 250 ms and run off the event loop.

**This is a single-instance limit, not a distributed security guarantee.** Workers
must share the same OS temporary filesystem. Independent replicas, rolling
instances and separate hosts do not coordinate; ephemeral filesystem replacement
resets counters. Before scaling, adopt a separately reviewed centralized limiter.
Do not claim a deployment-wide durable limit merely from these local tests.

Client identity comes only from the ASGI client address, with IP normalization;
arbitrary `X-Forwarded-For`/`Forwarded` headers cannot change the key. Before live
acceptance, inspect the actual server/trusted-proxy topology under separate owner
authorization. A proxy address presented as the client will group users into one
budget; do not fix it by trusting caller-supplied headers indiscriminately.

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
budget, expiry/client/store isolation, bounded/error states, and configured-PIN
prep/count/task compatibility. Frontend coverage includes ignored old response
sessions, personal-login navigation, disabled/limited errors and native portal
compatibility. Record final test attempts/results in the review packet before
requesting draft publication; local tests do not prove hosted acceptance.

Before any hosted work: obtain separate owner approval, verify the accepted
deployment/head and single-instance/proxy boundary, and confirm personal manager
accounts and explicit store PIN configuration through approved private handling.
Do not create accounts, set PINs, rotate secrets or alter service settings without
that approval. Deploying this patch rejects old PIN sessions and may disable
unconfigured portals; report this behavior before merge approval. Reverting the
backend can restore the old vulnerability and must not be treated as a routine
security rollback. A separately approved fictional live acceptance can follow.

Reviewed-par installation, runtime-role/RLS work and Companion adoption remain
separate. Track 1 accounting, par-editing hold and manual ordering are unchanged.

## Completed local validation

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
`staff-pin-build-20261021T023835487571Z`. No live/deployment acceptance, new CI,
credential change, session revocation on a running server, or mitigation of
Companion ingress-header trust is claimed. Draft publication awaits the owner.
