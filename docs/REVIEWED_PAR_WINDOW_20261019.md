# Reviewed-par maintenance window October 19, 2026

Status: **closed without schema application**. All approved producers were restored
to their recorded original states at **12:39:21 AM Eastern**, before the 1:06:26 a.m.
deadline. No executable par plan or exact-plan approval was produced. The new
par table remains absent; par editing stays frozen and ordering remains manual.

## Approval and source

The owner approved a new 45-minute window and no other manual SQL/script writes.
It began October 19 at 12:21:26 a.m. Eastern (04:21:26 UTC), with deadline
05:06:26 UTC. Companion was reconfirmed local-only; approved writers were only
Render jaymax-api and Toast jobs 3 and 4. The window authorized their temporary
pause, strict drain, fresh encrypted application backup and disposable restore.
Schema application remained reserved for separate approval of an exact plan hash.

Accepted source is PR47 merge `a7270ca310592e70ead51615da8cdad2659d7e7f`, matching
tested `755aff3`. Protected code/migrations/snapshot/grants and app/Render
connection settings match that merge. Local pre-window documentation checkpoint
was `23995b1`; the one-use orchestration scripts and private evidence are outside
Git. No application code or accepted tooling was edited during maintenance.

## Scoped control and strict drain

Render API `srv-dauimuugekts73ek9lr0` was verified Suspended through its dashboard.
Only these exact cron controls were temporarily disabled, after their identities,
schedules, command hashes and original enabled states were recorded:

| Job | Name | Stored schedule | Original / recovered state |
| --- | --- | --- | --- |
| 3 | jmax-toast-berts-rudds-daily | 15 10 * * * | Enabled / enabled |
| 4 | jmax-toast-papa-daily | 20 10 * * * | Enabled / enabled |

Two quiet observations at 04:25:49.330197 and 04:26:34.248345 UTC passed: both
jobs inactive, zero HTTP queue, zero active cron runs and no unfinished Toast
sync. Full visibility covered the three reviewed login roles, with zero
application sessions, write transactions or unobservable activity. No pooled-PID
exemption, backend termination or weakened guard was used. Direct IPv6 operator
connections retained verified TLS/read-only settings and closed their owned clients.
Drain receipt SHA-256:
`69071518881ab91dd6f26d7c7c19cca2b5def6ff139d4a8d3dca38eb28089814`.

## Fresh encrypted export and disposable restore

Export completed in 129.687 seconds; real disposable restore in 34.141 seconds.
Both passed on PostgreSQL 17; the local 17.11 patch differed from the hosted patch.

| Verification | Observed result |
| --- | --- |
| Application/ledger relations | 120 matched |
| Restored rows | 45,608 matched |
| Catalog groups | 13 matched |
| Migration evidence | 32 canonical files captured and current-source hashes matched |
| Encryption/artifacts | Authenticated archive readback, listing, ACL checks and publication/partial cleanup passed |
| Restore refusal | Nonempty target refused |
| Access separation | Accounts denied private Inventory schemas; Inventory denied account tables |
| Local cleanup | Exact starting database/role inventories restored; owned loopback server stopped; no cleanup errors |

Seventeen temporary NOLOGIN role stubs supported restoration of object ownership
and ACLs; role memberships were not restored. No managed Supabase Auth, Storage or
Vault recovery is claimed. Track 1 relation fingerprints and two closed-period
rows matched; no fresh runtime Food Cost calculation was compared. This is scoped
application recovery evidence, not operational-release approval.

Archive SHA-256:
`32b29c1ad9c6a301100880498a0b9e6b2bdb4f79d636868c9dbd6033cfe113d3`.
Encrypted archive SHA-256:
`5eac6a9306c54220bcce56fb95e77e1ab970c35807cad78136d8e9629df4e2b4`.
Manifest SHA-256:
`5e8f575d45e3f116ef4da3f691015765e5d4331c3ca415159516856242bc60b8`.
Private complete receipt SHA-256:
`9ffc01535dcb27aa870633bebf7d89357ebd7e1c8a5a5a8580156f7c835c78cf`.
Archive, key, full role identifiers and private artifact paths remain outside Git
and shared Pages. Safe local evidence is
`pr47-window-backup-restore-20261019T043015891914Z.json`.

## Plan held before DDL

The accepted adapter's dry-run returned `held`, `commitAttempted:false` and
`sqlCommitted:false` after 120.719 seconds. It produced no executable plan.
There was no apply invocation, plan-hash approval, DDL or ledger insertion.

A separate bounded direct read-only diagnostic passed exact original-plus-index
ledger verification and confirmed the par table/function/names absent. Readiness
then returned 107 findings, all for the single existing trusted Inventory backend
role: 3 schema-access checks,
85 relation-access checks and
19 function-execute checks.
There were no warnings and no anon/authenticated findings. The role has existing
private Inventory access, while `readiness.inspect(..., client_roles=...)` treats
every supplied role as a browser-style client that must have none.

This identifies a role-classification conflict. It does not prove every existing
backend privilege is correct, nor justify revoking required runtime access or
dropping that role from all checks. The retained review uses one client-role list
for both ledger-denial and private-client-denial checks. Resolve those distinct
requirements through reviewed local evidence/tooling and a disposable regression,
without weakening browser denial, backend ledger protection, writer visibility,
backup or exact-plan approval. No guard was bypassed and no grant was changed.

## Recovery and remaining work

Fresh independent reads verified both cron jobs restored with their original
enabled states, schedules and command hashes. Render suspension was removed on
the same accepted API deployment `dep-dbap7km7bikc73esuat0` / `a7270ca`.
Window closure: `2026-10-19T04:39:21.740224+00:00`; elapsed 1075.74 seconds.
The window is closed and cannot be reused for an application attempt.

Public API health result: `observed`; its response was
`status: ok`, `database: connected`. The normal in-app Inventory
tab reached its sign-in screen, so a fresh authenticated walkthrough is not
claimed. Health alone is not permission or accounting acceptance.

Next: local review of trusted-backend versus browser denial expectations; prove
the current role contract and regression cases before publishing any change.
Then obtain the normal draft-PR/CI/merge gates if code changes are necessary,
followed by a new owner-approved window, new backup/restore and fresh executable
plan hash. Prompt before applying anything to Supabase. Do not reuse this backup
as a fresh active-window baseline after writers have resumed.

Retain the initial screenshot-format bookkeeping failure: the browser supplied
JPEG bytes under a .png name, so suspension marking refused before proceeding.
The original bytes were preserved as .jpg and verified with PIL; no SQL outcome
or database guard was changed. The successful backup does not turn the held
plan into a passing migration rehearsal.

This continuation changes documentation only. Prior reviewed-head and merged-main
CI remain scoped to accepted source; no new application tests are claimed for
prose edits. Validate documentation links, generated guides, protected-source
equality and whitespace before committing locally. No new PR is authorized here.

JMAX workflow, hub, migration plan and combined-build boundary were updated after
recovery. Full readback verified all 11 intended block replacements, unchanged
titles/order/counts across 184 blocks, and preservation of every unrelated block,
including Companion text in the shared boundary. No sharing or agent instructions
were changed. Repository static checks passed protected-source equality, generated
guide consistency, 218 relative links and whitespace. No application test suite
was rerun for this documentation-only continuation.

References: [read-only validation](PR47_READONLY_IPV6_VALIDATION_20261019.md),
[installer](HOSTED_REVIEWED_PAR_INSTALLER.md),
[migration plan](HOSTED_REVIEWED_PAR_MIGRATION_PLAN.md),
[current workflow](WORKFLOW_RECONCILIATION_20261015.md).
