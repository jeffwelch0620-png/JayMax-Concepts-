# S1 protected input transport and local rehearsal

## Decision and scope

The missing request boundary from the October 24 S1 attempt is implemented as a
**local-only prototype** in [s1_request_transport.py](../tools/ops/s1_request_transport.py).
It has no hosted mode, application import, credential-file lookup, browser
integration or production command. It refuses the Render API and every other
non-loopback destination before creating a client. Fictional in-process HTTPX
transports are accepted only at `https://s1-fixture.invalid`; real sockets are
restricted to numeric `127.0.0.1` and an explicit unprivileged port.

This completes the authorized local design/rehearsal slice. It does not enable a
new S1 attempt. Publish a draft only with owner approval, obtain independent
review, then prepare and review a separate hosted activation adapter and packet.
No prior S1 approval is reusable. Credential, grant, schema and all hosted work
remain held. No app routes, dependencies, migrations or Render settings change.

The accepted source baseline is PR64, merged as `f4235f7`, with separate green
[reviewed-head CI](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/40057721329)
and [merged-main CI](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/40058597235).
These are existing baseline results, not fresh CI for this unpushed branch.

## Protected input and personal login

The proposed operator path is an operator-owned local console. Both account
email and password, and the store PIN, use a non-echoing `getpass` prompt. Piped
stdin and `getpass`'s echoing fallback are refused. No argument, environment
variable, clipboard, browser token, password-manager export or database PIN read
supplies these values. The local prompt explicitly says fictional rehearsal.

`login_from_terminal` connects this input path to the existing `/api/auth/login`
endpoint. The response must identify the requested role and entered email before
an opaque session is retained in memory. Each of owner, manager and staff has a
separate login slot and session, with distinct subject IDs. Shared-PIN identify
responses cannot populate that session store. Personal `/auth/me` responses must
match their own login's subject, role and email. This does not grant or change a
role, create an account, reset a password or mint a token outside normal login.

Only fictional input was used. The actual Windows human-operated, non-echoing
console interaction has not been observed; tests exercise its protected reader
and refusal paths with fictional substitutions. Before a live proposal is
executable, demonstrate that operator handoff locally without real secrets.
The Codex tool terminal must not receive secret input through chat/tool arguments.

Passwords and PINs are not retained by the boundary after their call; session
references are cleared on close. Python strings, library buffers and OS memory
cannot promise forensic zeroization. A future operator wrapper must suppress
tracebacks/core dumps and must never serialize exception contexts or private
objects. No saved receipt contains a response body, account, staff identity,
token, PIN, password or request header. The operator process must exit after use;
clearing local references does not revoke a server-issued session.

## Request isolation and limits

| Boundary | Local implementation |
| --- | --- |
| Anonymous vs personal | A fresh HTTPX client for each exchange; anonymous callers cannot supply headers or a session. Personal authorization comes only from that role's private login result. |
| Ambient state | No cookies carried between requests, `trust_env=False`, no netrc/proxy inheritance, no redirects, fixed origin and immutable method/path table. |
| Routes | P01–P12 and R01–R06 only, plus three explicit login slots L01–L03. No arbitrary URL, verb or body interface. |
| Changed client hint | Only P08 adds the fixed fictional `X-Forwarded-For: 192.0.2.19`; it grants no authority and cannot carry operator-supplied headers. |
| Request replay | Each slot is consumed before sending. Timeouts, lost responses and invalid responses consume it too. No retry or concurrent send. Claims are local to one object, not durable across processes. |
| Time | Monotonic window no longer than 780 seconds; first P01 at most 90 seconds, every other exchange at most six seconds; no automatic login retry. |
| Response | At most 65,536 bytes, identity encoding, JSON content type, duplicate-key/NaN/shape refusal, bounded 4 KiB chunks, fixed status and shape per request. |
| Throttle | `Retry-After` must be an ASCII integer from 1 through 61. The future controller must wait for that observed value plus one and enforce the packet's overall cutoff. |
| Guard | Required caller guard before a send and during exchange; a guard failure cancels the owned task. Existing source/resource/deadline packet controller remains a separate integration obligation. |
| Output | Request label, fixed outcome, expected HTTP status and bounded retry seconds only. No body/header/identity in public facts. |

The successful verify response includes the existing roster array, under the same
response cap; it is validated and discarded. Only tokenless `ok/name/role` with
`owner_admin` satisfies the designated identify case. Receiving unexpected fields
or a token holds that case. Transport completion alone is not security acceptance.

Cancellation and cleanup are tested with cooperative HTTPX/ASGI transports. This
prototype does not claim an OS-enforced deadline against a frozen process or
hostile cancellation-resistant injected transport. A future hosted operator
process needs bounded supervision and durable claimed/pending/closed evidence.

## Rehearsal and evidence

The new test module is included in the existing Windows offline CI profile.
The complete fictional app rehearsal obtains all three tokens through the real
login route, real PBKDF2 password verification and fake database rows. It then
checks all 18 P/R cases through the actual FastAPI app using ASGI, including the
store-wide wrong-PIN lockout, correct-PIN refusal during lockout, recovery after
advancing only a fictional clock, and the owner/manager/staff read matrix. It
never calls the token helper directly. No app lifespan or real database starts.

A separate real TCP rehearsal uses an owned ephemeral loopback HTTP server and
the ordinary HTTPX network transport. Four requests (fictional login, personal
identity read and two anonymous verifies) prove that an unreachable ambient proxy
is ignored, Set-Cookie is not replayed, and personal authorization stays off
anonymous requests. Captured DEBUG logging contains none of the fictional secrets.
The server is stopped, socket closed and thread joined. These four socket requests
do not by themselves prove deployed TLS or the full live role matrix.

Negative cases cover missing inputs/approval/session, nonlocal origins, path
injection, replay/concurrency, wrong login role/email, header injection, duplicate
JSON keys, malformed/oversized/encoded responses, redirects, retry-header bounds,
deadline/resource failure, cancellation, protected-input fallback and redaction.

Initial validation found a fake pool allocating a different connection on release,
then exposed an overly narrow successful-verify validator that omitted the real
roster field. Both were corrected. A non-ASCII HTTP header fixture also correctly
failed at HTTPX construction rather than the later JSON validator; its refusal
assertion now accepts the earlier safe failure. Earlier failing receipts are
preserved outside the checkout.

Validation passed: the broad offline profile reported **1,666 cases** (594 tests
and 1,072 subtests), with no failures, errors or skips. After strengthening the
socket/login, canonical-origin and fixed-client-hint checks, the final transport
module rerun passed **46/46 tests**. These profiles overlap and must not be summed.
Five existing FastAPI/multipart deprecation warnings remain. No frontend code,
database/SQL or app routes changed; frontend build and disposable PostgreSQL were
not rerun for this operator-only slice. Fresh GitHub CI is pending publication.

Reproduce the selected checks with `python tools/run_review_tests.py offline
--report <new-local-junit-path>`. The transport test alone is
`python -m pytest --noconftest -q backend/tests/test_s1_request_transport.py` in the
same fictional, dotenv-disabled environment used by that runner. Saved public
rehearsal evidence binds the source hashes and distinct JUnit reports; earlier
failing reports remain separate from final passing evidence.

## Required next proposal changes before any live request

1. Independently review this local prototype; do not silently enable hosted URLs.
2. Add a separately reviewed HTTPS-only activation adapter bound to the fresh
   approved packet hash, exact API origin, tested source/deployment proof, private
   durable single-use claim, loaded-memory gate and active window. Recheck those
   guards during requests and before each prompt/send. Refuse absent bindings.
3. Validate the operator's private terminal handoff with fictional input first.
   Define a fixed safe-result handoff; no local web relay, browser storage read,
   permission change or saved credential is required or proposed.
4. Explicitly replace the prior allowance of up to three human browser logins
   with **up to three programmatic personal logins** using that same endpoint.
   Proposed controlled API maximum becomes 21: 18 probes plus three login requests,
   without hidden bootstrap reads. This is a scope change requiring fresh approval,
   not use of the expired v3 approval. Existing endpoint access may produce ordinary
   audit entries and PIN attempts modify temporary limiter state; disclose both.
5. Rehearse the complete controller: sealed sources/approval, durable replay
   refusal, conditional skips for missing accounts/PIN/roster, P08/P09/P10 timing,
   immediate stop after a held result, private evidence failures and process cleanup.
   This prototype deliberately leaves those orchestration rules outside transport.
6. Only then present the exact fresh live packet for owner approval. Keep the
   existing two-connection read-only metadata scope separately bounded; do not add
   maintenance, service pauses, credential/grant/schema changes or par installation.

The earlier S1 partial metadata observations remain dated evidence. G04/G13/O1,
runtime actor/consumer attribution and live PIN/personal-role acceptance remain
open. Ordering stays manual, pars remain frozen and Track 1 stays independent.
