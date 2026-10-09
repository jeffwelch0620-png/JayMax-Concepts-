# Combined credential rotation and recovery rehearsal

Follow-up: the [parallel-account review](PARALLEL_ROTATION_REVIEW_CHECKPOINT.md)
verifies current original permission profiles and six successful original pooler
connections, alongside six direct timeouts. The 66 existing role-addressed policies
match the reviewed profile, and role/policy/membership metadata is preserved.
It records the singleton-policy verifier prerequisite and a staged replacement
plan; no credentials or policies changed. This combined rehearsal remains held.

October 9, 2026. Local review branch only. Hosted receipt:
`combined-rotation-rehearsal-20261009T2218325582424Z.json`.
Format: `jaymax-combined-rotation-rehearsal-v1`.
The hosted rehearsal ended `held_recovery_required` at 6:25:44 p.m. Eastern
(22:25:44 UTC). The original receipt retains that status. A separate read-only
comparison verifies the full application baseline, and a final credential check
verifies original session-pooler access and temporary-password rejection. The
combined rotation/recovery gate remains held. No further password changes were
made during reconciliation.

## Observed result and recovery

| Check | Evidence |
| --- | --- |
| Temporary credentials authenticate; old passwords rejected | Passed through direct and pooler paths |
| Existing owned session continuity | Passed; password change did not revoke open sessions |
| Both actual replacement pools; unavailable configured accessors | Passed; actual LOGIN/JSON codec and 503 without fallback |
| Controlled accounts and inventory NOLOGIN comparisons | Both passed under the versioned corroborated-denial contract |
| Temporary permission assessments / complete exercise | Not verified; exercise held after the per-role comparisons |
| Original-password restoration | Owner transaction acknowledged twice; original receipt could not verify reconnection |
| Separate original credential check | Both original credentials accepted and temporary passwords denied through both paths at 6:27 p.m. |
| Subsequent direct connection checks | Timed out; transport failures are not authentication denials |
| Current application connection path | Both original session-pooler credentials accepted; both temporary passwords rejected with native 28P01 |
| Complete source comparison through verified owner session pooler | All 120 table/sequence fingerprints, 13 catalog groups, Track 1, complete ledger and original role attributes preserved |

The current credential/baseline receipt is
`restored-pooler-credentials-20261009T2233155126105Z.json`, with status
`verified_restored_session_pooler_credentials_and_application_baseline`.
It links the unchanged baseline receipt
`combined-rehearsal-reconciliation-20261009T2230335580969Z.json` and original
held trial by SHA-256. Current direct availability remains unverified.

The first read-only reconciliation,
`combined-rehearsal-reconciliation-20261009T2227140942420Z.json`, verified all
credential checks but held with InterfaceError before a completed data comparison.
The second held on a direct-owner connection timeout. The third used the existing
certificate-verified session-pooler owner connection and a fresh connection for
the read-only comparison; its full baseline passed, while its direct client
timeouts correctly kept its overall status held. No historical receipt is relabeled.

The initial trial's terminal error and recovery error are InvalidPasswordError.
Its recovery finally block superseded the original exercise exception, so the
underlying exercise failure is not independently attributed. Do not infer cache
causation from the later transport timeouts. The revised local module preserves
the original exercise error type/stage, journals each permission-connection stage,
and permits bounded native-password refresh during original-credential recovery.
Transport and unrelated errors still stop recovery verification. An independent
terminal guard rejects incomplete or errored exercises even if earlier booleans
are true. The exact hosted module/runner are frozen in the snapshot; these revised
controls are locally tested and have not been exercised by another hosted rotation.

## Controlled process

This is a complete temporary credential round trip. The original private
configuration stays intact and must be restored even when the exercise passes.
Temporary credentials are written exclusively to a fresh local credential folder
with current-user and SYSTEM access. Both original and temporary file ownership,
allowed ACL identities and protected parent-folder permissions are checked.
The temporary file remains inactive after recovery; no application .env is swapped.

The passing [two-role corroborated-denial receipt](CORROBORATED_POOLER_DENIAL_CHECKPOINT.md)
is an explicit prerequisite. Its project, role OIDs, baseline role attributes,
versioned contract and exact tested source hashes are checked. Current source
fingerprints must match the authenticated verified six-schema encrypted backup.
All table/sequence, catalog, role-attribute and complete ledger fingerprints are
saved durably before any password or LOGIN change. Both original credentials
must authenticate through direct and session-pooler paths.

Only the two pinned generated build roles can have their passwords changed.
All identifiers, password literals and both OIDs are checked before a password
statement executes, inside one transaction with bounded statement/lock timeouts.
An uncertain commit acknowledgement also triggers restoration of both originals.
Only safe stages and error categories enter the atomic journal; passwords, URLs,
raw driver messages, SQL and business records do not.

The exercise tests continuity of its already-open owned sessions, then closes
them and authenticates the temporary credentials. Replacement refresh permits
at most three attempts, separated by 15 seconds, exclusively for native password
denial. Other errors hold. Original passwords must then be rejected through both
direct and pooler paths with native InvalidPasswordError / 28P01; the provider
lookup category is not allowed to substitute for password-rejection evidence.

Both actual application pool constructors run with certificate-verified TLS.
The account pool must pass its existing startup permission gate. Actual LOGIN
identity, read-only mode and the JSON codec are checked. Pools close before
disable tests. The actual configured-pool accessors must return 503 when absent,
without selecting an owner connection or the other pool.

Using temporary credentials, accounts is tested before inventory. Each role is
confirmed NOLOGIN by the direct owner connection; fresh direct denial is required.
Only its verified newly owned pooler test connection may be terminated. The
[versioned denial contract](CORROBORATED_POOLER_DENIAL_CHECKPOINT.md) requires
matching ownership, backend/client closure, both bounded fresh lookup denials,
peer availability and credential reconnection after LOGIN restoration. The native
strict-pass flag remains distinct. A per-role check's
`originalCredentialReconnectedOnBothPaths` refers to the temporary credential
supplied for that comparison; `comparisonCredentialScope` states this explicitly.
It does not mean the pre-rotation password was active at that stage.

After both comparisons, temporary inventory/account permissions are assessed
read-only. The finally block restores both original passwords and LOGINs, proves
original authentication through both paths, then requires native rejection of
both temporary passwords through both paths. A passing exercise still performs
this recovery. A second owner-assisted recovery path covers a closed owner or
an incomplete first restoration. The original permission profiles are then
assessed, and the entire source/role/Track 1/ledger baseline is compared again.

## Validation and limits

Fifty-eight local tests and 101 subtests pass. The new guards cover prerequisite
versions/recovery, missing durable-baseline/private-staging gates, invalid role
or password literals before SQL, role OID drift before any password statement,
exact password-denial signatures, bounded refresh, codec setup cleanup, uncertain
password transaction recovery, journal failure, early old-password acceptance,
owned-disable failure stopping the second role, and restoration after success.
Existing rotation, corroborated-denial, native classification, explicit session
setup and owned-session signalling guards are included. The dependency warning
is a pending multipart-library deprecation, not a failed check. The broader
backend/browser suite was not rerun for this controlled probe.

Additional guards verify bounded recovery refresh on both paths, refusal to retry
transport failures, preservation of the exercise error before recovery, and
terminal qualification that cannot turn recovered errors into passing results.

No business rows, schema, grants, role membership, application flag, active
connection file or endpoint are changed. No operational invoice imports, external
integration calls, paid IPv4 add-on, pooler restart, deployment, push or merge occur.
Existing application sessions are observed but never termination candidates.
Track 1 is compared independently and remains the accounting baseline.

A passing rehearsal clears this specific combined connection/recovery evidence
gap. It does not activate permanent replacement credentials, retire all clients,
prove managed Auth/Storage/Vault recovery, approve publication or validate browser/
Data API exposure. Earlier held rotation receipts retain their original status.
The authoritative hosted database and separate encrypted local backup remain the
planned setup, using the session pooler on port 5432.

Next: review parallel new-role credential rotation and direct-path reliability
before another hosted credential mutation. Avoid repeated same-role password
cycles to bypass this hold. Then reconcile the remaining deployment/PR checklist,
browser/Data API exposure and sequential PR chain before naming a safe merge point.
Permanent credential cutover remains a separate action. Original pooled build
credentials remain in place; temporary configuration is inactive. Keep merges held.
