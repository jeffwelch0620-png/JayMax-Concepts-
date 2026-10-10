# Local process recovery and populated Food Cost checkpoint

October 9, 2026 (America/New_York). Follow-up to the
[local installer rehearsal](LOCAL_PARALLEL_INSTALL_CHECKPOINT.md).
This adapter and its workers accept only a passwordless loopback connection to
an independently created disposable test database. There is no hosted installer,
credential writer, active configuration promotion or automatic retry.

## Independent recovery inputs

Before any installer mutation, `backend/local_install_recovery.py` verifies both
actual original pool constructors and their separate permission profiles. It
rechecks the prepared catalog and writes an exclusive, fsynced archive. The
archive contains the original metadata, application row fingerprints, migration
ledger fingerprints, sequence values, exact reviewed plan, original role
identities, opening journal hash and hashes of the required source/contracts.
It contains no passwords, connection URLs, business rows or invoice imports.
Its reviewed permission statements and metadata are retained for local recovery.

The owning supervisor retains the archive hash independently before mutation.
It also retains the latest journal hash from the actor's flushed checkpoint
output. Recovery requires both external pins; it never learns a new baseline
or latest checkpoint from the archive, journal or live database being checked.
A valid journal prefix with its final records removed fails the latest-hash
check. Changed code/contracts, wrong targets, altered plans, duplicate JSON
keys, torn records, illegal stage order and reused original OIDs hold progress
before connecting to PostgreSQL.

JSON object order is not a plan input. The inventory/account rendering order
is explicit so saving an archive with sorted fields and reopening it in another
process yields the same reviewed statements. Two earlier integration attempts
held before their first mutation because the original rendering depended on
dictionary insertion order; their receipts, logs and exact source are retained.

## Fresh process behavior

Recovery reconstructs the controller from the pinned archive and legal journal
history, then opens a new owner connection and checks the actual catalog.
Exact durable before-state means not committed; exact expected after-state
means committed; any other state remains ambiguous and held. Accepted states
must also preserve the original row, ledger, sequence and access baseline.
Recovery appends a fsynced reconciliation record but does not execute database
mutation, repair a record, retry a stage or retire a role automatically.

Pool verification does not survive a process restart. Return to singleton
policies requires a new verification of both original and replacement cohorts
through the actual paired constructors. Disabling/revoking replacement roles
requires another fresh original singleton check through the default account
constructor and original inventory permission preflight. Unverified attempts
hold without appending another mutation intent.

## Populated regression and validation

Validation passes: **11 tests and 32 subtests**, including ten guard/controller
tests and one real PostgreSQL integration case. The integration case takes
217.44 seconds and runs twelve separate worker actions. The dependency emits
one existing `python_multipart` deprecation warning; there are no failures or
skips. Exact tested source, the independent metadata archive, public worker
receipts and the passing XML/log are sealed in the local review package.

The disposable fixture uses invented purchase, physical count, prep, waste and
sales context through the existing committed workflow. Its expected period
result is **$55.00 actual Food Cost** with **$40.00 net food purchases**. Received
date remains the purchase date of record, purchased items remain Track 1, and
explicit count values determine opening/closing valuation. Prep/waste/sales
context leaves the complete accounting report and its hash unchanged. Source
taxes and fees remain separately retained. User sample invoices are not imported.

The integration trial genuinely exits worker processes with an open transaction
before CREATE commit and after successful CREATE, LOGIN-enable and singleton
restore commits before recording acknowledgement. Separate OS processes recover
each outcome. An independently introduced column privilege must produce an
ambiguous hold until the owning fixture reverses that exact invented change.
Final verification compares the entire report, all scoped original row/ledger
fingerprints, sequence values, metadata/access projection and archive bytes.
The runner verifies exact database/role cleanup and stops only its owned server.
The passing receipt records nonempty accounting rows, unchanged full report/hash
and all preservation comparisons, both committed/uncommitted recoveries, an
ambiguous hold, and an unverified disable attempt that leaves the journal intact.

## Limits and next requirements

The supervisor remains alive while workers exit; whole-machine power loss and
supervisor death before checkpoint persistence are not proved. A checkpoint
mismatch must hold for independent review. File fsync and readback do not prove
parent-directory crash durability, Windows private-file ACL provisioning,
protection against a compromised supervisor or maliciously rewritten external
pins. This is a local trust-authenticated trial, not hosted password proof.

Hosted pooler capacity and registered client/revision counts, secure durable
replacement credentials, reviewed promotion and a complete combined recovery
trial remain separate gates. The earlier combined recovery hold is not cleared
by this local result. Managed Auth/Storage/Vault and global credential restoration
are outside the existing six-schema backup proof. Merge and operational release
remain held. No GitHub push, merge, deployment, paid add-on or hosted mutation
is part of this checkpoint. The original 40 continuation files remain preserved.

The next useful local step is a durable supervisor checkpoint/credential-store
contract and a registered-client handoff plan. Those must precede any hosted
parallel-account rehearsal; refreshing hosted capacity alone cannot authorize it.
