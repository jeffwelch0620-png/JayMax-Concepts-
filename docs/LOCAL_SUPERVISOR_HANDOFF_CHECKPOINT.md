# Independent supervisor checkpoints and client handoff contract

October 9, 2026 (America/New_York). Follow-up to the
[populated process-recovery trial](LOCAL_INSTALL_PROCESS_RECOVERY_CHECKPOINT.md).
This checkpoint stays local. Supabase roles, policies, credentials, configuration,
business data, native feature flags and GitHub PRs remain unchanged.

## Durable independent metadata

`backend/local_supervisor_checkpoint.py` creates an exclusive witness file in a
separate existing directory outside the repository. It accepts only the same
generated disposable database identities as the local installer. The controller
provides a run UUID, independently archived baseline hash and opening journal
hash before mutation. Recovering a missing or partial witness never creates or
repairs it. Source changes, identity mismatches, damaged history, incompatible
durability mode and stale writers hold progress.

The witness uses SQLite transactions with FULL synchronous mode and the DELETE
journal mode. It stores only hashes, run/database identities, sequence numbers
and a checked checkpoint history. **No inventory, purchases, counts, prep,
sales, invoice data, URLs or passwords are stored here.** PostgreSQL remains
the application data source. This small file is recovery-control metadata.

Each update holds a SQLite write transaction and compares the caller's previous
receipt before recording its next checkpoint. The receipt is captured inside
that same transaction and returned only after commit. Duplicate observations
of the current head are idempotent; a stale writer cannot overwrite a newer
checkpoint. The original metadata contract never changes during updates.

`CheckpointedJournal` first fsyncs a legal journal record and then commits the
separate witness checkpoint. `recover_from_witness` reads the surviving witness
and supplies its external pins to the existing archive/journal recovery logic.
It persists the resulting reconciliation checkpoint and attaches the same
journal wrapper for subsequent explicitly requested local stages. It does not
execute installer stages, change global pools or promote configuration.

If a process ends between the journal write and witness commit, the two files
differ and recovery holds before connecting to PostgreSQL. There is no trimming,
automatic retry, checkpoint adoption from live state or permission cleanup.
Fresh pool proofs remain required after restart.

## Exact client handoff review

`backend/client_handoff_review.py` validates an independently pinned declaration
of every backend instance, its source commit, distinct original/candidate config
revision UUIDs, immutable credential bundle references, and both profile pool
limits. The pool size is exactly two per profile, matching the actual paired
constructors. Registry inputs are copied; later edits cannot alter the plan.

Declaration assessment requires one recent acknowledgement from every registered
instance, the expected source and candidate revision, and both original pools
declared closed. Missing, duplicate, unknown, stale, future-dated, mixed-revision
or incomplete observations hold. Capacity must cover the exact instance count
in both PostgreSQL and the session pooler; a PostgreSQL sample alone is not
accepted as pooler capacity. The existing limit-six role budget also constrains
how many overlapping instances fit; adding workers requires another capacity
review, rather than assuming an idle application has no connections.

These are **declarations and review contracts**, not proof of live client state.
Even a passing declaration assessment keeps promotion authorization, verified
live registration, credential verification and operational release false. No
environment discovery, network call, SQL, secret reader/writer, configuration
switch or role retirement occurs in this module.

## Credential storage contract

The selected original private local connection file remains in use. This step
does not migrate it, read its secrets during testing, or create new credentials.
Candidate and original bundles must eventually have distinct immutable references
under a fresh private local directory outside the repository and sync roots.
The contract requires owner-only ACL readback, encrypted credentials and an
independent recovery mechanism, durable candidate storage before LOGIN, actual
password/TLS checks and recovery of the exact original bundle. Public receipts
must contain only references and safe verification results.

The candidate credential store is **not implemented or verified** here. An
eventual hosted backend needs its own reviewed secret-provider adapter; this
Windows-local contract does not establish how a Linux host receives credentials.
No paid service or deployment selection is introduced by this checkpoint.

## Validation and limitations

**21 tests and 61 subtests pass** in 8.24 seconds, with one existing dependency
deprecation warning and no skips. Separate OS processes exit before and after
actual SQLite COMMIT, and fresh readers observe the correct previous/new
checkpoint. A real exit in the journal/witness gap holds recovery before
networking. Concurrent stale writers cannot both succeed; malformed registries,
invalid capacity and valid truncated journal prefixes are rejected. A mocked
PostgreSQL connection verifies that the existing recovery logic records a
not-committed reconciliation and persists its new independent checkpoint.
That mocked case is not an additional live PostgreSQL recovery proof.

The preceding populated PostgreSQL proof remains in its own unchanged snapshot:
$55.00 actual Food Cost, $40.00 net food purchases, unchanged complete report and
original rows/ledger/sequences/access. PostgreSQL and hosted checks are not
repeated here because this checkpoint changes recovery metadata and review
contracts, not the original transaction engine or accounting logic.

The first run exposed an unclosed SQLite handle in fixture cleanup on Windows.
The fixture now closes its handles explicitly; its failed XML and exact source
are retained. Automatic approval review rejected recursive removal of that one
earlier temporary fixture, stating "blocked by policy"; the metadata-only folder
was left in place. Current passing fixtures clean up successfully.

Process-exit evidence does not establish whole-machine power-loss durability,
directory-entry persistence, disk-controller guarantees or protection against
malicious replacement/rollback of the witness and external pins. Private ACLs,
encrypted credential storage and trusted supervisor ownership are still separate
requirements. Both files can disagree after a crash; that is an explicit held
state for independent review, not automatic recovery success.

## Next step and release status

Implement and locally verify the private candidate credential-store adapter and
its exact original-bundle recovery before attempting a hosted parallel-account
trial. Connect independently observed client/session evidence to the registry
and measure both hosted capacity limits before any promotion. The earlier
combined backup/credential recovery hold, merge and release gates remain held.
No hosted change, push, merge, deployment or operational import is authorized
by a passing local declaration or witness receipt. The original 40 continuation
files remain byte-for-byte preserved.
