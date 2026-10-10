# Paired connection preparation and installer review plan

October 9, 2026. Local implementation with read-only verification of unchanged
hosted credentials. No hosted replacement role, grant, policy, password, active
configuration, application pool, invoice, inventory fact or migration is changed.
Combined rotation/recovery, active cutover and merge gates remain held.

## Concrete preparation completed

`connection_transition.bind_revision` binds an independently verified overlap
record to a registered client's configuration revision and both exact connection
targets. It requires the same endpoint/project and both original roles or both
replacement roles. Mixed revisions, profile swaps, changed credentials/URLs,
wrong projects and routing overrides hold preparation. URL fingerprints remain
private in-memory implementation data; receipts contain no URL, password or
credential fingerprint. Registration/configuration provenance must come from the
trusted controller; a supplied label is not independent registration evidence.

The guarded loopback reference is limited to a uniquely named disposable database
on `127.0.0.1`, with an explicit port and no overrides. Hosted preparation uses the
existing exact Supabase port-5432 endpoint/project checks and verified TLS. It does
not add a paid service, change endpoint modes or alter the certificate policy.

Both actual pool constructors now accept the explicit bound revision. Every new
physical connection receives the normal JSON codec, verifies its actual LOGIN and
current identity, and passes the read-only same-profile cohort/privilege assessment.
Inventory also verifies the recorded catalog reference. Assessment time is bounded
separately from connection establishment, because the full inventory catalog check
can exceed the normal 20-second handshake budget. Failed initialization closes the
connection through the driver's initializer cleanup. No owner fallback is added.

`prepare_pair` validates both targets before connecting and returns an owned pair
only when both constructors succeed. Failure/cancellation closes this attempt's
partial pools. Bounded close failures terminate only owned pools; cancellation
remains interruption. The prepared pair never assigns `_pool`, starts background
retry tasks, edits environment/configuration files or promotes itself to the app.
The normal server startup does not load an overlap record automatically.

Default account startup retains its exact singleton permission check. The default
inventory pool retains its previous connection behavior and requires the separate
candidate-permission preflight for cutover readiness. The new per-connection
inventory check is specifically part of the explicit revision path. This corrects
the overly broad reading of the earlier statement that every unmodified startup
constructor enforces singleton policies: the account constructor does; inventory's
existing preflight is separate.

An existing reporting defect was also corrected: inventory's function-check loop
overwrote the catalog-reference label returned in its receipt. The function's own
reference now has a distinct variable, so `local`/`hosted_build` remains the
reported assessment basis. The actual frozen catalog comparison remains intact.

## Exact installer and rollback review plan

`parallel_install_plan.prepare` renders review SQL from the frozen migration,
privilege matrix and catalog contracts after the original role/policy contract
passes. It requires two distinct generated replacement names and independent
application-row, Track 1, complete-ledger, unaffected-access and administrative-
membership preservation pins. Their provenance must be verified outside this
renderer; they cannot be copied from an unreviewed target and treated as proof.

The review SQL contains exactly two restricted NOLOGIN role creations, direct
profile grants, 66 TO-list additions, 66 original-singleton TO-list restorations
and corresponding exact replacement-grant revocations. Account grants remain only
public-schema USAGE and CRUD on `app_users`/`push_subscriptions`. No password SQL,
owner privilege copy, membership copy, default-privilege change, ownership transfer,
business DML, migration update or broad DROP OWNED is generated. It has no database
apply entrypoint and always returns `sqlExecutable: false`.

The staged plan requires durable private credentials before LOGIN, fsynced intent
journals before mutations, collision/OID/attribute checks, an independent creation
and administrative-membership receipt, verified client revisions, bounded atomic
grant/policy transactions and preservation checks. Missing COMMIT acknowledgement
holds as `commit_unknown`: reconnect and reconcile actual catalog state before any
retry. A failure does not prove rollback, and retrying role creation blindly is
not reconciliation.

Rollback is deliberately ordered: close owned replacement probes; freshly verify
the original pair while the overlap record's four LOGIN requirements still hold;
close those original overlap probes; restore exact old singleton policies; verify
original default account startup and inventory preflight; then pin and disable the
new role OIDs. Revoke only the reviewed new grants if they are unchanged, verify
preservation and retain the new NOLOGIN roles for dependency review. Do not disable
replacements before an overlap-based original assessment: that would correctly
fail the four-role guard. Unknown sessions hold retirement; no existing application
session is automatically terminated and neither original role/password is changed.

## Capacity gate and evidence limits

The review budget assumes max-two pools and the existing limit-six restricted
roles. It reserves replacement pools for every registered client instance, one
diagnostic connection per profile and one owner controller. Existing connections
remain in the observed usage; they are not assumed to disappear. A one-instance
example needs seven additional slots and a peak of three per replacement role;
two instances need eleven and five per role. These are synthetic planning examples,
not measurements of this project's available capacity or deployment instance count.
The observation must separately provide session pool size; the per-role peak must
fit that configured role/database bucket as well as the role's limit of six.

An absent, stale, future-dated, malformed or over-budget observation holds the
capacity gate. Unknown pooler capacity does not become zero usage or unlimited
capacity. PostgreSQL SQL can observe current settings/client backends but cannot
by itself establish the hosted session pooler's configured size, global client
quota and current free slots. Obtain the applicable per-role/session and global
pooler limits and registered instance count before applying a hosted overlap.
[Supabase's pooling and limits guide](https://supabase.com/docs/guides/database/connecting-to-postgres/pooling-and-limits)
explains the separate client/backend limits and dashboard monitoring; its
[session-mode troubleshooting](https://supabase.com/docs/guides/database/prisma/prisma-troubleshooting)
also describes the pool-size limit for each role/database combination.

Local tests cover revision/project/profile/endpoint binding, every physical
initializer, safe driver failures, partial-pair/cancellation cleanup, exact SQL
scope, preservation pins, capacity holds and rollback ordering. The PostgreSQL
trial uses a complete disposable fixture to exercise both real constructors,
two simultaneous physical connections, expiration/reconnect, JSON codecs,
account privacy, original/replacement pairs, failed-peer cleanup, singleton
original return, exact new-role NOLOGIN and unchanged business rows/ledger.
Loopback uses the dedicated test server's trust configuration: actual LOGIN
identity is verified, not hosted password rotation or password rejection.

Final local validation passes: **36 tests and 93 subtests** (35 guard/TLS/plan
tests plus the complete paired-constructor PostgreSQL trial). The owned local
server stops, the original local database/role inventory is restored, all scoped
business-row and migration-ledger fingerprints match, and no global app pool or
retry task changes. The trial also verifies no remaining backend sessions for its
four invented roles before its exact fixture cleanup.

Hosted receipt `paired-startup-originals-20261009T2008136733316.json` finishes as
`verified_original_profiles_pools_and_database_capacity_sample`: both original
read-only profiles and both default real pool constructors pass; actual identity,
JSON codec, unavailable-configured 503 behavior, unchanged role/policy/membership
metadata and owned connection cleanup are verified. Inventory's receipt correctly
reports `hosted_build`. The earlier receipt ending `1949301570449` remains held on
`ConnectionDoesNotExistError` during inventory assessment; it is retained, not
counted as a completed profile or credential-denial test.

The final read-only database observation records max_connections 60, three
superuser-reserved and zero additionally reserved connections, and ten client
backends including that owner observer: 47 unreserved slots at that instant.
These are PostgreSQL backend counts, not proof of registered app instances or
free pooler client/session capacity. Session pool size and available pooler slots
remain unknown, and `installationCapacityGatePassed` remains false. No quota,
paid add-on, service setting or endpoint was changed.

Hosted verification is limited to unchanged original profiles/default constructors,
read-only identity/codec/accessor checks and catalog/capacity observations. Hosted
overlap startup, private replacement-file staging, committed installer recovery,
live application promotion, all-client registration and old-role retirement are
not proved by local fixtures. No recovery gate or merge approval is inferred.

## Next step

Implement and rehearse the controlled installer/journal reconciliation on the
disposable local database, including failure and lost-COMMIT acknowledgement cases.
Use this exact grant/policy/rollback plan and owned paired constructors. Keep the
hosted capacity and client-registration requirements explicit before planning a
hosted trial. Promotion, retirement, combined recovery and publication remain
separate measured steps.

See the [transition permission checkpoint](TRANSITION_PERMISSION_CHECKPOINT.md) and
[parallel-account review](PARALLEL_ROTATION_REVIEW_CHECKPOINT.md) for preserved
earlier evidence and boundaries.
