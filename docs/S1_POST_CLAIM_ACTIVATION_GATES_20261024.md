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
not_created; a partial write or later journal-opening error remains
creation_unconfirmed. No blanket exception catch calls a partial claim unused.
Existing uncertain-callback behavior still avoids a raced final journal write.

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
   The CLI prepare command defaults to the full shape; use the reviewed
   equivalent prepare API/builder with explicit roles/roster/PIN arguments for
   reduced variants. Never assume the default is owner-only or hand-edit a
   sealed profile to make its shape appear to match.
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

## Coordination and validation

S2a credential-retirement planning and P1 preparation may proceed alongside S1
diagnostics, with their own consumer/recovery evidence and separate live
approvals. Credential work stays separate from par maintenance. Inventory is
the stock writer; Track 1 remains independent, pars frozen and ordering manual.
G04/G13/O1, identity/permissions and live acceptance remain open.

Final local validation passed **1,889 offline cases** (817 tests plus 1,072
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

This is local candidate validation, **not G1 live qualification**: the candidate
is not yet accepted/merged, no new live packet is sealed, and the required
same-session rehearsal must be fresh immediately before a separately approved
live proposal. Numeric G2 success alone grants no execution authority.

The unchanged existing dependency paths/pins were used; no package was installed
or changed. Existing FastAPI/multipart deprecation warnings remain. No new local
frontend build or PostgreSQL run is needed for this operator-only change. README
and JMax are updated; prompt before the next draft push, then fresh CI,
independent review and separate merge approval. Hosted work and credential,
grant and schema changes remain held.
