# Receiving coordinator: local implementation and fictional acceptance

October 26, 2026. Accepted base: PR74, `826f54ef64c27367ffa55d35052c2c31ede7e610`.
This is a local-only candidate; publication requires the owner's requested prompt.

## Resulting behavior

The existing receiving installer has no backup-receipt input, and the new journal
backup proof requires `operations` to exist. One generic proof cannot safely cover
both sides of installation. The new coordinator keeps the phases distinct:

1. Authenticate a complete legacy six-schema archive through the unchanged v1
   reader, with independently expected archive/manifest/facts/restore-receipt
   digests, current source bindings, dependency policy and fresh windows.
2. Prepare an exact local plan using the accepted transactional installer, then
   bind its original baseline, source system/database identity, three exact
   payloads, consumer matrix and the pre-install proof. Recheck the archive and
   current database before application.
3. Require working-key closeout before applying. The plan retains only authenticated
   metadata and fingerprints, not plaintext archive rows or key bytes. It pins the
   working path's digest so a different missing filename cannot satisfy closeout.
   Deleting the key therefore does not require recreating it to recheck the archive.
4. After installation, authenticate a new seven-schema v2 archive and typed restore
   receipt, reconcile installed state read-only, and compare current complete data,
   catalogs, dependencies and authority against the verified post-install archive.
5. Remain at `verified_local_recovery_custody_closeout_pending` until the caller
   removes the post-install working key and supplies the required custody Boolean
   confirmations. Final result is `passed_local_transition_activation_held`.

The engine never moves/deletes keys or recovery databases, provisions roles,
activates the feature, changes runtime connections, reads live configuration,
retries migrations or opens a hosted connection. Its only source connection goes
through the existing explicit loopback/managed-marker refusal. A missing or
invalid post-install proof returns `installed_recovery_held`; it does not drop an
installed schema or imply that committed SQL was rolled back. Unknown commit
acknowledgements remain activation-held and require read-only reconciliation.
`featureActivated: false` reports that this consumer performs no activation; it
does not inspect or certify the current flags on a running hosted app.

## New files and preserved contracts

| Component | Responsibility |
| --- | --- |
| `backend/receiving_install_evidence.py` | Exact phase/identity/artifact/source/window validation, v1/v2 authentication, required consumer dispositions, operator attestations and key closeout. No configuration or database connection on import. |
| `backend/receiving_install_coordinator.py` | Local prepare/apply/reconcile/finish/closeout state transitions, unchanged installer delegation, read-only source equality and minimized failure results. No CLI or application route. |
| Offline tests | Authenticated fictional envelopes, profile substitution and semantic refusals, stale/source/target/digest/consumer/custody/reserve failures, unknown acknowledgement and later-window behavior. |
| Database tests | Actual six-to-seven installation and recovery across two independent fictional PostgreSQL clusters, with exact history replay and error-state checks. |
| Review runner and CI | Select the new cases; add one disposable PostgreSQL 17 recovery service with synthetic-only credentials. Existing action SHAs and the three required test jobs remain. No deployment step or secret is added. |

The accepted legacy backup/CLI/par code, PR73 installer/recovery and marker guards,
PR74 adapter/typed validator, current migrations/reference manifests, app routes,
UI, stock writers and feature flags stay unchanged. A new explicit inventory pins
the coordinator, reviewed engine/helper files and receiving SQL/reference inputs;
it is not attestation of the whole application, OS or third-party runtime. Core/local plan and
v2 backup formats remain separate; no legacy source pin is silently rewritten.

Plans and authenticated manifests are private operator records. Their role/target/
SQL/helper metadata must not be uploaded to chat, JMax or GitHub. Public evidence
contains only minimized statuses, code/test counts, timings and source digests.
Source digests bind the tested Windows checkout bytes. The public record also
records normalized Git blob digests, since CRLF normalization changes some bytes;
fresh CI remains required for the published checkout.

## Consumer and live prerequisites

The required local matrix names legacy backup, journal backup, par, source-index,
calibration, security-recovery and routine consumers. Each is explicitly supported,
completed or held with a caller-supplied owner-acceptance Boolean; a required
consumer cannot be held. These fictional declarations do not inspect live jobs or
establish real owner acceptance to disable an existing recovery path. The actual
supported/completed/held inventory remains a hard pre-H2 approval requirement.

Keep retained six-only par work before H2 or obtain a separate decision on its
disposition. Six-only post-install maintenance stays held until separately adapted.
The proposed initial routine backup policy remains approved writer-drained quiet
windows, with no schedule enabled here. S2a precedes administrative windows;
retained P1 and actual R1 qualification before H3 remain separate. This local
coordinator is not the future hosted executor and does not reopen the S1 harness.

### Remaining hosted deliverables before H2 (PR75 D1)

This checklist distinguishes implemented local safeguards from unimplemented hosted
execution. It is a proposal, not a live packet or authorization.

1. **Hosted installer adapter — not started.** PR73's installer remains literal
   loopback/UUID-test-database only. A separate reviewed adapter must preserve its
   exact-plan, managed-target and transaction protections for the actual target;
   the local implementation is not permission to point it at Supabase.
2. **Hosted transition coordinator or reviewed exact operator runbook — local
   rehearsal only; hosted delivery not started.** PR75's coordinator is also
   loopback-only. Bind real source/project/roles, phase-specific evidence, writer
   states, deadlines, custody and failure/reconciliation rules in the hosted path.
3. **Real seven-consumer matrix with owner acceptance — fictional rows rehearsed;
   real inventory not started.** Resolve legacy backup, journal backup, par,
   source-index, calibration, security-recovery and routine consumers as supported,
   completed or held. An active required recovery path cannot be held or broken.
4. **Qualified exact pre-install packet budgets — not started.** Export, restore
   verification, verified custody move/working-key deletion, plan checks and apply
   must fit the same original capture window, at most **2,700 seconds**, including
   a writer-restoration reserve of at least **600 seconds**. Initial planning caps
   are export 600 + restore verification 600 + custody move **120** + apply and its
   guards 600 + restoration reserve 600 = **2,520 seconds**, leaving at most 180
   seconds for all remaining preparation/receipt/operator work. The 120-second
   custody allowance is explicit but unqualified; actual transfer, independent-key
   access verification and local working-copy deletion must be measured before a
   packet uses it. A larger required allowance must fit by reallocating qualified
   phases within the same limit, not by shrinking the reserve or extending the
   window. **If the complete sealed budget does not fit, do not activate the
   packet.** Local fixture timing does not establish hosted margin, and this
   checklist does not add a global timeout to the frozen legacy restore.
5. **Post-install seven-schema/v2 proof — local rehearsal only; hosted proof not
   started.** Obtain a fresh authenticated export and independent disposable
   restore in a **separate approved, writer-drained window** after H2. Keep feature
   activation held through proof/custody closeout; never renew the expired
   pre-install capture or relabel its six-schema/v1 proof as v2.

Required order: **S2a -> P1 with retained six-schema tooling (or a separately
accepted disposition) -> deliverables 1–4 -> H0–H2 -> deliverable 5 in its separate
window -> actual R1 qualification -> H3**. The pre-install chain uses six-schema/v1
recovery; v2 is the post-install proof. Local feature-role LOGIN tests and inert
restore stubs are not actual R1. S2a, real credential/grant/schema changes,
service pauses, hosted installation and activation all remain separately held.

## Custody and authority limits

Closeout requires `keyMoved`, `separateKeyAccessVerified`, `restoreVerified`,
`localKeyCopyDeleted` and `retentionConfirmed`, all true, plus absence of the
specific bound working-key path (including a symlink entry). Other cleanup and
working-key privacy attestations are required when preparing each proof.
These are operator assertions combined with a local path check, not automated
verification of independent physical media, other copies, retention destruction
or forensic erasure. Final `forensicErasureVerified` remains false.

The rehearsal models a second key location using fictional temporary files on
the same machine. It does not certify independent real custody. Fixture keys,
archives, databases and stubs are owned and cleaned by the test harness.
Application password hashes and currently plaintext staff PINs remain sensitive
in real archives, including old archives after future PIN hashing. Carry PR74's
separate-custody and rollback-retention procedure into every later live proposal.

The source uses synthetic operational/accounts LOGINs. The independent restore
cluster uses ownership-preserving inert NOLOGIN stubs, without copying passwords.
Source feature-local LOGIN tests, restore replay and real operational R1 are
distinct claims. No real credential recovery, provider recovery, full native/account
permission qualification or operational release is established by this slice.

## Timing interpretation

The coordinator preserves the 45-minute window maximum, its ten-minute stage cap
and a minimum ten-minute writer-restoration reserve. Preparation and application
refuse when that reserve is reached. Current source/role/ledger/dependency equality
is still required; time remaining cannot excuse a failed guard.

Pre-install proof and post-install proof have independently bound windows. A later
post-install window can qualify the installed state without reactivating an
expired pre-install plan. The conservative four-operation ceiling plus reserve is
still 50 minutes before other work. Local phase measurements are fictional timings,
not hosted transfer measurements or permission to combine live windows. Plan split
windows unless an independently reviewed exact live packet demonstrates fit.

The backup/restore primitives are separate explicit operations, not launched by
this coordinator. In particular, the frozen legacy restore is not given a new
global timeout here. A future operator executor must supervise that operation
under its proposed budget; the four ten-minute figures are conservative planning
allowances, not a claim that this wrapper controls every older tool's runtime.

Final named full-chain fixture measurements after the timeout amendment:

| Phase | Seconds |
| --- | ---: |
| Legacy six-schema export | 3.469 |
| Legacy six-schema restore | 5.109 |
| Plan preparation and proof/baseline checks | 16.688 |
| Exact local application and guards | 25.625 |
| Fictional LOGIN and history exercise | 8.312 |
| Seven-schema export | 3.516 |
| Independent restore preparation | 0.610 |
| Seven-schema restore | 5.125 |
| Transition finish and post-proof checks | 13.593 |
| Full fixture chain with database closeout | 101.609 |

The four export/restore phases total 17.219 seconds. The aggregate includes setup,
custody modelling, deliberate failed-post-proof reconciliation, replay/assertions
and cleanup; selected component timings do not sum to the aggregate. It excludes
server startup/shutdown, real operator actions, independent physical-key transfer
and hosted latency. The final affected two-method PostgreSQL rerun took
168.174 seconds; the earlier all-five checkpoint took 234.737 seconds.

The final rerun server-launch checks passed at 1,293 MiB / 21.44% and
1,146 MiB / 19.00%. The full-chain fixture loaded samples were
942 MiB / 15.61% and 882 MiB / 14.62%.
These samples do not establish sustained live-memory qualification. The earlier
all-five run fell below 1 GiB after startup. No guard was lowered: retain the
1 GiB / 15% server-start gate and obtain more loaded headroom or an independently
approved execution arrangement before live work.

## PR75 review amendments and deferred interface note

The [independent review](https://github.com/jeffwelch0620-png/JayMax-Concepts-/pull/75#issuecomment-6430479145)
reported no blocking code defect. D1's explicit remaining deliverables, ordering
and custody allowance are added above and in the installation proposal. The
original head `e689f73` subsequently passed all four
[CI checks](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/40424814637).
Fresh CI is required on this documentation amendment before merge.

L1 is a low-priority interface consistency follow-up. The existing
`hosted_journal_backup.open_profile` contract is asymmetric: `LEGACY6` takes
**encrypted-file and key-file paths**, delegates to the frozen legacy reader and
requires `expected_project`; `RECEIVING7` takes **encrypted bytes and key bytes**
and delegates to `open_envelope` with its independently expected binding, digest
and dependency policy. Do not assume interchangeable input types. The existing
legacy-path compatibility test and receiving-byte envelope tests cover those
supported paths. Uniform path inputs, a path round-trip and explicit `Held`
normalization for wrong legacy input types remain a separate optional code slice;
none is claimed here. The advisory docstring edit is deliberately deferred with
that slice to preserve tested reader bytes and existing source bindings. D1 is
the review's merge condition; L1 is not reclassified as a blocker.

One review wording correction: outer timeout after engine entry or lost commit
acknowledgement returns `commit_unknown_activation_held`. An exception carrying
`commitAcknowledged=True` instead returns
`installed_reconciliation_required_activation_held`; both hold activation and
refuse automatic retry, but the known acknowledgement is not discarded.

The sibling JSON and its JMax Files copy remain the sealed **pre-amendment local
evidence snapshot at e689f73**. Its `acceptanceDocumentSha256` refers to that
commit's original document, not this documentation-only revision. No runtime,
SQL, test selection, source pin or execution authority changes in this amendment;
the PR and JMax track amended-head/merged-main CI and publication separately.

## Validation record

Validation and phase timings are recorded in the sibling
[local evidence record](RECEIVING_COORDINATOR_LOCAL_EVIDENCE_20261026.json).
The final broad offline run passed **2,189 reported cases: 907 methods plus 1,282
subtests**, with no failures/errors/skips (386.057 seconds). All five named
PostgreSQL methods passed at the earlier checkpoint; the affected full chain and
lost-acknowledgement methods then passed again after the timeout amendment
(168.174 seconds). The final focused selection passed **33 methods plus
102 subtests**. PostgreSQL cases use two independent fictional clusters and
explicit non-UTC source settings.
The broad run retained five inherited FastAPI/multipart deprecation warnings;
the focused/database selections retained the inherited multipart warning only.
No entire repository PostgreSQL profile or frontend build was rerun locally:
frontend and accepted engine/SQL bytes are unchanged, and fresh full CI remains
required after publication. All owned test servers stopped; fixture databases,
role stubs, working keys and temporary artifacts were cleaned by their owners.
Selections overlap and must not be summed as unique scenarios. An initial broad
offline run began before the final key-closeout adjustment and was stopped
incomplete under memory pressure after showing a failure. It is not a passing
current-code receipt; preserve its log as historical diagnostic evidence.

The initial database selection also collected eight imported installer regression
methods. It passed those eight and the new wrong-cluster refusal, but four new
cases failed because the coordinator compared the frozen installer's session-
dependent baseline after the backup reader had normalized timestamps to UTC.
The fix compares each oracle under its own settings within the same snapshot;
no source data or frozen engine is changed. The final selection removes the
accidental imported class and forces America/New_York on the owned source fixture
even when CI defaults to UTC. Its JUnit properties retain minimized phase metrics.
The next fail-fast rerun passed the changed-baseline refusal, then v2 correctly
refused an empty migration-file inventory supplied by the fixture. Both capture
fixtures now supply the reviewed receiving migration hash; the coordinator also
explicitly binds that manifest inventory to its expected receiving source digest.
The v2 guard was preserved. These initial failures are not passing final receipts.

The final audit also tightened outer-timeout classification: a timeout before
installer entry remains failed/held; after entry it is conservatively
`commit_unknown_activation_held`, because cancellation may obscure acknowledged-
commit cleanup metadata. Both positions are tested; no retry is authorized. The
affected PostgreSQL recovery/acknowledgement cases and full offline profile were
rerun after this change.

No frontend code changed. CI, independent review and merge remain later gates;
no new CI run is claimed before an approved push. Hosted testing and real
credential, grant, policy, schema, service, connection and activation changes
remain on hold. No live execution packet or maintenance window is activated.
