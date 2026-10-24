# PR66 review amendments — October 24, 2026

The owner authorized local A1/N1/N2/N3 amendments, fictional tests, JMax updates
and pushing to the existing draft. Merge and its automatic Render test deployment
remain separately approved steps. All hosted execution and credential, grant and
schema changes remain on hold. No real PIN, password or token is requested here.

## Review disposition

| Item | Amendment and boundary |
| --- | --- |
| A1 | The supervised worker collects and validates fields before any attempt claim or HTTP client. Each field allows the original entry plus two corrections. Its exact readiness event contains no values. The parent revalidates authority, resources, sources and the remaining window, creates/fsyncs the exclusive claim, then grants dispatch. |
| A1 window | Require 397 seconds to the existing stop-checks cutoff: 65 quiet + 90 cold request + 120 other-request budget + 62 recovery wait + 60 integrity/IPC/storage/scheduling margin. Check again after environment validation immediately before claiming. No timestamp extension or additional request/retry is added. |
| N1 | The disabled-PIN profile sends only an empty non-candidate for P01 and expects the exact disabled 403. Normal profiles/base transport still require valid PIN syntax. Existing server throttle accounting is preserved. |
| N2 | Record worker and controller full-integrity-check milliseconds per dispatch. Retain full hashing; do not cache file contents based on path/size/mtime. |
| N3 | Every returned attempt receipt labels preflight facts as `owner_reported`. Supplied API/runtime/quiet/time facts are checked against bindings but not independently observed by this adapter. |
| N4 | The activation checklist requires each account holder's own protected entry or approved dedicated test accounts. Passwords are not relayed. Private evidence records role labels only; these do not prove who physically entered them or replace actor bindings. |

## Corrections to the supplied review

The server deliberately reserves the shared store throttle slot before checking
whether a PIN is configured. Empty or omitted PINs do not bypass that reservation.
The real-route test must assert the exact disabled response **and one reserved
attempt**, not zero reservations. Changing the server order/refund would weaken
an existing reviewed protection and is outside this amendment.

P01/P02 already precede the personal logins. L01-L03 precede **deliberate failed
PINs starting P03**, not all PIN activity. A wrong personal password is not
detectable locally; its one normal login request still consumes that attempt and
holds before the deliberate failed-PIN sequence. Local correction is only for
format, binding and length mistakes before any network request.

## Failure and ownership rules

Input cancellation, three failed local entries or a too-short window creates no
claim. A ready-but-held return says `inputs_collected_no_claim`; incomplete input
is distinguished. Unused approval is still bounded by its original timestamps
and source bindings. No automatic retry, approval extension or retained-secret
resume is provided. Once a claim may exist, ambiguity remains held and consumed.
Unconfirmed controller I/O never races a final evidence write. The worker and
its descendants stay in the owned Windows job during input and dispatch alike.

The output always reports `securityAcceptance: false`. No live acceptance,
security-risk closure, server-session revocation or credential ownership proof is
inferred from fictional success. The earlier real human fictional-console test
remains dated evidence; these amendments do not collect real account inputs.

## Activation handoff checklist — inactive

- [ ] Independently review the amended head and passing CI; obtain separate merge approval.
- [ ] Prepare a fresh profile from accepted source and an isolated reviewed runtime.
- [ ] Obtain separately authorized deployment/actor/quiet-period evidence and label its source accurately.
- [ ] Confirm that each account holder will type their own credentials, or identify the approved dedicated test accounts; do not relay passwords.
- [ ] Obtain a new exact owner approval of scope, participants, request limits, side effects and fixed UTC deadlines. Earlier approvals are spent.
- [ ] Recheck access/resources before supervised input; record only role labels for participation in private evidence.
- [ ] Complete the readiness/remaining-time gate; claim only afterward, then dispatch the fixed sequence once.
- [ ] Confirm owned cleanup, retain minimized evidence and separately assess acceptance. Do not treat local reference clearing as server revocation.

## Validation

The final full offline profile passed **1,770 cases**: 698 tests plus 1,072
subtests, with zero failures, errors or skips. The existing five FastAPI/multipart
deprecation warnings remain. The earlier focused selection passed 147 of 148;
one new fixture incorrectly created a different fake connection for release.
After preserving that report and correcting the fixture, the three selected
fixture/partial-claim/role-recording cases passed. The final broad run includes
all these cases; these profiles overlap and must not be added.

The final owned, supervised 21-request loopback receipt reports 8,543.487 ms of
worker integrity checks and 8,833.980 ms of controller checks: **17.377 seconds
combined**, or about 827.5 ms per dispatch for both checks. This is one local
fictional sample, not a hosted performance prediction or a completion guarantee.
It supports retaining full hashing within the conservative 60-second margin;
IPC/storage/scheduling overhead is not part of this measurement. Quiet/recovery
waits in this scenario use the explicit virtual test clock. Actual process
containment/deadline tests use real time and passed in the final full profile.

The suite includes a real owned spawned worker correcting an email typo and
completing the sequence with one claim, three invalid email/PIN entries holding
with no claim, fake-clock short-window refusal, exact value-free readiness,
pre-dispatch protocol rejection, partial-claim ambiguity, role-only evidence,
disabled-PIN real-route/throttle behavior and nonfinite/timing metadata rejection.
All test identities, passwords, certificates, database rows and endpoints are
fictional, in-process or owned loopback fixtures. Test scratch and prior reports
are preserved outside the checkout. No PostgreSQL server or real console input
was needed locally; fresh CI will also run its disposable database profile.
