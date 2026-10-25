# S1 activation adapter implementation and fictional acceptance

## Scope and current authorization

The owner authorized local implementation and fictional testing after reviewing
the activation-adapter proposal. This slice adds operator tooling only. It changes
no application endpoint, frontend, dependency, migration, database, account,
credential, grant, Render connection or service configuration. No hosted app,
Render or Supabase request was issued; no real PIN/password/token was read.

Accepted main remains PR65 `1db9797`, with separately passing
[reviewed-head](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/40103720101)
and [merged-main CI](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/40104331749).
This follow-up is published as [draft PR66](https://github.com/jeffwelch0620-png/JayMax-Concepts-/pull/66).
The owner authorized the A1/N1/N2/N3 amendments and their push to the same PR;
review, merge and any live attempt retain separate approvals.

## Components and guarantees

| Component | Result |
| --- | --- |
| `tools/ops/s1_request_transport.py` | Keeps the original local-only destination policy. Small protected hooks allow the separate adapter to reuse response, client-isolation, timing and recovery logic. Oversized numeric headers are rejected before integer conversion. |
| `tools/ops/s1_activation.py` | Inert profile builder, source/runtime/trust pins, finite application-code equivalence proof, exact approval/identity/target/window validation, exclusive attempt claim, flushed dispatch/result journal and approved-network factory. |
| `tools/ops/s1_process.py` | Separate spawned worker, bounded JSON control messages, parent deadline/resource checks, Windows kill-on-close job containment, termination of owned descendants and checked job emptiness. |
| `tools/ops/s1_operator.py` | Prepare/check commands send no requests. Rehearsal uses fictional inputs and local targets. The distinct hosted command requires isolated Python, private owner-bound approval/actor files, exact target and explicit operator attestation. It was not executed here. |
| `tools/ops/s1_console.py` | A separate, network-free human console milestone with a fixed fictional phrase, protected input, resource checks, independent supervisor and a receipt containing booleans only. |

The factory accepts hosted HTTP only for the fixed HTTPS API origin after the
supervised operator path validates the profile and approval. It rejects test
transports, test TLS contexts, endpoint overrides and unsupervised hosted clients.
`LocalTransport` still refuses the hosted API; there is no allow-hosted boolean
added to that class. Python internal objects are not a sandbox against malicious
code already running as the operator; approval remains a trusted human/operator
attestation, not a new identity provider or cryptographic consent service.

Profiles bind raw execution-source hashes, Python executable/version, HTTPX and
its transport/runtime package sources, certifi trust bytes and the finite API
source proof. Preparation does not read private configuration or activate an
approval. Source/approval/actor changes hold rather than silently regenerate a
permitted profile. Already imported modules are not hot-reloaded. The future
live runtime must be a separately prepared, isolated Python 3.12 environment with
the reviewed pinned dependencies; no new runtime was provisioned in this slice.

## Durable dispatch and failure behavior

The exact approval binds the profile, actor-reference digest, attempt identifier,
private evidence directory, owner-reported API proof, quiet-period
confirmation and UTC timestamps. The approval must explicitly attest the owner
reference; a public profile alone never enables execution. The existing
health/calibration approval validator is unchanged and is not reused as S1 consent.

The owned worker is armed under independent supervision before network-free input
collection. Each field permits three total entries (the initial entry plus two
corrections). Bound email must match exactly; configured PINs require 4-8 ASCII
digits; passwords must contain 1-1,024 characters. Rehearsal still accepts only
fixed fictional values. No network client is created during input. A typo does
not consume the attempt; password correctness is established only by the later
ordinary login request, without a login retry.

The worker sends exactly `{"event":"inputs_ready"}`, with no values. The parent
revalidates approval, bindings, sources, resources and the evidence environment.
It requires at least **397 seconds** to the existing stop-checks cutoff: 65 seconds
quiet + 90 for P01 + 20 x 6 for remaining requests + 62 maximum recovery wait +
60 margin for integrity, IPC, storage and scheduling. The check is repeated after
the evidence environment checks immediately before claim creation, even for
reduced variants. This conservative start gate does not extend deadlines or
guarantee completion on a stalled machine; the watchdog still enforces cutoff.

Only then is an exclusive claim created and flushed/fsynced, before the parent
sends `{"start_dispatch":true}`. Slow/invalid input or failed revalidation holds
without a claim; the returned receipt distinguishes `inputs_collected_no_claim`
from inputs that never became ready. An unused approval remains subject to its
original timestamps/source bindings: it is never automatically extended. Any
partial or uncertain claim creation remains consumed or held for reconciliation.
The controller flushes an intent before granting each individual dispatch, and accepts
only the expected result shape for the pending case. A partial claim, pending
intent, failed result, evidence failure, interrupted worker or unexpected message
cannot be replayed as a fresh attempt. The approved directory cannot be replaced
by moving/copying the packet to another path. The actor records are copied and
their binding is checked during the run. No password/PIN/token or raw response
appears in the claim or journal.

Evidence I/O errors poison the journal and prevent further requests. Controller
callbacks run separately so a stalled fsync/handler cannot block the parent from
stopping the owned worker. A callback whose closure cannot be confirmed produces
an explicitly held/unconfirmed result; it does not race a final write against the
stalled writer. Its incomplete evidence and claim remain consumed. This is not a
whole-machine power-loss durability or frozen-Windows guarantee.

The worker starts only after job assignment and the parent's initial start grant;
dispatch requires the separate post-input claim grant described above. The
parent checks the active window/resources independently of blocking terminal
input and cooperative HTTP cancellation. Cleanup targets only the owned process
and job, including descendants. Tests cover stalled workers, blocked parent
callbacks, worker return with an owned descendant, and parent exit after the
worker is armed. Startup without a grant exits on the closed control channel or
its timeout. Runtime-import/OS freezes are not represented as tested guarantees.

## Profile, identity and session limits

The proposed normal order is P01/P02, available L01–L03 logins, P03–P09 limiter
checks, available R01–R06 personal reads, guarded P10/P11 recovery and P12 anonymous
denial. P01 remains the first request and retains the 90-second cold-start limit.
Other requests retain six seconds. The normal maximum is 21 attempted requests;
the controller has no extra warmup, health, discovery or retry request.

Only finite variants can omit missing roles/roster cases or use the predeclared
P04/P06 verify fallback. Unconfigured-PIN verification has its own exact disabled
response and sends an empty, non-candidate PIN, not `0000`. The exception is scoped
only to that profile's P01; configured profiles and the base LocalTransport retain
the normal PIN input rule. The server deliberately reserves its store attempt
slot before checking configuration, so the disabled request still consumes one
slot. No bypass/refund or server change is introduced. If a supposedly disabled
portal is configured, the empty input cannot authenticate it and the unexpected
response holds the attempt. Omitted request
labels are reported; they do not become spare request capacity. The client checks
the selected owner-admin roster ID before identifying it. Login and identity
responses must match independently bound ID, email, role and exact intended store
scope. Roster owner-admin is never substituted for personal owner authority.

The parent validates owner-reported preflight facts against its bindings; it does
not independently observe the running deployment, runtime or quiet interval.
Receipts state `preflightSource: owner_reported`. `apiCommit`, `runtimeSha256`,
`quietConfirmed` and `observedAt` require separately approved supporting evidence.
They are attestations, not observations made by this adapter.

The activation handoff must require each account holder to enter their own email
and password at the protected console, or use explicitly approved dedicated test
accounts. Nobody relays passwords to the operator. The private receipt records
only `credentialEntryRoles` for the roles whose input phase completed; this does
not identify or independently prove who physically typed. The owner checks the
participants' role-level participation during the supervised handoff. These role
labels do not grant authority or replace bound actor records. P01/P02 precede the
personal logins; L01-L03 precede the deliberate failed-PIN sequence starting P03.

The wrong PIN is derived in worker memory only after P01 succeeds and is guaranteed
to differ from the supplied PIN. Real operator inputs would be requested only
after fresh approval validation and only in the supervised protected operator
console; the claim follows validated input and precedes every HTTP dispatch. No browser
token, clipboard, password-manager, database PIN or environment-secret lookup is
implemented. Rehearsal input is restricted to fixed fictional values and
`@example.invalid` accounts. Default preparation and help do not collect secrets.

The 13-minute stop-checks cutoff and 15-minute hard deadline retain the two-minute
cleanup reserve; T1 recovery wait and T2 absolute deadline guards remain enforced.
Hosted profiles use real clocks only. Local end-to-end rehearsal is explicitly
marked `clockMode: virtual`: quiet/recovery waits advance an injected test clock,
while real process cleanup/deadline tests use real elapsed time. It does not claim
that a live limiter interval or process continuity has been observed.

Public results always state `securityAcceptance: false`. Profile completion is
not G04/G13/O1 closure, exhaustive audit review, runtime actor attribution or live
authorization. Clearing worker references does not revoke issued stateless
sessions; the configurable source default remains eight hours. I1 current-actor
resolution and revocation work is unchanged.

## Fictional acceptance and evidence

PR66's original head passed all four [CI checks](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/40108443508).
The A1/N1/N2/N3 amendment keeps full source/runtime/trust hashing in both worker
and controller before each dispatch. Private receipt `integrityChecks` records
each label's measured `workerMilliseconds` and `controllerMilliseconds`; no
path/size/mtime shortcut is used. Measurements cover those hash validations only,
not total IPC, fsync, quiet/recovery waits or hosted latency. Start/close and
per-request behavior remain subject to the source/approval/deadline guards.

The real operator console milestone completed with the exact prescribed fictional
phrase. Its receipt reports `fictionalInputMatched: true`,
`ownedCleanupConfirmed: true`, `hostedRequests: 0` and
`realCredentialsRequested: false`; it does not retain the input text. The owner
reported completion, and the receipt and process exit were independently checked.

The initial focused process/transport/controller run passed 91 tests. The
strengthened run passed 102 tests, including:

- the real FastAPI password-login/PIN/role routes against fake database rows,
  including normal, missing-roster/missing-role and unconfigured-PIN profiles;
- a full supervised 21-request HTTPX loopback scenario with separate anonymous
  and personal contexts, strict dispatch order and replay refusal;
- real local TLS using an isolated fictional CA, and rejection without that CA;
- multi-process claim races, source/approval/actor/scope binding, stale deployment
  proof, recovery/deadline guards, response/header bounds and redacted output;
- actual Windows owned-worker/descendant/parent-exit containment and blocked
  worker/controller cleanup.

Original-head validation passed **1,736 offline cases** (664 tests plus 1,072 subtests),
with zero failures, errors or skips. That run includes the added storage,
malformed-protocol, private-binding and validation-order fault cases. The prior
full run passed 1,735 before the final private-file validation-order test was
added; all profiles overlap and must not be summed. Five existing deprecation
warnings remain. The public acceptance receipt binds final source hashes, JUnit
report hashes and the network-free human console receipt. All data and certificates are
fictional, all sockets are in-process or loopback, and owned fixtures are closed.
The new modules are selected by the existing offline CI profile. No local
PostgreSQL, migration, backup/restore or frontend build was needed for these
operator-only changes. Existing FastAPI/multipart deprecation warnings remain.

The launcher validates the public profile before opening the explicitly supplied
private binding files, and checks the operator approval reference/profile digest
before reading actor records. The request worker deliberately emits a generic
held event on failure; the durable pending case identifies the uncertain stage.
It does not forward exception text or raw responses for diagnosis. More detailed
reason reporting must retain that fixed-category/privacy boundary if added later.

The review amendment disposition, corrected throttle expectations, inactive
account-holder checklist and fresh validation are recorded in
[PR66 review amendments](PR66_REVIEW_AMENDMENTS_20261024.md). The amended full
offline profile passed 1,770 cases (698 tests plus 1,072 subtests) with no
failures/errors/skips. The final 21-request loopback recorded 17.377 seconds of
combined full-integrity checks; hosted timing remains unproven. The earlier
focused fixture failure and corrected rerun are retained and explained there.

## Remaining gates

Current accepted baseline is merged PR68 **15d7f1f**; the historical PR66 checklist
below records its earlier workflow. Before any new live proposal, apply the
[F1/G1/G2/G3 qualification checklist](S1_POST_CLAIM_ACTIVATION_GATES_20261024.md):
accepted source/runtime, an immediately preceding real-time rehearsal in the
same operator-machine session with matching roles/roster/PIN/floor shape, a
private receipt SHA-256 binding, all seven version-2 resource phases observed,
and quiet-wait minima **>=1536 MiB on both sides**. The standard new live profile
uses a matching operatorStartFloorMiB of at least 1536, checked before claiming.
Do not request live approval if any gate fails. No code/test merge authorizes
real credentials, an API/PIN test or a new live window. The original live cause
remains unknown; all hosted work and credential/grant/schema changes stay held.

1. Finish the authorized PR66 amendment checks and JMax readback, commit cleanly
   and push to the existing draft; return for merge approval after fresh CI.
2. Obtain independent review, fresh CI and separate merge/automatic-deployment
   approval. The operator code is not imported by the deployed application.
3. Prepare separately approved, bounded API deployment/configuration/actor
   preflight and a fresh exact live packet from the accepted adapter source.
   Keep database/Render metadata reads out of the 21-request HTTP budget.
4. Obtain explicit approval of the new programmatic logins, temporary Bert's
   lockout, active timestamps, resource gates and expected limiter/audit/session
   side effects before any live call or real secret input. Old approvals are spent.

No service pause, credential/grant/schema/provider, connection, business-data,
Toast or Companion change is included. Inventory remains the stock writer,
Track 1 stays independent, par editing remains frozen and ordering manual.
