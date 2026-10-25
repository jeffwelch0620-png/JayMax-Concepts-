# S1 first-verification diagnostic distinction — October 25, 2026

## Scope and observed problem

The owner authorized local tooling changes, fictional regression tests and JMax
updates, with a prompt before publishing a draft PR. Hosted execution and all
credential, grant and schema changes remain held. This follow-up changes no app
route, PIN, role, limiter, schema, memory threshold or request budget.

Accepted base is merged PR69, `6740590b6d9d71765cbe2e88ceeda7705b2431a9`.
The separately approved October 25 original-start S1 attempt under bundle
`4c38164bc9c8920885a83d7488480eaeee49edff00121a1acc398fe46c07e4b6`
closed held at 11:02:28 a.m. Eastern after one P01 intent and zero validated
completed results. Render showed the accepted commit Live. The first response
reached decoded JSON validation but failed with `probe_shape`. No owner login,
deliberate wrong-PIN sequence, lockout or recovery test followed. Claims are
consumed; the cleanup and closed journal are retained.

That generic reason could represent either an exact negative verification or
an invalid positive response. No response body was retained, so this change
cannot retrospectively determine which occurred. In particular, it does not
establish a wrong entered PIN, password failure or backend defect.

## Bounded distinction

Only P01 gets an additional closed-vocabulary reason:

| Decoded P01 response after existing HTTP/encoding/body/JSON checks | Result |
| --- | --- |
| Exactly `{"ok": false}`, with a real Boolean false | Hold with `pin_verification_rejected` |
| Valid existing positive verification and roster contract | Existing success |
| Anything else, including false plus additional fields, wrong types, missing roster or a token field | Existing hold with `probe_shape` |

`pin_verification_rejected` means the endpoint returned an explicit negative
verification. It is not proof of why verification was rejected. The new reason
is a constant in the existing version-1 failure descriptor allowlist. No extra
descriptor fields, response excerpts, response keys, roster data, credentials,
tokens or exception text are persisted. Existing response bounds and exact
positive/negative validation remain authoritative.

P03 and other expected negative wrong-PIN slots keep their existing semantics;
P10 recovery validation and all other routes keep their existing reasons.
A P01 rejection still consumes its one-use slot and stops the supervised
sequence before owner login. The parent retains a pending intent and closes
held; it does not invent a successful completion, retry, reclaim the request
or continue with unused slots.

## Validation

All **298 selected cases** passed across an initial **296/298** run and a
corrected **2/2** TLS rerun, with no source changes between runs. The initial
two failures were `ModuleNotFoundError: cryptography` in the existing actual
loopback TLS controls. Adding the existing `pr21-recovery-test-libs` directory
after the main `actual-inventory-test-libs` directory in the local dependency
path resolved them; no package installation was performed. The original report
is preserved. The first run took 456.14 seconds; the rerun took 11.88 seconds.
Counts overlap and must not be added as 300 distinct cases.

The six-module selection covers transport, failure diagnostics, activation,
claim/resource gates and owned Windows process cleanup. All **14 new cases**
passed in the initial run. New fictional controls cover exact negative rejection, malformed/extra
fields, unchanged positive and expected-negative behavior, no secret leakage,
request reuse refusal, and the real worker/IPC/closed-journal path for both
rejection and malformed response. The repository's sanitized offline runner
disables application database settings and dotenv loading. No database server,
hosted request or actual input is needed for this follow-up. The broad offline,
frontend/build and PostgreSQL suites were not rerun for this bounded tooling
change; fresh complete CI remains pending draft publication. Local reports are
`s1-pin-diagnostic-tests-20261025/focused.xml` and `tls-rerun.xml` in the build
work area, with separate logs and runner selections.

## Next gate

Prompt before draft publication; fresh CI and merge approval remain separate.
Any live attempt needs accepted source, fresh qualification/binding checks,
a newly sealed packet and explicit approval. Existing packets and consumed
claims must not be edited or reused with these changed source bytes.

The earlier live attempt stayed above its selected 1,024-MiB/15% start and
512-MiB/10% running guards, but missed the separate 1,536-MiB quiet evidence
target. That limitation and the `probe_shape` stop are distinct. This change
does not relax either gate or claim security acceptance. G04/G13/O1, N2/I1 and
omitted identification, cross-endpoint, manager/staff, unset-PIN, session-activity
and revocation coverage remain open. Inventory owns stock; Track 1 remains
independent, pars frozen and ordering manual.
