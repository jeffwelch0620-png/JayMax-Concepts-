# Permanent runtime connection and workflow checkpoint

October 8, 2026. Extends local commit `cb2b3a6c3420d0b05c995528428c5293ac406629`.

## Connection boundary found in the current application

`db_pg` currently has one pool, selected by `DATABASE_URL`. The already tested
inventory candidate excludes `app_users` and `push_subscriptions`. Account and
notification code still queries those tables through that same pool. A direct
switch from the saved owner connection to the inventory role therefore breaks
these paths even though the inventory catalog and LOGIN trial pass.

| Current path | Required access | Current inventory candidate |
| --- | --- | --- |
| Account bootstrap and user creation | `app_users` SELECT/INSERT | Excluded |
| Account login and owner user list | `app_users` SELECT | Excluded |
| Owner password reset and account removal | `app_users` UPDATE/DELETE | Excluded |
| Push subscription and endpoint replacement | `push_subscriptions` INSERT/UPDATE | Excluded |
| Push delivery and stale endpoint removal | `push_subscriptions` SELECT/DELETE | Excluded |
| Push PIN checks | `staff_pins` SELECT | Included in inventory candidate |

Source: `backend/server.py` account handlers, PostgreSQL push handlers and
`_pg_notify_new_staff_task`; `backend/runtime_permissions.py` reviewed matrix.
This is a connection/access issue, not a redesign of application sign-in.

The existing deployment holds prevent treating either an owner login or a
catalog-only assessment as a finished restricted deployment. The saved hosted
connection, feature flags and real invoice records are unchanged in this step.

## Recommended permanent arrangement

Keep the reviewed inventory role and its complete native permission matrix.
Introduce a separately reviewed backend connection for account/notification
tables, with only the current required table verbs, explicit role-addressed RLS
policies and no inventory, native journal, Toast-definer, DDL or owner rights.
PIN authorization remains on the inventory connection before subscription
access. This uses the same PostgreSQL database; no second inventory copy, sync
process or parallel accounting ledger is created.

Both connections should authenticate as ordinary nonowner LOGIN roles. Neither
should inherit an owner role. Keep migration/recovery credentials outside normal
route pools. When a separate connection is configured but unavailable, its routes
should report unavailable instead of silently falling back to the owner or
inventory connection. Retain the current connection until both paths pass.

The simpler alternative is one expanded application role covering the two extra
tables. It reduces pool/configuration work but makes account hashes available to
every inventory query using that role and requires an explicit expansion of the
frozen inventory permission profile. The two-connection approach preserves that
profile, at the cost of another credential, pool and recovery/rotation procedure.
Two roles inside one backend process do not isolate a compromise of that process;
application location/role gates remain necessary.

This is the prepared connection design, not a deployed role or a saved new
connection variable. Passwords are not written to this document or its package.
Supabase documents [ordinary LOGIN roles and object grants](https://supabase.com/docs/guides/database/postgres/roles).
The [asyncpg pool API](https://magicstack.github.io/asyncpg/current/api/index.html#connection-pools)
documents separate connection arguments and acquisition setup callbacks. The
two-connection arrangement above is our recommendation from the reviewed code,
not a requirement stated by those documentation pages.

## Ordinary LOGIN workflow validation

**26 selected behavioral checks pass, with seven passing subtests**, in 30m34s.
Four selected static/fixture safeguards also pass, with five passing tampering
subtests. There are no failed or skipped cases in either selected receipt. Existing
FastAPI/Starlette deprecation warnings remain. No frontend source changed; the
preceding 494-test frontend/build result is historical, not rerun in this step.

The selected workflows cover physical-count history/corrections/period closures
and replay; order receiving and purchase-cost separation; supplier prices and
contacts; container-waste corrections; prep-period analytics/reopening; menu
dependencies and rollback; catalog retirement; roster races/history; retired
task archives; shared-state/sales drafts; and forecast/AI-history boundaries.
Their existing accounting assertions pass with direct restricted LOGIN pools.
This is representative workflow coverage, not the full backend suite or a new
hosted staff-production run.

The new selected suite reuses the prior behavioral checks with a pool that
authenticates directly as a temporary restricted role. It checks both
`session_user` and `current_user` on acquisition, assesses the complete frozen
local contract, and tests five held clients in a newly created pool after each
case. The physical-correction replay now uses the fixture's pool factory so its
recreated pool retains the selected authentication mode.

The dedicated loopback server temporarily uses SCRAM password authentication for
nonowner roles; the fixture administrator keeps its existing local trust path.
A wrong-password attempt must fail. Unique invented databases and roles are
removed, then the server stops and its original authentication file is restored
and checked byte-for-byte. No hosted configuration is altered by this suite.
The before/after identity sets match: older retained test databases/roles are
preserved, and this run leaves no additional ones. A configured owner connection
using SET ROLE cannot substitute for the ordinary LOGIN checks.
There are 45 retained matching test databases before and after, and zero matching
runtime roles before and after. The run does not remove prior test evidence.

Evidence included in the local review package:

- `runtime-login-workflows-20261009T025154910282Z.xml`: 26 passing cases.
- `runtime-login-workflows-20261009T025154910282Z-output.txt`: result and existing warnings.
- `runtime-login-workflows-20261009T025154910282Z-receipt.json`: source hashes,
  authentication restoration and exact before/after temporary identity sets.
- `runtime-login-static.xml`: four passing safeguards and five tampering subtests.

An initial collection attempt omitted PostgreSQL mode from its process
environment and held at server import, before test/database work. The isolated
runner explicitly supplies the mode and synthetic local authentication settings;
the final selected run above passes without changing saved application settings.

The local workflows use the unchanged 94-function/123-relation reference and
the exact reviewed native migration chain. The preceding checkpoint independently
reconciles the hosted 96/127 variant and proves hosted pooler LOGIN; this suite
does not claim to execute hosted business writes or test hosted SCRAM behavior.

## Remaining steps

Implement and validate the separate connection boundary, review its exact
account/notification grants against the hosted schema, provision recoverable
permanent credentials, then validate complete enabled workflows with those
connections. Browser/Data API exposure, matched frontend/server flags, managed
recovery and sequential PR stack validation remain open. Keep holding merges.
The saved owner readiness file contains no Supabase API-key configuration, and
neither checkout has a frontend `.env` available for that check. A valid build
project publishable/anon key is still needed for live Data API validation; SQL
permission evidence alone does not prove HTTP exposure.

See [the preceding hosted catalog/LOGIN checkpoint](HOSTED_RUNTIME_LOGIN_CHECKPOINT.md)
for the registered reference, temporary hosted access and independently verified
cleanup. Earlier checkpoints retain their own validation boundaries.
