# Backend permission diagnostics and preflight record

Local follow-up to owner-approved PR48 merge `cbe8e88` (reviewed head `12dba79`).
The merge tree matches that tested head. Reviewed-head and
[merged-main CI](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/39455849090)
passed all four checks. This follow-up implements review notes N1/N2 only.
No Supabase connection, writer pause, permission change or migration is included.
Prompt before draft publication and before any hosted work.

**Subsequent acceptance:** this follow-up merged as PR49 `6f1774a`, identical to
reviewed `e72d597`; [reviewed-head CI](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/39459639861)
and [merged-main CI](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/39527741640)
passed all four checks. PR50 is now accepted as `cf0f127`; the new local
[role-preflight packet](PAR_ROLE_PREFLIGHT_PACKET.md) prepares the next observation
without executing it. Earlier publication/merge language below records historical
stages. Hosted role compatibility has not been rechecked; hosted work and
credential changes remain on owner hold.

## Private diagnostic contract

`BackendPermissionHeld` remains a `ValueError` with the existing fixed messages.
Only this typed exception can supply `backendPermissionHold` in a private receipt:

```json
{
  "backendPermissionHold": {
    "role": "test_only_backend",
    "rule": "membership"
  }
}
```

The role must be a valid reviewed PostgreSQL identifier and the rule must be one
of the six labels below. Driver messages, SQL/grant text, passwords, connection
URLs and arbitrary exception attributes are never copied. Role names stay in
the protected operator receipt; the command's public stdout summary omits this
field. Shared error formatting and historical index tooling are unchanged.

| Rule | Existing refusal, unchanged |
| --- | --- |
| `flags` | Missing role, NOLOGIN, SUPERUSER, BYPASSRLS, CREATEDB, CREATEROLE or REPLICATION |
| `membership` | Backend membership in another role, or incoming membership other than the current administrative reader |
| `ddl` | CREATE on this database or a checked schema, database ownership, or ownership of a checked schema, including with CREATE revoked |
| `ownership` | Relation/function ownership in the checked application/ledger schemas |
| `default_acl` | Default grants to the backend at global scope or in a checked private/ledger schema |
| `new_par_access` | Table/column access to the new par table or EXECUTE on its guard function |

Preparation and reconciliation can report the typed detail directly. The core
also carries it through an `AdditiveFailure` during installation. Receipt fields
such as `status`, `sqlCommitted`, `commitAttempted` and `rollbackCompleted` retain
their existing meaning. A role/rule label never proves that SQL was not sent:
failed rollback remains unknown and a known commit with failed independent
verification remains committed/held. No retry or permission repair is added.

This changes source hashes, not the v2 review/plan formats or accepted SQL/catalog
delta. Retained plans with earlier source hashes are not reusable. No old review,
approval, encrypted backup or maintenance window is updated in place.

## Managed-project findings and exact checked scope

Managed-project role memberships, schema CREATE rights and global default ACLs
are possible preflight findings, not assumptions about the current Supabase
configuration. A platform-provided permission is not an installer exception.

The direct DDL/schema-ownership check covers `public`, `integrations`,
`purchasing`, `actual_inventory`, `prep_inventory` and `supabase_migrations`.
The relation/function ownership check uses the same namespaces. The default-ACL
check covers global grants and `purchasing`, `actual_inventory`, `prep_inventory`
and `supabase_migrations`; it does not check every schema-specific default ACL.

`extensions` is **not** included in that direct schema check. CREATE or ownership
there, and public/extension-scoped defaults, require a separately scoped read-only
observation and permission review. Do not describe the current installer as a
complete managed-platform authority audit or silently broaden/waive its rules.
The full restricted runtime-role/RLS cutover (O1) remains open.

## Dated record before any new window

After local review/CI and owner merge approval, present the exact read-only hosted
preflight plan for owner approval. It must not pause writers or use the
maintenance-bound `dry-run` command with a fabricated/expired window or backup.
No such hosted preflight has been run for this follow-up.

Before requesting another window, save its results as a dated record, for
example `docs/REVIEWED_PAR_ROLE_PREFLIGHT_YYYYMMDD.md`, covering:

- Accepted source/merge SHA, reviewed role classification and preflight scope.
- UTC and Eastern execution date/time, read-only/TLS/session checks and owned
  connection cleanup, with the private receipt fingerprint.
- A per-role/per-rule result: `passed`, `held` or `not_evaluated`. The guard stops
  at the first refusal; unvisited rules are not inferred to have passed.
- Additional managed-schema observations, including whether `extensions` was
  actually examined, with unexamined scope clearly marked.
- The disposition of each hold and the independently reviewed permission-change
  reference when applicable. No automatic grants, revokes or installer bypass.

Use role aliases and safe summaries in shared Git/JMAX records. Exact role names,
credentials, grant text and connection/backup/key locations stay private. An
unresolved hold blocks the next maintenance proposal. Resolve it in a separate
reviewed permission change, then repeat the approved read-only validation.

A later installation still needs reconfirmed writers, a newly approved window,
strict drain, fresh encrypted backup/disposable restore, a new v2 plan, separate
approval of its exact SHA-256, bounded apply and independent reconciliation.
Par editing remains held, ordering manual and Track 1 accounting independent.

## Local validation

All runs passed with fictional data and sanitized connection variables:

| Evidence | Result |
| --- | --- |
| `par-hold-diagnostics-targeted-20261020T161944189837Z` | 38 methods plus 145 subtests: 183 cases. Every rule is checked in private receipts across read-only preparation, known rollback, unknown rollback and committed verification, using both maintenance connection modes. Console omission and rejection of driver/impostor metadata are asserted. |
| `maintenance-ipv6-database-20261020T162106179159Z` | Three methods plus six subtests: nine cases. Real catalog violations match all six labels; the normal backend install/reconcile preserves fictional $55.00 Food Cost; lost commit acknowledgement stays unknown until reconciliation and does not acquire an unrelated permission label. |
| `par-hold-diagnostics-offline-20261020T162432174236Z` | 348 methods plus 737 subtests: 1,085 cases, no failures/errors/skips. Both Windows ACL cases passed. This overlaps the focused selection and is not added as unique coverage. Five existing deprecation warnings remain. |

The database receipt proves original database/role inventories were restored,
the owned loopback PostgreSQL 17 server stopped and no hosted connection was used.
AST comparison proves the permission predicates and other core guard functions
are unchanged; only typed refusals and diagnostic propagation differ. Python
syntax, generated guides, relative documentation links and whitespace pass.
Application/frontend, shared error formatting, CI workflow, historical index
tools, migration/snapshot and pinned permission/catalog inputs are unchanged
against `cbe8e88`. Frontend tests/build were not rerun locally for this follow-up.

Local results do not establish hosted role compatibility, deployment health or
operational release. The follow-up is not pushed; fresh CI and independent review
follow a separate owner draft-publication decision.

The existing JMAX workflow, build-progress hub, hosted plan and root have been
reconciled for the approved merge and local continuation. Eleven guarded block
updates were read back across all 184 blocks, preserving unrelated content,
ordering, metadata and the Companion portion of the shared root summary.
