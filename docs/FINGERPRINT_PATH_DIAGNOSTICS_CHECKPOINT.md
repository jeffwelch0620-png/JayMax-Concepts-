# Fingerprint path diagnostics follow-up

## Accepted baseline

PR32 merged with owner approval at **7b616204852217ca31c5ce352bdc67043899902a**.
Refreshed documentation head **3d1eaccd4b38993bd099302ef745d14782b31efc** passed
[all four CI checks](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/38674779748):
689 frontend tests/build, 728 offline cases and 79 full PostgreSQL cases.
[Merged-main CI](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/38675114565)
also passed all four checks.
The current local branch is `codex/backup-fingerprint-path-diagnostics`.

## Diagnostic contract

`backupDiagnostics.fingerprintPaths` contains only allowlisted nonnegative
integer counts, each bounded to one billion:

| Field | Meaning |
| --- | --- |
| `serverAggregateRelations` | Complete relation accepted from the bounded aggregate. |
| `cursorFallbackRelations` | Full size probe discarded, followed by a completed full cursor read. |
| `cursorOnlyRelations` | Completed sequence, legacy raw-row or explicitly cursor-selected read. |

Counts advance only after the selected path finishes. A failed aggregate or
partially read cursor does not increment a completed-relation count. Held exports
may therefore retain partial counts; those counts are never proof of a complete
backup. Counts are scoped to the current export, contain no relation names, and
are excluded from manifests and fingerprint equality comparisons. Calls outside
an export, including ordinary restore verification, have no export counters.

For a completed default current-format export, `cursorOnlyRelations` should
equal the number of sequence entries (`kind == 'S'`) in the manifest. Zero
`cursorFallbackRelations` is expected for the previously measured small dataset;
a future nonzero count means a relation safely reached the size fallback, not
that its backup is corrupt. Completed path counts sum to the manifest relation
count, including sequences and the existing partition relation semantics.

The existing diagnostics sanitizer rejects booleans, negative/excessive numbers,
floats, strings and unknown keys. Old diagnostics without this optional field
remain readable. No archive version, hash algorithm, SQL behavior, connection,
role, migration, client/server timeout or hosting setting changes.

## Validation

The source-frozen run completed at **2026-10-15T03:55:58Z** (October 14,
11:55:58 p.m. EDT):

- **741 offline cases** (285 methods and 456 subtests), zero failures/errors/skips.
- **79 full PostgreSQL cases** (64 methods and 15 subtests), zero failures/errors/skips.
- Source hashes matched before/after; database and role inventories were unchanged,
  and the owned local server stopped. No hosted connections or real invoices used.
- Only five existing dependency deprecation warnings per selection remained.
  The full database run took 2,495.57 seconds on Windows; this is suite duration,
  not a hosted fingerprint timing measurement.

Tests exercise successful and failed paths, export isolation, safe diagnostics,
real below/at/above-boundary counters, sequences/legacy data, and real encrypted
export/restore with matching optimized/cursor table and catalog fingerprints.

Receipt SHA-256:
`c5b719f8f7ecc306d1f264c466b75d3601a35850e8131beabacfcded0d83b65f`.
JUnit/logs and frozen source hashes are retained locally. Frontend code and
migrations are unchanged; frontend tests/build were not rerun locally.
[PR33 CI at reviewed head 28fad50](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/38679036355)
passed all four checks: 689 frontend tests across 67 suites and production build,
741 offline cases, and 79 PostgreSQL cases, with no failures/errors/skips.
The owner approved the small documentation/test polish and merge. The real-export
test now also checks that completed counts sum to the manifest relation count
for both optimized and cursor-selected exports. Amended-head CI must pass before
merge; the original source-frozen receipt above remains historical evidence.

The amended real encrypted export/restore case passed locally with its new
total-count assertions: **1 targeted PostgreSQL case**, zero failures/errors/skips,
source hashes unchanged, database/role inventories unchanged and local server
stopped. No hosted connection was used. Receipt SHA-256:
`aa4010f40d2587c38ce8697ff6d96b78dc6cc41e86934a3dadc860953f48706c`.
The full selection is checked by amended-head CI rather than repeating the
41-minute Windows suite for this test-only and documentation amendment.

## Next hosted rehearsal remains separate

Retain the 60-second client command budget and the existing export budget. A
bounded aggregate is one statement; a large relation may still spend time on
the bounded probe before its full cursor scan. Record actual fingerprint-phase
duration, all path counts, relation/row counts and effective client/server limits
in the next separately approved maintenance window. Historical 158.9/181.0-second
observations have differing source/environment conditions and do not prove the
cause of the earlier stall or establish a controlled performance benchmark.

The previous maintenance window remains closed. Fresh writer inventory/drain,
canonical encrypted backup with verified disposable restore, hosted pooler
cancellation checks and separate exact-index-plan approval remain required.
The restricted deployed runtime-role gate stays OPEN before operational use;
current build deployment/connection choices stay unchanged. No hosted database,
jobs, credentials or Companion changes are included. Prompt before pushing a
new draft PR for independent review.
