# Hosted application backup and source-index window — October 15, 2026

## Authorization and source

The owner approved a new **1:45:17–2:30:17 p.m. EDT** window
(`2026-10-15T17:45:17Z` through `18:30:17Z`), including temporary suspension of
`jaymax-api`, pausing the two named Toast cron jobs, writer-drain verification,
a fresh encrypted application backup and disposable local restore. The owner
confirmed no other manual/script writes during the window; Companion remains
local-only per the earlier confirmation.

The API was verified live on PR34 merge `ce7eb27` before suspension. Local
execution source was the clean documentation continuation `1a9a9c3`; runtime
source hashes were bound in the backup receipt. No runtime source, role/grant,
credential, pooler, hosting-plan or paid-service change accompanied the window.
Temporary service/job controls and the separately approved index are recorded
below. This supersedes expired-window/hold wording in earlier planning records.

## Pause, drain and fresh backup

Render confirmed the exact API service `srv-dauimuugekts73ek9lr0` suspended.
Cron jobs 3 (`jmax-toast-berts-rudds-daily`) and 4 (`jmax-toast-papa-daily`) were
verified inactive with their original names, schedules and command hashes
unchanged. Two idle pooled sessions initially held the drain guard. They cleared
without termination; the third observation passed with complete activity
visibility, zero reviewed application sessions/write transactions, no active
cron run and an empty HTTP queue. The same guard passed immediately before export.

One fresh encrypted export and isolated restore passed:

| Check | Recorded result |
| --- | --- |
| Export / disposable restore duration | 119.953 s / 23.532 s |
| Relation fingerprints / catalog groups | 120 / 13 matched |
| Restored rows | 29,088 matched |
| Fingerprint paths | 119 completed server aggregates, 0 cursor fallbacks, 1 cursor-only relation |
| Canonical migration source hashes | All 31 captured repository-relative files; required reviewed native migration hashes matched |
| Nonempty target refusal | Passed |
| Restored account/inventory separation probes | Passed both negative-access checks |
| Owned local cleanup | Disposable DB and 17 created NOLOGIN role stubs removed; original role/database inventories equal; local server stopped |
| Retained artifact verification | Encrypted backup, separate key and receipt ACLs verified; archive hashes matched; no export partials |
| Export-session cleanup | Both exact export-reference application labels absent with full activity visibility |

The manifest was created at `2026-10-15T17:52:14.617414Z`, inside the approved
window. It is an **application-scope backup/restore**, not a Supabase managed
Auth/Storage/Vault/project recovery. Major PostgreSQL versions matched; patch
versions differed. Role memberships were not restored and no operational login
credentials were recreated. A restored closed-period runtime calculation was
not performed; data/catalog fingerprints include the relevant tables.

Effective export limits: client connection 20 s, command 60 s, tool 240 s,
overall export 600 s and cleanup 5 s. The observed server statement timeout was
120,000 ms; no timeout setting was changed persistently. The fingerprint phase
took 31.140 s in this run. Differing previous datasets/limits do not establish a
general performance improvement or the cause of older failures.

## Read-only plan preparation and owner approval

The first dry-run held with no committed SQL. Its local operator packet had
incorrectly included the privileged inventory/accounts backend roles among the
ordinary clients that must be denied private access. A separate SELECT-only
diagnosis verified original ledger history and confirmed that public-client
readiness had exactly the two expected missing-index findings. The inventory
backend's purchasing access is intentional; the accounts backend lacks it.

Only the local packet was corrected: `clientRoles` is `anon` and
`authenticated`; `writerLoginRoles` still includes both backend LOGIN roles and
the deployed `postgres` identity. No grant, database guard or source validation
was weakened. The corrected dry-run passed in 158.140 s and matched the current
database to the fresh restore-verified backup.

The owner then explicitly approved this exact prepared plan:

- Plan SHA-256: `d4c6ddb62a0ddaa1c7103d3367c12881b6161598148325e02a2251b9abf61fd8`.
- Source: `migrations/20261013_purchase_source_lookup_index.sql`, SHA-256
  `2e9ea948fd2fb0c7f298ef3484fe838ec710ddbbeacf4bada7bb31241ba2eb97`.
- Delivery version: `20261015175921`.
- Nonunique B-tree: `purchasing.document_source_rows_version_run_idx` on
  `(document_version_id, parse_run_id)`.
- One index plus one ledger entry in an atomic transaction; 5 s lock timeout,
  30 s DDL timeout, 600 s adapter operation budget, no automatic retry.

## Execution and recovery

The single application passed in **457.109 s**, including independent
fresh-connection reconciliation. Its result is `passed_hosted_additive_install`,
with `sqlCommitted: true` and no automatic retry. Writer checks passed before
table locks, while locked before the change, and while locked afterward.

Independent reconciliation verified the exact index, original application rows
and columns, catalog/permissions, historical migration rows and backed-up
rows/sequences. Native catalog/ACL readiness passed with **zero issues and zero
warnings**. The ledger has **55 rows**, preserving the original 54 and adding
only delivery `20261015175921`. This does not grant operational release or prove
every external deployment/authentication prerequisite in the generic readiness
checklist.

Postflight verified the index definition and ready/valid/live flags, both exact
export-session labels absent, private artifact integrity, local cleanup, and the
two Toast jobs restored to their original active states/schedules/command hashes.
The legacy job-control helper's `indexApplied: false` field means that helper did
not apply index DDL; it is not the database outcome. The approved apply receipt
and postflight establish `indexPresent: true` and the 55-row ledger.

Render showed `jaymax-api` **Live on the same `ce7eb27` deployment**, and fresh
health reads returned HTTP 200 / `ok` / database `connected`. The window closed
early at **2:14:45 p.m. EDT** (`18:14:45.807419Z`), with all writers restored.
The local window pointer is marked inactive; older approvals and packets remain
immutable historical evidence.

A separate SELECT-only accounting comparison matched **all 82 protected
relations** exactly to the final pre-index recovery checkpoint, including store
payloads/revisions and current received-purchase facts. The complete historical
Actual Inventory report remains **$212.00**, hash
`e85c53b4edb66eb34f0ffa5c52f40bbdbbc72557e8d05f212d5b70e703321d66`.
The index installation changed no physical counts, purchase/correction facts,
prep records or Food Cost values.

After recovery, the signed-in owner UI reopened the latest fictional source and
read its saved **5 each**, conversion **1**, received date **October 15**, review
note and both correction-history entries; no retained submitted correction
remained. The first refresh displayed a Network Error notification. Ordinary
Dashboard-to-Invoice-Master navigation then loaded the source and saved details
successfully; no network root cause is claimed. No purchase was submitted in
this post-index smoke check. The disabled product Backup/Restore buttons remain
separate from the verified manual operator backup procedure.

## Remaining work

Source-capture/manual-entry persistence and the remaining schema-mapping audit
remain local follow-ups. Real dropped-response correction acceptance, distinct
staff/manager identity walkthroughs and broader UI work are separate from this
backup/index result. Managed Supabase recovery, credential rotation and restricted
deployed-role cutover remain deferred gates; the current build connection and
hosting standard are unchanged. No new PR or application deployment was initiated
by this window. This checkpoint changes documentation only; no local test suites
were rerun for it.

## Local evidence

Private backup/key/receipts remain under `%LOCALAPPDATA%/JayMaxBuild`, outside
Git and synced folders. Public-safe evidence filenames are relative to the
existing `usin/work` folder; no credentials or business row values appear here.

- `pr34-window-backup-restore-20261015T175253364053Z.json`.
- `pr34-window-paused-postflight-20261015T175309377078Z.json`.
- `pr34-window-index-plan-20261015T175552437332Z.json` (held first packet).
- `pr34-index-readiness-diagnosis-20261015T175846754156Z.json`.
- `pr34-window-index-plan-20261015T180211376336Z.json` (approved exact plan).
- `pr34-window-index-apply-20261015T181129171577Z.json` (verified application).
- `pr34-index-window-restored-postflight-20261015T181236440475Z.json`.
- `pr34-post-index-accounting-20261015T181353108685Z.json`.
- `pr34-maintenance-window-closed-20261015T181445807419Z.json`.

Encrypted artifact SHA-256:
`8c28e18083389ddaf4ff4e34e48d5edada0efd6ac6ccb68bb91a255f47efba9c`.
Authenticated archive SHA-256:
`8afa3ed99db999fe9a307f3a9182ed1b84a832e4ec56d3fb8e8cb4765ac65c48`.
Private backup/restore receipt SHA-256:
`b6aaf232c595dcd96244c8c4553c95e6f22e865f7fd18fbb5c986d2148a477c1`.
Private index-application receipt SHA-256:
`cf6575c17d6af2f1f0ab9fafd6c5693d672cca0ad51e305e9deb0604d3303493`.
Post-index accounting receipt SHA-256:
`806b97c8ea01b460071a9568725f81b8ed17d81f5b9908b078c073d2081b4fe6`.

`pr34-hosted-index-window-manifest-20261015.json` binds 33 public-safe receipts,
UI observations/screenshots and local operator sources. SHA-256:
`6a53ecd07505725eda80742c4782135a03d894d53db92b1c2a23322654854b74`.
It records one export, one application and two plan-preparation attempts,
including the first role-classification hold. Private backups and keys are not
copied into Git or this manifest.
