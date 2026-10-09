# Hosted inventory/account connection trial — October 9, 2026

**The final hosted two-pool trial passes.** Sixteen clients authenticate across
two rounds: ten inventory and six auxiliary clients. Both reviewed permission
assessments pass; inventory/account boundaries reject the three prohibited read
attempts in each round. Both temporary roles and their policies/grants are removed.
A separate final connection confirms the same pinned catalog, normalized
effective object ACLs, policy metadata, migration ledger and observed row counts.
No business row is written. Three local target-guard tests also pass.

Evidence retained with the review package:

- `hosted-two-pool-20261009T1310221826920Z.json`: passing assessments, 16 client
  identities, source hashes and matching before/after snapshot hashes/counts.
- Matching `.progress.json`: completed trial reference; no connection material.
- `hosted-two-pool-target-guards.xml`: three passing guard tests, no skips.
- The interrupted-run recovery receipt and tooling described below.

The guard tests reject a mismatched project, a direct endpoint for this
session-pooler canary and enabled native feature flags before any database
connection is attempted. Existing Starlette deprecation warnings remain.

This follows the locally validated
[separate account/notification connection](AUXILIARY_CONNECTION_CHECKPOINT.md).
The target is the previously designated Supabase build project. The saved owner
readiness file selects PostgreSQL with native feature flags held. The canary
requires an explicit matching project reference and session-pooler connection;
it does not infer authorization from a URL alone.

## Trial boundary

`backend/hosted_auxiliary_trial.py` creates two fresh random LOGIN roles with
generated passwords held only in memory, a one-hour password expiry, no elevated
attributes or inherited memberships, and read-only transaction defaults. It
commits only temporary grants and policies needed to test ordinary logins.
It does not write accounts, subscription rows, purchase documents, count records
or other business data. It does not invoke web push, Toast or other integrations.
No saved application URL, flag or permanent credential is changed.

The inventory role receives the existing frozen matrix and exact required native
invoker functions. The auxiliary role receives public USAGE and the four reviewed
table verbs on `app_users` and `push_subscriptions`, with explicit role-addressed
RLS policies. No inventory privilege is added to the auxiliary profile and no
account privilege is added to inventory. Backend authorization remains the
location/user boundary for the account policies; this is not a new sign-in design.

Two rounds create simultaneous inventory and auxiliary pools. Five primary and
three auxiliary clients are acquired together per round. Each checks actual
LOGIN/current-role identity, an explicitly established read-only boundary and
the JSONB codec. The inventory assessor checks the complete hosted 96-function,
127-relation contract; the auxiliary assessor checks its narrow permissions.
The auxiliary pool is created by the actual `db_auxiliary._try_connect` helper.

Read attempts verify that inventory cannot read accounts and that auxiliary
cannot read native posting batches or staff PINs. Permitted table counts are
read without returning account, password or business row contents. This is
hosted connection/permission evidence; account writes and Food Cost comparisons
were tested locally in the preceding checkpoint, not by this hosted canary.

## Cleanup and preserved state

All client pools close before cleanup. A new owner session reconciles the two
exact generated roles, including after an uncertain commit acknowledgment.
Cleanup verifies each policy still belongs only to its intended trial role,
removes the exact policies and grants, and drops those roles. An uncertain
cleanup holds the result and attempts to disable only those trial logins.
Unrelated roles, policies and grants are never removed.

A separate subsequent connection verifies role absence and compares the original
catalog, normalized effective object ACL entries, policy metadata, migration
ledger and selected table counts. ACL normalization compares effective entries
rather than the spelling of an implicit versus explicit default ACL. The receipt
retains hashes and observed counts, not catalog SQL bodies or business rows.
Unchanged counts alone do not prove unchanged row content; the canary itself
issues no business writes and clients operate read-only.

The base schema, both catalog references, inventory permission matrix, application
pool code and all 29 migration hashes remain unchanged in this step. The previous
snapshot remains the source for the eleven selected local passing checks; those
tests are not counted as newly rerun hosted business workflows.

## Retained interrupted attempt

The first hosted run stalled after temporary role creation and client connection.
It produced no completed permission/cleanup receipt. Its specifically verified
local process was stopped, and a recovery probe verified the two exact role OIDs
and complete expected policy set before disabling those logins and removing
their policies/grants/roles. An independent connection confirmed role absence,
candidate policy absence and the unchanged pinned hosted catalog. That attempt
remains held. Its original ACL baseline existed only in process memory, so a
complete before/after ACL comparison is not claimed for the interrupted run.

The recovery receipt is `hosted-two-pool-recovery-20261009T130958558270Z.json`.
The retry records safe baseline hashes before applying grants and emits progress
stages without connection material. Inventory assessment is bounded and runs
once per trial; the second round checks fresh simultaneous logins and boundaries
under those unchanged grants. Auxiliary pools still perform their real startup
assessment in each round. Recovery tooling and the interrupted source version
are retained with the review evidence.

Supabase documents [custom role usernames and session pooling](https://supabase.com/docs/guides/database/connecting-to-postgres)
and [database LOGIN roles](https://supabase.com/docs/guides/database/postgres/roles).
Actual trial receipts, rather than those general documents, establish this
project's connection and cleanup results.

## Remaining rollout and merge hold

The measured rollout sequence is:

1. Choose the backend's private secret storage and recovery custodian; keep
   deployment credentials out of Git, shared snapshots and browser configuration.
2. Provision permanent inventory and auxiliary LOGINs with the same reviewed
   boundaries. Verify effective privileges before wiring either into the app.
3. Store both URLs together for the same endpoint/project and retain the owner
   connection separately for controlled administration and recovery. Keep native
   feature flags held during the connection change.
4. Exercise enabled workflows with invented, identifiable build-project fixtures
   and verify accounting records before/after, replay, concurrency and cleanup.
   Selectively enable matched frontend/server flags after those checks pass.
5. Verify rotation/reconnect and recovery, browser/Data API exposure and the
   sequential PR stack before recommending any merge or publication.

The user selected **private local configuration for continued build/testing**
for the next credential step. Prepare the two secrets in an access-restricted
local directory outside Git and shared snapshots; retain the existing owner
readiness connection separately. No permanent credential is provisioned or
saved by this checkpoint, and the active application connection is not switched.

Prepare permanent credentials with a secure storage/rotation and recovery plan,
then validate enabled application workflows using those connections. The
temporary removed trial roles are not deployment credentials. Browser/Data API
acceptance, matched frontend/server flags, managed Auth/Storage/Vault recovery
and sequential PR stack revalidation remain open. Continue holding merges.
This is a local review checkpoint; nothing is pushed, merged or published.

## Subsequent retained connection setup

The [private build connection checkpoint](PRIVATE_BUILD_CONNECTIONS_CHECKPOINT.md)
now provisions and validates retained inventory/account LOGINs and stages their
secrets in the selected access-restricted local configuration. It preserves the
previous temporary-trial evidence and frozen references. The active application
is not switched; enabled workflows, rotation/recovery and remaining release gates
still need validation. Keep holding merges.
