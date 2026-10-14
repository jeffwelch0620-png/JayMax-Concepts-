# Additive source-index installation rehearsal

PR25 is merged at **fbf06b7c9beda305ef42fb3b06d8215d165202bf**. All four CI
checks passed on refreshed head **53809e1** and on merged main. Migration 30
remains unapplied on Supabase. The first follow-up provides an incremental engine
and a disposable-only CLI in `backend/apply_additive_migration.py`; it is not a
hosted installation adapter or an operational release approval.

## Reviewed history and plan

The original successful installation receipt supplies the mapping between all
29 source files, their staged delivery versions and their executed SQL bodies.
Earlier ledger rows are preserved by full-row fingerprints. The hosted archive
records native delivery versions **20261008172951** through **20261008173019**;
these are separate from source filename dates and the apply-order numbers.
Local fixtures use separate fictional delivery versions and historical rows.

A read-only dry run refuses missing or extra versions, changed historical rows,
changed native statement bodies/names, incorrect delivery mappings and any
existing source index without a reviewed additive outcome. The prior installation
must pass readiness except for the two expected missing-index findings. Source
file checksums and executed-body checksums are verified independently. Migration
30 must also match the pinned runtime source manifest.

The resulting private plan contains database/actor identity, the complete ledger
fingerprints, original column identities, application-row fingerprints, catalog
metadata, the new delivery version and both migration checksums. It contains no
connection credentials, business row values or migration statement bodies.
Review and hash this file before applying; do not regenerate it silently after
another session changes the database. Changes to rows, catalog, identity or
history require a new dry run and review.

## Atomic application and independent recovery

Application uses one repeatable-read transaction, the existing installer advisory
lock **781340621**, an exclusive ledger lock and short SHARE locks on the
reviewed application tables. This first rehearsal deliberately preserves the
whole reviewed application projection; its lock scope is broader than the single
index build and must be assessed before a hosted adapter is authorized.
Lock waits are bounded at five seconds, statements at thirty seconds, and idle
transaction waits at 120 seconds. Metadata probes impose shorter query budgets.

The validated outer `BEGIN`/`COMMIT` are removed from the SQL file. The original
inner body, including its lock limit, is executed without changing its bytes;
the ledger insertion stays in that same outer transaction. Before commit,
verification requires the exact usable index, unchanged business rows/columns,
unchanged old ledger rows and unchanged catalog/permissions except for the new
index's relation, definition and two attribute rows.

A new read-only connection verifies the committed result. A lost commit
acknowledgement is **unknown**, never an automatic rollback or retry. Reconciliation
first takes the installer advisory lock non-blockingly, before opening its
consistent snapshot. If an original writer still owns that lock, the outcome
stays held rather than incorrectly reporting the invisible transaction as
unapplied. The verification lock is released explicitly on completion.
Reconciliation
from the retained reviewed plan reports either exact original/unapplied state or
the exact installed index and ledger outcome. Mixed, partial or changed states
hold for review. Applying an already-applied plan is refused; an exact read-only
reconciliation can still verify it.

SQL-body parsing is cached only by immutable file bytes. Every check rereads and
hashes the source files; changed bytes cannot reuse a previous parsed body.

## Disposable CLI

The CLI accepts only `NATIVE_PURCHASE_TEST_DSN` pointing to `127.0.0.1`, an
explicit port, user `purchase_implementation_test` and a
`native_purchase_test_*` database without URL overrides. Supabase and the normal
application connection are refused. The default safety boundary is enforced for
all three modes; library helpers are not exposed as application routes.

```text
python backend/apply_additive_migration.py dry-run --original-install-receipt <fictional-install-receipt.json> --delivery-version <new-14-digit-version> --output <new-plan.json>
python backend/apply_additive_migration.py apply --plan <reviewed-plan.json> --plan-sha256 <exact-file-sha256> --output <new-apply-receipt.json>
python backend/apply_additive_migration.py reconcile --plan <reviewed-plan.json> --plan-sha256 <exact-file-sha256> --output <new-reconciliation.json>
```

Keep plans and receipts outside Git. New evidence paths are required; existing
receipts are not overwritten. An interrupted process retains its original plan
for explicit reconciliation instead of blind reapplication.

## Validation and remaining hosted prerequisites

The new offline guards and disposable database tests cover source/delivery
checksums, true read-only preparation, completed application and fresh-connection
verification, rollback after a failed ledger insertion, lost acknowledgement,
already-applied refusal, changed or partial history, changed business rows,
unexpected indexes, other readiness failures, database identity, nested
application and lock contention. A shared fictional template contains a real
purchase/count/prep history with **$55 actual Food Cost**, preserved exactly by
the successful incremental application. This is separate from the hosted
fictional **$212** control, which this rehearsal does not query or modify.

The first attempted database suite had four failures: the catalog comparison
initially omitted the new index's two attribute rows, and one mutation fixture
used incompatible nested isolation. Both were corrected; its receipt/logs are
retained outside Git. The corrected focused run passed **30 reported cases**
(20 offline and 10 database). After adding active-writer reconciliation and CLI
mode coverage, the expanded final run passed **621 reported cases** with zero
errors, failures or skips: **218 offline test methods plus 351 subtests (569)**,
and **45 database test methods plus 7 subtests (52)**. The database selection
contains all **12 incremental installer cases**, the existing accounting/replay
checks and the full-chain backup/restore readiness checks. Exact read-only
preparation, original-row/catalog preservation, the full fictional **$55** report,
rollback, lost acknowledgement after commit and held reconciliation before an
unresolved writer disconnects all pass. CLI dry-run/apply/reconcile modes pass,
including changed plan-hash refusal and preservation of existing receipts.

Successful receipt **additive-source-index-tests-20261014T022756180722Z/receipt.json**
records unchanged starting role/database inventories and a stopped server.
Only fictional local databases were used; older unrelated failed fixtures remain
retained. The intermediate receipt and first failed log are preserved separately.
Frontend source is unchanged; the prior merged-head CI remains separate from
these local results. This follow-up is published as
[draft PR26](https://github.com/jeffwelch0620-png/JayMax-Concepts-/pull/26).
[All four initial-head CI checks pass at e1144cb](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/38503716266):
689 frontend tests across 67 suites and the strict build, 45 database methods
plus 7 subtests, 218 Windows offline methods plus 351 subtests, and the aggregate
check. The publication-only test cleanup removes one trailing blank line and
retains identical parsed code. The PR check panel is the current-head authority;
the original local acceptance and review manifest remain immutable checkpoints.

Before hosted DDL, prepare a separately reviewed adapter that pins the intended
Supabase build project and administrative connection, fresh private backup and
isolated restore evidence, original installation receipt and reviewed plan hash.
The hosted adapter must also pin the migration ledger's column/default, unique
version constraint and access metadata; local fixture ledgers use a version
primary key, and the engine's existing ledger-shape check is limited to the
required column types and unexpected mandatory fields. Review the maintenance
window and lock scope, retain uncertain-commit evidence,
and obtain explicit hosted installation approval. Then independently inspect
readiness and recheck current-source reads plus the closed **$212** accounting
control. Do not replay the fresh 30-file installer, change existing connections
or import real vendor invoices as part of this work.
