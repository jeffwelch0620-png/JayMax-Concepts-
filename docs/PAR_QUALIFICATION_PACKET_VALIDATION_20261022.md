# Local qualification packet validation

## Result and scope

The source-bound supervised handoff is ready for independent review. It builds
and verifies local public-source packets and never invokes the stored commands.
All approvals remain false, window times remain unbound and hosted execution is
held. See the [operator guide](PAR_QUALIFICATION_EXECUTION_PACKET.md) and
[maintenance proposal](REVIEWED_PAR_MAINTENANCE_PROPOSAL_20261022.md).

The change adds one standard-library-only local tool, fictional tests, offline CI
selection, public source pins and a newline attribute for the new pin manifest.
Existing application code, the 31 migration bodies, catalog/permission candidate
content and hosted installer/export/restore implementations are unchanged.

## Test evidence

| Run | Result |
| --- | --- |
| Initial focused packet suite | 23 unittest methods passed before the additional proposal-newline case and checkout-neutral fixture strengthening. |
| Initial full offline profile | 1,260 reported cases: 6 failed and 1,254 passed (437 ordinary/parameterized cases plus 817 subtests). Six existing proxy-pipeline cases refused local Uvicorn 0.54.0 because requirements pin 0.25.0. No source/assertion/requirement relaxation was used. |
| Final complete offline rerun | **1,261 cases passed: 444 ordinary/parameterized cases plus 817 subtests; zero failures, errors or skips.** The existing local `g04-uvicorn025-libs` was put first on the test path. This includes the final 24 packet test methods and their subcases, existing packet-neighbor installer/writer/backup guards, both Windows ACL cases and CI runner isolation. Runtime 68.74 seconds; five existing dependency/startup deprecation warnings. |

The final run used `tools/run_review_tests.py offline` with a new JUnit evidence
file, dotenv disabled and hosted connection variables scrubbed by the existing
runner. Initial and final XML files are retained separately outside Git. Profiles
overlap and their counts must not be added together. Generated review guides
matched source. No frontend or database-server suite was rerun for this local
handoff-only change; no application/SQL behavior was edited.

## Integrity and boundary checks

- Validate the pinned October 22 proposal and 49 accepted core sources; compare
  accepted Python/JSON content with LF/CRLF equivalence only. All SQL hashes stay
  exact. A new output binds the actual bytes of all 56 source files and proposal.
- Refuse changed/missing source, altered pin manifest, unsafe source paths/links,
  incorrect external artifact hash, rehashed command/approval tampering,
  false/zero type substitution, duplicate/nonfinite/malformed/oversized JSON and
  attempts to overwrite earlier output.
- Check timing preserves the full qualification and restoration budgets and that
  the only command templates are accepted export, isolated verify-restore and
  read-only dry-run modes. The tool has no activate/apply/execute mode, network,
  subprocess, credential loader or service-control capability.
- Verify CLI prepare/verify receipts remain local-only; no live readiness or
  approval can be inferred from successful file verification.

Actual packet generation/verification uses a new file outside Git after the
candidate is committed, with its exact packet hash retained separately alongside
the source revision. A packet is checkout-specific; later byte changes require a
new reviewed handoff, not an edited hash or bypassed verification.

Supabase/Render were not accessed, service controls were not changed, credentials
were not read or altered, and no local PostgreSQL server/database was started.
Shared JMAX updates report this local progress without implying hosted testing.
Fresh CI, draft publication, merge, maintenance execution and any later exact-hash
schema application retain separate approval gates. Resource/writer/owner checks
must be renewed before a future window. Ordering remains manual and par editing
frozen; O1/G04 and operational release remain open.
