# Reviewed-par permission preflight packet

October 21, 2026. **Local preparation only; hosted work and credential changes
remain on owner hold.** Prompt before publishing a new draft PR. This packet is
not permission to inspect Supabase, pause services, change grants, apply SQL,
create credentials or reuse an expired maintenance window.

## Accepted source and why this comes next

The baseline is PR50 merge `cf0f127e3a5f8247e43746c269a47b75d2e58d1a`, identical
to approved `b22734a`. All four [reviewed-head checks](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/39635235513)
and [merged-main checks](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/39638706456)
passed. PR49 merged as `6f1774a`, matching reviewed `e72d597`; all four
[reviewed-head checks](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/39459639861)
and [merged-main checks](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/39527741640)
passed. These are source/CI baselines, not deployment or live acceptance evidence.

The last [par maintenance attempt](REVIEWED_PAR_WINDOW_20261019.md) stopped at
backend-role permission classification. PR48 corrected classification; PR49
added bounded private diagnostics. Neither establishes current hosted role
compatibility. The next hosted gate, when separately authorized, is a narrow
read-only role observation before considering another outage.

## Local helper and exact scope

`tools/ops/par_role_preflight.py` accepts an already-open dedicated idle connection
and explicit client/backend lists. It opens no connections, reads no environment
or credential files, writes no receipts and provides no hosted command-line entry
point. The caller owns target/TLS validation, connection deadlines, private receipt
storage and connection cleanup. Collection has its own 60-second overall deadline.
No app startup, migration or automatic retry
invokes it. At most 32 classified roles are accepted, including mandatory `anon`
and `authenticated`; at least one backend must be explicitly reviewed.

The helper uses one repeatable-read read-only snapshot, pins `search_path` to
`pg_catalog`, verifies all three settings and sets local 20-second statement,
five-second lock and 30-second idle transaction limits. Each backend guard gets
a read-only savepoint. A refusal
marks earlier checks `passed`, that check `held` and later checks
`not_evaluated`; it does not bypass the refusal to test later rules. Other
reviewed roles can still be observed. The existing installer guard is called
unchanged; a rule-order regression test protects the prefix interpretation.
Missing roles hold rather than disappearing from the result. Unexpected query,
transaction or cleanup failures propagate; no completed receipt is returned.

| Observation | Scope and limitation |
| --- | --- |
| Backend `flags` | Existing unprivileged LOGIN; no SUPERUSER, BYPASSRLS, CREATEDB, CREATEROLE or REPLICATION. |
| Backend `membership` | Existing membership guard, including incoming membership and the administrative-reader exception. |
| Backend `ddl` / `ownership` | Existing checks on `public`, `integrations`, `purchasing`, `actual_inventory`, `prep_inventory`, `supabase_migrations`, plus database CREATE/ownership. |
| Backend `default_acl` | Explicit grants to that backend in global defaults and the private/ledger schemas; not all schema-specific defaults. |
| Backend `new_par_access` | Existing table/column access to `inventory_par_versions` or EXECUTE on `guard_inventory_par`. |
| Ledger denial | Reuse existing table/column ledger denial for every classified client and backend. This is not a full client-private-schema audit. |
| Supplemental managed observations | Per backend, schema CREATE/ownership, relation/function ownership and role/PUBLIC future grants in `public` and `extensions`, plus explicit global PUBLIC future grants. Missing schema presence is recorded. Flag-refused roles are not evaluated here. |

Supplemental findings require permission review; they never change the installer's
predicate or authorize an exception. They report privileges, not why they exist,
whether they are platform-required or whether removing them is safe. Default-ACL
observations examine explicit `pg_default_acl` entries; a false future-grant value does
not assert the absence of PostgreSQL's implicit defaults or unexamined scopes.
The result is `observations_recorded`, never an installer pass or operational release.
Full readiness, browser private-schema access, writer drain, backup/restore and
runtime RLS cutover (O1) are explicitly `not_evaluated`. Any later install still
rechecks all its existing guards.

## Proposed hosted execution, approval still required

This is the plan for a future separately approved invocation, not a runnable
hosted adapter in this slice. Present its accepted source SHA, source hashes,
exact scope and private target/role inventory for approval first.

1. Reconfirm the intended Supabase build project and explicitly classified role
   list through private handling. Do not infer trust from a role name or create a
   role. Use the existing approved maintenance connection; no credential or app
   connection change is part of this plan. Do not read those private inputs now.
2. Use the existing direct maintenance connection helper with `readonly=True`,
   verified TLS, pinned expected project/actor/database, a bounded application
   name and no retries. Record server version, own backend PID, read-only settings
   and safe target fingerprints. Fail on any identity/TLS mismatch.
3. Call `collect` on the idle owned connection; its overall 60-second deadline
   is independent of the per-query limits. Preserve any original
   failure and bounded cleanup categories; never include driver text in shared
   output. A read-only commit is snapshot completion, not a schema/data change.
4. Close the owned connection within five seconds. Use one separately bounded
   read-only observer to verify that exact PID is absent, refreshing its local
   statistics snapshot first; close the observer within five seconds. Maximum two
   connection attempts, no retry, and 120 seconds for the complete invocation.
   A failed/uncertain close or absence check holds the overall result.
5. Save the private report and its SHA-256 only after cleanup disposition is
   recorded. Retain exact role names privately; shared Git/JMAX notes use aliases,
   UTC/Eastern time, per-rule statuses and receipt fingerprints. The public
   summary contains fixed categories/counts only, including supplemental findings.

API/Toast stay running during this future read-only observation. It does not
claim stopped writers, validate a backup, produce an executable migration plan
or establish maintenance readiness. Do not invoke the maintenance-bound installer
`dry-run` using an invented window or stale backup. No hosted step above has run.

## Disposition after the observation

- Any `held`, `not_evaluated`, supplemental authority finding or cleanup failure
  requires an explicit disposition. Do not treat aggregate counts as clearance.
- Resolve any necessary privilege changes in a separate reviewed proposal with
  owner approval; never auto-grant, auto-revoke or relax an installer rule.
- Only after the role findings are resolved and revalidated should a new window
  be proposed: reconfirm writers, pause/drain, take a fresh encrypted backup and
  disposable restore, prepare a new exact plan and prompt before its application.
- The restricted runtime-role/RLS cutover remains separate O1 work. Par editing
  stays held, ordering manual, and Track 1 accounting independent.
- PR50 live PIN/personal-login acceptance, credential strength/rotation, activity
  review and Companion ingress trust remain separately held. Merged code and
  green CI do not close those operational/security findings.

## Local rehearsal evidence

All serial runs passed, with no failures, errors or skips:

| Evidence stem outside Git | Result |
| --- | --- |
| `par-role-preflight-targeted-20261021T173350885817Z` | Final focused offline selection: 41 methods plus 137 subtests, 178 reported cases. Covers refusal prefixes, other-role continuation, missing roles, ledger denials, private-summary redaction, invalid classification, read-only/session-setting refusals, deadline cancellation, timeout cleanup metadata and existing receipt/installer guards. One existing dependency warning. |
| `maintenance-ipv6-database-20261021T172247765217Z` | Initial selection: six methods plus 12 subtests, 18 cases. Includes all four new database methods plus unchanged installer refusal and normal install/reconcile tests, retaining the fictional $55.00 Track 1 control. |
| `maintenance-ipv6-database-20261021T173438665169Z` | Final new database selection after search-path/deadline hardening: four methods plus six subtests, 10 cases. Proves all six real refusal categories, metadata findings, rejected write, normalized/restored session settings, unchanged catalog/data fingerprints and owned connection closure. Redundant per-refusal deep snapshots were removed; the complete before/after accounting/catalog fingerprint case remains. |
| `par-role-preflight-offline-20261021T173624901519Z` | Full offline profile: 407 methods plus 754 subtests, 1,161 cases. Both Windows ACL checks passed; five existing dependency/lifespan warnings remain. Generated review guides match source. |

Earlier focused runs passed 173 and then 177 cases while coverage expanded. All
these profiles overlap; their totals must not be added as unique coverage. Both
database-run receipts verify unchanged original database/role inventories, the
owned loopback PostgreSQL 17 server stopped and no hosted connection used.
The final role-prefix test keeps the real catalog refusals without repeating the
full fingerprint for every refusal; the dedicated fingerprint case retains that
independent preservation proof.

Fixtures create only fictional roles/databases on the dedicated loopback server;
no Supabase or application configuration is loaded. Read-only enforcement and
source hashes are tested, but hosted TLS/deployed role compatibility is not
claimed. The existing installer/permission predicates, app/frontend, migrations,
snapshot, pinned catalog/permission inputs, hosting configuration and CI workflow
are unchanged. Only explicit review-runner selections add the new tests to CI.
Frontend tests/build were not rerun locally for this ops/documentation slice.
Python syntax, whitespace and 182 local documentation link targets pass.

This continuation remains local. Prompt before draft publication; fresh exact-head
CI and independent review follow publication, with merge and hosted execution
separate decisions. No credential, role/grant, service or app connection change
was made, and no hosted preflight, maintenance or migration was run.
