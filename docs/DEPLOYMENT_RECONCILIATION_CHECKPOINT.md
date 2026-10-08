# Deployment reconciliation checkpoint - October 8, 2026

The deployment slice now builds on draft PR16 correction commit
`91b028d8d44ac94a0253c1b8c2173a937f628c7f`. It includes the preserved readiness
tool, final private-access migration and exact-newline restore fix. The original
40-file continuation remains unchanged and has its own immutable preservation
snapshot. The rest of its legacy cutover, correction UI and hosted-development
tooling has not yet been brought into this narrower checkout.

## Reconciled bundle

The readiness tool lists all 29 native migrations exactly once, in dependency
order. `20261008_container_waste_corrections.sql` follows the existing waste and
staff-production migrations, immediately before final private access hardening.
The September 30 recurring-prep migration is already in the public reference and
is excluded. Plans retain file checksums; catalog presence is not proof of an
applied checksum. Do not apply files alphabetically or blindly replay existing
hosted objects.

Example configurations now explicitly select PostgreSQL in both applications.
All fifteen native feature pairs remain false. Actual runtime environments and
compiled frontend flags were not changed. The file-only preflight passes these
examples and reports that no database connection was requested.

## Local evidence

Fourteen selected checks pass on PostgreSQL 17.11 in the dedicated loopback test
cluster, using invented data. The first 13-case run covers configuration, full
29-file installation, hardening, inherited client privileges, disabled guards,
missing roles, later DDL exposure, complete SQL recovery and exact invoice line
break preservation. It includes five inherited backup cases. The additional
ordinary-owner case uses a separately created disposable LOGIN role with
NOSUPERUSER, NOCREATEDB, NOCREATEROLE, NOREPLICATION and NOBYPASSRLS.

That ordinary role owns the disposable application database and native objects.
Both source and restored API pools connect as that role. The full recovery
contract posts and corrects synthetic purchases, records purchased physical
counts with explicit values, closes/reopens periods and restores immutable
history. Food Cost reports and original correction request-key replay match
after restore. Literal CRLF invoice text and internal psql-like text survive
unchanged. This validates the intended owner-backed transaction model; it is
not a separately designed nonowner least-privilege grant model. Table owners
retain PostgreSQL's normal owner access to tables with RLS.

An ordinary unverified nonowner role is held by the readiness inspector even
when granted schema visibility. Direct client table reads and execution of the
new invoker waste-reversal helper are denied even with temporary schema USAGE.
Those temporary grants are rolled back. The final function/role catalog and
whole database restore remain consistent.

The restore helper refuses remote databases, nonempty targets, damaged dumps,
source-as-target restores and unsupported version changes. Its exact-byte decode
retains line endings while removing only matching outer pg_dump guards. It is
a disposable application recovery verifier, not a hosted operational restore
command. Administrative test connections still create/drop isolated databases,
create/drop synthetic roles and perform the controlled dump/restore.

## Remaining work

Bring forward and reconcile the remaining legacy cutover, correction review and
schema/managed-development tools against the corrected application. Run their
combined workflow and restore cases with the retained history and staff privacy
contracts. Safe API/UI history paging and residual recipe/source batching remain
separate open work.

Hosted applied migration checksums and partial objects, actual connection-role
ownership, Data API exposed schemas, hosted backup/isolated restore, connection
recycling and browser acceptance remain unverified for this reconciled release.
Earlier read-only hosted inspection is historical evidence, not a refresh or
proof of this new bundle. The ordinary local owner test cannot establish managed
Supabase role, extension or recovery behavior.

Track 1 remains purchased-item physical inventory, received-date purchases and
explicit count values. Prep and future sales explain usage without changing its
accounting baseline; taxes and fees remain separate. No operational data was
imported and no hosted SQL, deployment, merge, feature enablement or login redesign
occurred. PR14-16 remain draft and unmerged. This checkpoint is local and has not
been pushed to a pull request.
