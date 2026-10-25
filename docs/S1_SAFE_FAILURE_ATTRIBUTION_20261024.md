# Safe S1 failure attribution â€” October 24, 2026

The owner authorized this local tooling change, fictional regression tests and
JMax updates, with a prompt before a draft PR push. Hosted work and credential,
grant and schema changes remain held. No browser/API/database call, real input,
service control or deployment is included in this change.

## Problem and evidence

The accepted PR66 baseline is `42a78b8`. A separately approved owner-only attempt
under sealed proposal `52e6f725` confirmed the accepted Render deployment and
accepted protected inputs locally, then held after claiming but before its first
request intent. Zero requests were dispatched. Owned cleanup passed; the window
and request claims are consumed. The original worker/supervisor discarded its
failure stage and category, so its cause cannot be recovered from that receipt.

A subsequent read-only local review passed seven final fictional cases: four
in-process controls and three actual Windows owned-worker cases. Successful
fresh/aged-window cases completed thirteen mocked exchanges. Wrong-password
controls completed P01 and failed at L01, which does not reproduce the original
zero-intent receipt. No real password/PIN was tested. An invalid rehearsal-origin
control was corrected and its initial failed receipt preserved. That review is
separate evidence; these changes do not retrospectively identify the live cause.

## Change

`s1_failure.py` defines closed vocabularies for stages, request labels, reason
codes and exception types. Unknown/custom exceptions receive constant fallback
values. Only exact trusted exception classes may supply a single exact allowlisted
reason argument. No `str(exception)`, `repr`, exception chain, traceback, locals,
raw request/response, actor, path, token, PIN, password or DSN is serialized.

The worker records fixed stages around profile/approval/input validation,
dispatch handoff and revalidation, transport construction, sequence/quiet wait,
the current request slot, recovery wait and client cleanup. Stage acknowledgments
carry no input values and grant no dispatch authority. The parent validates exact
message fields, stage vocabulary, selected request labels and current request
position. The added stage budget is finite (64); the original per-request permits,
source hashes and durable one-use claim remain authoritative. Invalid or extra
metadata holds the attempt.

The final result's `failureDiagnostics` and, where safely writable, the journal's
closed record contain:

| Field | Meaning |
| --- | --- |
| version | Fixed schema version 1 |
| workerPosition | Last acknowledged fixed stage and optional approved request label; null for an old/unobserved worker |
| controllerStage | Last fixed controller stage |
| primaryFailure | First known worker/controller failure, or null |
| workerCleanupFailure | Independent worker client-close/cleanup failure, or null |
| supervisorFailure | Sanitized supervising guard/protocol/callback failure, or null |
| supervisorCleanupFailure | Independent owned Windows job/process cleanup failure, or null |
| closureFailure | Independent final evidence-write failure, or null |

Each non-null failure descriptor contains only `stage`, `request`, `reason` and
`errorType`. Resource guard failures are reported with a constant category, not
their diagnostic text. A request label describes where a failure was observed;
it does not prove a request reached or committed at the server. The journal's
intent/completion facts remain the source for that distinction.

The worker owns final client cleanup before DONE. Standalone/rehearsal sequence
calls retain their existing automatic close; only a supervised capability may
delegate that close to the worker. This allows a request/quiet-wait failure and
a subsequent client-close failure to be retained separately. Tokens/credentials
are still discarded locally; local cleanup is not server-side session revocation.

The supervisor preserves its sanitized primary failure when owned cleanup also
fails. Cleanup uncertainty and unconfirmed controller callbacks stay held; the
controller does not race a final journal write or label an ambiguous claim unused.
Malformed diagnostic objects never reach the evidence stream. Historical legacy
worker events remain accepted without inventing a missing worker stage.

## Boundaries

No endpoint, role, login behavior, PIN budget, response bound, request order,
397-second dispatch bound, quiet/recovery interval, RAM threshold, cleanup reserve,
source-hashing policy or hosted configuration is relaxed. Additional local IPC
can consume some window time; it does not extend deadlines. All stored source
profiles and consumed packets remain unchanged and cannot authorize these new
tool bytes. Any future live packet must be regenerated from accepted source and
separately approved. `securityAcceptance` remains false.

## Validation and next gate

Targeted tests cover secret-like exception text and hostile string conversion,
unknown/extra/out-of-profile fields, malformed stage/failure messages, the stage
budget, parent resource failures after input, evidence-closure errors, actual
owned-worker constructor/quiet/window/password failures, independent worker
cleanup errors, successful fictional execution and simultaneous supervisor/owned
cleanup failure. Successful paths retain the existing claim and sequence tests.

The final full offline run passed **1,809 cases**: 737 tests plus 1,072
subtests, with zero failures, errors or skips. It includes all 39 new diagnostic
cases. The corrected focused selection passed 41 cases; the six proxy/PIN cases
also passed separately. These profiles overlap and must not be added.

The initial focused run passed 181/183; its two existing TLS cases could not
import cryptography from the selected local dependency folder. An already
installed local package was added to the test search path. The first broad run
passed 1,803/1,809; six unchanged proxy/PIN tests correctly refused Uvicorn 0.54.0
when the repository pins 0.25.0. Selecting the existing pinned local package
resolved those six and the final full run passed. The initial reports remain
preserved. No dependencies were downloaded, installed or changed in the app;
backend requirements and hosted settings are unchanged. The existing five
FastAPI/multipart deprecation warnings remain.

No new frontend build or PostgreSQL run is needed for this operator-only change.
CI will run only after separately approved publication; it is not claimed here.
Prompt before pushing a draft PR, return for merge approval after review/CI, and
obtain fresh exact approval before any hosted execution or real console input.
