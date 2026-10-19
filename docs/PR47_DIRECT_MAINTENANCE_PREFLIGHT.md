# PR47 direct maintenance validation plan

Status: **the owner separately approved this plan and its read-only check passed
on October 19.** See the [execution result](PR47_READONLY_IPV6_VALIDATION_20261019.md)
for the exact two-client scope, private-config creation and cleanup evidence.
The remaining sections retain the approved preparation; they do not authorize
a maintenance window or schema application. Keep par editing held and ordering manual.

## Accepted source and validation

Owner-approved [PR47](https://github.com/jeffwelch0620-png/JayMax-Concepts-/pull/47)
was squash-merged as `a7270ca310592e70ead51615da8cdad2659d7e7f` from
`755aff316f84835ec30687650f9531294c325453`. The complete merge tree matches the
tested head. Its final commit changes publication documentation only; executable
code/tests match locally tested `e92cd37`.

All four [reviewed-head checks](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/39195536162)
passed: 1,026 frontend tests/80 suites plus strict build, 182 reported backend
PostgreSQL cases, 1,013 Windows offline cases and the aggregate gate. The
[merged-main run](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/39196674518)
also passed all four checks on exact merge `a7270ca`, with the same reported
counts. Neither run has failed, errored or skipped cases. Overlapping local and
CI cases are not summed. The [IPv6 runbook](MAINTENANCE_DIRECT_IPV6.md) retains
the seven-case local database selection and earlier failed/incomplete attempts.

## Proposed read-only check after separate approval

1. Reverify the accepted executable tree and successful merged-main CI. Use the
   designated existing build project and its existing owner credential. Create
   a new, separate current-user/SYSTEM-owned private maintenance config outside
   Git/Drive, using `MAINTENANCE_DATABASE_URL` with interpolation disabled. Do not
   overwrite existing config or display/copy credentials into commands, logs or
   shared documentation. Validate its ACL and exact target with accepted helpers.
2. Use accepted `maintenance_connection.connect(..., readonly=True)` with its
   trusted CA and hostname checks, native IPv6 peer validation and effective
   actor/database/default/transaction checks. Retain the 20-second connect/probe
   bound and five-second owned cleanup. No application pool or pooler fallback.
3. In an explicit read-only snapshot, record safe pass/fail evidence for server
   identity/major version, the current backend identity and visibility. Optional
   object-presence/ledger-count reads are dated observations, not complete
   baseline preservation or proof of writer drain while the API/jobs are active.
4. Close that exact owned client. Open one new direct read-only observer and
   check that the original backend identity (PID plus backend start) is gone;
   do not treat a cached PID as permanently owned or exempt from writer checks.
   Close the observer as well. Any unexpected transport/settings/cleanup result
   holds the process. No SQL backend termination or broad cleanup is permitted.
5. Check the accepted IPv6-only dump-routing settings locally, without dumping
   data. Record safe hashes/booleans, timestamps and cleanup status outside Git;
   never dump process environment, full connection URLs or driver error text.
   Limit this check to two owned database clients and a 120-second overall
   observation budget, including cleanup. Do not retry automatically.

This approval would cover only separate private local config and the above
read-only check. No API suspension, Toast control, backup, DDL, DML, grants,
credential rotation, app connection change or paid IPv4 add-on is included.
If connection cleanup cannot be confirmed, stop and report before further work.

## Gate after a successful read-only check

Reconfirm every writer and the ability to recover the API/jobs. The last owner
confirmation listed `jaymax-api`, Bert's/Rudd's Toast job and Papa Leoni's Toast
job; Companion was local-only. Re-read live identities, schedules, command hashes,
enabled states and activity. Do not assume those dated values remain current.

Then request a new bounded maintenance window and a no-other-writes commitment.
After pausing only approved producers, prove strict drain using direct operator
sessions. Retained unidentified sessions still hold. Take a fresh encrypted
application backup and verify a disposable restore before generating a concrete
par plan. Prompt separately with that plan's exact SHA-256 before applying it.

The October 18 window closed at 8:35:28 p.m. Eastern and cannot be reused. Old
backup/plan hashes, dates and approvals cannot be repaired into new authority.
Migration 31, its raw/body hashes, catalog reference, grants and historical index
tools remain unchanged. Follow the [hosted plan](HOSTED_REVIEWED_PAR_MIGRATION_PLAN.md)
and [closed-window record](REVIEWED_PAR_WINDOW_20261018.md) for the later boundary.

## Validation of this preparation

This continuation changes documentation only. Generated guides, 198 relative
links and whitespace checks pass; executable/SQL/permission trees are unchanged
against accepted merge `a7270ca`. Application/database suites are not rerun for prose-only edits;
the separate exact-source CI runs above establish code validation. No new
implementation PR is required merely to use already accepted maintenance tooling.
