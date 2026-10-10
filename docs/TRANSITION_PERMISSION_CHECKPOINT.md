# Restricted-account transition permission checker

Follow-up: [paired pool preparation and the installer review plan](PAIRED_STARTUP_INSTALL_PLAN_CHECKPOINT.md)
now implement the explicit constructor path and ordered review SQL. Pools remain
owned and unpromoted; no hosted overlap or active configuration is installed.
That checkpoint also clarifies the separate default inventory preflight.

October 9, 2026. Local implementation; hosted verification is read-only.
No hosted accounts, passwords, grants, policies, application configuration or
business rows change. The combined rotation/recovery and merge gates remain held.

## What changed

Both permission inspectors accept an explicit independently verified overlap
record for diagnostic assessment. Their default remains a single-role policy
cohort. Inventory retains its frozen migration, object/column/sequence/function
privilege matrix, ownership checks and catalog reference. The account inspector
now checks the exact eight named per-verb policies and rejects any extra applicable
policy, including PUBLIC, inherited, restrictive and broader ALL-command policies.
Its two-table scope remains `app_users` and `push_subscriptions`; it cannot acquire
inventory-schema or staff-PIN access through this transition.

Account assessments also require a dedicated connection outside a transaction,
NOINHERIT, a read-only snapshot, and a bounded statement timeout. They report the
observed transaction read-only state. The real account pool's startup inspector
still uses the default singleton mode and fails closed when overlap is present.
There is no environment toggle, owner fallback or automatic application cutover.

`transition_permissions.verify_record` requires independently supplied pins for
the record bytes, project, both exact original/replacement name-and-OID pairs,
original policy digest and administrative membership metadata. Only the explicit
`overlap` phase qualifies. The record cannot prove its own provenance: copying its
fields into the expected pins does not constitute independent review. The eventual
installer must supply those pins from the preserved preflight and controlled
creation journal. No valid hosted overlap record has been created here.

Within each assessment's read-only snapshot, all four recorded roles must exist
with exact OIDs, LOGIN, NOINHERIT, connection limit six and no elevated attributes.
An overlap policy must contain exactly the same-profile original and replacement
OIDs, in either order, with no duplicates, PUBLIC or third role. Its table, name,
verb, permissive setting, USING and WITH CHECK expressions remain exact. Policies
addressed only to the counterpart are also scanned, so partial additions cannot
pass for the assessed role. Expanded effective grants continue to hold assessment.

The standalone `assess_url` diagnostic constructs its own fresh connection,
requires the recorded Supabase project/profile/login on port 5432, rejects routing
overrides, verifies TLS and actual session/current identity, and always closes its
client. A successful LOGIN is reported separately from permission success. Neither
result grants release approval. Local catalog tests call the inspectors directly
on guarded disposable loopback fixtures; they do not certify hosted overlap LOGIN.

## Administrative membership discovered during verification

The first read-only preflight deliberately stopped when a broader membership scan
found an inbound relationship missing from the earlier outgoing-membership review.
Further read-only inspection identifies `postgres` as the member of each current
build role, granted by `supabase_admin`: ADMIN OPTION true, INHERIT OPTION false,
SET OPTION false. The runtime roles themselves receive no memberships.

These options control inherited privileges and role assumption under
[PostgreSQL's membership rules](https://www.postgresql.org/docs/17/role-membership.html).
ADMIN OPTION still permits membership administration; it is not a promise that
the administrative account could never change those options. Any such change
would differ from this checkpoint's pins and hold the transition assessment.

The transition record pins exact administrative membership rows, including member
and grantor identities/OIDs. It accepts only recorded creator administration by
`postgres` with no inheritance or role assumption. Unknown members, changed OIDs,
new memberships, SET/INHERIT rights, membership granted to a runtime role, or an
unreviewed grantor hold assessment. These rows are not automatically copied to a
replacement; the controlled creation journal must independently record any
administrative metadata produced when each new role is created.

This is a newly observed catalog relationship, not evidence that an inbound
relationship was compared in the prior checkpoint. Before/after preservation in
the current verification includes both directions explicitly.

## Validation and evidence boundaries

Final validation passes: 20 local guard/pool-selection tests with 76 subtests,
plus nine disposable PostgreSQL regression tests with 15 subtests: **29 tests and
91 subtests** total. The owned local server stops and the original local database
and role inventory is restored. The independently preserved 40-path continuation
remains byte-for-byte unchanged; package/source secret scans exclude private
connection values and backup keys.

Hosted receipt `transition-default-profiles-20261009T1907098352885.json` finishes
as `verified_original_default_profiles_after_transition_checker`. Both original
LOGINs pass their read-only permission assessments in `single_role` mode: inventory
`passed_local_candidate`, accounts `passed`, with no issues. The exact 58 inventory
and 8 account policies match the earlier reviewed original contract. Original
role/policy/outgoing-membership metadata matches that prior receipt, and the
current before/after comparison additionally includes the two observed inbound
administrative membership rows. All owned verification clients close.

Validation is recorded with source hashes, local test reports and hosted receipts
in the sealed checkpoint package. Tests cover independent record/project/policy
pins, malformed identities, PUBLIC/cross-profile/extra cohorts, changed policy
expressions/verbs, exact creator membership, role attribute drift, privilege
expansion, rejected account startup during overlap, successful singleton startup,
actual loopback LOGIN identity and connection cleanup.

Disposable PostgreSQL tests install the complete reviewed migration chain and
compare catalog metadata, all scoped business-row fingerprints and the complete
migration ledger around read-only assessments. The existing inspector's effective
privilege, membership, ownership, function-body, trigger and catalog drift tests
also run. Hosted original-profile checks use unchanged private credentials and
the current TLS-verified session-pooler path. No hosted replacement-role test,
new business import, direct-connectivity fix, full recovery rehearsal or production
load validation is implied.

The initial local regression run exposed a PostgreSQL overloaded-function argument
type mismatch; an explicit OID cast fixes it. Its fixture also needed independently
generated build-role grants while preserving the existing fixture's stricter role
name boundary. Initial failures and the administrative-membership hold remain
historical evidence; final passing tests certify the corrected local source only.

## Next concrete step

Prepare the journaled parallel-account installer and its rollback plan for review.
Before applying any hosted TO-list overlap, prepare and test the explicit startup
integration and registered-client configuration revisions that consume the same
independent record. Unmodified application startup intentionally rejects overlap,
so the diagnostic checker alone is not enough to enable a production transition.

The installer needs independently pinned preflight/creation records, a measured
connection-capacity budget, staged private credentials and NOLOGIN identities,
exact grant/TO-list deltas, uncertain-commit reconciliation and rollback checks.
It must preserve business rows, Track 1 and the complete migration history and
leave original credentials usable. Actual switching and old-account retirement
retain their separate gates and require completed recovery evidence. No push,
merge, deployment or account creation occurs in this checkpoint.

See the [parallel rotation review](PARALLEL_ROTATION_REVIEW_CHECKPOINT.md) for the
overall sequence and the [combined rehearsal checkpoint](COMBINED_ROTATION_REHEARSAL_CHECKPOINT.md)
for the retained recovery hold.
