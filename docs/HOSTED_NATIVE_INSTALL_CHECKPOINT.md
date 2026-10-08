# Durable native installation on the designated Supabase build database

October 8, 2026. Local continuation on `codex/deployment-reconciliation-review`.
PR14–16 remain draft and unmerged; this continuation has not been pushed.

## Confirmed installation

The owner designated the existing connected Supabase project for build testing.
The 29-file native chain is now committed on that project, with a complete
independent verification from a new connection. No operational supplier files
were imported and application feature flags were not changed on disk.

The installer checks the exact source/delivery bytes, current catalog, existing
rows and migration ledger before DDL. It serializes installation with an
advisory lock, locks existing tables against concurrent writes for the short
installation window, and runs all native DDL and new migration records in one
transaction. A version collision, partial native installation, stale baseline,
unreviewed trigger or unknown mandatory ledger field holds installation.

Existing **40 application/integration tables** retained their original column
values and row counts. New fields are excluded explicitly from preservation
hashes; removed or retyped original columns hold. Timestamp fingerprints use
UTC so identical timestamptz values compare across machines without changing
stored data.

The original **25 historical migration records** were preserved, including hashes
of full old ledger rows. Exactly **29 new delivery versions** were recorded only
when their SQL executed. Each new ledger statement contains the executed body;
its SHA-256 matches the retained delivery receipt. No historical migration was
replayed or marked applied merely to make history appear aligned.

The applied delivery begins at `20261008172951`, in the explicit dependency
order, with container-waste corrections before final private access hardening.
Retain that immutable native bundle and its source-to-delivery hash map.
This is a native delivery bundle, not a complete Supabase CLI history checkout;
do not run `db push`, invent empty old migrations or use migration repair to
hide the repository's incomplete historical file set. Supabase documents the
importance of coordinating deployment through migration history in its
[migration guide](https://supabase.com/docs/guides/deployment/database-migrations).

## Held attempt and recovery evidence

The first attempt prepared all 29 migrations but lost its connection during
precommit verification. No COMMIT was attempted. Rollback acknowledgement was
unavailable, so the tool correctly recorded an unknown outcome instead of
claiming success or immediately retrying SQL. An independent read-only check
proved that native schemas and new ledger entries were absent and that all
original data, catalog and historical ledger hashes matched. Only after that
proof did a fresh attempt proceed. The precise connection-loss cause is not
proved. Both attempts and the reconciliation are retained.

Before installation, the retained private application archive was restored into
a unique disposable loopback database on PostgreSQL 17.11. All **40 table
fingerprints** matched the hosted baseline. The restore initially held because
the archive creates `public`, which a new local template already supplies;
only that empty schema in the newly created local UUID database was removed.
A subsequent timestamp comparison exposed session-timezone formatting, fixed
by UTC normalization. All held attempts were retained. The disposable database
was removed and the local server stopped after validation.

This proves application-data restore locally. The original archive excluded
Supabase migration bookkeeping, ownership/grant recovery and managed Auth,
Storage, Vault, cron and project settings. Full managed recovery remains open.

## Committed workflow validation

The separate-connection probe uses an invented UUID location and item, retained
as explicitly labelled build-test facts. It uses the actual purchase and
actual-inventory routers with a narrowly scoped synthetic actor. This exercises
native SQL/API behavior, not application login or staff authorization.

The probe tests concurrent same-key purchase/prep retries, closes the entire
pool, and replays the same requests through a new pool. Invented invoice bytes,
unknown columns and multiline values are preserved. Purchases use the received
date and retain fees/taxes separately. Explicit purchased-inventory values keep
Food Cost at $60 opening + $40 received purchases - $45 closing = **$55**.
Prep, waste and sales context explain usage without changing that Track 1 value.
Incomplete sales coverage remains unavailable; prep monetary cost remains unknown.

Initial hosted workflow validation held with a socket error during pool cleanup.
Its completion and underlying cause are not proved. Cleanup was changed to
preserve the original workflow error, and short reader leases replace an idle
observer held across API calls. Stage/identity diagnostics retain partial test
facts without deleting immutable history. Updated local workflow and rollback
checks passed. The retry **passed on hosted PostgreSQL**, including concurrent
purchase/prep replay, a completely new pool, exactly one purchase and prep batch,
private SELECT denial after successfully selecting each ordinary client role,
and unchanged Track 1 after prep/waste/sales context. This does not establish the
underlying cause of the earlier socket error.

The held attempt's labelled invented location is retained. Preservation checks
exclude only the explicitly recorded invented store/item IDs from the four
affected public tables; all original 40 table projections still match. No
prefix-based exclusion is applied to fingerprints, and all private test facts
remain in the audit history. The live ledger still has exactly **54 records**.

A post-install custom archive now includes `supabase_migrations` as well as all
application schemas. Its SHA-256 is
`2b59811ce88efe48d06efb0f3a8aec93b4e6578690c1ccd29af612c38043e56d`
and size is **11,391,979 bytes**. The source backup and its row/ledger fingerprints
use the same exported repeatable-read snapshot, avoiding a comparison between
different moments. The dump, archive listing and original records remain private
outside Git/Google Drive. Its isolated local restore **passed**, with all **118
application-table fingerprints** and all **54 full migration-ledger fingerprints**
matching the exported snapshot. The temporary database was removed and the local
server stopped. Ownership/grants and full Supabase platform recovery remain
outside this local restore proof; no restored external job or function was invoked.

Local evidence comprises **25 distinct selected cases** across the native install,
preservation and rollback-trial suites, exercised in the 22-case run and focused
follow-ups after new guards and short reader leases were added. These are not
all one 25-case run. The final changed pooled/rollback workflow cases passed;
one existing multipart deprecation warning remains. No frontend implementation
changed, so the earlier 454-test/54-suite evidence was retained rather than rerun.
GitHub currently reports no checks for the PR14–16 branches; local evidence is
not a hosted CI result.

## Merge and release boundary

A useful merge checkpoint requires the committed hosted workflow to pass, the
remaining staff review/runtime and browser/Data API checks to be assessed, and
this final continuation to be published as a reviewable PR. Then review the
stack in order: PR14, retarget/revalidate PR15, retarget/revalidate PR16, followed
by the continuation. No merge is authorized by this checkpoint.

Application publication remains a separate decision. Full managed recovery,
ordinary backend-role validation, matched frontend/backend flags and deferred
login work cannot be inferred from owner-role probes. Scheduling, Operations,
analytics and real Toast ingestion remain later integration work. Do not treat
invented sales context as actual consumption or complete sales mapping.
