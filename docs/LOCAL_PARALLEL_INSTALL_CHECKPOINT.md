# Local parallel-account installer and failure-recovery rehearsal

October 9, 2026. This checkpoint implements the next disposable PostgreSQL trial
from the [paired startup plan](PAIRED_STARTUP_INSTALL_PLAN_CHECKPOINT.md).
Hosted Supabase, selected private credentials and active application configuration
remain unchanged. Combined recovery, active cutover, merge and release remain held.

## Implemented behavior

`backend/local_parallel_install.py` accepts only an explicit `127.0.0.1` port and
a unique `native_purchase_test_<32hex>` database, with no password, query-string
overrides or fragment. It verifies the actual loopback server, database and
unchanged session/current superuser identity before mutation. There is no hosted
apply command, environment switch, active-config writer or automatic role drop.
This is a trust-authenticated local test adapter, not private credential staging
or proof of hosted password authentication.

The controller renders its stages from the existing exact profile plan: create
two restricted NOLOGIN roles, apply the profile grants and 66 same-profile TO
additions, enable the local test roles, restore the 66 original TO singletons,
then disable and revoke the replacement grants. Original passwords, role
attributes, ownership, default privileges and memberships are not deliberately
altered. Retained new roles require independent dependency review before removal;
only the owning fixture drops its unique database and exact invented identities.

Before each transaction, a metadata-only journal records the intent and baseline
digest and fsyncs the file. It records the expected after-state digest and actual
created role OIDs before COMMIT. Records form a checked hash chain. Reusing a
journal path, malformed metadata, corruption or failed persistence holds progress.
There is no SQL, URL, password, business row or migration statement in the journal.
The chain detects accidental corruption; it is not a signature or protection
against malicious rewriting/truncation. Parent-directory crash durability and
Windows credential ACL provisioning are not established by this local trial.

Changes use bounded transactions, a cooperative database-specific advisory lock,
SHARE locks on the original application tables, and a repeated baseline check
after locking. Locks are not a prohibition on independent administrators changing
global role metadata. Unexpected catalog changes hold the controller instead of
being overwritten. An independent after-state/preservation check runs before
commit. Partial grant/role steps roll back together.

A missing COMMIT acknowledgement is always unresolved initially. The controller
closes its own connection, refuses another mutation, and checks a fresh connection
against durable before/after digests. Exact after-state means committed; exact
before-state means not committed; any other state remains ambiguous and held.
There is no automatic retry or repair. The caller must explicitly request the
next stage after successful reconciliation.

Return to the originals follows the ordered plan. Both actual paired constructors
must pass for the original and replacement cohorts while all four local roles
still allow LOGIN. All owned pools are closed. Original singleton policies are
restored, then the default account constructor and original inventory permission
preflight pass before new roles become NOLOGIN. Unknown sessions prevent restore
or revoke; the controller does not terminate them or change global pools/retries.

## Preservation scope

An independently captured baseline pins all original columns and row digests in
public, purchasing, actual_inventory, prep_inventory and integrations; complete
ledger rows and ledger column identities; sequence values; schema definitions,
ownership and policy expressions; all visible role attributes, memberships and
database-role settings. Effective access comparisons additionally cover schema,
relation/sequence, function, type, column and database ACLs, grantors and grant
options, plus all default ACL rows. Ledger schema access is included.

The projection masks new-role grantees and new-role policy TO OIDs. The SQL plan
supplies the exact same-profile changes; actual startup inspectors separately
check the complete replacement privileges and policy cohorts. Column grants to
original roles, PUBLIC/inherited access, original
role settings/memberships, policy conditions and accounting rows are not masked.
NULL and explicit owner-only ACL representations are compared by their effective
privileges. Sequence reads are not MVCC snapshots; the disposable fixture has no
independent business writer, and SHARE locks only serialize table writes.

This is preservation of invented local rows. It is not another hosted row audit,
backup or operational-data import. Track 1's purchased-item actual-count/accounting
facts remain separate from prep, waste and sales explanation. No invoice is imported.

## Test evidence

Final evidence is recorded in the sealed local package and its XML/JSON receipts.
Thirty-nine unit cases and 108 subtests pass; two real PostgreSQL cases and two
additional subtests pass, for 41 cases and 110 subtests. The real run takes 586.46
seconds because each failure/commit boundary captures the full baseline again.
The dependency's `python_multipart` deprecation warning does not fail a check.
The trial exercises statement failure, cancellation, failed durable expectation
write, committed and uncommitted lost acknowledgements, exact creation OIDs,
actual pool failure cleanup, original singleton return, name collision, unknown
session holds and ambiguous column-ACL drift. Full baseline projection, row,
ledger and sequence preservation are asserted; fixture cleanup compares all local
database/role identities before and after and stops its owned local server.

This fixture contains invented public item/store rows; its native accounting
tables have no closed-period facts. Their zero-row digests and schema/access
preservation are checked. This run is not a nonempty Food Cost report regression;
the next recovery fixture should include the existing synthetic purchase/count,
prep/waste/sales workflow before pinning its baseline. Initial actual original
profile verification must also be part of a future hosted preflight, rather than
relying on a test fixture's known grants and policy setup.

Two earlier attempts are retained as held evidence. The first stopped before
controller mutation because PostgreSQL reports an inet text value with `/32`;
the actual host check now uses `host(inet_server_addr())`. The second stopped
during preflight because `aclexplode` rejects zero-dimensional empty ACL arrays;
the snapshot retains empty-object metadata while avoiding that expansion. Both
attempts completed exact fixture cleanup and stopped the owned server. Neither
is counted as a passing installer rehearsal.

## Remaining work

The journal currently reconciles interruption in the same running controller.
It does not reconstruct a controller after process/machine restart: the full
independent baseline and original identities remain in memory. Next, archive and
validate those independent pins, reopen a checked journal without truncating it,
and rehearse recovery from a separate process against that populated synthetic
baseline before any hosted installer is built.

Hosted preparation still requires verified client/configuration registration,
measured session-pool/client/backend capacity, secure private replacement-file
staging and a separately authorized controlled hosted trial. The earlier hosted
original-profile verification is retained in the predecessor package; no hosted
check was repeated here. Provider-specific combined recovery, promotion, retirement
and publication remain separate held gates. Local tests do not clear those gates.
