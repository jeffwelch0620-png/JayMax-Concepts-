# API database role and writer review

The subsequent [October 22 local maintenance proposal](REVIEWED_PAR_MAINTENANCE_PROPOSAL_20261022.md)
is ready for review. This dated role/writer observation does not authorize that
window or substitute for its fresh confirmation and live control checks.

## Findings

The separately owner-approved read-only follow-up completed October 21, 2026,
at 10:52:17 p.m. Eastern (October 22, 02:52:17 UTC). The API's current Render
configuration uses **`postgres` through this build project's Supabase shared
pooler on port `6543`**, database `postgres`, with `USE_PG=true`. This resolves
the configured-primary-connection question from the
[earlier preflight](REVIEWED_PAR_HOSTED_PREFLIGHT_20261021.md).

Render's last successfully deployed API commit remains accepted PR53
`46461e51ea8803b61c5b1d0a2cd7c5564d3a48dd`. The deployed source's
[pool initialization](../backend/db_pg.py) reads `DATABASE_URL` directly and
does not select either reviewed restricted login. PostgreSQL mode retires Mongo.
The inspected fields were read-only; connection and mode values were re-masked.
No password, full DSN or project identifier is included in shared evidence.
No Edit, Save, Deploy or service-control action ran.

This is configuration plus deployed-source evidence. No API client session was
connected in either database snapshot, so there is no independent per-process
`current_user` observation. The code sets no unique API database application
label. An absent session cannot identify a sleeping/disconnected/pooled client.

The observed `postgres` role is not PostgreSQL superuser, but has create-role,
create-database, replication and RLS-bypass attributes. The earlier 16 passing
checks describe the reviewed restricted candidate roles, not this current API
owner role. O1 restricted-runtime adoption remains separate; no role, grant,
credential or connection cutover is included. A missing `sslmode` DSN parameter
does not establish plaintext: the deployed pool explicitly uses the
certificate-verifying [TLS helper](../backend/db_tls.py). The running app's TLS
socket was not inspected.

## Writer inventory

| Producer or service | Evidence and current state |
| --- | --- |
| `jaymax-api` | Configured primary application writer on the existing owner-connected build path; deployed at PR53, left running. No `AUXILIARY_DATABASE_URL` among visible environment keys. Secret-file contents were not inspected; no separate account-pool binding is asserted. |
| Toast job 3 | Bert's/Rudd's daily job; enabled, expected name/schedule/database/actor/command hash unchanged; executes as `postgres`. |
| Toast job 4 | Papa Leoni's daily job; enabled, expected bindings unchanged; executes as `postgres`. |
| Other cron/sync activity | Complete bounded listing found no additional active cron jobs, no in-progress cron runs and no unfinished Toast syncs. This does not stop future scheduled/network activity returning. No job was replayed. |
| Render frontend | Static service, not a separate server-side database worker. Selected workspace shows one project; its Production environment lists only API and frontend, with no environment groups. Other workspaces/providers are outside this inventory. |
| Companion | Last owner confirmation remains local-only. Latest two turns in Companion App Integration show it held as the reference chat with no parallel work. This is coordination evidence, not an audit of every external process or credential holder. |
| Manual SQL/scripts/coworkers | No additional application client identifiable in these snapshots. Fresh owner confirmation and producer controls remain necessary before maintenance. |

Both complete, full-visibility activity snapshots excluded the owned observer and
showed the same **six other sessions**: idle PostgREST (`authenticator`), idle
pooling client (`pgbouncer`), idle `pg_net` worker (`postgres`), idle unlabelled
`supabase_admin` client, `pg_cron` scheduler and idle PostgreSQL exporter.

These are consistent with Supabase platform services, not evidence of six
additional restaurant apps. The unlabelled administrator and pooling clients
cannot be assigned to a particular human/app from these fields alone. No open
transaction or active write/DDL command was observed. Command-prefix classification
is not a write audit: SELECT/function calls and future/disconnected clients can
write. No writer drain is claimed; no platform session was terminated. No
business rows or raw SQL query text were read or stored.

## Boundaries and recommendation

The known controllable application-writer list remains API plus Toast jobs 3/4;
this read did not identify another application producer. Keep the current build
connection unchanged under the owner's hold. Do not repair permissions or require
O1 cutover merely to prepare the already-reviewed additive par install.

The next proposed step is a fresh maintenance proposal using this documented
build path, with current owner confirmation of writers, exact pause/resume
controls, resource checks and a fresh encrypted backup/disposable restore. This
review does not authorize starting it. A later full preparer must recheck target
and baseline; schema application still requires the exact plan hash and separate
approval. Par storage remains absent, par editing frozen and ordering manual.
G04/O1 and fictional live acceptance remain open.

Two read-only direct IPv6 connections verified TLS and server read-only mode,
completing connected work in **6.282 seconds** under a two-attempt/120-second
ceiling. Both clients closed cleanly; the second verified the first exact backend
absent. No third connection or server-side termination was used. Original private
input hashes were unchanged.

The [sanitized receipt](API_ROLE_WRITER_REVIEW_20261021.json) records the session
snapshots and jobs. Protected receipt SHA-256:
`65d084ceaca19270ca3799d015f4ca1963b72155d33387908a4fcc489fc5749d`.
Raw receipts remain outside Git/cloud-sync. This follow-up changed documentation
only. No service pause, hosted data/configuration change or credential/grant/schema
action occurred; no window is active. Documentation checks replace no application
suite or hosted functional acceptance.
