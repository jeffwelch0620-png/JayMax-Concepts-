# Owned connection signal rehearsal and retirement test plan

October 9, 2026. Local review branch only. This step tests closing newly created,
read-only clients for the two exact retained build roles. It is not an old-role
retirement, application cutover, pooler restart or credential rotation.

## Observed evidence

`credential-retirement-review-20261009T203550486659Z.json` acknowledges both
owned-client terminations, confirms each backend disappeared, observes each client
closed, and records fresh direct reconnection with the unchanged original
credential. The owner had both function EXECUTE and pg_signal_backend membership;
the actual successful signals now go beyond the earlier capability-only review.
The preflight session survey found zero existing sessions for either build role.
Only the two test-created direct clients were signalled; no observed application
session was targeted. Both LOGINs, passwords, grants and application flags remain
unchanged. Direct connections used certificate and hostname verification.

The process stopped during final comparison before writing its terminal receipt.
That interrupted journal remains held, unchanged and separately hashed. The
read-only reconciliation receipt is
`credential-retirement-reconciliation-20261009T210138614659Z.json`.
Its status is `verified_reconciled_owned_probe_signal_rehearsal`, completed at
2026-10-09 21:04:00 UTC. Reconciliation never repeats the signals, changes a LOGIN
or rotates a password. Both acknowledged test backends are absent, no current
build-role sessions were observed, and unchanged original credentials authenticate
as the intended roles on direct and session-pooler paths. Full original-column
application fingerprints, global Track 1, the complete migration ledger,
catalog/access/policy/count snapshot and role attributes match the earlier
recovered baseline `build-rotation-20261009T1507511805325Z.json`.

The interrupted probe did not durably record its own complete preflight baseline.
This reconciliation therefore compares against that independently preserved
recovered baseline; it does not invent a missing final receipt or relabel the
interrupted journal as passed. Its SHA-256 is
`da3f6c2251c5cfd82afb4568da713f585f23b513284c221fdc95784afbe43f1b`.
Future mutation probes must save complete preflight hashes before issuing signals.

Ten guard tests and 15 subtests pass. They reject owner/protected/unknown roles,
changed role OIDs or backend identities, reused PIDs, arbitrary application clients,
busy or transaction-bearing clients and clients with locks. Signals require the
caller-held client, generated UUID label, matching role/database/backend start,
read-only identity and an idle client backend. These predicates are repeated in
the signal statement. A changed candidate, absent acknowledgement or backend
still present holds the test. Evidence excludes query text, addresses and arbitrary
application labels. Existing application connections are never signal candidates.

## Next bounded comparison

Keep the [isolated LOGIN hold](ISOLATED_LOGIN_COMPARISON_CHECKPOINT.md) and combined
credential/recovery checkpoint held. The earlier fresh pooler client accepted a
confirmed NOLOGIN role; today's direct-client signal rehearsal does not resolve it.

The next comparison should:

1. Require the verified application backup, unchanged private configuration,
   original credentials, exact recorded role OIDs and recovered baseline. Save
   complete preflight comparison hashes durably before any mutation. Observe
   sessions first; do not infer that every session using a build role belongs to
   the probe, even if the initial survey is empty.
2. Open a new labeled, read-only session-pooler client for one recorded role.
   Verify its actual LOGIN, PID, backend start, forwarded application label and
   owner-visible idle/no-transaction/no-lock state. If ownership cannot be
   established, stop; do not broaden the signal selection.
3. Temporarily set only that exact role NOLOGIN. Confirm the owner catalog state
   and native fresh direct login denial. Preserve the other role's availability.
4. Close only the newly owned pooler client's backend using the reviewed identity
   guards. Require its disappearance and client closure. Test fresh pooler
   authentication after the bounded propagation interval. A timeout, arbitrary
   internal error or accepted connection cannot pass as a denial.
5. Restore LOGIN in finally, then verify unchanged original credentials through
   direct and session-pooler paths. Repeat for the second role only after the
   first role has recovered. Record full original-column, Track 1, migration,
   catalog/access and role comparisons. Keep partial or interrupted runs held
   until separately reconciled; do not retry mutations blindly.

This would test whether draining an explicitly owned connection changes the
observed NOLOGIN behavior. It would not prove a managed pooler cache was purged,
retire other clients or terminate arbitrary sessions. If fresh pooler acceptance
persists, stop and preserve the evidence. Consider provider guidance/support or
new-role migration rather than weakening the strict release criteria.

[Supabase rotation guidance](https://supabase.com/docs/guides/troubleshooting/supavisor-error-password-authentication-failed-after-password-rotation)
recommends new-role migration for gradual credential replacement. It does not
establish immediate revocation of this project's cached clients.
[Connection management](https://supabase.com/docs/guides/database/connection-management)
documents observation and signalling permissions; having those permissions alone
does not establish that old application access has been retired.

## Release boundary

No push, merge, deployment, paid IPv4 add-on or active configuration change.
Preserve the protected original continuation. Actual pooled-login retirement,
combined rotation/recovery, managed-service recovery, browser/Data API and remaining
release/PR-chain checks still need their own passing evidence. Application-level
staff authentication remains outside this database-connection rehearsal.
