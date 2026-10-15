# Bounded server-side backup fingerprint follow-up — October 14, 2026

## Accepted baseline

The owner approved merging PR31 and proceeding with the review recommendations.
PR31 merged at `cb63129e30e6810ba3994b9591d5d2a39cac8555`, reviewed head
`7be06da404b8ea5f9b2fcd2f72c1e703c2313473`.
[Head CI](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/38670997386)
passed all four checks: 689 frontend tests/build, 724 offline cases and 78 full
PostgreSQL cases. [Merged-main CI](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/38672033102)
also completed successfully. These results supersede the historical pending-CI
entries in PR31's preparation notes. A new local branch starts from that merge;
the follow-up is [PR32](https://github.com/jeffwelch0620-png/JayMax-Concepts-/pull/32).

## Implementation and compatibility

`hosted_backup.relation_fingerprint` aggregates the current algorithm's sorted
hex row hashes and trailing LF bytes on PostgreSQL. It returns one count/hash
record instead of fetching every row hash in cursor batches. It preserves the
existing `ROW_ALGORITHM` and encrypted manifest formats.

The inner query limits the probe to `8 MiB // 65` rows: **129,055 hash lines**,
each 64 ASCII hex bytes plus one LF. Its aggregate payload is at most 8 MiB.
Only a probe with fewer rows is accepted as complete. A full probe, including an
exact-threshold table, discards its partial count/hash and uses the original
cursor over the entire relation in the same caller-owned snapshot. No catalog
estimate or separate snapshot can authorize acceptance of a partial table.

This bounds the aggregate hash-line payload, not PostgreSQL's total sorting,
JSON conversion or other workspace memory. Large tables incur the bounded probe
plus a full cursor scan; no speed-up is promised for that case. Catalog reads
remain unchanged. No server setting, role or persistent configuration changes.
Actual hosted timing and pooler behavior still require a later approved rehearsal;
local equivalence cannot establish a duration in seconds or the old stall's cause.

Sequences retain the original `last_value`/`is_called` JSON hashing. Archives with
the older raw-row algorithm retain their original ordering and cursor path.
Partitions and materialized views retain the same relation/count semantics.
`server_aggregation=False` provides an explicit comparison path for tests; it is
not a new deployment setting or UI control. SQL errors propagate and hold the
backup; only a full size probe selects fallback. The PR31 export deadline,
ownership, graceful cancellation, safe diagnostics and publication gates remain.

## Validation

New fictional loopback checks compare complete optimized/cursor fingerprints
for empty tables, duplicates, SQL nulls, UTF-8/emoji, CRLF/newlines, JSON, numeric
scale and binary data, with partitions, a materialized view and a sequence.
Forced small bounds exercise below/at/above-threshold behavior and prove that a
partial aggregate is never accepted. Legacy raw-row results are compared too.
The real encrypted export/restore fixture now captures both optimized and cursor
archives, compares their table/catalog fingerprints, and restores the cursor
archive through the optimized reader. The algorithm/version stays unchanged.

Offline guards cover aggregate errors without a cursor retry and full-probe
discard followed by complete streaming. The first offline run exposed a prior
heartbeat test's 60-ms timing assumption on Windows; its test-only budget is now
500 ms, while production deadlines remain unchanged.

The final source-frozen run completed **October 14 at 10:50:16 p.m. EDT
(2026-10-15T02:50:16Z)**:

- **728 offline cases** (283 methods and 445 subtests): zero failures/errors/skips.
- **8 targeted PostgreSQL cases** (4 methods and 4 subtests): zero
  failures/errors/skips. These include the new equivalence/boundary/legacy case,
  real optimized and cursor export compatibility with encrypted restore,
  busy/idle deadline and operator cancellation, and the fresh active-writer guard.
- Runtime/test source hashes stayed fixed. Before/after local database and role
  inventories match; the owned local server is stopped. No hosted connection or
  real invoice was used. Only existing dependency deprecation warnings remain.

The full database selection and frontend build were not repeated locally for
this follow-up. [PR32 CI at reviewed head 49291d0](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/38674127950)
subsequently passed all four checks: 689 frontend tests across 67 suites plus
production build, 728 offline cases (283 methods and 445 subtests), and 79
PostgreSQL cases (64 methods and 15 subtests), with no failures/errors/skips.
The owner approved the documentation refresh and merge; the documentation
commit must also have green CI before merging. JUnit reports, frozen source
hashes, the initial heartbeat-test failure and the final receipt are retained
locally for independent review.

Final source-hash test receipt SHA-256:
`b4d8bc3ce7c80fa842d8e3c197333fc842eae7b8a0dd7a5f038694b06139f01c`.

## Private artifact inventory

A metadata-only inventory accounts for **38 pre-existing artifact sets** in the
private local backup/credential roots: **6 encrypted backups with keys, 3 key-only
sets pending review, and 29 metadata-only sets**. The inventory itself is stored
in a newly ACL-protected private directory and is excluded from those counts.
All present key/archive/partial files had their ACLs verified. The single known
cancelled recapture key was matched to the checksum-verified historical early-close
receipt and remains retained without a final archive or partials.

No key contents were read, no business data was decrypted and no artifact was
deleted. Key-only sets are candidates for provenance/retention review, not
automatically disposable keys. Exact paths remain in the private inventory;
none are published here. Private inventory SHA-256:
`d39011d605eaf6dd77f3f0a4b8df6bbd13e609bd1c3df73ea86b42629647a26f`.

## Remaining gates

The README and maintenance plan now name the **OPEN pre-operations restricted
runtime credential gate**. The recorded owner deployment is distinct from the
tested restricted inventory/account roles. Application authorization and data
constraints continue to matter, while owner connections do not gain the intended
restricted-role separation. Current build connections remain unchanged pending
owner/coworker decisions and a separately approved deployment cutover.

A new hosted rehearsal still needs refreshed source pins, writer inventory/drain,
a newly approved window, a fresh canonical encrypted backup and verified restore,
and separate approval of the exact index plan. Hosted cancellation must separately
verify the exact export/tool sessions and the broader writer guard; local tests
do not qualify Supabase pooler cleanup or managed-service recovery. The old
October 14 window and active control pointer remain closed. No hosted database,
job, index, credentials, schema migrations or Companion integration changed in
this follow-up. Diagnostic path counters are a separate local follow-up;
command/export budgets stay unchanged. At the next approved hosted rehearsal,
record fingerprint duration against the earlier 158.9/181.0-second observations;
those historical durations do not establish a comparable benchmark or cause.
