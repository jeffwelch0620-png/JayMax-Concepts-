# Separate account and notification connection — October 9, 2026

This checkpoint implements the separate connection recommended in the preceding
[restricted LOGIN workflow review](RUNTIME_CONNECTION_WORKFLOW_CHECKPOINT.md).
It is a local implementation and validation checkpoint, not a hosted deployment
or merge approval. Authentication design remains a future build item.

## Connection boundary

`DATABASE_URL` continues to serve inventory, purchases, counts, prep, sales drafts,
planning and staff PIN checks. PostgreSQL account queries and push subscription
queries now use `db_auxiliary.pool()`. Set `AUXILIARY_DATABASE_URL` to a separate
server-only LOGIN in the **same host, port, database and Supabase project**.
Pooler usernames must have the same project suffix. This prevents accidentally
splitting operational and account data between two configured projects.

When the auxiliary setting is absent, existing single-pool compatibility remains.
An explicitly empty, invalid, mismatched, unavailable or overprivileged auxiliary
connection is held without falling back to the primary connection. Unavailable
account routes return 503; the primary pool remains independently usable.
Valid connection failures retry separately; shutdown cancels and awaits that
retry and closes its pool. Connection errors log categories/types, not driver
messages or URLs. Both pools retain the existing JSONB codec.

Before replacing the owner connection with the restricted inventory LOGIN,
configure **both** URLs. The inventory profile deliberately excludes account and
subscription tables; leaving the auxiliary setting unset is not a working
restricted-role deployment. Saved readiness credentials were not edited here.

## Reviewed auxiliary access

The candidate needs CONNECT to the chosen database, public schema USAGE and
SELECT/INSERT/UPDATE/DELETE on `public.app_users` and `public.push_subscriptions`.
It also needs explicitly role-addressed permissive RLS policies for those four
operations. These policies allow the trusted backend to access accounts across
locations; existing application authorization controls users and locations.
This is not tenant isolation within PostgreSQL or isolation of the backend process.

The read-only assessor checks actual LOGIN identity, elevated attributes, role
memberships, database CREATE, schema ownership/CREATE/delegation, table and column
privileges and grant options, required RLS policies, sequences and native/definer
functions in public and the four named application namespaces. Extra table or
column access, private schema USAGE and inventory role membership hold the
candidate, even if a membership is NOINHERIT. Public invoker functions used by
existing defaults/triggers remain permitted. Unknown namespaces and managed
Supabase facilities still require the separate hosted/full deployment review.
This assessor does not install grants, continuously monitor ACL changes or
replace the frozen inventory catalog/permission gate.

The inventory permission matrix, both catalog contracts, base schema and all
29 migration hashes remain unchanged. No production grant/policy migration is
introduced. Policies/grants in these tests apply only to unique disposable
local databases and generated temporary roles.

## Validation and retained attempts

Seven connection unit tests, two existing account compatibility tests and both
local two-pool database tests pass, with no failures or skips in the final
selected receipts. Existing FastAPI/Starlette deprecation warnings remain.
Final receipts and results are recorded with the review package. The selected
unit tests cover target selection, legacy compatibility, no fallback, connection
retry, shutdown cancellation, safe logging and closing a held candidate pool.
Two existing account-route tests check compatibility with the original pool.

The database suite uses two independent ordinary LOGIN pools and invented data.
It exercises account bootstrap/create/list/login/password reset/delete; subscription
upsert and stale-endpoint cleanup; wrong/valid staff PINs through the inventory
pool; auxiliary unavailability and reconnect. Delivery is mocked: no external
notification is sent. Native accounting fingerprints and the physical-count
Food Cost report must remain exactly unchanged throughout these account/push
operations. The inverse table access attempts are denied.

Negative checks add and remove five types of excess access: native table SELECT,
inventory column SELECT, private schema USAGE, inventory role membership and
account table grant option. Every variant must hold; the restored candidate must
pass again. Local schema reference remains 94 functions/123 relations. The
separately reconciled hosted 96/127 reference is not exercised by these writes.

Three held attempts are retained. The first two stopped during setup because
internal catalog relation/policy codes needed casting to text for comparisons;
the assessor now performs those casts. The third passed the account/push and
accounting-boundary case, but its negative test referenced the hosted-only
`integrations` schema. That fixture now uses existing `purchasing` schema USAGE.
No permission requirement was relaxed. Each attempt restored the original
authentication file, stopped the loopback server and preserved the exact
before/after set of older test databases and roles.

Final evidence:

- `auxiliary-pool-unit-v2.xml`: seven passing unit tests.
- `auxiliary-account-compatibility.xml`: two passing existing route tests.
- `auxiliary-connection-workflows-20261009T095101927374Z.xml`: both passing database cases.
- Matching `-receipt.json` and `-output.txt`: source hashes, results and cleanup.

The final database run retains the same 45 prior matching test databases and
zero prior matching runtime roles. Its original authentication-file hash is
restored; the local server is stopped. The three earlier held receipts and their
outputs are included so a final pass does not conceal earlier failures. An
additional unit collection command initially omitted the local backend URL
needed by the existing conftest; it stopped before collection and was corrected
in the command environment. It did not connect to a database or change source.

## Next step and merge hold

Review the auxiliary grants and RLS policy requirements against the connected
hosted build database, then run a temporary two-role hosted pool trial with
independently verified cleanup. Prepare permanent credentials and recovery
before changing saved application configuration. Browser/Data API exposure,
matching frontend/server flags, managed recovery and sequential PR stack
validation remain open. Continue holding merges. No real invoice import,
permanent credential change, hosted write, push, merge or publication occurs
in this checkpoint. Previous full frontend/build results remain historical;
frontend source did not change here.
