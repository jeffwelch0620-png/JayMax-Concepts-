# S1 post-claim phases and activation headroom gates

## Authority and accepted baseline

The owner approved merging PR68 and local F1/G1/G2/G3 work, fictional tests and
JMax updates, with a prompt before the next draft PR push. Hosted execution and
credential, grant and schema changes remain held. No live attempt, real input,
Render/Supabase inspection, service control or database change is included.

PR68 merged as `15d7f1fac5d77db4d7ba9ab24c916e7b20b2436b`, tree-identical to
reviewed `b1053a0b6a58c0f20be8f676613fd21b328a0ff9`.
[Reviewed-head CI](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/40155278817)
and [merged-main CI](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/40156278013)
each passed all four checks. Automatic test deployment was part of merge
approval; its current status has not been re-inspected under the hosted hold.

## F1: record the durable claim boundary accurately

The accepted PR68 mapping put transport/sequence construction into pre_claim,
although they follow the durable claim and start_dispatch. This slice separates
that span in resource evidence without changing request authority:

| Phase | Boundary |
| --- | --- |
| input | Worker profile/approval checks and fictional/protected input collection |
| pre_claim | Validated inputs, worker_dispatch_wait, controller_claim and final pre-claim checks |
| post_claim_setup | Durable claim flushed; journal opening and worker_dispatch_check/transport/sequence setup, before quiet wait |
| quiet_wait | Real 65-second quiet interval |
| requests | Individually permitted request slots |
| recovery_wait | Required Retry-After recovery interval |
| cleanup | Owned client/process cleanup and optional numeric observations |

The parent's shared monitor changes immediately after the claim is durably
flushed, before opening the journal. The worker changes after start_dispatch.
A bookkeeping callback marks claim creation started only immediately before the
exclusive claim-file open. Headroom/window refusal before that callback reports
not_created; a partial claim write, journal-opening or initial journal-write error remains
creation_unconfirmed. No blanket exception catch calls a partial claim unused.
Existing uncertain-callback behavior still avoids a raced final journal write.

### PR69 P1: retain the journal before the post-claim guard

Independent review found that the first resource check in post_claim_setup
could throw inside Journal construction, after the durable claim but before
opening/writing the journal. The controller never received the journal and
could only report creation_unconfirmed. That evidence gap is corrected with
two-phase initialization: construct and durably append claimed, retain the
journal in the controller, then call post_claim_check before returning
start_dispatch. Moving a throwing check elsewhere inside the constructor alone
would not allow the controller to retain the object.

A post-claim resource refusal now closes the retained journal as held with
resource_guard_failed at controller_claim, claimStatus=created, zero request
intents and confirmed evidence closure when storage and owned cleanup succeed.
The running memory floor is unchanged. Direct fictional clients still enforce
Journal.guard before every intent. Genuine claim/journal storage failures and
unconfirmed callbacks retain their uncertain evidence/cleanup semantics; the
amendment does not claim they can always be closed safely. No new failure-stage
or resource-evidence version is needed.

`resourceObservations.version` is now **2**. It requires exactly supervisor and
worker summaries with the seven phases and strict bounded numeric rows. A null
worker or zero-sample phase means unobserved. IPC phase snapshots require the
new seven-key shape; old six-phase snapshots are refused. Historical receipts
remain intact as dated evidence but cannot satisfy the new qualification gate.
`failureDiagnostics.version` remains **1** because its shape did not change.
This is an operator evidence contract change, not a database migration.

## G3: optional raise-only floor immediately before claiming

`prepare --operator-start-floor-mib 1536` adds profile field
`operatorStartFloorMiB`. It is a strict integer in 1024..8192; bool, float,
string, out-of-range and explicit-null fields are refused. Absence preserves
the prior profile shape. The profile/approval digest binds the selected value.

The final dispatch-window checks re-read memory, apply the existing 1 GiB / 15%
start guard, and require available MiB at least the selected operator floor.
They run again in journal construction immediately before any claim-file open.
A failure reports the allowlisted resource_headroom_insufficient reason and
creates no claim. This does not change the 512 MiB / 10% running guard, override
the percentage condition or extend the 397-second remaining-window requirement.
Cleanup is never prevented by a low-memory observation.

The field may also be used in a virtual fictional profile for boundary tests;
that does not make virtual waits or injected memory qualifying evidence. The
standard new live proposal selects **1536 MiB or higher**, with the same value
in its qualifying real-time rehearsal. A high starting reading cannot guarantee
that memory stays high during the later quiet wait.

## G1/G2: required procedure before requesting live approval

These are approved qualification requirements for a future packet, not live
execution authority. Do not request approval of a live S1 attempt until all of
the following have been checked in the private operator packet:

1. Start from accepted/reviewed source with its actual Python/dependency/source
   pins. Use a fresh local-only rehearsal profile, fictional actors/inputs and
   loopback/fixture origin; never route the rehearsal to the build API.
2. Match the proposed live **shape** exactly: ordered roles, roster flag,
   pinConfigured flag and operatorStartFloorMiB (including absent versus present).
   Mode, origin, attempt IDs and fictional/live actor identities necessarily
   differ; do not compare whole profile digests as though they should match.
   Real actor bindings still need their separately approved private preflight.
   The CLI prepare command defaults to the full shape. Use --roles (comma-separated
   in owner,manager,staff order), --no-roster and --pin-disabled for reduced
   variants. Owner remains required; duplicates, unknown roles and wrong ordering
   are refused by the existing profile validator before any profile file is
   opened. Never assume the default is owner-only or hand-edit a sealed profile.
3. Run with `--mode rehearsal --real-time-resources` in the same operator-machine
   OS session immediately before the proposed live attempt. Record start/end
   timestamps and the operator's same-session confirmation. A restart/sign-out or suspend/resume,
   source/runtime/shape change, substantial intervening work or delay invalidates
   this qualification and requires a fresh rehearsal. A receipt digest alone is
   not proof of provenance, real time or same-session execution.
4. Require passed execution, all expected fictional slots, seven observed phases
   on both sides, confirmed owned cleanup/journal closure and unchanged source
   pins. Virtual/accelerated or injected-memory unit tests cannot qualify.
5. Require `quietWaitGate.passed=true`: both supervisor and worker have at least
   one quiet-wait sample and **minimum available memory >=1536 MiB**. A missing,
   partial, old-version or lower reading does not pass. Close unused apps
   manually if needed; never lower guard floors or close unrelated apps for the
   owner. A functionally passed rehearsal with a failed gate is not live-ready.
6. Record the gate result plus counts/minimum MiB/required MiB only. The returned
   receipt and safely writable journal closure include the same numeric gate.
   No process list, secret, actor name or raw error text belongs in this evidence.
7. Calculate the exact completed receipt's SHA-256 and bind it, its private
   location, both profile digests/shapes, accepted source/runtime pins, timestamps
   and operator same-session confirmation into a **new inactive** live proposal.
   Recheck loaded resources, source and access immediately before any separately
   authorized live execution. Do not reuse consumed claims or old approvals.

G2 is an explicit pre-live gate, strengthening PR68's earlier suggested buffer.
It is distinct from the lower running safety floors. A true numeric gate by
itself does not authorize activation or prove S1 security acceptance. No current
local candidate or synthetic receipt is a qualified live packet.
The minima are the lowest observed samples, not a guarantee about memory between
polls; all live running guards remain mandatory even after a qualifying rehearsal.

### PR69 P2: explicit CLI shape and safe summary

For an owner-only, configured-PIN/no-roster fictional rehearsal, prepare with
`--roles owner --no-roster --real-time-resources --operator-start-floor-mib 1536`
along with the existing --mode rehearsal, --origin and fresh --output arguments.
The origin must be the actual approved fictional fixture/loopback origin; these
flags do not start a fixture or authorize any hosted connection. This shape
contains thirteen request slots. --pin-disabled selects the existing disabled
portal variant, rather than assuming a store PIN exists.

After an exclusive profile save, the CLI prints only ordered roles, roster,
pinConfigured, requestCount, realTimeResources and operatorStartFloorMiB. A null
summary floor means absent from the saved profile. No actor identifier, email,
password, PIN, token, DSN, attempt ID, origin or file path is printed. Profile
creation remains inert with executionApproved=false. Each shape is still bound
by the profile digest and requires its own matching rehearsal and approval.

## Coordination and validation

S2a credential-retirement planning and P1 preparation may proceed alongside S1
diagnostics, with their own consumer/recovery evidence and separate live
approvals. Credential work stays separate from par maintenance. Inventory is
the stock writer; Track 1 remains independent, pars frozen and ordering manual.
G04/G13/O1, identity/permissions and live acceptance remain open.

Original-head local validation passed **1,889 offline cases** (817 tests plus 1,072
subtests), including 40 new claim/gate cases, with zero failures/errors/skips.
The **121-case final focused selection** overlaps. The first focused run passed
119 cases. Two final regressions cover explicit-null profile fields and fixed
resource-failure attribution after the durable claim; they were added before
the final frozen-source run. No test result was discarded or overwritten.

The initial full actual-clock/resource loopback run passed thirteen fictional
requests in 139.781 seconds, with quiet-wait minima about 1700.164 MiB and the
1536 MiB operator floor. After the final diagnostic regression, the full run
was repeated on the final code bytes and passed thirteen requests in
**139.047 seconds** with zero fixture errors. All seven phases
were sampled on both sides; journal closure and owned cleanup passed.

| Phase | Supervisor minimum MiB | Worker minimum MiB |
| --- | --- | --- |
| input | 1811.051 | 1814.297 |
| pre_claim | 1813.473 | 1814.340 |
| post_claim_setup | 1819.383 | 1819.422 |
| quiet_wait | 1765.848 | 1763.367 |
| requests | 1782.328 | 1782.887 |
| recovery_wait | 1722.445 | 1719.621 |
| cleanup | 1831.637 | 1831.680 |

The numeric G2 gate **passed**: supervisor quiet minimum
**1765.848 MiB**, worker **1763.367 MiB**,
required **1536 MiB**. The same selected operator floor was used. All
143 recorded source-file hashes match the final bytes.
The receipt digest and detailed source/test hashes are in the private local
validation record; source/profile/actor evidence remains fictional/local.

These original-head receipts are preserved historical evidence; the P1/P2 code
amendment changes their source binding and requires fresh local validation.
This is local candidate validation, **not G1 live qualification**: the candidate
is not yet accepted/merged, no new live packet is sealed, and the required
same-session rehearsal must be fresh immediately before a separately approved
live proposal. Numeric G2 success alone grants no execution authority.

The unchanged existing dependency paths/pins were used; no package was installed
or changed. Existing FastAPI/multipart deprecation warnings remain. No new local
frontend build or PostgreSQL run is needed for this operator-only change. README
and JMax are updated; PR69 amendment publication is owner-authorized, followed
by fresh CI and separate merge approval. Hosted work and credential,
grant and schema changes remain held.

## P1/P2 amendment validation

The corrected focused selection passed **56 cases**, covering all 55 claim/gate
cases plus the affected controller-guard diagnostic. The broad offline run
executed **1,904 cases** (832 tests plus 1,072 subtests): **1,903 passed and one
unchanged Windows process-timing test failed**. It expected a blocked callback
to start within a 1.5-second process envelope, but worker startup instead reached
worker_deadline. The complete unchanged process suite immediately passed **10/10**
on a serial rerun without code changes. These profiles overlap; the broad local
run is not represented as a fully passing run. Fresh full CI remains required.

The initial 207-case focused run passed 198 and failed nine. Corrections were
limited to test setup/assertions: reset injected low memory before checking
consumed-claim replay; expect the existing safe held category for seven invalid
role variants rather than exposing a non-allowlisted internal string; and let
the mandatory new post-claim guard complete before injecting a later parent
guard failure. No production memory/deadline/diagnostic guard was relaxed to
make the tests pass. Initial and corrected JUnit files are retained privately.

P1 tests prove claimed precedes checking, a running-floor refusal closes held
with zero intents and no start_dispatch reply, resource_guard_failed is fixed,
the claim cannot be reused, and storage/initial-flush failures remain uncertain.
P2 tests cover the default 21-request shape, owner/no-roster 13-request shape,
owner/staff shape, disabled-PIN variants, real-time/floor options, safe summary
fields and refusal of reordered/duplicate/unknown/empty roles before file creation.
Resource evidence remains version 2 and failure diagnostics version 1. Five
existing FastAPI/multipart deprecation warnings remain; dependencies and pins
are unchanged. No frontend, app route, database, credential, grant or schema
change is part of the amendment.

The fresh actual-clock/resource fictional loopback run prepared its profile
through the amended CLI (--roles owner --no-roster, configured PIN, 1536 MiB
operator floor). It passed all **13 requests in 139.453 seconds** with zero
fixture errors, all seven phases observed on both sides, confirmed owned cleanup
and journal closure, and all **143 source-file hashes unchanged**. The receipt
and closed journal agree on quietWaitGate. Its numeric **G2 did not pass**:
both quiet-wait minima were **1386.793 MiB**, below 1536 MiB while above the
unchanged running guards. Functional completion is not a qualifying rehearsal.
Do not reuse either these receipts or the original-head passing G2 as fresh
accepted-source, same-session G1 evidence. A new qualifying rehearsal and exact
live proposal/approval are still required after acceptance; no live packet was
prepared or activated here.
