# S1 real-clock/resource rehearsal and subclass diagnostics

## Authority and baseline

The owner approved merging PR67 and implementing N1, R1 and the disabled-portal
limiter note locally, including fictional testing and JMax updates. Prompt before
pushing the next draft PR. All hosted execution and credential, grant and schema
changes remain held. No new live S1 packet or real input is authorized.

PR67 merged as `e0adc3b485b734e28849bd598631129898e955ac`, with a tree identical
to reviewed `dedeb821254c92ea8ef3e48245a24f6beb642049`.
[Reviewed-head CI](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/40149826393)
and [merged-main CI](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/40153362211)
separately passed all four checks. Merge approval includes the existing automatic
Render test deployment; no Render inspection or hosted test is included here.

## N1: useful categories without private error text

Exact trusted Held/ProcessHeld handling remains first. Only these exact classes
may contribute an allowlisted single reason argument. Other exceptions use the
actual class ancestry and a fixed specific-first table, with BrokenPipeError
before ConnectionError and specific I/O categories before OSError. ImportError
also covers ModuleNotFoundError. Arbitrary class names, spoofed instance
`__class__`, exception text/properties/chains, paths and inputs are not read.
A Held subclass receives only its generic ValueError category, never its reason
argument. An unrelated Exception subclass remains OtherError/unknown_error.

## R1: explicit, digest-bound local rehearsal

R1 here is the PR67 review finding label; it is distinct from the restricted-role
R1 workstream in the coordinated security/permissions plan.

`s1_operator.py prepare --real-time-resources` selects a rehearsal-only field
`rehearsalResources: real` and a real clock. The complete profile digest binds
both; changing either invalidates the profile/approval. Existing virtual profiles
retain their exact shape and behavior. The new flag is refused in hosted mode.
It cannot authorize a hosted origin, alternate hostname or expanded route set.

Use the existing fictional loopback server with an explicit `127.0.0.1` origin
for a full supervised run. Fixture transports remain possible through the
existing rehearsal-client API. The flag does not install or discover a server,
read credentials/configuration, change PINs or create real accounts. Operator
rehearsal inputs retain the fixed fictional PIN/password and example.invalid
email restrictions. Any loopback service must itself be a fictional fixture.

The supervisor and worker use the same resource helper/floors as hosted mode:

| Boundary | Absolute floor | Percentage floor |
| --- | --- | --- |
| Start | 1 GiB available | 15% available |
| Running | 512 MiB available | 10% available |

Both conditions must pass. On a 6 GiB machine the running percentage condition
is about 614.4 MiB. A 914 MiB observation fails the start floor, but exceeds
both running floors. Resource pressure is a leading hypothesis to test, not an
established cause. Historical 610/914 MiB observations do not establish the cause
of attempt `52e6f725`; its original cause remains unknown.

The 65-second quiet wait and Retry-After recovery wait use real monotonic time.
The worker checks guards in bounded 50-ms sleep slices; the existing supervisor
continues its own checks. This is not an OS scheduling or freeze guarantee.
The request/time/source/claim/response limits and full integrity hashing remain.

## Numeric observations and failure evidence

`resourceObservations` in the returned receipt and safely writable journal closure
has separate supervisor and worker summaries. Each has exactly six phases:
input, pre_claim, quiet_wait, requests, recovery_wait, cleanup. Every phase holds
only sample count, minimum free MiB and minimum free percent. Zero samples plus
null minima means unobserved, not a successful measurement. An unavailable or
terminated worker may have a null/partial summary; supervisor observations do
not prove what the worker sampled. No process list or input values are recorded.

Sample counts and IPC metadata are bounded; extra fields, nonfinite/bool/invalid
numbers, regressing counts and erased minima are refused. Telemetry grants no
request authority. Stage snapshots preserve partial worker observations before
failure; a final snapshot uses its own bounded acknowledgment before the
unchanged bare failure/DONE terminal message. A failed resource check
records its numeric observation before refusing. A worker resource hold retains
`resource_guard_failed` and the fixed current stage; parent guard attribution is
retained separately from its last acknowledged worker position.

Cleanup observation never enforces a memory floor and cannot prevent closing
the owned client/job or overwrite the primary failure. No claim/evidence writer
is raced after an unconfirmed callback. A starting resource hold returns a safe
receipt with no claim or worker and no API request. This does not make any
consumed packet reusable, or establish S1 security acceptance.

## Operator gate before another live proposal

After accepted review/merge, run the real-time rehearsal on the operator machine
with fictional inputs and a fresh local-only profile/claim. Inspect all phases,
cleanup and the exact source hashes; a virtual pass is insufficient for this
resource question. Aim for at least 1.5 GiB available throughout to provide
headroom; that is an operational target, not a changed guard or guarantee.
Do not lower floors or close unrelated apps automatically. A held rehearsal
requires diagnosis and a fresh local attempt, not live activation.

Only then consider a fresh sealed live proposal and separate owner approval.
Credential-retirement (S2a) planning and par (P1) preparation may proceed alongside
this diagnostic work; neither gets execution authority from S1 or this document.
Keep credential work separate from the par maintenance window. Pars stay frozen,
ordering manual and Track 1 independent; shared identity/permission gates remain.

## Validation

The final frozen-source focused selection passed **80 cases**, including all
40 new resource/subclass cases, 39 existing failure-attribution cases and the
existing pre-claim window check. Profiles overlap with the broad offline suite.
No hosted call or real input is included.

Exploratory evidence is retained: the first focused selection passed 75 cases;
an intermediate selection passed 76/77 (one cleanup fixture completed twelve
rather than thirteen exchanges while implementation edits were still in
progress). The complete 80-case selection passed after code was frozen.
An earlier exploratory selection was interrupted before producing a final
report and is not counted as acceptance evidence.

The first actual-clock loopback rehearsal completed all thirteen fictional
exchanges and confirmed cleanup, but correctly remained held after 157.828
seconds. Its new telemetry-bearing DONE message did not match the supervisor's
exact terminal protocol. The fixed failure attribution retained a constant
BrokenPipeError/connection_error descriptor; no exception text was serialized.
This candidate defect was corrected with a separately acknowledged, bounded
final resource-summary message before the unchanged DONE. A real owned-worker
completion regression now verifies the receipt and journal close successfully.
This local discovery says nothing about the original pre-request live hold.

The corrected full rehearsal **passed in 148.828 seconds** with all thirteen
fictional loopback requests, zero fixture errors, successful journal closure
and confirmed owned cleanup. Both real waits ran without acceleration. Every
phase has observed samples on both sides; the source-file snapshot remained
unchanged. No hosted request, database connection or real input occurred.

| Phase | Supervisor minimum MiB | Worker minimum MiB |
| --- | --- | --- |
| input | 1238.004 | 1238.250 |
| pre_claim | 1208.641 | 1224.629 |
| quiet_wait | 1149.199 | 1149.199 |
| requests | 1226.328 | 1226.328 |
| recovery_wait | 1242.781 | 1242.781 |
| cleanup | 1322.781 | 1322.781 |

The minimum free percentage was 19.0572%; every observed guard passed. This
demonstrates the new local mode, but **does not meet the suggested 1.5 GiB
headroom target**. Obtain a fresh accepted-source rehearsal with better headroom
before proposing another live S1 attempt. No floor is lowered and no live packet
is activated. The first run's quiet-wait minimum was about 631 MiB, close to its
running percentage floor, but it did not record a memory-floor failure either.

The final full offline profile passed **1,849 cases**: 777 tests plus 1,072
subtests, with zero failures, errors or skips, including all 40 new cases. The
80-case final focused selection overlaps. All 142 rehearsal source-file hashes
still match; ten changed Python sources are pinned in the local validation
receipt. Existing dependency paths select the unchanged pinned Uvicorn and local
cryptography; no package was installed or changed. The existing FastAPI/multipart
deprecation warnings remain. No new local frontend build or PostgreSQL run is
needed for this operator-only change. Initial receipts are preserved, not
overwritten. This follow-up remains local and unpublished; prompt before a new
draft push, then obtain fresh CI, independent review and separate merge approval.
