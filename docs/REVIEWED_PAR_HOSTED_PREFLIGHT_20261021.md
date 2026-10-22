# Reviewed par bounded hosted preflight

## Finding and decision

The owner-authorized read-only observation completed on October 21, 2026, at
10:29:56 p.m. Eastern (October 22, 02:29:56 UTC). Both Render services show the
accepted PR53 merge, the narrow permission checks passed, and reviewed-par storage
is still absent. **This is not full installer readiness or permission to start a
maintenance window.** Service pauses and credential, grant and schema changes
remain on hold. Par editing stays frozen and ordering manual.

The observation used accepted main
`46461e51ea8803b61c5b1d0a2cd7c5564d3a48dd`, with the documentation-only local
proposal at `fb1a1603e68f03a4421befc5b3a47991fcbfe695`. Its 49 installer-source
bindings matched, and backend/tools/migration sources were unchanged from main.
The [installation and acceptance proposal](REVIEWED_PAR_INSTALL_ACCEPTANCE_PLAN_20261021.md)
retains the exact intended database delta and later approval gates.

## Observed results

| Check | Result and scope |
| --- | --- |
| Render API | `jaymax-api` shows Live at accepted `46461e5`; [automatic deployment](https://dashboard.render.com/web/srv-dauimuugekts73ek9lr0/deploys/dep-dbcmpe5g1s2s7387ta1g), duration 2m04s. No manual deployment or health/app request was made. |
| Render frontend | `JayMax-Concepts-` shows Live at the same accepted commit; [automatic deployment](https://dashboard.render.com/static/srv-dauh8qid0e5s73fo9e40/deploys/dep-dbcmpe5g1s2s7387tagg), duration 38.8s. Deployment status is not functional acceptance. |
| Selected Render project | Production lists only those two services and no environment groups. This is not an account-wide or external-writer inventory. |
| Maintenance connection | Existing private configuration verified target identity, hostname-verified TLS, native IPv6, PostgreSQL major 17 and server read-only mode. Existing input hashes were unchanged. This identifies the maintenance connection, not the running API connection. |
| Role checks | All 16 accepted checks passed: six rules for each of two reviewed backend roles plus four independent ledger-denial checks. No held/unvisited rules or supplemental managed-schema/default-ACL findings. This is the scoped collector, not the full installer preparer. |
| Browser/client access | Both reviewed client roles had zero effective schema-usage, relation, column, sequence and function access counts in the private application schemas. These are catalog observations, not attempts to log in or invoke the Data API. |
| Existing source index | Exact invoice-source index contract returned no issues. This does not replace full historical-ledger or catalog preservation reconciliation. |
| Migration ledger | Present with 55 versions, maximum `20261015175921`. Ledger counts/max alone do not verify every historical body, name and fingerprint. |
| Reviewed-par storage | `purchasing.inventory_par_versions` absent. No migration version was allocated and no executable application plan was produced. |
| Toast | Jobs 3 and 4 present, enabled and matching their expected identity/schedule/actor/database/command-hash bindings. No additional active cron jobs; no unfinished Toast syncs reported. Neither job was changed or replayed. |
| Activity | Complete visible snapshot contained six sessions across six groups, including the observer; zero sessions matched the two reviewed backend roles and five belonged to other named roles. This neither attributes the API nor establishes writer drain. No platform session was terminated. |

## Remaining uncertainty before maintenance

The running API's database role and connection binding were not established by
this observation. A maintenance connection using the existing owner credential,
or zero currently connected reviewed backend roles, cannot establish that binding.
Do not infer that the API uses a restricted backend role or that O1 is required
before the owner's existing build path may install the reviewed schema.

Confirm the current runtime binding through a separately bounded read-only
configuration/deployment check, without exposing secrets or changing the
connection. Also reconfirm all potential writers, including manual/script writes
and Companion's current status, before proposing a pause. Idle, disconnected or
external writers cannot be ruled out by this snapshot or the selected Render
project's two-service list.

Full preparer checks remain unrun: exact historical ledger/body reconciliation,
complete current catalog/security/row/sequence baseline, new-object collision
checks and fresh backup equality. A later approved window must stop producers,
verify strict drain, take and restore a fresh encrypted backup, and bind those
results to the executable plan. Present that plan's exact hash for separate schema
approval. Fictional par app/transport acceptance remains a later separate scope.
G04, O1, managed-project recovery and Companion adoption remain open.

## Probe history, budget and cleanup

The first probe closed cleanly after its supplemental privilege query encountered
`WrongObjectTypeError` / SQLSTATE `42809`. The external probe incorrectly allowed
relation-specific privilege functions to receive other object kinds. Its partial
results and failure receipt were retained. CASE guards corrected the probe only;
no repository application/tooling source or database object was changed.

The one remaining connection attempt completed the previously unvisited checks
and verified the first exact backend was absent. There were **two total read-only
connections**, with **14.203 seconds combined connected work** (3.578 + 10.625),
inside the bounded two-attempt/120-second connected-work ceiling. The gap between
attempts was local correction/review time, not an open database session. Both
clients closed cleanly. No third connection or server-side termination was used;
final-client close is not a separate third-connection absence observation.

The [sanitized receipt](REVIEWED_PAR_HOSTED_PREFLIGHT_20261021.json) preserves both
the initial held probe and corrected completion. Protected raw receipts remain
outside Git/cloud-sync. Final private receipt SHA-256:
`602da862d01efa24a59eb5634d1e0c1650d02e38b4f9753fca72e0159b9b7241`.
Initial held receipt SHA-256:
`d5b2dafcabf53f14ba6371b2951cf3d2f6cb7ac8485ac66282d0d6254346132f`.

Only operational metadata was queried; no application business rows were read or
written. No service control, credential/configuration, grant, schema, app
connection, backup/restore, local server or live app test was changed/run. No
maintenance window is active. Repository documentation and JMAX summaries record
the scoped result; they confer no further authority. Application suites were not
rerun for this evidence/documentation update; PR53's earlier CI remains dated
coverage.
