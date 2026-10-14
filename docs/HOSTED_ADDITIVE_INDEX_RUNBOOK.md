# Hosted source-index adapter and maintenance procedure

PR26 merged with owner approval at **51b0f6d1bd9cab69b0dc8c76ac111ec4058e9546**
on October 13, 2026 (23:24 EDT). Its reviewed head **332f154** passed all four
Inventory CI checks: 689 frontend tests/build and 621 reported backend/offline
cases. This follow-up prepares an adapter; no hosted execution is authorized by
its preparation, publication or eventual merge. Migration 30 remains unapplied
by this workflow. The live Render deployment commit has not been verified here.

## Connection and scope

Run `tools/ops/hosted_additive_index.py` manually from the complete local checkout.
It is outside Render's `backend` root and has no app route or deployment hook.
The shared additive engine has moved to `tools/ops/apply_additive_migration.py`;
existing installation/backup support modules remain in backend for their existing
consumers. Retiring that older operations dependency tree is separate work.

Keep the existing Render/Supabase connection standard and private credentials.
The adapter reads a separate existing administrative dotenv file; it never rewrites
the app's configuration. Only a designated Supabase owner direct/session endpoint
on port 5432 is accepted, with certificate and hostname verification. Transaction
pooling on 6543 and URL option overrides are refused. This procedure relies on a
single stable backend session for advisory locks, snapshots and transactions.

Supabase documents session mode as an IPv4 alternative to direct connections.
Its general recommendation for migrations/backups is direct mode; the current
build's session mode therefore still needs an explicit connectivity/session
rehearsal at the hosted approval stage. Preparation does not buy IPv4 or change
hosting. See [Supabase connection guidance](https://supabase.com/docs/guides/database/connecting-to-postgres).

This applies only `20261013_purchase_source_lookup_index.sql` with its pinned
raw/body hashes and a new reviewed delivery timestamp after every actual ledger
version. Never replay the 30-file fresh installer, replace original delivery
versions, repair history, import real vendor invoices or enable operational use.
Track 1 accounting remains independent of prep/sales analytics.

## Before the window

1. Review the adapter PR and its local/CI evidence. Separately approve the
   designated build project, administrative endpoint/actor, maintenance operator,
   controls and index installation. Approval to merge is not approval to execute.
2. Choose a 10-to-60 minute window and identify **every writer**: Render backend,
   other app instances, coworkers/browser submissions, jobs, imports and direct
   SQL sessions. Confirm the available Render controls before selecting a stop or
   read-only mechanism. This adapter does not suspend services or disable jobs.
3. Prepare private files under `%LOCALAPPDATA%\JayMaxBuild`, outside Git/Drive.
   Retain the successful original 29-file installation receipt and hash it.
   No password, owner URL, business rows or backup key belongs in README or Pages.
4. Use the existing encrypted backup/export and isolated restore tools. The
   fresh backup must include all application schemas and `supabase_migrations`,
   use the current source hash map and sorted-row-hash algorithm, and be captured
   inside this same maintenance window. A successful isolated restore receipt
   must match the decrypted archive hash and table/catalog counts. This proves
   application-scope recovery, not managed Auth/Storage/Vault/project recovery.

## Inside the approved window

1. Stop submissions and all writers; drain in-flight requests. Record the method
   and confirmation in the private review file. These flags are operator
   attestations: the tool cannot prove that every external writer is stopped.
2. Export a fresh encrypted backup and complete its disposable isolated restore.
   Keep the encrypted archive, separate key, restore receipt and their hashes.
3. Complete the private review JSON described below. Pin it by raw SHA-256.
4. Run `dry-run`. It authenticates the backup, verifies original delivery/history,
   compares live application/ledger/catalog facts to the restore-verified backup,
   and performs mandatory `anon`/`authenticated` checks. Additional ordinary
   untrusted client roles may be listed; privileged backend roles are not ordinary
   denied clients. Existing runtime permissions are retained and still require
   their established profile checks and later live acceptance.
5. Review/hash the generated `plan.json`; record elapsed time and exact project,
   actor, endpoint, CA hash, migration, permissions and backup bindings. The
   adapter rejects local-only plans, omitted client checks and changed evidence.
6. After separate approval of **that exact plan hash**, run `apply` once. One
   transaction acquires the exclusive ledger lock and SHARE locks across the
   reviewed application tables under session installer lock 781340621. Only after
   table writers drain does its first SELECT establish the repeatable-read snapshot;
   a write committed during the lock wait is visible and refuses the old plan.
   The engine freezes ledger
   defaults, immediate unique non-null versions, ownership, ACLs, policies,
   triggers, role attributes and memberships. Recheck the backup under the locks,
   execute the unchanged index body plus one ledger row, then verify before COMMIT.
7. A fresh read-only connection reconciles the exact outcome. Verify readiness,
   the current-source reopening read and the closed fictional **$212** Food Cost
   control separately; record those results as hosted acceptance, not local proof.
8. Resume writers only after an exact applied outcome and acceptance pass. Record
   who resumed each writer and test normal submissions. Preserve all evidence.

SHARE locks block normal inserts/updates/deletes while allowing ordinary reads.
App requests can still wait while the operator holds locks; the installer does
not impose timeouts on independent app sessions. See
[PostgreSQL lock behavior](https://www.postgresql.org/docs/17/explicit-locking.html).

## Budgets and recovery

Budgets are deliberately fixed and included in the reviewed plan: lock wait 5s,
verification statements 20s, DDL statements 30s, idle transaction 120s and a 600s
database-operation limit (input/ACL validation precedes it). Probe helpers set their own 20s limits; raising
only an outer statement limit would not increase their budgets. Record total
backup/restore/prepare/apply/reconcile duration before scheduling the hosted run.
Any budget increase requires a code/review change; do not silently relax it.

Precommit failure rolls back only when rollback acknowledgement succeeds. Lost
commit/rollback acknowledgement, apply timeout, interruption or a process crash
holds an uncertain result. The adapter writes an `apply_in_progress_outcome_unknown`
receipt before sending SQL; do not infer failure from a browser/process error.
Retain the exact plan and invoke **reconcile**, never resend SQL automatically.
Reconciliation can run after the old window expires and holds if the original
writer still owns the advisory lock. It checks the database identity, complete
ledger/catalog, original rows and sequence states in a consistent read-only
snapshot. Changed/mixed states require investigation and a new reviewed plan.
An already-applied plan is refused by apply; independent reconciliation remains
available. Existing plan/evidence folders are never reused.

Plans now use core format `jaymax-additive-source-index-plan-v2` because ledger
metadata is part of the baseline. Old v1 local plans are not silently upgraded.
Preserve their original source checkpoint if reconciliation is ever needed.

## Local acceptance evidence

The final source-pinned checkpoint passes **635 reported cases**, with zero
failures, errors or skips: 230 offline methods plus 379 subtests (609), and 22
additive-core/hosted-wrapper database methods plus 4 subtests (26). Existing
dependency deprecation warnings are retained separately. Actual Windows protected
input ACL acceptance and refusal of a broad grant pass. Required client checks,
ledger defaults/column grants/uniqueness, original rows and sequences, rollback,
lost commit responses, active writers and a write committing during table-lock
wait all pass. The real fictional $55 Food Cost report remains unchanged.

Private receipt `additive-source-index-tests-20261014T042105488974Z/receipt.json`
has SHA-256 **705e14b7c153fce31567961ccb1ba321133e547a4c1470b3fdcad17d6a54331b**.
It pins all nine tested source hashes and records unchanged starting/ending role
and database inventories, a stopped local server, no hosted connections and no
real invoice imports. The overnight clock interruption is visible in the
database log's elapsed duration; no deadline was weakened and every case passed.
That duration is not a hosted maintenance benchmark.

An earlier broad accounting/restore checkpoint passed **668 reported cases**
(605 offline and 63 database). Its separate receipt
`additive-source-index-tests-20261014T033930817153Z/receipt.json` has SHA-256
**109b378c13b580fec08978063165ec1f2f65ca4ee640c8abb87b8de75a152d2b**.
Some adapter refinements occurred during that earlier run, so it remains an
intermediate checkpoint, not proof of the complete final source. The final
offline XML has SHA-256
**1cc3c5ad9182b20914828ccf769df1bb7148fef0afb8ad89dd911528b508df92**;
the focused final database run reuses that unchanged, passing offline evidence.
Counts overlap and are not summed. New PR CI and the actual hosted backup,
dry run, application, reconciliation and $212/current-source acceptance remain
separate pending steps. The encryption evidence unit fixtures contain fictional
bytes; they do not establish an actual hosted archive restore.

## Private review file

The JSON is an operator artifact, never a repository configuration. Substitute
actual private paths/project/time/version and exact SHA-256 values. The template
intentionally does not assert stopped writers or contain usable hosted evidence.

```json
{
  "format": "jaymax-hosted-additive-index-review-v1",
  "projectRef": "<designated-build-project-ref>",
  "deliveryVersion": "<new-reviewed-14-digit-timestamp>",
  "clientRoles": ["anon", "authenticated"],
  "budgets": {"lockSeconds": 5, "probeSeconds": 20, "ddlSeconds": 30,
    "idleTransactionSeconds": 120, "operationSeconds": 600},
  "maintenance": {"startsAt": "<UTC ISO timestamp>", "endsAt": "<UTC ISO timestamp>",
    "reference": "<approved-window-reference>", "allWritersStopped": false, "inFlightDrained": false},
  "originalReceipt": "<private-original-install-receipt>",
  "originalReceiptSha256": "<sha256>",
  "backup": {"encryptedFile": "<private-backup.jmax.enc>", "encryptedSha256": "<sha256>",
    "keyFile": "<separate-private-backup.key>", "restoreReceipt": "<private-restore-receipt.json>",
    "restoreReceiptSha256": "<sha256>"}
}
```

Each invocation requires a **new** output child directory named
`%LOCALAPPDATA%\JayMaxBuild\backups\backup-<32-lowercase-hex-uuid>`; the existing
private-directory tool applies/verifies current-user/SYSTEM ACLs before connecting.
Inputs are restricted to local JayMaxBuild files; redirected paths and grants to
other identities are refused, and current-user ownership is verified. Retain
protected ACLs using the existing private configuration and backup tools.
Credentials stay in the owner dotenv file, not CLI arguments.

```text
python tools/ops/hosted_additive_index.py dry-run --owner-config <private-owner-env> --expected-project <ref> --review <private-review.json> --review-sha256 <review-file-sha256> --output-directory <new-private-directory>
python tools/ops/hosted_additive_index.py apply --owner-config <private-owner-env> --expected-project <ref> --review <private-review.json> --review-sha256 <review-file-sha256> --plan <retained-plan.json> --plan-sha256 <plan-file-sha256> --approve-plan-sha256 <separately-approved-same-hash> --output-directory <another-new-private-directory>
python tools/ops/hosted_additive_index.py reconcile --owner-config <private-owner-env> --expected-project <ref> --review <retained-private-review.json> --review-sha256 <review-file-sha256> --plan <retained-plan.json> --plan-sha256 <plan-file-sha256> --output-directory <another-new-private-directory>
```

The code can enforce artifact identity and a supplied approval hash, but cannot
establish human authorization. Follow the approval boundary above. No hosted
dry run, export, restore or index application has been performed for this follow-up.
