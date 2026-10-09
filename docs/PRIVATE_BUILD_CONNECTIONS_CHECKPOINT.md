# Retained build connections and private local storage — October 9, 2026

**Both retained build connections pass verification.** Eight simultaneous clients
authenticate as the intended inventory/account roles; both permission assessments
pass and all three prohibited reads are denied. The independent post-provision
check confirms the same catalog, ledger and observed counts and unchanged
pre-existing effective object permissions/policies. Only the two reviewed build
roles' new access is retained. The staged file and its folder permit only the
current Windows account and SYSTEM; active application configuration is unchanged.

Safe evidence retained in the review package:

- `build-connections-20261009T1338099970427Z.json`: passing role assessments,
  eight client identities, before/after preservation checks and source hashes.
- Matching `.progress.json`: stage metadata; the completed receipt is authoritative.
- `build-connection-provision-guards-v2.xml`: four passing local guard cases.
- `build-credential-acl-20261009T1341368131743Z.json`: file/folder protection check.
- `build-connections-20261009T1335386806285Z.json`: initial local ACL-check hold.

The private file's values are excluded from shared evidence. The review packager
also checks its entries against the actual staged connection URLs/passwords,
without emitting those values. Original pending source work is preserved.

This step follows the passing [hosted two-pool trial](HOSTED_TWO_POOL_CHECKPOINT.md).
The user selected private local configuration for continued build/testing. It
stages retained database credentials without switching the active application or
enabling operational workflows. Inventory accounting/schema logic is unchanged.

## Provisioning and secret boundary

`backend/provision_build_connections.py` requires the explicit designated hosted
build project, a session-pooler owner connection and held native feature flags.
It checks the frozen hosted catalog and collisions before applying permissions.
It creates two fresh generated build roles with no elevated attributes,
memberships, database creation, role creation, replication or ownership grants.
The inventory role receives the unchanged reviewed matrix/native invoker access;
the account role receives only its reviewed two-table access and explicit RLS
policies. The retained roles are separate from the removed trial roles.

Credentials are generated in memory and staged exclusively in a new private
`runtime-connections.env` under `%LOCALAPPDATA%/JayMaxBuild/credentials/`. The
folder disables inherited access and permits only this Windows user and SYSTEM.
The tool rechecks that protection and ownership using PowerShell 7 before writing.
It refuses another location, reparse/junction targets, failed ACL verification or
an existing credential file. No saved file is overwritten. The file is flushed
before committing new role access so a lost acknowledgment does not lose its
credentials. Progress records contain only safe metadata and hashes.

The file contains the two same-project connection URLs, PostgreSQL selection and
all native feature flags explicitly held. Authentication secrets, browser/API
keys, owner credentials and external integration credentials are not copied into
it. It is a connection overlay for later controlled validation, not a complete
replacement for the application's environment. The existing owner readiness
file remains the administrative/recovery connection, outside this staged overlay.

Roles start NOLOGIN within the grant transaction and receive generated strong
passwords/LOGIN only after exact grants and policies have been installed. Their
passwords do not have the trial's one-hour expiry. Rotation/recovery testing is
still required; retaining a credential is not proof of a complete recovery plan.
If an assessment or post-provision check fails, the result is held and the tool
independently looks up only its generated identities and disables their logins.
It retains private configuration and safe diagnostics for review, rather than
overwriting secrets or assuming an uncertain commit rolled back.

Supabase documents [custom LOGIN credentials and grants](https://supabase.com/docs/guides/database/postgres/roles).
The actual role assessments, file ACL checks and receipts establish this build
project's behavior; general documentation does not establish deployment readiness.

## Validation scope

Four local guard tests check rejection of a mismatched project before storage or
network access, rejection of unsafe storage before a connection, directory scope,
failed ACL verification and refusal to overwrite an existing file. The first
provisioning attempt held before connecting because Windows PowerShell 5.1 could
not load the ACL module in the inherited tool environment. The tool now requires
the available PowerShell 7 runtime. The actual private folder check passes and
the four guard tests pass again after that correction. The held receipt is retained.

The retained-role verification acquires five inventory and three account clients
together, checks actual LOGIN/current-role identity and JSONB decoding, performs
the full frozen hosted inventory assessment and the narrow auxiliary assessment,
and requires denied account/native/staff-PIN cross-boundary reads. Verification
sessions are explicitly read-only; the retained roles support the reviewed writes
needed for later workflow testing. No business data is written by provisioning.

A separate owner session compares the pinned catalog, migration ledger and
selected row counts, and hashes pre-existing effective object ACLs/policies with
only the two new grantees/policies excluded. The new roles' access is intentionally
retained; pre-existing access must remain unchanged. Count comparisons do not
prove row-by-row equality, and managed Auth/Storage/Vault recovery remains open.

## Next workflow and recovery steps

Use the staged connection overlay for controlled enabled-workflow validation
with invented build-project fixtures and accounting before/after checks. Keep
the active application settings and browser flags unchanged until those checks
pass. Then exercise credential rotation/reconnect and recovery using the separate
owner connection, followed by browser/Data API exposure, matching compiled/server
flags and sequential PR-stack validation. Continue holding merges.

For recovery, the owner connection can disable exactly the generated build logins
or issue replacement credentials after confirming their recorded identities and
grants. Update the private overlay together with such a credential change; never
substitute owner access as an automatic runtime fallback. A missing or uncertain
credential should hold the corresponding routes. Do not paste the overlay into
chat, Git, a PR or a shared reference document.

This checkpoint does not change active `.env` files, enable integrations, import
real invoices, push/merge a PR or publish the application. All 29 migration hashes,
both frozen catalog references, the inventory permission matrix and application
pool/routing source remain unchanged. Shared review artifacts include source and
safe evidence only, never this credential file or the existing owner configuration.

The subsequent [retained LOGIN workflow checkpoint](RETAINED_LOGIN_WORKFLOW_CHECKPOINT.md)
passes selected enabled account, forecast and prep/replay workflows plus independent
accounting/history preservation. Six guards pass; reconciled holds remain visible.
Active configuration and merge holds remain unchanged. Credential rotation,
reconnect and recovery are next.
