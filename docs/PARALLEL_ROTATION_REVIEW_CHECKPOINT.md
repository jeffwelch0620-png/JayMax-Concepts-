# Parallel account rotation and connection-path review

Follow-up: the local [transition permission checker](TRANSITION_PERMISSION_CHECKPOINT.md)
implements the diagnostic cohort prerequisite and pins newly observed inbound
creator-administration metadata. Application startup remains singleton-only;
installation, switching and recovery gates remain held. Results below describe
the earlier read-only source and evidence.

October 9, 2026. Local only; no credential, role, grant, policy, business-row,
application configuration or endpoint changes. Hosted read-only receipt:
`parallel-rotation-review-20261009T2242136669784Z.json`.
Final status: `reviewed_parallel_rotation_dependencies_and_connection_paths`.
Both original read-only permission profiles pass. Role/policy/membership metadata
matches before and after the review, and all owned connections are closed.

## Observed results

| Read-only check | Result |
| --- | --- |
| Original inventory session-pooler clients | 3 of 3 accepted with actual LOGIN/read-only setup verified |
| Original account session-pooler clients | 3 of 3 accepted with actual LOGIN/read-only setup verified |
| Direct inventory/account clients | All 6 timed out; none counted as an authentication denial |
| DNS families | Direct: IPv6 only; session pooler: IPv4 only |
| Inventory permissions | passed_local_candidate; no reported issues; read-only |
| Account permissions | passed; no reported issues; read-only |
| Existing role-addressed policy contract | 58 inventory policies and 8 account policies match the reviewed profile |
| Role/policy/membership preservation | Before/after catalog digest matches |

These bounded samples distinguish the working application path from the presently
unavailable direct diagnostic path. IPv6 reachability is a plausible area to
investigate, not a demonstrated root cause. No network settings were changed.
The earlier [combined rehearsal](COMBINED_ROTATION_REHEARSAL_CHECKPOINT.md) remains
held; this read-only result neither reruns it nor proves old-role retirement.

## Recommendation

Keep the authoritative hosted Supabase database, the existing session pooler on
port 5432 and the separate encrypted local recovery copy. No paid IPv4 add-on is
needed for the currently verified application connection path. The direct endpoint
is a distinct diagnostic path; its transport failures cannot be counted as failed
passwords or successful credential retirement.

Prepare a parallel replacement for each restricted inventory/account login. Keep
the current credentials working while the new pair is independently verified.
Switch clients in a controlled step only after verification, then retire old logins
after all clients have moved. This avoids changing a currently used username's
password during the transition. [Supabase's rotation guidance](https://supabase.com/docs/guides/troubleshooting/supavisor-error-password-authentication-failed-after-password-rotation)
recommends gradual migration to a new custom role. This is a plan, not evidence
that new accounts have been created or the combined recovery gate has passed.

The tradeoff is temporary overlap: four restricted login roles, additional pool
capacity and a policy transition that must be explicitly reviewed. Measure actual
database/provider pool limits and client instances before choosing the overlap
budget. The existing role limit is six; the existing app pools have a maximum of
two connections apiece. Neither value is a measurement of remaining capacity.

## Required prerequisite discovered in the source review

Inventory's current permission inspector requires each applicable public policy
to have exactly its own role OID. Simply appending a replacement role to the policy
would fail that check. Re-running the original provisioner also refuses existing
candidate policies, so it is not a parallel-rotation installer.

Before creating replacement accounts, prepare a narrowly scoped transition
inspector. Its default remains the current single-role rule. A separately verified
rotation record may permit only the exact old/replacement OIDs for the same
profile, project and phase. Pin actual role identity and attributes independently;
the proposed record cannot accept its own target as an unreviewed baseline.
Reject PUBLIC, unexpected OIDs, inherited policy access, changed expressions,
restrictive/additional policies, changed verbs, role membership or expanded grants.

For each of the 58 inventory and 8 account policies, the intended overlap changes
only the TO role list. Preserve its name, table, command, permissive setting, USING
and WITH CHECK expressions. [PostgreSQL's ALTER POLICY documentation](https://www.postgresql.org/docs/17/sql-alterpolicy.html)
confirms that the role list can be changed independently of omitted expressions.
After old-role retirement, return to the singleton replacement-role policy state.

The account permission inspector and startup gate must also validate the recorded
policy cohort and preserve exact effective privileges for its two account tables.
Current scope remains app_users/push_subscriptions; inventory's native schemas and
staff credential tables must not become account-role privileges. Avoid duplicating
permissive policies with new names merely to satisfy the old inspector.

## Proposed implementation sequence

1. **Prepare transition guards and the exact permission delta.** Use the reviewed
   candidate manifest and its migration hashes, not a blanket copy of the existing
   owner's privileges. Require current roles/policies to pass first. Record original
   role attributes, no memberships, full business-row/Track 1/ledger fingerprints,
   unaffected catalog/access hashes, and each exact intended grant/policy change.
   The review planner emits no SQL and cannot authorize installation.
2. **Stage two new accounts beside the existing pair.** Write strong credentials to
   a fresh verified private directory before enabling either login. Create distinct
   recorded names/OIDs with NOLOGIN initially, no admin/bypass/inheritance flags,
   the reviewed connection limit, no memberships and direct profile-specific grants.
   Apply only reviewed policy TO-list additions. Do not transfer object ownership
   or automatically change future default grants. These operations need their own
   controlled installer, rollback journal and preservation checks.
3. **Verify replacement clients before switching.** Test actual LOGINs, certificate
   verification, both real pool constructors and permission profiles, unavailable
   configured-pool behavior, source preservation, and measured backend workflows.
   Keep original clients usable. An unavailable direct path remains a distinct
   native-denial/retirement evidence gap; a timeout never substitutes for that proof.
4. **Switch registered clients and prove rollback.** Record which configuration
   revision each app, worker, backup/migration tool and future integration uses.
   Reconnect replacement pools, then prove a controlled return to the unchanged
   originals. Keep backend/frontend flags matched and held until workflow gates
   pass. This review does not switch any file or client.
5. **Retire originals deliberately.** Require all registered clients to be moved,
   stop old clients, confirm exact old role identities and NOLOGIN, and verify fresh
   rejection through the relevant paths. Existing sessions require their own
   ownership/retirement evidence. Unknown application sessions hold retirement;
   the owned-probe signal is not permission to terminate them. Remove only reviewed
   old grants/policy references after the rollback window. Broad DROP OWNED or
   automatic role deletion is outside this plan.

Until these stages pass, keep original credentials current and the combined
rotation/recovery gate held. Do not repeat same-role password cycles to bypass it.
No new schema mapping or stock facts are introduced by this plan: Track 1 remains
the independent accounting baseline, with prep/sales as explanatory tracks.

## Evidence boundaries

The read-only planner requires complete reviewed role-addressed policies and no
build-role memberships before proposing a transition. Five tests and 20 subtests
pass: extra/PUBLIC/cross-profile OIDs, missing/duplicate/unreviewed policies,
expression/command/restrictive drift and elevated/inherited roles are held.
The runtime permission inspectors, provisioner and access policies are unchanged.

Connection samples use the unchanged original credentials with verified TLS and
actual read-only LOGIN identity; no raw errors, URLs or password hashes are saved.
The review also compares role/policy/membership metadata before and after its
read-only assessments. Full business-row fingerprints were not repeated: the
preceding [recovered rehearsal checkpoint](COMBINED_ROTATION_REHEARSAL_CHECKPOINT.md)
already verifies that baseline, and this review performs no writes.

[Supabase's connection guide](https://supabase.com/docs/guides/database/connecting-to-postgres)
supports the shared session pooler for persistent backends on IPv4-only networks.
The observed DNS families and connection samples are local evidence, not a network
root-cause diagnosis, sustained availability guarantee or production load test.
Staff sign-in redesign, managed recovery, Data API/browser exposure, the sequential
PR chain and publication remain separate. No push or merge occurs here.

Next: implement and test the default-strict transition permission inspector,
then prepare a concrete, journaled parallel-account installer for review.
