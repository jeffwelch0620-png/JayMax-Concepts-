# Guarded reviewed-par installer and local rehearsal

**PR47 accepted tooling:** owner-approved merge `a7270ca` matches tested `755aff3`
exactly and has green reviewed-head/merged-main CI. The [new preflight](PR47_DIRECT_MAINTENANCE_PREFLIGHT.md)
prepares separately approved read-only validation, then a fresh window,
backup/disposable restore and exact-plan application approval. Earlier local/draft
statuses below remain history. No hosted execution occurs in this preparation.

**Local follow-up under review:** [maintenance-only direct IPv6](MAINTENANCE_DIRECT_IPV6.md)
adds an explicit operator option and separate private maintenance URL for export
and this adapter. The app's saved connection and all writer, backup, plan-hash,
timeout and reconciliation gates remain unchanged. Pending reviews/plans need
new source hashes after acceptance; no hosted execution is included.

**Latest hosted checkpoint:** the [October 18 window](REVIEWED_PAR_WINDOW_20261018.md)
closed early with writer drain held. API and Toast controls are restored; no
fresh backup/restore, executable plan or schema application was started. Resolve
operator/pool session ownership read-only before proposing another window.

**Merged checkpoint:** owner-approved PR46 merged as `f762808` from `31f65c3`.
Reviewed-head and merged-main CI passed all four checks. The
[maintenance preflight](REVIEWED_PAR_MAINTENANCE_PREFLIGHT_20261018.md) records
deployment and local input/evidence checks. Draft publication/merge gates below
describe the earlier local stage; a new hosted window, fresh backup/restore and
separate exact-plan application approval remain open. No hosted SQL was applied.

Local follow-up to owner-approved PR45 merge `9dac63e`. The owner authorized
building the installer and disposable local rehearsal, requested a prompt before
publishing a draft PR, and reserved every Supabase application for separate
approval. This is not a maintenance window or an operational release.

## Scope and entry points

`tools/ops/apply_reviewed_par_migration.py` is a par-specific core, not a generic
SQL runner. `tools/ops/hosted_reviewed_pars.py` is its manual hosted envelope.
Neither is imported by application startup or exposed as an API route. The old
source-index engine/adapter and historical receipts are retained unchanged.

The only SQL input is migration 31, `20261018_reviewed_inventory_pars.sql`:

- Raw SHA-256 `84814517f75bb58940a36facdbf5a7934036ff5b388e97a820038e837416506e`.
- Verified body SHA-256 `3a189a8b2a352cbd560cea88194dbde1940f160a54e7bcd4616d719c47b88c48`.
- Catalog reference SHA-256 `8a18effb17929604c76817ed7478b112033df4886e4434c0c1e6a4cce01e8e17`.

The catalog reference is generated from actual migration execution on disposable
PostgreSQL 17, with existing object preservation checked by multiset subtraction.
It includes seven relation records (table plus six indexes), 28 column records
(including index attributes), 17 constraints, one guard function, three user
triggers, 12 internal foreign-key trigger records and six index definitions.
Existing index validity/ready/live flags are frozen in the baseline. Every new
par index must also have the expected uniqueness, primary/immediate and other
state flags; identical deparsed SQL alone is insufficient. Security primitives
are imported from the unchanged historical hosted adapter, with a regression
checking their identity; the new wrapper does not fork those checks.

Only the executing owner identifier is normalized; definitions, RLS, privileges
and trigger states are not ignored. A different PostgreSQL major version holds
until a separately reviewed compatible reference exists. This is intentionally
stricter than table presence or a blanket purchasing-schema exclusion.

Column ACLs and application/global default privileges are preserved separately:
table-level grants alone cannot prove these unchanged. The migration introduces
no column grants or default privileges. Role attributes and memberships remain
part of the unchanged ledger-security baseline.

The new table must be empty at installation reconciliation. No old ambiguous par
is backfilled, no zero is auto-confirmed, and no business row or store revision
is changed by installation. Once later par commands legitimately append rows,
this maintenance reconciler must not be reused as a routine application-health
check; use a separately scoped post-acceptance record instead.

## Prior installation and source bindings

Preparation verifies the successful original 29-file delivery and its earlier
ledger fingerprints, plus the retained **source-index core plan** from its
approved installation. For a retained hosted source-index envelope, extract its
unchanged `core` object into a new protected private file and review/hash that
file; never pass the envelope or rewrite the original receipt. The par tool
validates original-delivery agreement, source-index raw/body hashes and the live
installed index/name/body/history, without comparing current business data to
an obsolete source-index snapshot or replaying its SQL.

Every installed ledger version must be accounted for. No missing, changed or
extra version is repaired. The new 14-digit delivery version must exceed every
actual installed version. A fresh baseline binds identity, rows, columns,
catalog/security, ledger metadata, current-source hashes, pinned reference and
server major. Plans and receipts have distinct strict formats; arbitrary SQL,
changed source, extra plan fields and true execution/release flags are refused.

## Hosted prerequisites and envelope

The public command requires Windows, Python 3.12+, PowerShell 7, private
current-user/SYSTEM-owned artifacts and the existing certificate-verified
administrative Supabase direct/session endpoint. It does not change the saved
Render application connection, buy IPv4 or switch credentials. Transaction pool
6543, endpoint override options and wrong project/actor/TLS are refused.

Private review format is `jaymax-hosted-reviewed-par-review-v1`; the generated
hosted plan is `jaymax-hosted-reviewed-par-plan-v1`, containing the distinct
`jaymax-additive-reviewed-par-plan-v1` core. Original index plans/reviews cannot
be supplied as par plans. Keep all real paths, identifiers and backup/key
material in the protected local operator folder, outside Git/Drive/Pages.

```json
{
  "format": "jaymax-hosted-reviewed-par-review-v1",
  "projectRef": "<designated-build-project>",
  "deliveryVersion": "<new-reviewed-version-after-current-ledger>",
  "clientRoles": ["anon", "authenticated"],
  "writerLoginRoles": ["<deployed-login>", "<other-reviewed-application-logins>"],
  "budgets": {"lockSeconds": 5, "probeSeconds": 20, "ddlSeconds": 30,
    "idleTransactionSeconds": 120, "operationSeconds": 600},
  "maintenance": {"startsAt": "<approved-UTC-start>", "endsAt": "<approved-UTC-end>",
    "reference": "<new-owner-approved-window>", "allWritersStopped": false,
    "inFlightDrained": false},
  "originalReceipt": "<private-original-install-receipt>",
  "originalReceiptSha256": "<exact-sha256>",
  "sourceIndexPlan": "<private-retained-source-index-core-plan>",
  "sourceIndexPlanSha256": "<exact-sha256>",
  "backup": {"encryptedFile": "<new-private-archive>", "encryptedSha256": "<sha256>",
    "keyFile": "<separate-private-key>", "restoreReceipt": "<new-private-restore-receipt>",
    "restoreReceiptSha256": "<sha256>"}
}
```

The template deliberately does not assert that writers are stopped. A complete
writer inventory and a new approved window are required, including a fresh
Companion/manual-writer confirmation. No expired approval is reused. Preparation
requires an authenticated encrypted application backup made after drain inside
that window, matching current migration hashes and a successful disposable
restore. Managed Supabase Auth/Storage/Vault recovery is not established.

Application also requires at least **660 seconds remaining** (the 600-second
operation budget plus a one-minute recovery reserve); the parser's accepted
10-to-60-minute duration range does not mean a ten-minute window can qualify.
Choose the actual window after measured rehearsal timing and leave more recovery
time where needed. No provider notice or paused producer is assumed current.

## Transaction, preservation and recovery

The adapter refreshes full writer/activity visibility before locks, under locks
before DDL and before COMMIT. Quiet sessions are supplementary evidence, not a
mechanism for preventing disconnected writers from returning. Unknown write
transactions and hidden/disabled activity hold. No platform session is killed.

The core acquires the unchanged installer session lock `781340621`, starts its
own transaction, locks the ledger and reviewed existing tables **before the
first repeatable-read snapshot**, and rechecks the exact baseline. The existing
SQL lexer removes only the outer BEGIN/COMMIT; one outer transaction creates the
new objects and inserts exactly one ledger row with the verified body. Precommit
verification checks the full allowed catalog delta, old rows/columns/history,
new empty table and current 31-migration readiness. The hosted guard also checks
the broader backup's materialized rows, sequences and unchanged catalog groups.

After a known commit, a fresh connection independently reconciles. Losing a
commit/rollback acknowledgement or interruption preserves an unknown result and
the exact plan hash. A private progress receipt is written before sending DDL.
No automatic retry, DROP repair or history rewrite occurs. Reconciliation can
run after the old window expires but holds while the original writer owns the
session lock. An already-applied plan is refused by application.

The timeout budgets are unchanged: lock 5 s, probes 20 s, DDL 30 s, idle
transaction 120 s and operation 600 s. Do not lengthen them to make a held run
pass. Restore exact producer states only after a known, verified outcome; see
the [maintenance and failure plan](HOSTED_REVIEWED_PAR_MIGRATION_PLAN.md).

## Manual command contract - not execution approval

Each invocation needs a new protected output directory in the existing
`%LOCALAPPDATA%/JayMaxBuild/backups/backup-<32-lowercase-hex-uuid>` convention.
Use a private owner dotenv file; never pass a URL/password as a command argument.

```text
python tools/ops/hosted_reviewed_pars.py dry-run --owner-config <private-owner-env> --expected-project <ref> --review <private-review.json> --review-sha256 <review-sha256> --output-directory <new-private-output>
python tools/ops/hosted_reviewed_pars.py apply --owner-config <private-owner-env> --expected-project <ref> --review <private-review.json> --review-sha256 <review-sha256> --plan <retained-plan.json> --plan-sha256 <exact-plan-sha256> --approve-plan-sha256 <separately-approved-same-hash> --output-directory <another-new-private-output>
python tools/ops/hosted_reviewed_pars.py reconcile --owner-config <private-owner-env> --expected-project <ref> --review <retained-review.json> --review-sha256 <review-sha256> --plan <retained-plan.json> --plan-sha256 <exact-plan-sha256> --output-directory <another-new-private-output>
```

The code checks supplied approval hashes; it cannot grant human approval.
Prompt the owner after a concrete plan is generated and before application.
Publication or merge of this tool does not authorize a window, backup, hosted
dry run or application. Future restricted-role grants/RLS policies and credential
cutover remain O1 work; no new runtime access is silently inherited.

## Validation record

Local acceptance is complete, with draft publication approval still pending.
All tests use fictional data and synthetic credentials. No Supabase connection,
real invoice import or active app configuration is used.

| Final evidence | Result and counting boundary |
| --- | --- |
| Split A, `reviewed-par-installer-a-20261018T230954623691Z` | All 17 methods plus 28 subtests passed: 45 reported cases. Includes the final column/default-privilege guards and unknown-rollback receipt case. |
| Split B, `reviewed-par-installer-b-20261018T225622356310Z` | Six methods plus their 14 subtests passed: 20 selected cases. The whole run is **not green**: the restore method failed its fixture database-name guard after three history subtests passed. That entire four-case restore slice is excluded here and replaced by the corrected rerun below. |
| Corrected restore, `reviewed-par-installer-r-20261018T230627765737Z` | One method plus three subtests passed: four cases. Real encrypted export, authenticated readback and disposable `pg_restore` retained both tiny-decimal/confirmed-zero par versions, immutable-history enforcement and the exact $55.00 fictional Food Cost report. |
| Disjoint targeted coverage | **24 methods plus 45 subtests: 69 reported cases**, covering every new test method across the selection and corrected restore rerun. Counts from earlier/smoke runs are not added. This is not a claim that the failed whole B run passed. |
| Full offline profile, `reviewed-par-installer-offline-20261018T231934811535Z` | **328 methods plus 617 subtests: 945 cases passed**, no errors/failures/skips. Both unchanged Windows ACL cases passed in this run; their earlier startup timeouts remain historical. This profile overlaps the targeted guards and is not added as unique coverage. Five existing deprecation warnings remain. |
| Static/source checks | Python compilation, generated review guides, relative documentation links and whitespace passed. Accepted SQL bytes, original index tools, runtime permission candidate/implementation and application server remain unchanged against PR45 merge `9dac63e`. |

Completed database-run receipts prove the starting database/role inventories
were restored, the owned loopback PostgreSQL server stopped, and no hosted
connection was used. External evidence is retained under the local work folder;
`reviewed-par-installer-final-validation.json` audits method coverage, receipt
hashes, protected sources and non-overlapping count selection. Reference
generation separately passed with the same owned-cleanup checks. A fresh hosted
backup/restore, independent review/CI, merge and exact-plan approval remain open.

The selected CI profiles include the new par plan/receipt guards and database
cases, alongside the existing historical index guards. Frontend code is unchanged;
these tests do not claim hosted par UI acceptance. Ordering remains manual and
Track 1 accounting remains independent of par, prep and sales explanations.

Earlier unsuccessful attempts remain part of the validation record:

- The first broad run reached its 1,200-second runner limit without a complete
  report. An imported historical fixture class was being collected as tests;
  the new module now imports only its fixture operations. A typed-column
  comparison defect was also corrected. This run is not reported as passing.
  Exact run-owned databases/roles were removed after checking the recorded
  inventory; unrelated pre-existing test databases and roles were preserved.
- The first split A run reported 39 passing cases and one failure. Identical
  catalog reads differed with the caller's search path. Snapshot reads now own
  or nest a consistent transaction and normalize deparser settings; strict
  fingerprint equality was retained.
- The first B attempt stopped on an ambiguous numeric multiplication in the
  fictional history insert. Its placeholders now have explicit numeric casts.
  The second B attempt reached the backup schema guard: the original native
  fixture predates the empty hosted `integrations` schema. The restore fixture
  now creates that missing fictional schema before planning, and asserts no
  unclassified schema exists. Neither backup scope nor its guard was weakened.
- The third B run passed its other six methods and 17 subtests, including the
  append-only history refusals, and completed real encrypted export. Restore
  then refused the fixture's database-name prefix. The fixture now uses the
  existing required `native_purchase_test_backup_<32-hex-uuid>` convention;
  restore naming/empty-target guards remain unchanged. The corrected restore
  method is rerun separately rather than counting this whole run as green.

Completed runner receipts retain before/after database and role inventories,
owned-server shutdown and the no-hosted-connection boundary. The final coverage
record supersedes those failed attempts; it does not turn them into passes.
