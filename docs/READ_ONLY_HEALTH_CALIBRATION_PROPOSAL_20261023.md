# Read-only health and calibration proposal — October 23, 2026

**Status: local proposal for owner review; no execution approval.** No health
request, Supabase connection, Render inspection, service pause or private-config
read was performed to prepare this document. Credential, grant, schema and
runtime-connection changes remain held. This proposal does not implement a probe.

## Recommendation and accepted baseline

Proceed in two separately approved stages: one anonymous API health observation,
then a bounded direct read-only database calibration if that preliminary screen
passes. First approve a small local-only probe implementation and tests, review
its exact source/evidence packet, and approve each hosted stage separately.
Existing installer commands are not a substitute for this probe.

[PR58](https://github.com/jeffwelch0620-png/JayMax-Concepts-/pull/58) is accepted as
`3bdf8be1609c72d0c05e25b534e576d95a489d44`; its tree
`f6c6d02cab69799eaa81894315db29b61f10a88b` matches reviewed
`a9a786d80336f1a484e5d7a2a58004ce645687b6`. The saved reviewed-head and merged-main
CI records passed separately. Automatic Render test deployment was authorized,
but completion and live behavior have not been inspected. This task verified
the local accepted tree, not current GitHub, Render or database state.

The [runbook](REVIEWED_PAR_INSTALLATION_RUNBOOK_20261022.md) requires complete
coverage and a maximum observed driver query await of **10 seconds per family**
before installation-window planning. This is a conservative margin against the
unchanged 20-second statement timeout, not an empirical performance guarantee.
The [dated local measurement](LOCAL_PAR_BATCHED_FINGERPRINTS_20261022.md) records
764 apply/verification query calls in 45.063 seconds; the old additive sensitivity
is 362.527 seconds against a 450-second planning screen. Neither is hosted proof.

## Stage A — one health observation, separately approved

Proposed request: one anonymous HTTPS GET to
`https://jaymax-api.onrender.com/api/health`, using certificate verification,
no cookies, authorization headers, personal sign-in or PIN. Disable automatic
retries and redirects. Use a 20-second connection limit within a **90-second
total deadline**, a 4 KiB response limit and a fixed JSON shape check. The total
allows a slow initial service response without changing server timeouts. A
request may wake the existing service and its normal connection initialization.

Record UTC time, bound source, target host/path, status, elapsed time and only
the expected `status`/`database` fields. Require HTTP 200, `status: ok` and
`database: connected` to pass this preliminary screen. Missing database status,
unexpected shape, redirect, TLS failure, timeout or a disconnected response holds
the next stage and returns findings. Do not retry, restart, deploy or repair.

Source review: `server.health` deliberately returns HTTP 200 even when the pool
is unavailable. `database: connected` means `db_pg._pool is not None`; it does
not execute a query or verify the auxiliary pool, permissions, personal login,
business routes or recent deployment. `/api/health` bypasses the activity-log
middleware. A passing result therefore permits proposing Stage B, not declaring
functional health recovered or closing G04/G13. This plan does not authorize
Stage B automatically after Stage A.

## Stage B — proposed database calibration, separately approved

### Connection and transaction boundary

Use one owned connection through the existing maintenance-only direct IPv6
connector and existing private maintenance configuration. Do not create or
rewrite credentials/configuration, fall back to app environment values, change
Render routing or alter app pools. Verify designated project/host/database,
certificate hostname, TLS, native IPv6 peer, session/effective actor and both
default/effective read-only settings before scoped reads. Unexpected identity,
route, source or settings holds. The existing connector uses the administrative
login, so explicit read-only enforcement is a required guard, not a new grant.

The proposed local harness must bound connection establishment to 20 seconds
and use a read-only repeatable-read outer snapshot for discovery and both
fingerprint families. Preserve helper nesting within that snapshot. Set and
verify transaction-local statement timeout 20 seconds, lock timeout 5 seconds,
idle-in-transaction timeout 120 seconds and existing canonical hash settings.
Session-local read-only settings and transaction boundaries are the only
database control commands in scope. No advisory/table lock commands, SET ROLE,
DDL, DML, sequence advancement, installer prepare/apply/reconcile or backup/export.

One attempt, serial only: **600-second work deadline including connect, identity,
scope discovery, both families and snapshot completion**, followed by at most
15 seconds reserved for cancellation/rollback/owned-client close. Use bounded
5-second cleanup steps; on failed close, terminate only the owned local client
transport as the existing connector does. No SQL backend termination, observer
connection or automatic reconnect. Failed/ambiguous cleanup is a held outcome,
not proof the server session disappeared. No extended deadline or second run.

### Exact relation and statement coverage

The source-reviewed manifest must bind the five application schemas used by
`schema_reconciliation.SCHEMAS`: `public`, `integrations`, `purchasing`,
`actual_inventory`, `prep_inventory`. The backup family additionally includes
`supabase_migrations`, as in `hosted_backup.SCHEMAS`. Exclude managed schemas;
this is not a managed-service recovery or permission audit.

1. Read original column/type metadata in the snapshot; use that exact current
   projection as the calibration baseline, with no synthetic exclusions. Invoke
   `fingerprints_batched` at chunk size two, without truncation or sampling.
2. Invoke `fingerprint_batched` with row hashes and server aggregation enabled,
   retaining its catalog/default-ACL reads, relation enumeration, two-relation
   aggregation, existing 8 MiB payload probe, full cursor fallback and sequence
   read paths. Preserve the distinct backup hash format. The relation-count
   limit and payload probe do not bound all PostgreSQL workspace memory.
3. Reconcile enumerated, attempted, completed and failed coverage for every
   family, catalog group and actual query/cursor path. Missing/duplicate facts,
   excluded scope, unsupported instrumentation or unexplained calls hold.
   Historical 120-table/45,648-row counts are context, not current expectations.

The runtime inventory is captured privately inside this one snapshot and bound
to its scope digest. Any pre-existing owner-approved inventory must match before
hashing; otherwise stop for scope review. If no current inventory exists, owner
approval must explicitly authorize complete discovery within these exact schema
and relation-kind predicates, not an invented fixed table count. New schemas or
an expanded predicate require a revised proposal. Read-only hashing can consume
database CPU/I/O and hold ordinary read locks; no disruptive load trial is included.

Use the same snapshot to relate the two families, but do not equate their hash
formats. Live writers remain running. Sequences are not MVCC-stable, and activity,
cache and data volume can change; the results are timing observations, not a
drained installation baseline or cross-run preservation assertion.

### Timing and decision rules

The existing `local_query_metrics` observer records aggregate query/operation
time, not all required maxima. A new local-only observer must record individual
query outcomes/durations and the maximum for each family, plus setup/catalog
maxima and total elapsed time. Measure monotonic driver awaits; never label them
server execution time or network round trips. Retain cursor API counts separately.

For cursor fallback and sequence paths, observe the full cursor lifecycle as a
conservative elapsed envelope as well as individual driver awaits. This covers
work hidden by buffering; a long envelope may conservatively hold even if each
fetch is short. Do not add buffered row requests to network-call estimates or
claim statement coverage from aggregate fetch maxima alone. Require tests that
every read path is observed; unobserved work makes calibration incomplete.

Stop after the first completed read/envelope above 10 seconds, or any timeout,
error, cancellation, resource failure or coverage/identity guard failure. Report
partial results as held; do not run the remaining family to obtain a partial
pass. For a pass, both families must complete with each observed maximum at most
10 seconds, all setup/catalog reads within the same conservative screen, exact
coverage, total work within 600 seconds and successful bounded cleanup.

Passing is necessary, not sufficient, for a new installation proposal. Record
workload/cache/order limitations and avoid extrapolating one fingerprint pass to
all install phases. The 450-second end-to-end planning screen remains a separate
gate; do not recalibrate its old latency coefficient from these awaits. Above
10 seconds, return for review of chunk size one and a new local rehearsal, source
review and separately approved calibration. No automatic fallback, cached reuse,
timeout increase or weakening of the original/backup checks.

## Local implementation and evidence gate — not yet approved

Before either hosted stage, implement only after owner acceptance of this design:

- A separate opt-in local operator harness with no app/runtime imports that start
  pools, no installer entrypoints, no default hosted execution, and exact source,
  target, scope and approval bindings. Validate inputs before reading private config
  or connecting; refuse stale source/approval and mixed-stage invocations.
- Offline tests for deadlines, redirects/response bounds, health shapes, scope
  coverage, maxima/outcomes, redaction and refusal paths. Disposable loopback tests
  for read-only enforcement, both hash formats, aggregation/fallback/sequences,
  cancellation, cleanup and no unintended writes; fictional public fixtures only.
- A source manifest covering the harness and all transitive SQL/connection/hash/
  observer dependencies. The seven anchors below are not a complete execution
  manifest. Review/push/CI/merge follow the usual separate owner gates; do not
  mutate or reuse the qualification-only packet as calibration authority.
- Private receipt: source/target/snapshot/scope digests, member-level coverage,
  per-read outcomes/maxima, resource/transport/session facts, deadlines and cleanup.
  Public/JMax report: fixed categories, counts, elapsed/maxima, scope-complete flag,
  result/limitations and receipt hashes. No DSNs, keys, SQL, row values, member
  identifiers or raw driver errors publicly. Preserve typed timeout, validated
  SQLSTATE and cleanup categories privately; public sanitization stays unchanged.

At execution time recheck local memory under load: at least 1 GiB and 15% free,
with serial work and a proposed 512 MiB / 10% stop floor. Check private-output
ACLs/free disk and current source/approval bindings before any request. Refuse to
start below the existing start floor; stop and clean up if the monitoring floor
is crossed. Do not close unrelated apps or start local PostgreSQL during a hosted
probe. Thresholds are proposed controls, not evidence that resources are sufficient.

## Approval sequence and limits of the result

| Next gate | What it would authorize | Still excluded |
| --- | --- | --- |
| Accept this local design | Local harness, regression tests and documentation | Hosted requests; publication until prompted |
| Review implementation / approve publication | Draft PR and fresh CI | Merge or live execution |
| Approve reviewed merge | Existing automatic test deployment consequence, if stated | Health/calibration requests |
| Approve Stage A exact packet | One bounded anonymous health request | Database connection or repair |
| Review A; approve Stage B exact packet | One bounded read-only calibration attempt | Pauses, installation, grants or credentials |
| Review complete results | Prepare a new installation-inclusive proposal if justified | Actual maintenance or schema application |

No active maintenance window exists. Later installation needs fresh writer and
Companion confirmation, explicit pause authority, strict drain, fresh encrypted
backup/disposable restore, new exact plan hash and separate application approval.
Last owner-confirmed writers were API and Toast jobs 3/4, with Companion local-only;
that is dated evidence, not a fresh writer check. Par editing remains frozen,
ordering manual and Track 1 independent. Personal-login/G04/G13, managed recovery
and fictional functional acceptance remain separate open work.

## Local source anchors inspected

These byte hashes identify inspected accepted source only; they grant no execution
authority. Historical proposals, SQL, manifests and receipts are unchanged.

| File | SHA-256 |
| --- | --- |
| `backend/server.py` | `741d29cf4ec1d71c509e48c4ce85d690dfef5f5929d75fef05072b9e37ef317f` |
| `backend/db_pg.py` | `9d7ce355d0989a41884c37f9074eea4bd72bebaf855a5eebe41eed67ab733639` |
| `backend/maintenance_connection.py` | `7e44e7e95ef6b4211a9dabf6c68ccfeebd0811ad68c54f5736cc7add24e11a5f` |
| `backend/readonly_snapshot.py` | `803c9551e3e31407497c06a44e6fe898a82f08518bfbdd265e89efdb5c535123` |
| `backend/hosted_install_preservation.py` | `3e064e658235e8598cb86c408826ffa0400d03d1df77bd30e9a4114c299204fd` |
| `backend/hosted_backup.py` | `891164d236c56ad9388a2c943f630d06ff7fffcc92668f54e45c2020064048f8` |
| `tools/ops/local_query_metrics.py` | `d7a81ed4b9bae8732f86412881616d48fd7728602515fb74c12510acc7e094fb` |
