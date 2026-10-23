# Local read-only health and calibration probe — October 23, 2026

## PR59 publication and generated-artifact ownership follow-up

The owner approved publication as
[draft PR59](https://github.com/jeffwelch0620-png/JayMax-Concepts-/pull/59)
at tested head `70bbc85`. Its first CI run passed frontend/build and backend
checks, but the Windows ACL fixture exposed a fresh-file ownership difference:
an elevated Windows process can assign its administrator group as owner even
inside a protected directory. The existing verification correctly held.

The follow-up exclusively creates each new claim/receipt, explicitly assigns
current-user ownership and current-user/SYSTEM-only protected ACLs, then applies
the unchanged verifier. It never repairs a supplied/existing artifact or
credential; an existing path refuses before any ACL operation. Failed preparation
retains the fresh artifact, closes its handle and stops before configuration or
network access. The receipt handle stays bound to that exclusive creation.

The focused follow-up passed **65 cases** (20 methods + 45 subtests) in 23.21
seconds, including real Windows generated-artifact ACL handling, broad-grant
refusal and existing-file no-overwrite/no-repair coverage. The fresh broad
offline rerun passed **1,443 cases** (495 methods/items + 948 subtests) in 92.95
seconds, zero failures/errors/skips. Profiles overlap. No database/SQL/application
behavior changed; the earlier 18-case owned PostgreSQL preservation run remains
applicable local evidence, not a fresh hosted observation. Corrected-head CI
remains separate from the first failed run.

The corrected 91-source public health packet verifies with execution approval
false; SHA-256
`c8d80ea8bbd0527851463136991236cae21ea18bf56be9c56324147713cd47c2`.
Earlier packets below are retained superseded evidence and cannot authorize
execution. Hosted execution, service controls and real credential/grant/schema/
connection changes remain held. Fresh CI and merge approval stay separate.

## Original local scope and approval boundary

The owner approved implementation/testing of the
[reviewed local design](READ_ONLY_HEALTH_CALIBRATION_PROPOSAL_20261023.md), based
on accepted PR58 main `3bdf8be` and the local proposal commit `437c5c5`.
No hosted request, credential/configuration read, service control or real
credential/grant/schema/connection change was performed. Disposable database and
temporary filesystem fixtures are fictional. Hosted execution remains held.

The new [operator library](../tools/ops/read_only_probe.py) is separate from
the installer and application pools. Its CLI only creates/checks public packets;
there is no CLI run shortcut. `execute_approved` requires a fresh, exact-stage
owner approval, complete source binding, private evidence directory and resource
checks before any configuration/network access. No approval was generated here.

## Implemented behavior

- Health: one anonymous certificate-verified fixed-endpoint GET, environment
  proxy/cookie/auth avoidance, no redirects/retry, 20-second connect / 90-second
  total limits, 4 KiB identity-encoded response bound, duplicate-key refusal and
  exact JSON signal. A pass is preliminary pool-presence evidence only.
- Calibration: existing separate maintenance configuration and direct IPv6/TLS
  connector; one owned connection, default/effective read-only checks and an outer
  repeatable-read snapshot. Complete current column/relation discovery is either
  explicitly approved or matched to a reviewed inventory digest. Both existing
  hash formats retain two-relation batching, full fallback, sequences and catalogs.
- The observer covers each query/await, cursor exhaustion and full cursor
  lifecycle envelopes, with per-family maxima. It stops on a completed duration
  above 10 seconds or failed/incomplete coverage. It never treats cursor API
  counts as network round trips or driver await as server execution time.
- Work is capped at 600 seconds, with bounded resource monitoring/cancellation,
  snapshot rollback and owned-client close/termination fallback. Cancellation
  propagates, including during close. No backend termination or reconnect.
- Existing private files/ACLs are verified, never repaired. Fresh claim/receipt
  files are verified before network access; an exclusive claim consumes the
  approval in its bound directory. A retained exclusive receipt handle prevents
  reopening/overwriting earlier evidence. Ambiguous cleanup holds. Only the
  trusted local operator may supply approval; this is not a new remote auth service.
- Private receipts retain snapshot/transport facts, exact inventory, independent
  hashes, per-read outcomes, typed timeout/SQLSTATE and cleanup categories. Public
  output is an explicit fixed-category/count/timing allowlist. Evidence is capped
  at 100,000 observed events; complete coverage is mandatory, never sampled.
- Source packets conservatively bind all non-test Python/SQL/CA files beneath
  backend and tools/ops, plus backend requirements and the reviewed proposal.
  They do not import application startup, read secrets or grant execution approval.

## Local validation

The broad offline profile passed **1,439 reported cases** (492 methods/items plus
947 subtests), with zero failures/errors/skips, in 145.84 seconds. The initial
broader run failed six unchanged proxy-pipeline checks because the local path
selected Uvicorn 0.54.0 instead of repository-pinned 0.25.0. Reusing the existing
pinned local package corrected the environment; no dependency/requirement was
changed. An early focused run also exposed an unnecessary database-module import
on the health-error path; timeout metadata imports are now calibration-only.

Final focused validation passed **64 reported cases** (19 methods plus
45 subtests), zero failures/errors/skips, in 15.92 seconds. This includes actual
Windows private-evidence ACL acceptance and broad-read-grant refusal on temporary
fictional files. The focused selection covers the final receipt-handle,
connection-monitor, simultaneous primary-error preservation, durable claim and
cleanup-cancellation refinements after the broad run;
totals overlap. The original public health packet was generated and checked locally
before publication with every execution approval false. Its 91 source bindings
verified; packet SHA-256 is
`1144b5f3e0b24e2aa681108765194ad51bfd69e139bcdb57e3e379cb10ff521a`.
The first locally generated packet is retained as superseded by the final guard
refinements; it is not current execution evidence or authority.

The guarded PostgreSQL run passed **18 reported cases** (seven methods plus
11 subtests), zero failures/errors/skips, in 35.10 seconds. Loaded start memory
was 1,604.7 MiB / 26.6% free, after the earlier below-floor observations held
startup. It verified exact parity with independent original/backup oracles,
aggregation/cursor fallback/sequence coverage, missing-inventory/result refusal,
read-only DML/DDL/sequence-advance denial, timeout/cancellation/resource rollback,
and stopping before the later family on failure. Original database/role inventories
matched after cleanup, owned server stopped, zero hosted connections used.

Retained local evidence (outside Git): `probe-offline-final-20261023.xml`,
`probe-offline-final-guarded-focused-20261023.xml`, and
`readonly-probe-database-20261023T143105337811Z/database.xml` plus its owned-run
receipt/inventories. No new frontend/build run is claimed for this tooling-only
slice. Fresh CI remains a publication gate, not hosted proof.

## Next gates

The owner approved pushing draft PR59; obtain independent review and fresh CI
at the corrected head. Merge remains separate. Only later may the owner approve an exact
health packet. Review that result before preparing/approving the calibration
packet bound to its fresh private health receipt and exact target/scope.
The API and Toast stay running. No maintenance window or installation authority
exists. The 450-second installation planning screen, fresh writer confirmation,
backup/disposable restore, exact-plan approval, credential/grant holds and
functional acceptance remain separate. Ordering manual, par editing frozen and
Track 1 independent; O1/G04/G13 and managed recovery remain open.
