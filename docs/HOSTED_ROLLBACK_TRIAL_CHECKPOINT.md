# Existing Supabase test database: hosted rollback trial

October 8, 2026. Local continuation on `codex/deployment-reconciliation-review`;
not published, merged or deployed by this checkpoint.

Historical rollback-only checkpoint. The later
[durable installation checkpoint](HOSTED_NATIVE_INSTALL_CHECKPOINT.md) supersedes
its database-state and pending-installation statements; original proof remains retained.

## Result

The user explicitly designated the already connected Supabase project as a
build/test database. `backend/hosted_test_trial.py` accepts that designation only
with an explicit project reference matching the saved private connection. The
separate-project workflow in `managed_development.py` still refuses its source
project as a development target. `native_backup.py` still refuses remote targets.

**The hosted rollback trial passed on PostgreSQL 17.6 through the session pooler.**
All 29 migrations ran in reviewed dependency order, with the waste correction
before final access hardening. Exact file bytes were hashed before execution.
Only reviewed outer BEGIN/COMMIT statements were removed; the full chain and
invented API workflow ran in one explicitly rolled-back transaction.

The database contained existing records despite having no operational data
according to its owner: 9 invoices, 13 count sessions, 24 prep logs and Toast test
history were present. Two scheduled jobs were active. No empty-database
assumption, reset, existing-record cleanup, scheduled-job call or real supplier
file import was used. A UUID-based temporary location/item kept invented facts
separate from the existing restaurants. Five existing application triggers were
checked against the reviewed timestamp-only helper before DDL; unknown trigger
side effects would have held the trial.

After rollback, all **40 application/integration tables** matched original
whole-table SHA-256 fingerprints and row counts. Application catalog, ordinary
client permissions and hosted migration version/name history also matched.
No temporary location or native schema remained. The hosted ledger was read,
never repaired or populated with invented historical versions.

## Hosted checks

| Check | Observed result |
|---|---|
| Current baseline plus all 29 native migrations | Passed, including populated legacy-prep retention |
| Native columns, constraints, triggers and client ACLs | Passed inside transaction |
| Invented PFG/US Foods capture | Raw CSV bytes, headers, unknown fields and literal CRLF retained |
| Received-date purchase posting | October 4; $40 food cost; $1 fee and $2 tax retained separately |
| Explicit purchased-inventory values | $60 opening + $40 purchases - $45 closing = **$55 Food Cost** |
| Purchase/prep retry | Original batches reused; changed purchase body with same key held |
| Prep production, counts and container waste | 48 lb production; .25 lb waste; .6 lb observed depletion; .35 lb residual analytical use/loss |
| Prep correction dependency | Void held while container dependencies remained |
| Track 1 isolation | Entire actual-inventory report unchanged after prep, waste and invented sales context |
| Incomplete coverage | Final sales variance unavailable; monetary prep cost unknown |
| Ordinary clients | `anon` and `authenticated` denied private purchase access |
| Rollback verification | Original schema, data, permissions and migration identities matched |

## Backup and local evidence

A fresh read-only custom-format application backup retained rows and ACLs. Its
archive listing is readable. It is **10,648,627 bytes**, SHA-256
`148ff21a903e8be0922b69ea468ce7dabba5ec17f5a167e88e05daea4c83705e`.
Dump/listing remain in the private local JayMaxTests directory, outside Git,
Google Drive and shared review packages. Auth, Storage, Vault, cron, platform
roles and project configuration were not exported. **Hosted restore is unverified.**

The private-path guard initially held three launches before remote DDL because
Windows packaged-app path resolution redirected LocalAppData. The corrected
guard compares fully resolved paths; the successful backup stayed inside the
resolved private local directory. Held attempts are preserved.

**20 selected local checks passed in the final run**, including the same complete migration/API
chain and rollback, row fingerprints, SQL boundary parsing, target/feature
holds, private backup paths, trigger refusals, schema reconciliation and exact
migration delivery. The earlier 19-case run passed before one additional guard
case was added. The managed-development tests now expect 29 files and still
refuse same-project source/target use in their distinct-project workflow. A final
offline guard recheck passed 12 overlapping cases and skipped its local-database
case; these are not 12 additional distinct cases.

Final review strengthened the client permission probe so a failed SET ROLE
cannot be mistaken for a denied SELECT. That final guard passed the additional
local case and a narrow hosted rollback fixture: both client roles were selected
successfully and denied the purchase query, the owner role was restored, and the
temporary schema disappeared. The full hosted workflow preceded this guard
refinement; the revised guard itself has direct hosted evidence, without repeating
the unchanged 29-migration/API chain.

No frontend or ordinary application implementation changed in this slice. Earlier
454-test/54-suite frontend runs and build evidence were retained, not rerun.
All original 40 pending source paths remain preserved separately without edits.
Native flags were enabled only inside the isolated test Python process. Actual
environment files, compiled flags, PRs and published application were untouched.

## Remaining work

1. Controlled durable native installation on the designated test database, with
   exact file checksums and a truthful migration record. Reconcile partial objects;
   never replay the reference snapshot or repair history to pretend files ran.
2. Separate committed requests/connections, connection recycling, staff review
   workflows and ordinary backend-role behavior on managed PostgreSQL. This
   trial uses one connection and real nested savepoints; it does not prove
   concurrency, separate-transaction replay, independent staff review or login.
   Local evidence for those workflows remains distinct from hosted proof.
3. Recovery on an isolated managed target, including review of platform state
   omitted from the application backup. A readable archive is not restore proof.
4. Actual Data API exposure/settings and built-frontend walkthrough with matched
   flags. Installed retirement changes legacy availability even with flags off.
5. Remaining workflow/history-read review and the next PR publication checkpoint.

Future Toast ingestion/sales-to-recipe analytics were not exercised. The test
sales context remained explanatory and did not become actual consumption.

## Repeating the trial

Use after explicit owner designation of the test database. The reference argument
is an identity guard, not user authorization. Native schemas must be absent;
partial installs are refused. Keep the DSN in an ignored private file and use
trusted PostgreSQL tools. Supply a fresh directory under the fully resolved
local JayMaxTests directory, never a raw-dump path inside the checkout.

```text
python backend/hosted_test_trial.py --backend-env <private-env-file>
  --designated-test-project <explicit-20-character-project-ref>
  --pg-dump <trusted-pg-dump-executable>
  --private-backup-directory <fresh-private-local-JayMaxTests-directory>
  --output <redacted-evidence-json>
```

No commit, reset, history-repair, remote-restore or lasting feature-enablement
mode exists. Driver errors/row values are withheld; evidence contains fixed
statuses, safe source frames, metadata, counts/hashes and invented results.
An incomplete or held trial never constitutes operational release approval.
