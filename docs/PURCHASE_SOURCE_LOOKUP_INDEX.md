# Invoice-source lookup index follow-up

The current-source preview follows a document version through immutable source
links, parse runs and captured files. Its filter is on `document_version_id`.
The existing source-link primary key starts with `(parse_run_id, row_ordinal)`;
it serves file reads but does not provide the intended version-first lookup.
This is an import-scale preparation change, not a measured hosted slowdown.

## Additive database contract

`20261013_purchase_source_lookup_index.sql` adds the nonunique B-tree index
`purchasing.document_source_rows_version_run_idx` on
`(document_version_id, parse_run_id)`. The leading column supports the version
filter; the second carries the parse-run key used by the captured-file join.
Repeated links remain permitted, and latest-file ordering and restaurant checks
stay in the existing query. There is no new business writer or accounting rule.

The original 29 SQL files and the public reference snapshot retain their exact
bytes. This file is appended as step 30, preserving the existing apply-order
prefix. The generated order guide and runtime candidate migration hash map include
the additional file. Only the derived profile/reference pins change: permission
matrices, function and table/view contract payloads remain unchanged. The archived
hosted catalog payload is retained; its revised profile pin does **not** assert
that the index has been installed on Supabase.

## Read-only installation check

The deployment preflight now includes explicitly declared native index presence
in its migration-object inventory. For this new lookup index it also verifies
the target table, key order, B-tree method, lack of uniqueness/predicate/expression/
included columns, default UUID operator classes, ordering/collation options and
valid/ready/live state. A missing or mismatched index holds the preflight instead
of accepting a matching name. Object checks do not replace ledger checksum review.

These flags and key/included-column distinctions come from PostgreSQL's
[index catalog](https://www.postgresql.org/docs/17/catalog-pg-index.html).
The inspector uses its existing read-only transaction and reads metadata only.
It does not install, repair or drop an index. This adds a readiness requirement;
it does not change the application's preview or posting commands.

## Local validation

The new disposable PostgreSQL test captures two fictional revisions in separate
files and adds 5,000 fictional linked rows for a different invoice to exercise a
selective lookup. It compares every purchasing-table row before and after index
creation, confirms identical current-source previews and original source bytes,
and checks that the normal planner can select the new index without disabling
sequential scans. No purchase is posted by that test.

Readiness tests detect the missing index and a same-name index with reversed
keys. Offline checks cover invalid/unready/dropping state and other contract
mismatches. The CI selection includes the new tests and the full-chain backup/
restore readiness check. Existing ordinary-owner accounting/recovery and exact
replay checks remain selected. Local execution results are recorded below when
complete; hosted validation is separate.

The completed local review passes **600 reported JUnit cases**, with zero
failures, errors or skips in the accepted runs:

| Selection | Executed result |
| --- | --- |
| Windows offline review | 212 tests plus 337 subtests: 549 reported cases |
| Disposable database CI selection | 33 tests plus 7 subtests: 40 reported cases |
| Fresh native installation | 10 tests |
| Independent runtime catalog/permission baseline | 1 test |

The database selection includes the selective version lookup, byte/row-preserving
previews, missing/reversed index refusal, full-chain backup/restore and ordinary
owner accounting/replay. The independently rebuilt local catalog still matches
the unchanged function/table and permission contracts after adding the index.
Both successful server runs preserve their starting database and role inventories
and stop the local server. Frontend source is unchanged and was not retested for
this candidate; GitHub CI has not run for the unpushed branch.

Private successful-run receipts are in
`purchase-source-index-tests-20261014T004127151480Z/receipt.json` and
`purchase-source-index-tests-20261014T011846788500Z/receipt.json`. Earlier attempts
are retained: initial library-path setup lacked dependencies; adding migration 30
correctly exposed a stale pinned runtime source manifest; the broad database run
then found a missing `json` import in the new test and missing local IANA timezone
data. The test import, exact reference pins and private test setup were corrected
before the accepted reruns. This is not a claim of a clean first attempt. Earlier
failed local fixtures remain retained; successful-run inventory equality does not
claim that every older temporary database was cleaned up. No real invoice or
hosted connection was used.

## Review and later rollout

This is a local candidate. Existing Render hosting, Supabase connections, roles
and feature settings are retained. The hosted database currently retains its
previous installation; this workflow has not applied migration 30.

For the already installed build database, first review its history, retained
backup/restore evidence and the actual index definition. Plan only the additional
migration and its new checksum-bearing ledger entry; do not replay the 30-file
fresh-install bundle over the existing 29-file installation. The existing fresh
native installer is not an incremental-upgrade tool. Prepare that additive apply
procedure for separate approval before using it on Supabase.

The file uses a normal transactional index build with a five-second lock-wait
limit, suitable for a separately approved build/test maintenance window. Index
creation adds storage and write-maintenance work and blocks table writes while it builds;
lock contention holds the migration rather than silently treating it as installed.
There is no `IF NOT EXISTS` shortcut: PostgreSQL warns that an existing name does
not prove a matching definition. A future operational database may need a
different concurrent-build procedure, outside a transaction, with invalid-index
recovery reviewed explicitly. See
[PostgreSQL CREATE INDEX](https://www.postgresql.org/docs/17/sql-createindex.html).

After an approved additive rollout, use the read-only preflight and current-source
walkthrough again, retaining source history and the closed Track 1 control.
Prep and POS sales continue to explain actual inventory; they cannot alter it.
Source-capture/correction command recovery, the broader UI rework, Toast and
connection architecture remain separate workflows.
