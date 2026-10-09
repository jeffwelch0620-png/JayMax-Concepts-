# Read-only connection diagnosis — October 9, 2026

Direct PostgreSQL access over IPv6 works from this build computer for both
retained inventory and account LOGINs. The original private connection file
remains current. No credentials, roles, business rows or active application
settings changed during this diagnostic checkpoint. This does not complete the
held combined rotation/recovery test or authorize merging or deployment.

## Observed evidence

`direct-diagnostic-20261009T152121045865Z.json` records IPv6 resolution, TCP
reachability, fresh direct authentication for both roles, matching actual LOGIN
identities, and read-only transactions. Direct URLs were derived in memory from
the validated existing credentials, with the project-specific database host and
the PostgreSQL role name without the pooler's project suffix. No URL or password
is included in shared evidence, and the staged application configuration was not
replaced with these URLs.

The reproducible follow-up receipt,
`pooler-diagnostic-20261009T152749842855Z.json`, passes fresh authentication for
both retained roles through both direct and session-pooler paths, with verified
identities and read-only transactions. The owner comparison also runs read-only:
original application rows, global Track 1, the complete migration ledger,
catalog/access snapshot and role attributes all match the latest recovered
rotation baseline. The hosted `pg_shadow` definition filters `rolcanlogin`;
the visible `pgbouncer.get_auth` function references `rolcanlogin`. Only definition
digests and these structural facts are saved; no password values are queried.
These catalog observations support a possible NOLOGIN lookup mechanism but do
not prove which tenant query the managed Supavisor service used.

The existing project's Supabase dashboard Supavisor log detail shows:

| UTC time | Log ID | Observed message |
| --- | --- | --- |
| 2026-10-09 15:10:23.985756 | `44a2f597-1659-4e33-940c-ca50ea5225b0` | `ClientHandler: (EAUTHQUERY) user not found in the database` |
| 2026-10-09 15:09:43, displayed to seconds | `04eb9d06-aff4-40d9-b49b-dfb4fecde0be` | `ClientHandler: Validation secrets changed, cache updated, deleting upstream auth` |

The selected error's raw detail has `auth_user: null` and no additional role
metadata. It occurs during the held inventory NOLOGIN interval, but the role
attribution is **not independently verified**. The cache-refresh log verifies
that a refresh event occurred; it does not establish every cause of the earlier
old-password acceptance or later lookup error.

[Supavisor's authentication documentation](https://supabase.github.io/supavisor/connecting/authentication/)
describes database credential lookup through an auth query. The
[current public implementation](https://github.com/supabase/supavisor/blob/main/lib/supavisor/auth_query.ex)
returns a user-not-found error when that query returns no rows. This is a source
explanation, not proof of the version or tenant query deployed on this project.
A query using PostgreSQL's `pg_shadow` can exclude a NOLOGIN role because that
view filters login-capable roles. Inspecting the project's view and visible
pooler function definitions can support this mechanism without retrieving any
stored password values. The actual managed tenant query remains unverified.

## Next controlled test

Use the original retained credentials to compare direct PostgreSQL and session
pooler behavior for one exact recorded NOLOGIN role at a time, without also
rotating its password. Require owner catalog confirmation, a fresh direct
authorization denial, the other role's availability, restoration to LOGIN,
fresh successful authentication on both paths, and complete baseline comparison.
Capture only allowlisted error categories and SQLSTATE, never raw driver text.

If an exact EAUTHQUERY response is reproduced, treat it as corroborating lookup
evidence. Do not make arbitrary `InternalServerError` or XX000 responses qualify
as a passed revocation test. Keep the current strict combined probe unchanged
until the contract is demonstrated. A direct path can provide an independent
revocation check; it does not silently replace validation of the intended pooler
path or introduce an owner fallback.

[Supabase's connection guide](https://supabase.com/docs/guides/database/connecting-to-postgres)
documents the direct IPv6 path. This computer's successful connection does not
prove that a future hosting environment has IPv6 access or enough connection
capacity. An eventual direct backend connection choice requires that deployment
check and certificate-verification review. Today's probes use encrypted SSL
`require`; they do not claim certificate hostname verification.

Hold merges and active cutover. The account-role disable check, unavailable-pool
accessor checks, final combined permission assessments, browser/Data API checks,
managed recovery and remaining sequential PR validation are still outstanding.
See the [credential recovery checkpoint](BUILD_CREDENTIAL_RECOVERY_CHECKPOINT.md)
for the earlier recovered holds; none has been relabelled as a pass.
