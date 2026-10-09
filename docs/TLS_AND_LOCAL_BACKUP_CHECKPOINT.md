# Verified application TLS and local backup preparation

October 9, 2026. Local review branch only; no push, merge, deployment, private
configuration activation, schema changes, paid IPv4 add-on or credential rotation.
The protected continuation and its 40 pending paths remain separate.

## Connection decision

Use hosted Supabase as the authoritative database. Keep the existing shared
**session pooler, port 5432**, for the current application connection plan. The
local recovery copy is a backup; it does not become another editable inventory
database or synchronize changes back into Supabase. The user's latest decision
supersedes the earlier proposed paid IPv4/direct-deployment plan.

The repository still describes a Render-hosted API and frontend. Supabase hosts
PostgreSQL; this checkpoint neither moves the FastAPI server into Supabase nor
proves the configuration of any running Render service.

## Changes

Both `db_pg` and `db_auxiliary` now pass an explicit certificate-verifying
SSLContext with hostname verification. Previously the inventory pool could fall
back to plaintext, and the account pool used encryption without server identity
verification. The default trust file is the public dashboard Supabase CA.
`DATABASE_SSL_ROOT_CERT` supports a reviewed replacement CA; an empty, missing or
invalid configured CA holds the connection. Plaintext remains limited to explicit
loopback endpoints for disposable local tests. DSN routing overrides are rejected
so query parameters cannot bypass this boundary or the same-target gate.

Each pool now has a maximum of two connections per API process. The current build
roles each retain their existing limit of six: one process uses up to two per role;
two overlapping processes can use up to four per role. Three full processes would
consume that role's entire limit, leaving no same-role maintenance capacity.
Budget future workers, rolling deploys, probes and all database users together.
This conservative cap can increase queueing; load validation precedes publication.
No hosted role limits were changed. Inventory failures now log only the exception
class, and shutdown awaits cancellation of its pending reconnect task.

The placeholder environment example and Render comment now describe session mode.
The blueprint has not yet been completed for the reviewed two-role rollout; actual
Render secrets, auxiliary configuration and cutover remain later release gates.

## Evidence and its limits

Fifteen local TLS/auxiliary tests pass. They cover downgrade refusal, invalid trust
files, endpoint override rejection, safe driver logging, bounded pools, configured
auxiliary failure without fallback, permission holds and shutdown/retry behavior.
The initial run had two SSL initialization failures because its test fixture
removed Windows runtime environment variables. Retaining those variables fixed
the fixture; the initial failure report is preserved.

The hosted read-only receipt `reviewed-tls-20261009T170208372753Z.json` passed both
actual reviewed pool constructors. Both authenticated as their intended restricted
roles, passed explicit read-only query transactions and JSON codec checks; the
account startup permission gate also passed. A separate PostgreSQL SSLRequest
handshake verified the client-to-session-pooler connection with TLS 1.3,
TLS_AES_256_GCM_SHA384, certificate verification and hostname verification.
Both original roles remain LOGIN with limit six. No business rows were written.

The first reviewed probe held because it checked a session read-only setting after
the auxiliary pool released/reset that session. The final probe enforces an
explicit read-only transaction for its query checks. The initial receipt and
script are retained; neither is relabeled as passing.

The older `connection-ca-review-20261009T162017420764Z.json` also remains retained.
Its `sslActive=false` result queried `pg_stat_ssl` on the database backend reached
by the pooler; it did not measure client-to-pooler TLS. Its successful authenticated
connections used a verifying SSLContext, but its overall status was held by that
incorrect interpretation. The new independent handshake and constructor evidence
supersede this TLS measurement, not the separate LOGIN revocation hold.

Certificate checks do not establish complete credential retirement. The earlier
fresh-client acceptance after inventory NOLOGIN is still unresolved. No sessions
were terminated and no combined credential-rotation checkpoint was rerun.
**Continue holding merges and active cutover.**

## Prepared recovery workflow

See [Hosted-to-local backup workflow](HOSTED_TO_LOCAL_BACKUP_WORKFLOW.md).
Read-only catalog discovery confirmed PostgreSQL 17.6, all six initial application
and migration-history schemas, and zero `storage.objects` rows at this observation.
The available local `pg_dump` is PostgreSQL 17.11. These were preparation facts
at this checkpoint. The subsequent [application backup verification](HOSTED_BACKUP_VERIFICATION_CHECKPOINT.md)
records the completed hosted export/local restore; managed recovery remains pending.

The application export/restore step is now complete within its declared scope.
Next: address bounded exact-role retirement and the remaining release gates.
Keep original credentials/flags and unrelated continuation work unchanged. There
were no closed source periods, so runtime Food Cost report comparison is not claimed.

Sources:

- [Supabase backup/restore](https://supabase.com/docs/guides/platform/migrating-within-supabase/backup-restore)
- [Supabase SSL enforcement](https://supabase.com/docs/guides/platform/ssl-enforcement)
- [asyncpg SSL arguments](https://magicstack.github.io/asyncpg/current/api/index.html)
- [PostgreSQL pg_stat_ssl](https://www.postgresql.org/docs/current/monitoring-stats.html#MONITORING-PG-STAT-SSL-VIEW)
