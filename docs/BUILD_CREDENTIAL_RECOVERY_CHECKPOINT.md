# Retained build credential rotation and recovery — October 9, 2026

Follow-up: the [read-only pooler diagnosis](POOLER_DIAGNOSIS_CHECKPOINT.md)
verifies direct access for both original LOGINs and records the exact dashboard
EAUTHQUERY event with its missing role attribution. The combined hold below
remains unresolved; historical direct-access uncertainty is superseded only by
that later diagnostic evidence.

**Rotation authentication/reconnect checks passed; combined LOGIN-disable recovery
remains held.** Both recovered retries proved replacement authentication, old
credential rejection and pool reconnection. The final disable check returned
internal pooler errors on both bounded attempts, so it was not counted as a
successful revocation check. The original private credentials and both LOGINs
are restored and freshly verified. All application/native rows, global Track 1,
the complete ledger, catalog/access and role attributes match the starting
baseline. None of the replacement files is current. Eight local guards pass.
Active settings and merge holds remain unchanged.

This follows the [enabled retained LOGIN workflow checkpoint](RETAINED_LOGIN_WORKFLOW_CHECKPOINT.md).
The probe targets only the two exact recorded generated build roles on the
existing designated Supabase project. The active application's configuration,
native flags, schemas, business rows and external integrations remain unchanged.

## Controlled process

The probe verifies the provisioning and passing workflow receipts, project,
endpoint, role identities, held disk flags and restrictive role attributes.
It saves full original-column fingerprints, global Track 1 row fingerprints,
complete migration-ledger hashes, catalog/object ACL/policy hashes and role
attributes. Test sessions default to read-only. Credentials and passwords are
never part of the safe journal or shared package.

Replacement credentials are staged exclusively in a new Windows-private folder
before either password is changed. The original private file remains intact for
recovery. Only the recorded roles' passwords and LOGIN ability may change;
object grants, policies, role membership and privileges are not expanded.

After rotating both passwords in one owner transaction, the probe authenticates
replacement credentials first, with at most three attempts and 15-second intervals
only for password-denial errors. Transport failures stop the check. It then distinguishes
existing session continuity from fresh authentication. It requires replaced
credentials to be rejected by fresh clients; transport failures do not count as
authentication denials. Replacement pools must reconnect as the actual recorded
LOGINs. The separate account pool uses its application startup permission gate.

Next, one recorded LOGIN at a time is disabled with no live test sessions. A
fresh client must be rejected after a 15-second propagation interval while the
other role remains usable. One internal pooler error permits one additional
15-second retry; only a final authentication/authorization denial qualifies. A
second internal error holds the test. The owner
then restores LOGIN and a new authenticated client must connect. The test
accessors must return 503 when their configured pool is absent. No automatic
owner or cross-pool fallback is introduced. Final permission assessments and
independent full-row/catalog/access comparisons must pass.

If any post-mutation step holds, the owner restores both prior passwords and
LOGIN ability, verifies fresh connections through the original private file and
compares the full original baseline again. A held case does not authorize a
blind retry or claim that replacement configuration is current. Lost journal or
recovery acknowledgments require separate reconciliation before proceeding.

## Evidence and limits

Eight standalone guards test exact role/project/workflow prerequisites, unchanged
endpoint/flag values, exclusive private-file writes, rejection before connection,
authentication-denial versus transport-failure classification, bounded refresh
retries, disabled-LOGIN propagation retry classification and closing an
unexpectedly accepted connection. The repository-wide fixture expects a Linux
`/app/frontend/.env`; selected tests disable that unrelated conftest. These tests
are not a full backend suite, browser run or managed recovery exercise.

This is a database credential test, not human staff identity verification or a
sign-in redesign. Password changes and disabling LOGIN must not be presented as
termination of existing sessions; session termination needs a separately reviewed
process. Owner-assisted role recovery does not prove Auth/Storage/Vault recovery.

## Initial hosted hold and recovered baseline

The first hosted attempt committed the password change and confirmed that existing
sessions stayed usable. After closing those sessions, a fresh session-pooler client
still authenticated with the replaced credential, so the probe held immediately.
The owner restored both original passwords and LOGIN ability. Fresh original-file
connections passed; full application/native row fingerprints, global Track 1,
the complete ledger, catalog/grants/policies and role attributes matched the
starting baseline. The replacement file from that attempt is not current.

[Supabase's shared-pooler rotation guidance](https://supabase.com/docs/guides/troubleshooting/supavisor-error-password-authentication-failed-after-password-rotation)
describes briefly cached credentials and reconnect-driven refresh. This is
consistent with the observed old-credential acceptance, but direct PostgreSQL
bypass was not verified, so the cache diagnosis remains an inference. The revised
probe first verifies replacement authentication with bounded refresh retries,
then requires rejection of the replaced credentials. It does not conceal the
original hold or claim that a driver timeout proves credential revocation.

## Second held attempt and isolated LOGIN classification

The second attempt passed fresh replacement authentication, denial of both old
passwords (`InvalidPasswordError`) and reconnection of both replacement pools.
The first inventory-NOLOGIN check returned a pooler `InternalServerError`, which
was not treated as authentication proof. Both old passwords and LOGIN ability
were restored; reconnects and the complete starting baseline passed again.

A separate exact-role probe confirmed the inventory role was NOLOGIN, received
`InvalidAuthorizationSpecificationError` / SQLSTATE `28000` with only the known
"not permitted to log in" category retained, then restored LOGIN and verified the
original credential and both role attributes. No raw driver message or credential
was included. The combined probe permits one bounded retry of an internal pooler
error and still requires a subsequent real authentication denial; a repeated
internal error remains a hold. This isolates the observed error-format transition
without redefining arbitrary pooler failures as successful revocation.

## Remaining steps

Keep merges and active app cutover held. Browser/Data API exposure, matching
compiled/server flags, managed recovery, broader workflows and sequential PR
validation remain outstanding. Any observed hosted connection behavior must be
resolved before credential rotation is declared deployment-ready. Private files
remain outside Git, PRs and shared reference materials.

## Final held evidence and next diagnostic step

The latest receipt is `build-rotation-20261009T1507511805325Z.json`.
It preserves `InvalidPasswordError` denial results for both replaced credentials,
replacement pool reconnect success, the two internal-error frames from the
bounded inventory disable check, and verified original-credential restoration
with complete baseline preservation. The account-role disable check, later
unavailable-accessor checks and post-recovery permission assessment did not run
because the test held earlier; do not report them as passed. Pooler cache lag is
an inference supported by published guidance, not verified direct-connection
causation. Initial held attempts and the isolated inventory 28000 result remain
in the review package.

Before another credential change, inspect the hosted pooler logs and evaluate a
read-only direct PostgreSQL connection. Establish the precise disabled-role
error contract and whether direct/session-pooler results differ. If the shared
pooler remains unsuitable for same-role replacement/revocation, review staged
new-role rotation with parallel credentials and explicit old-role retirement,
as recommended by the cited Supabase guidance. Do not retry rotations blindly,
terminate broad sessions, replace owner access automatically, or treat every
XX000 internal error as authentication proof. Managed recovery and deployment
checks remain outstanding.

The original private file and all three inactive staged replacements pass actual
file-owner and user/System-only ACL checks; their parent folders retain protected
user/System-only access. Shared artifacts scan for every actual URL/password from
those four private files and exclude the files themselves.
