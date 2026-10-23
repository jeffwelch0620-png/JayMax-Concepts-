# PR58 review amendments - October 23, 2026

The owner authorized local amendments, regression tests and a push to the existing
[draft PR58](https://github.com/jeffwelch0620-png/JayMax-Concepts-/pull/58).
Merge approval remains separate. Hosted work/service controls and credential,
grant, schema and app-connection changes remain held. No maintenance window or
hosted probe is authorized by these changes.

## L1: complete private timeout attribution

Both par-only fingerprint families now classify a timed-out batch without retry
or fallback. Original-projection reads raise `FingerprintBatchTimeout`; backup
reads retain `BackupError`. Driver `TimeoutError` and PostgreSQL
`QueryCanceledError` are caught only around the actual reads. Ordinary task
cancellation propagates unchanged. Backup cursor fallback and sequence reads
also retain private attribution; a failed cursor is never restarted.

A frozen, typed context contains the fixed family, up to four candidate relation
identities and a bounded original error category. It is not a claim that a
particular member caused the timeout. The wrapper preserves validated SQLSTATE
and existing cleanup categories without copying driver messages or SQL.
Mutable/untyped driver attributes are not used as receipt metadata.

The par engine copies this context into its private failure report, including
rollback/unknown-outcome cases; the hosted envelope retains it for preparation
and post-commit verification failures. The existing public sanitizer stays
unchanged. Public CLI output still uses its fixed allowlist and excludes member
names, private detail and driver text. No business row data is added anywhere.

Four `TIMEOUT_TOOLING_AMENDMENTS` links start at the four current fingerprint
amendment hashes. The original two and earlier four links remain intact; V2
packets disclose the additional links and refuse missing/stale/disconnected or
unknown paths. Source coverage remains 49 core / 56 total / 31 exact SQL files.
Historical proposals, source pins, packets and receipts are unchanged. All
execution approvals remain false.

## H1: statement headroom is a separate hosted gate

The [installation runbook](REVIEWED_PAR_INSTALLATION_RUNBOOK_20261022.md) now
leads with accepted PR57 and candidate PR58, preserving its older qualification
and performance records as dated evidence. A separately approved API health
check precedes a separately approved, bounded read-only calibration proposal.
Neither check is implemented or authorized by this amendment.

Before proposing an installation window, the probe must cover all statements in
both two-relation fingerprint families inside repeatable-read read-only snapshots.
It must record complete scope, per-family maximum observed driver query await,
total elapsed time and workload/cache limitations. Each observed maximum must be
at most **10 seconds**, a conservative operating margin against the unchanged
20-second statement limit. This is not an empirical guarantee or isolated server
timing measurement. Any timeout, incomplete coverage or failed guard holds.

Above that threshold, consider size one only through a reviewed source amendment,
then re-measure statement and overall timing and re-evaluate the 450-second
planning screen. Extra calls may erase the planning margin. There is no automatic
fallback, broader timeout or removed verification. Memory still requires at least
1 GiB and 15% free under load; the operation limit stays 600 seconds.

## Validation and evidence

Fresh amended-head CI is verified separately after push. The complete local
PostgreSQL selection passed **141 cases** (32 methods + 109 subtests), with zero
failures/errors/skips, in 999.43 seconds. It verified server/client timeout
attribution, task cancellation propagation, cursor/sequence failures, digest
parity and installation security/rollback/recovery. Starting database/role
inventories matched and the owned PostgreSQL server stopped. All work used the
disposable loopback target; no hosted connection was used.

The database run started at 1,176.2 MiB / 19.5% free, after the earlier 959 MiB
resource observation held startup and the owner freed memory. The unchanged
1 GiB / 15% floor was enforced. This is regression-suite elapsed time across
32 methods, not the duration of a single installation operation.

The broad Windows offline profile passed **1,378 cases** (475 methods + 903
subtests) in 110.00 seconds, with zero failures/errors/skips. Profiles overlap;
the focused and database totals are not extra disjoint coverage.

Final source-packet SHA-256:
`c20d9e474579aadb04bd744892124e01eddc6d06716f19b4923e0a816c007789`.
It binds all 49 core / 56 total sources and 31 exact SQL files; every execution
approval remains false. Documentation checks found 201 working relative links.
SQL, historical pins and the shared public sanitizer remain unchanged.
The initial focused selection passed 61 methods plus 223 subtests (284 reported
cases), with zero failures/errors/skips. It covers private receipt phases,
public-output redaction, timeout metadata and source-amendment refusal.

The original `569ade9` retained-data timing and JSON receipt remain unchanged
dated evidence: 764 apply/fresh-verification calls / 45.063 seconds, 31.29% fewer
calls, and 362.527 seconds under the old additive planning arithmetic. This
diagnostic-only amendment does not claim a new timing benchmark or hosted fit.
The historical fingerprint function bodies, successful SQL/hash algorithms,
snapshot boundaries, exclusion rules, fallback/path counters and limits remain
unchanged. Only error handling and private attribution change.

Next: obtain fresh exact-head CI and return for owner merge approval. The PR stays
draft. Hosted health/profiling, service pauses, installation-inclusive maintenance,
fresh backup/restore, exact-plan approval, functional acceptance, O1 and G04/G13
remain separately gated. Ordering stays manual, par editing frozen and Track 1
independent.
