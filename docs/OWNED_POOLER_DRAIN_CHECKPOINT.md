# Controlled NOLOGIN and owned pooler-client drain

Follow-up: the separate [corroborated denial checkpoint](CORROBORATED_POOLER_DENIAL_CHECKPOINT.md)
passes for accounts and inventory under a new, versioned contract with independent
owner/direct/owned-connection/peer/recovery witnesses. Full recovery preservation
passes. This native-only receipt retains its original held status; the combined
rotation/recovery gate remains held.

October 9, 2026. Local review branch only. Initial receipt:
`owned-pooler-drain-20261009T2119254300057Z.json`.
The final trial receipt is `owned-pooler-drain-20261009T2129233178790Z.json`.
Final status: `held_recovered_owned_pooler_drain_comparison`, completed at
5:33:18 p.m. Eastern (21:33:18 UTC). The strict comparison remains held; the full
recovery baseline passes. Earlier held receipts are preserved without relabeling.

## Result

| Check | Observed result |
| --- | --- |
| Before mutation | Current source matches the authenticated verified six-schema backup; complete baseline saved |
| Inventory role | Owner confirmed its exact recorded OID was NOLOGIN |
| Fresh direct client | Known login-not-permitted denial, SQLSTATE 28000 |
| Owned pooler client | Exact labeled client verified, its backend terminated/absent and its client observed closed |
| Fresh pooler requests | Both bounded attempts rejected with the exact EAUTHQUERY user-not-found category, InternalServerError / XX000 |
| Other account during disable | Available through direct and session-pooler paths |
| Recovery | Inventory LOGIN restored; both unchanged original credentials authenticate on both paths |
| Scoped data and catalog | All 120 table/sequence fingerprints and 13 catalog groups preserved |
| Track 1 and complete migration ledger | Preserved independently |
| Role attributes | Match the recorded original baseline |
| Accounts-role disable | Not run; stopped after the inventory strict-denial hold |

No tested fresh pooler request was accepted after the owned drain. This differs
from the earlier [undrained comparison](ISOLATED_LOGIN_COMPARISON_CHECKPOINT.md),
which accepted a fresh inventory client after confirmed NOLOGIN. The current
controlled requests identify the exact requested role and corroborate the lookup
failure with owner catalog/direct-denial/drained-backend evidence. They do not
trace a managed cache purge or prove every other client's access was retired.

The native-denial-only guard correctly held on XX000. This checkpoint does not
silently reclassify that response as a passing strict authentication denial,
complete credential rotation or approve release. Both accounts and the full
baseline were restored/verified before this checkpoint was sealed.

## Controlled scope

The reviewed test temporarily disables only one exact retained build LOGIN at a
time, confirms fresh direct denial, closes only that role's newly created owned
pooler test connection and checks fresh pooled authentication. The other role
must remain available. LOGIN restoration and unchanged original-credential
reconnection precede testing the second role. The outer recovery also restores
each exact attempted role and verifies both original accounts.

No password, grant, role membership, business record, application flag or endpoint
is changed. No existing application connection is targeted; activity observations
are not termination candidates. There is no pooler restart, paid IPv4 add-on,
deployment, push or merge. Source data must match the authenticated verified
six-schema backup before any LOGIN change. Complete row/catalog fingerprints,
role attributes and migration-ledger hashes are saved durably before mutation,
then independently compared again after recovery. This covers Track 1 directly,
without deriving it from prep or sales.

## Safeguards and acceptance

Twenty-three guard tests and 18 subtests pass. Ten existing owned-signal guards are
included; thirteen new tests cover exact generated identifiers, strict denial/error
classification, closure of unexpectedly accepted clients, refusal before mutation,
safe journal failure and restoration after signal failure or accepted fresh access.
They also verify explicit read-only/label configuration, actual acknowledgement,
refusal to adjust a wrong-identity connection and closure on setup failure.
The ordinary backend/browser suite was not rerun for this probe-only checkpoint.

Owned pooler identity must be established through both the live client and the
owner's activity view: role/OID, database, PID, backend start, generated forwarded
application label, read-only session, idle state, no transaction and no locks.
Owner, protected or arbitrary identifiers are rejected. The previously reviewed
signal repeats the identity and idle predicates in its SQL; it does not signal
all sessions matching a username. Backend disappearance and actual pooler-facing
client closure must be observed.

The initial attempt stopped before any LOGIN change because it could not verify
the requested startup settings. Its full source/role/ledger recovery comparison
passed. A separate read-only diagnostic,
`pooler-session-settings-20261009T212217666496Z.json`, found that both tested pooler
clients ignored the requested startup label/read-only settings, while explicit
per-session SET/set_config succeeded. Both backend identities stayed stable and
the owner verified exact idle ownership afterward. The revised connector verifies
actual LOGIN first, sets read-only mode and its own generated label explicitly,
then requires acknowledgement. This affects the probe only, not application pools.

The second attempt held during the full fingerprint preflight with BackupError
before any LOGIN change. Its reporter retained the error type without safe detail;
do not infer a specific failing relation. Original accounts/role attributes and
owner closure were confirmed. Its receipt remains held. The final runner matches
the previously verified backup's 60-second data-query budget inside read-only
snapshot transactions and preserves safe fingerprint errors/object identities.
LOGIN statements retain 30-second statement and five-second lock limits. Earlier
held receipts and exact historical runner/module bytes remain preserved.

After the owned drain, one fresh pooler attempt follows a 15-second interval.
Only an internal pooler error permits one additional 15-second retry. Native
`28000` in the known login-not-permitted category or `28P01` password denial can
qualify. An exact EAUTHQUERY lookup error is recorded separately and does not
pass this strict comparison. Timeouts, unrelated authorization/internal failures
and accepted clients hold the test. Direct denial and owner-confirmed NOLOGIN
are required as independent corroboration.

The probe runs as a hidden local helper so a chat reconnect does not stop its
finally/recovery work. Its durable journal identifies any exact attempted role.
Do not start a second mutation probe while it is running. Preserve a partial
journal and reconcile access/baseline if a process or machine is interrupted;
never relabel missing terminal evidence as a pass.

## Release boundary and follow-up

Keep the earlier [isolated NOLOGIN hold](ISOLATED_LOGIN_COMPARISON_CHECKPOINT.md)
and combined credential/recovery gate held. Even a passing controlled two-role
comparison would not prove retirement of other applications' sessions or a
managed pooler cache purge. The combined rotation/pool-reconnect/recovery test
requires its own evidence. Managed recovery, browser/Data API, deployment and
remaining sequential PR checks are separate.

If fresh access still succeeds after the owned drain, preserve the recovered
baseline and stop retries of this revocation strategy. Review provider-assisted
retirement or gradual new-role migration rather than interpreting arbitrary
pooler failures as proof. This would remain a connection-mechanics limitation;
it does not change inventory accounting or introduce data synchronization.

The next review is the exact provider denial contract. Consider qualifying only
this allowlisted lookup category under independent same-role NOLOGIN, native
direct denial, proven owned-backend/client closure, other-role availability and
complete recovery witnesses. Do not qualify an arbitrary XX000, timeout, missing
acknowledgement or accepted client. Demonstrate the reviewed contract for the
accounts role separately before changing the combined probe's error handling.
Retain the native-only hold as historical evidence; a new contract would require
its own tests and versioned evidence, not a rewrite of these results. Do not
repeat password rotations or broaden session termination to bypass this hold.

[Supabase rotation guidance](https://supabase.com/docs/guides/troubleshooting/supavisor-error-password-authentication-failed-after-password-rotation)
describes credential-cache delays and gradual new-role migration, not a guarantee
that NOLOGIN immediately revokes this project's pooled access.
[Connection management](https://supabase.com/docs/guides/database/connection-management)
describes observing and signalling sessions. This trial uses the current
certificate-verified direct owner path; the application plan stays on the session
pooler on 5432.
