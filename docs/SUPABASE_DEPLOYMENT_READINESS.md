# Hosted Supabase deployment readiness

Latest local prerequisite: the [transition permission checker](TRANSITION_PERMISSION_CHECKPOINT.md)
accepts only independently pinned same-profile overlap during explicit diagnostics.
Normal startup remains singleton-only. Before any hosted TO-list change, prepare
the journaled installer, explicit startup integration and registered-client plan.
Current application credentials remain selected; merge/recovery gates stay held.
Both original hosted profiles pass the stricter default checks with unchanged
role/policy/membership metadata. Twenty-nine local tests and 91 subtests pass.

Latest October 9 review: keep the original restricted inventory/account logins
on the verified shared session pooler at port 5432, with the encrypted local
application recovery copy. Both current permission profiles and all six bounded
pooler samples pass; all six direct samples time out. The
[parallel-account checkpoint](PARALLEL_ROTATION_REVIEW_CHECKPOINT.md) records
the read-only evidence and transition-policy prerequisite. No paid IPv4 add-on,
replacement login or configuration switch was enabled. The combined credential
rotation/recovery and release gates remain held; this is not publication approval.

The [native installation checkpoint](HOSTED_NATIVE_INSTALL_CHECKPOINT.md) records
the later committed 29-file delivery and preservation evidence on the designated
build database. The [encrypted backup checkpoint](HOSTED_BACKUP_VERIFICATION_CHECKPOINT.md)
records the verified six-schema application backup/restore; managed recovery
remains separate. The older rollback-trial paragraph below describes its own
point in time, before that durable installation.

Earlier October 8 evidence: the user-designated existing test project passed
the complete 29-file migration and synthetic API **rollback trial**. See the
[hosted checkpoint](HOSTED_ROLLBACK_TRIAL_CHECKPOINT.md). Nothing was durably
installed; managed restore, separate-connection and browser checks remain pending.
The distinct-project path and local backup guards are intact. The older process
below is the release checklist, not a statement that deployment is complete.

The user selected the existing hosted Supabase database for this build. This is
a local preparation checkpoint, not permission to apply SQL, enable features,
import operational data, deploy, merge or restore the hosted database. PR #16 stays
draft and unmerged. This deployment slice is prepared on a separate local branch
based on its latest correction head. The earlier local/cloud architecture notes are design context;
they do not replace this selected deployment target.

## What is now prepared

`backend/deployment_readiness.py` builds an explicit, checksum-bearing **29-file**
native migration order and compares all fifteen backend/frontend feature pairs
and their prerequisites. Both modes must explicitly select PostgreSQL. Example
files now do so, with all native features still false. The runtime still retains
an explicit legacy mode; an unset/false deployment mode must not pass this preflight.
The tool does not apply SQL, create users or change runtime flags.

The order includes `20261008_container_waste_corrections.sql` immediately before
the final permission migration. Same-date or alphabetical file order is unsafe.
It excludes `20260930_recurring_prep_items.sql`, which is already represented in
the retained public reference. Plans contain exact hashes of the reviewed SQL
files; catalog object presence remains separate from applied-file checksum proof.

Optional database inspection uses a read-only, repeatable-read transaction with a
statement timeout. It checks native tables/functions/static triggers, key additive
columns, disabled guards, unvalidated constraints, store coordination rows,
private schema/object/function privileges, inherited client privileges and future
default-grant warnings. It reads catalogs and coordination identities, not invoice,
count, staff credential or operational inventory rows. It never prints a database
URL, password or driver error text. A missing/invalid connection remains held.

The final migration `20261007_native_private_access.sql` revokes existing private
schema/table/sequence/function access from PUBLIC and, when present, `anon` and
`authenticated`. It also restricts the three existing future Toast security-definer
RPCs in the reference `public` schema. Functions are preserved and database-owner
backend access is retained. No stock facts, receipts, taxes/fees or counts change.
This SQL is applied only to disposable tests in this checkpoint.

RLS on a table is not proof that a function cannot be called. PostgreSQL gives new
functions public execution privileges by default; Supabase separately controls
schema exposure and client permissions. See [PostgreSQL function privileges](https://www.postgresql.org/docs/current/sql-createfunction.html)
and [Supabase API security](https://supabase.com/docs/guides/api/securing-your-api).
The preflight therefore checks function access separately. It catches later DDL
that reintroduces permissions. The migration does not override every creating
role's default privileges or remove inherited access through unrelated roles.

## Existing-database process

1. Read the hosted migration history and compare it with the retained public
   schema reference. The reference is dated September 30 and is **not a live
   migration**. The recurring-prep migration is already represented there; do not
   automatically replay it. No Mongo export/import is part of this build.
2. Review the preflight's native file order and checksums against actual hosted
   migrations. Existing or partial objects require reconciliation, not a blind
   retry of CREATE/ALTER statements. Catalog presence is not checksum proof.
3. Prepare an isolated hosted development copy with the intended owner connection,
   exact native SQL chain, final permission boundary and public-client deny tests.
   Keep native schemas out of Data API exposed schemas. Decide whether the app
   needs the Data API at all; verify settings on the actual project.
4. Verify backup and restore of all application schemas and required external
   schemas/roles on that isolated copy. The current `native_backup.py` intentionally
   accepts only disposable loopback test databases. It is not an operational
   backup command or remote restore workflow. Keep that restriction intact.
5. Schedule a stopped-traffic migration window, verify a usable recovery copy,
   apply only reviewed missing migrations, and recycle backend database connections.
   Installing native schema freezes legacy writers even when flags remain false;
   a partial installation is not an ordinary rollback path.
6. Build and deploy matching frontend/backend flags for the chosen staged workflows.
   Validate the actual compiled build, not only a proposed environment file. Test
   owner bootstrap on the isolated environment, then use existing account handling
   on the hosted database; never reset users merely to make a deployment pass.
7. Exercise received purchases and explicit-value purchased counts first. Add
   measured prep workflows with their prerequisites and the combined correction/
   recovery trial. Track 1 remains purchased inventory only; Track 2 explains it,
   and future Toast sales remain separate Track 3. Taxes and fees stay separate.

## Running the preflight

From the repository root, with backend Python dependencies available:

```powershell
python backend/deployment_readiness.py --backend-env backend/.env.example --frontend-env frontend/.env.example --output readiness-plan.json
```

That reviews the proposed files only and does not connect. For a privately
configured backend environment and the matching frontend build configuration:

```powershell
python backend/deployment_readiness.py --backend-env backend/.env --frontend-env frontend/.env --inspect-database --store berts --store rudds --store papa --store comm --output readiness-catalog.json
```

Supply only intended operational location IDs. The database connection uses TLS
and read-only session defaults; output excludes connection values. Store reports
privately because they describe schema and role access. Exit 2 means held; exit 0
means the requested preflight checks passed, **not release approval**. Hosted Data
API settings, applied-file checksums, real recovery and browser validation remain
explicit external checks even after a successful catalog probe.

## Evidence and limits

The October 8 reconciliation has 14 selected passing local checks: 13 readiness/
backup cases plus one ordinary owner-role transaction/recovery case. The full
29-file chain and its restored catalog pass. An unverified nonowner is held;
client table reads and waste-helper execution remain denied even with schema
visibility. The ordinary owner role has no superuser or RLS-bypass privilege.
See [the current checkpoint](DEPLOYMENT_RECONCILIATION_CHECKPOINT.md) for precise
coverage and remaining combined-workflow/hosted boundaries.

Tests apply the complete native chain to the retained public reference in disposable
PostgreSQL. They show the initial function-permission gap, the final hardening,
inherited-role and disabled-guard detection, missing-role holds, later-DDL detection,
and whole SQL restore with identical preflight output. Configuration tests check
flag mismatches/prerequisites and redaction. Initial implementation errors remain
with corrected test evidence; local schema application is not hosted proof.

At the initial readiness checkpoint, no private hosted connection was configured;
the retained example report correctly records that earlier hold. A private ignored
connection file was subsequently configured, and live read-only catalog/history
inspection and a schema-only export succeeded. See the newer
schema-reconciliation notes in the separately preserved continuation for those results,
hosted additions, the exact-newline restore fix and the now-verified local
migration/restore trial after the user resolved the Windows block. No hosted SQL or business data import
was performed. Isolated hosted recovery remains unverified.
Login redesign, verified employee mapping and Toast operational integration remain
future work. Review findings remain open where those acceptance conditions remain.

## Catalog comparison command

The commands below describe that separately preserved continuation. Its
`schema_reconciliation.py` tool is not part of this narrower deployment slice;
bring it forward with its tests before using these commands in this checkout.

The private readiness file is separate from `backend/.env`, so configuring an
inspection connection does not change application startup. It is ignored by Git.
From the repository root, with backend dependencies available:

```powershell
python backend/schema_reconciliation.py capture --backend-env backend/.env.readiness --output ../../work/hosted-catalog.json
python backend/schema_reconciliation.py compare --reference ../../work/reference-catalog.json --hosted ../../work/hosted-catalog.json --output ../../work/schema-comparison.json
```

Generate the reference catalog by loading the retained public reference into a
fresh disposable local database and calling `schema_reconciliation.capture` there,
as the disposable test does. Never load that reference into the hosted project.
The capture command only reads application metadata and migration version/name
identities; function bodies/settings and expression text are stored as exact hashes.
It never repairs history or approves migration application. A structural match is
not checksum proof, an operational backup, or deployment approval.
