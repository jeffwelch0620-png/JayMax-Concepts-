# Isolated retained LOGIN comparison — October 9, 2026

This checkpoint compares fresh direct PostgreSQL and session-pooler clients
while disabling one exact recorded build LOGIN at a time. It does not rotate
passwords, change grants or policies, modify business data, change application
configuration, or complete the combined rotation/recovery checkpoint.

## Controlled comparison

The local probe validates the existing owner/project, retained connection file,
provisioning receipt and passing workflow receipt. It requires the full recovered
baseline before making any change. Both roles must authenticate with their
original credentials on both paths, as their actual LOGIN identities. All test
clients are closed before disabling a role; successful test connections default
to read-only transactions.

The owner uses a direct connection and disables only the exact selected role.
The probe confirms `rolcanlogin = false`, requires a fresh direct PostgreSQL
`28000` response in the known "not permitted to log in" category, and tests the
pooler after a 15-second interval. An unclassified internal error permits one
additional bounded interval. Timeouts, unrelated internal errors and any fresh
accepted client cannot qualify. The other role must remain usable on both paths.
The selected role is restored in `finally`, and its unchanged credentials must
authenticate again on both paths.

The outer recovery restores both exact LOGINs if any disable was attempted and
checks fresh original-file authentication on both paths. Catalog/access,
original application rows, global Track 1, complete migration ledger and role
attributes must match the prior recovered baseline. Passwords and private files
are unchanged. This does not terminate independently existing sessions or prove
that NOLOGIN revokes them.

## Classification guards

Four local tests pass: transport/unrelated internal failures stay unclassified;
only an exact allowlisted EAUTHQUERY user-not-found message qualifies as that
lookup category; direct authorization denial requires the correct driver class
and known login category; and an unexpectedly accepted connection is closed and
reported. An EAUTHQUERY lookup category is distinct from PostgreSQL's native
authorization denial and is corroborated by owner catalog/direct checks during
this comparison. General XX000 failures remain failures.

The probe and tests are preserved as local evidence in the chained review
package. Application code, the existing combined rotation probe, schemas and
migrations are unchanged. These four tests are probe guards, not a full backend
or production deployment test suite.

## Initial attempt

`isolated-login-comparison-20261009T153959915003Z.json` records a `gaierror`
before any role was disabled. No comparison ran and no password changed. The
subsequent fresh connections passed on both paths and the complete postflight
baseline matched. This held attempt is retained alongside the subsequent retry;
it is not relabelled as a passed comparison.

## Fresh pooler acceptance with confirmed NOLOGIN

`isolated-login-comparison-20261009T154254763721Z.json` records a passing
preflight baseline and original authentication on both paths. The owner then
confirmed the exact inventory role was NOLOGIN. Direct PostgreSQL rejected a
fresh connection with `InvalidAuthorizationSpecificationError`, SQLSTATE `28000`,
in the known login-not-permitted category. After the 15-second interval, the
session pooler **accepted a fresh client**. The connection helper verified its
actual session/current role identity and set read-only transactions before the
classifier closed it. This is accepted database access, not merely a successful
TCP handshake. The other account remained available on both paths.

The inventory LOGIN was restored immediately in `finally`, and the unchanged
original credentials reconnected on both paths. The outer recovery also verified
both original credentials on both paths. The test held on fresh disabled pooler
acceptance and did not proceed to disable the accounts role. No password change
or business write occurred. The earlier EAUTHQUERY hypothesis does not explain
away this accepted connection, and no arbitrary error has been counted as denial.

This demonstrates that NOLOGIN alone did not immediately block fresh pooler
clients under these test conditions. Reuse of existing backend sessions and cached
authentication is a possible mechanism, not a verified causal trace. No sessions
were terminated, no pooler was restarted, and no broader retirement or direct
application cutover was attempted.

The completed recovery receipt verifies both original credentials on both paths
and every postflight comparison: original application rows, global Track 1,
complete ledger, catalog/access snapshot and role attributes. Both LOGINs are
restored, the unchanged original private file remains current, and all 40 pending
paths in the protected original continuation checkout are preserved. The retry
is a **recovered hold**, not a passing isolated comparison. The account-role
disable result remains untested.

## Recommended next review

Later evidence: the [owned pooler drain checkpoint](OWNED_POOLER_DRAIN_CHECKPOINT.md)
confirms inventory NOLOGIN/native direct denial and closes only a newly owned
pooler client. Both subsequent fresh pooler attempts returned the exact lookup
error and none was accepted. The native-denial-only guard held and restoration/
full source comparisons passed. This narrows the observed behavior under owned
draining; it does not relabel the earlier accepted-client result or prove the
accounts-role case. Review the corroborated lookup contract before changing the
combined error classifier.

Follow-up: the [owned-session signal rehearsal](OWNED_SESSION_SIGNAL_CHECKPOINT.md)
now proves that the owner can terminate only newly created, labeled, read-only
direct test clients for both retained roles. Fresh unchanged credentials reconnect;
independent read-only reconciliation verifies the preserved recovered baseline.
No existing application session or LOGIN was changed. This supports the next
bounded pooler-client drain comparison; it does not resolve this NOLOGIN hold.

Separate credential replacement from immediate access revocation. The earlier
rotation runs already demonstrated replacement authentication, old-password
denial and reconnects; this isolated result is a separate revocation limitation.
Keep the strict combined checkpoint held rather than weakening its pass criteria.
Review a direct backend connection option against deployment IPv6 availability,
connection limits and certificate verification, and separately design retirement
of the exact old role's pooled/backend sessions if an immediate revocation
requirement is retained. Staged replacement roles alone do not prove old pooled
sessions are retired. Any future termination should be restricted to explicitly
identified build-role sessions and reviewed before execution.

## Release boundary

Keep merges and active cutover held. Complete the combined credential rotation,
pool reconnect, both-role recovery and permission checks before claiming that
checkpoint passes. Browser/Data API exposure, deployment configuration, managed
recovery and remaining sequential PR checks still need their own evidence.
See the [read-only diagnosis](POOLER_DIAGNOSIS_CHECKPOINT.md) and
[earlier recovered rotation holds](BUILD_CREDENTIAL_RECOVERY_CHECKPOINT.md).
