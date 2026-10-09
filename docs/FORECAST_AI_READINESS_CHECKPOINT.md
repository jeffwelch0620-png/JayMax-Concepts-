# Manual forecasts and retained AI conversation history

October 8, 2026. Extends local commit
`36d4fe8dc7c35ddb5967ab1676b6c861cb70953c`. Local review and invented tests only;
no Supabase query, hosted grants, real invoice import, provider request, flag-file
change, push, merge or publication is part of this checkpoint.

## Reproduced gaps and selected fixes

The proposed runtime role lacked access to both `store_sales_projections` and
`ai_chat_messages`; actual route reads raised `InsufficientPrivilegeError` in
the disposable full-native database. An owner-backed unreviewed forecast overwrite
returned 200. These are local reproductions, not evidence of hosted data loss.

Manual projected sales are planning dollars, not actual Toast sales, purchased
quantities, physical usage or accounting value. They stay in the existing
store/date table. Track 1 remains purchased-item physical counts with explicit
count values and received-date purchases. Taxes and fees remain separate.

`GET /api/projections/{restaurant}/review?date=YYYY-MM-DD` returns the saved
forecast or an explicitly missing row plus a version bound to store, date and
the complete stored row. PostgreSQL saves require that version in `If-Match`.
Missing versions return 428, malformed versions 422 and changed versions 409.
Same-date API commands serialize through an advisory lock; existing rows also
use row locks. Concurrent reviewed updates and inserts allow one winner.

Amounts use Decimal validation and the existing NUMERIC(12,2) range: nonnegative,
at most two decimal places, including zero. Booleans, nonfinite values, excessive
precision and overflow are rejected. Responses retain exact decimal strings.
The stored actor comes from the signed manager/owner session, not `enteredBy`
supplied by a client. Forecast versions are independent of shared-state revisions.

The forecast form displays the saved value before replacement, sends strings,
checks the acknowledgement's scope, basis, version, amount and note, and retains
drafts on failures or after navigation. A failed/lost acknowledgement requires
another explicit review. Typing during a save survives its acknowledgement.
Drafts survive navigation within the app session, not logout or a browser reload.
Recent forecasts remain reference entries with explicit read-failure status.

This is optimistic concurrency for API commands, not a forecast event journal,
automatic reconciliation, idempotency ledger or universal protection against
arbitrary owner SQL. A reviewed replacement after an uncertain response can
write the same value again. No theoretical forecast is posted into Track 1.
The new reviewed editor requires PostgreSQL; the old Mongo route remains
compatibility code and is not covered by this concurrency guarantee.

## AI history boundary

The proposed role gains SELECT only on existing AI messages. Chat INSERT and
clear DELETE remain denied. `GET /api/ai/capabilities/{restaurant}` reports the
connection's storage privileges. Under the candidate, history is readable and
chat/clear are unavailable. Server guards return 503 before provider initialization
or writes for unavailable actions; existing history stays retained.

Owner-backed connections with the existing privileges can still use the old
chat/clear routes. Capability checks are storage-privilege checks, not proof of
provider configuration, complete context availability, RLS/hosted login or
production readiness. AI chat storage writes still need separate scoped review
before expanding the nonowner candidate; this step does not add that grant.

History order uses timestamp plus UUID to make equal-time results deterministic;
UUID order does not reconstruct real conversational causality at equal timestamps.
The drawer validates history and scoped capabilities, shows failed reads as
unknown with retry, retains displayed messages on failed/unconfirmed clears,
and ignores late reads/stream callbacks after location changes or closing.
Streams are aborted on those changes. Failed or empty responses retain the
input and require a history refresh before retry. AI advice remains nonaccounting.

## Schema and permission scope

Two public tables extend the local candidate to 30 individually named public
tables: forecasts SELECT/INSERT/UPDATE; AI messages SELECT only. There is no
forecast DELETE, AI INSERT/UPDATE/DELETE, new migration or journal alteration.
These are trusted backend-role privileges, not employee or browser/Data API grants.
Existing application location and role gates remain necessary.

All 29 migration hashes, 94 function contracts and 123 relation contracts remain
unchanged. Only the permission-matrix pin changes:

- Previous: `3476ac48ea1278b41a26260b820ab0f8672d92420563bde1c758133d02fd2a84`
- Current: `c4113d46ca5730f680f80f19d872a42ea8b3fc3343c86a24de6152793aa6f46d`

The original 40-path continuation and preceding shared-state review package are
preserved and checked by the local snapshot builder. The hosted database is not
accepted as its own catalog reference.

## Validation and next release gates

Seven unique selected backend checks pass across retained runs:

- `planning-ai-final-v2.xml`: the passing forecast-read, history/storage-hold,
  profile-pin and read-only permission-verifier cases (four cases from the
  266.68-second run). Its three failures are excluded from successful evidence.
- `planning-ai-final-v3.xml`: all three affected forecast cases pass after the
  writer uses the signed token's existing `sub` field (55.64 seconds).

The cases cover exact decimals and zero; invalid input; missing/malformed/stale
versions; tokens bound to store/date; manager-location, staff and readonly
restrictions; signed actor attribution; concurrent existing-row and missing-row
commands; no shared-state revision bump; and an unchanged populated physical
report plus all eight accounting fingerprints. History tests use equal timestamps,
verify deterministic order and candidate read-only capabilities, hold chat before
the mocked provider is initialized, and retain messages after a denied clear.
The separate read-only verifier preserves catalog, rows and migration-ledger
fingerprints and leaves hosted LOGIN/release approval held. The local role is
NOLOGIN, selected with SET ROLE on pool acquisition, not a hosted LOGIN trial.

All 494 frontend tests in 61 suites pass in `planning-ai-frontend-v4.txt`
(105.015 seconds). Thirteen new cases cover reviewed forecasts, exact string
amounts/zero, failures/unconfirmed acknowledgements, retained drafts, typing during
saves, scope changes, AI read-only history, honest failed reads, failed/unconfirmed
clears, aborted/late streams, and input retention for provider/empty-response
failures. `planning-ai-build-v3.txt` compiles with only the existing
PurchaseOrdersTab/StaffTab hook warnings and Node `fs.F_OK` deprecation warning.

Diagnostics stay retained: `planning-ai-reproduction` has the three original
failures. `planning-ai-final-output.txt` is the interrupted broad filter's partial
progress log; it accidentally selected inherited suites, has no completed XML,
and contributes no passing evidence. The narrower v2 run exposed this writer's
incorrect assumption that decoded sessions contained `id`; existing signed
sessions contain `sub`. The v3 run fixes and verifies that integration error.
An intermediate frontend run exposed empty-response input loss; later runs fix
it. Intermediate builds retain the two new lint warnings fixed in the final build.

This is targeted backend route/accounting and permission-verifier coverage plus
the complete local frontend suite and production compilation. It is not a full
backend suite, hosted login, live browser, GitHub CI or managed recovery proof.

Continue holding merges. Next: reconcile approved hosted catalog differences
against the frozen reference, finish ordinary LOGIN/pool trials with reviewed
minimum grants, browser/Data API exposure checks, managed Auth/Storage/Vault/role
recovery, matched feature flags, then sequential PR stack revalidation. Earlier
PR statuses are historical unless refreshed live.

See [the preceding shared-state checkpoint](SHARED_STATE_CUTOVER_CHECKPOINT.md)
for retained period and adjustment boundaries, and earlier review packages for
purchase, count and prep validation.
