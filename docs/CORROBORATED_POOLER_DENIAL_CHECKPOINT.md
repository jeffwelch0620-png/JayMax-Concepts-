# Independently corroborated pooler denial

Follow-up: the [combined rehearsal](COMBINED_ROTATION_REHEARSAL_CHECKPOINT.md)
verifies both per-role comparisons under temporary credentials, but the complete
rotation/recovery exercise holds. Original pooled access and the full data baseline
are separately verified after recovery. This passing isolated contract remains
valid within its bounded scope; it does not clear the combined or release gates.

October 9, 2026. Local review branch only. Contract:
`jaymax-corroborated-pooler-denial-v1`. Hosted receipt:
`corroborated-pooler-denial-20261009T2145358003693Z.json`.
Final status: `passed_corroborated_pooler_denial_comparison`, completed at
5:50:19 p.m. Eastern (21:50:19 UTC). Both role comparisons and the complete
recovery baseline pass. The separate combined rotation/recovery gate remains held.

## Observed result

| Check | Accounts | Inventory |
| --- | --- | --- |
| Owner confirms exact recorded role NOLOGIN | Passed | Passed |
| Fresh direct login-not-permitted denial / 28000 | Passed | Passed |
| Only the verified owned pooler client terminated, backend absent, client closed | Passed | Passed |
| Two bounded fresh pooler requests | Exact EAUTHQUERY lookup denial / XX000 | Exact EAUTHQUERY lookup denial / XX000 |
| Other account available through both paths | Passed | Passed |
| Original LOGIN restored and unchanged credential reconnected through both paths | Passed | Passed |
| New independently corroborated lookup qualification | Passed | Passed |
| Native-only strict-pass flag | False; retained separately | False; retained separately |

Before mutation, all source fingerprints matched the authenticated verified
six-schema backup. After both roles were restored, all 120 table/sequence
fingerprints and 13 catalog groups matched that baseline. Independent Track 1,
complete migration-ledger and original role-attribute comparisons passed. Both
owned clients and the owner connection are closed. Both original credentials
remain current and usable through direct and session-pooler paths. No tested
fresh request authenticated while its role was disabled after the owned drain.

## Why this contract is separate

The [native-only controlled drain](OWNED_POOLER_DRAIN_CHECKPOINT.md) remains
`held_recovered_owned_pooler_drain_comparison`. Its inventory requests were denied
with the exact EAUTHQUERY lookup response, while its owner/direct/owned-connection
witnesses passed. This checkpoint introduces a separate, versioned qualification;
it does not rewrite the historical result or classify arbitrary XX000 errors as
native authentication denials. The native-only comparator and error classifier
remain unchanged.

[Supavisor authentication documentation](https://supabase.github.io/supavisor/connecting/authentication/)
describes retrieving user authentication material through an auth query. The
[public auth-query implementation](https://github.com/supabase/supavisor/blob/main/lib/supavisor/auth_query.ex)
distinguishes an empty user lookup (`user_not_found`) from failed or malformed
queries. That supports examining the specific response separately; it does not
establish this hosted project's deployed source version, tenant auth query or
cache state. No password hash is requested or included in evidence.

## Required runtime witnesses

The exact generated role must match its original recorded OID before disable and
after restoration. The owner confirms NOLOGIN, and a fresh direct connection
must return the known login-not-permitted category with SQLSTATE 28000 and the
expected driver error class. A password denial alone cannot corroborate NOLOGIN.

The live pooler client and owner activity view must verify the generated label,
actual LOGIN, read-only mode, role/OID, database, PID and backend-start timestamp.
Only this newly owned, idle, transaction-free, unlocked client may be signalled.
The signal repeats every ownership predicate; its role/PID/start must match the
prepared client. Backend absence and actual pooler-facing client closure are
required. Existing application sessions cannot qualify as owned test clients.

Two bounded fresh pooler requests, separated by the existing 15-second intervals,
must both reject access with the exact allowlisted lookup category and
InternalServerError / XX000 signature. The category originates from the existing
exact-message allowlist. Any accepted attempt, unknown internal error, transport
failure, mixed response category or missing witness holds qualification. The
other account must remain available through direct and session-pooler paths.

The native-only comparator restores LOGIN in its finally block. This wrapper
intercepts only its exact native-denial hold, then requires the original unchanged
credential to reconnect through both paths. Only afterward can it record
`provider_lookup_with_independent_witnesses` and
`corroboratedLookupDenialQualified=true`. The native strict-pass flag stays false.
A fully native denial has its own distinct mode; it also requires the same
ownership, peer availability and recovery witnesses.

## Controlled hosted scope

The accounts role is tested first, then inventory. Restoration and successful
original-credential reconnection precede the second role's NOLOGIN. A complete
preflight row/catalog/role/ledger baseline must match the authenticated verified
six-schema backup and be saved durably before mutation. The outer recovery
restores exact attempted roles, verifies both credentials and independently
compares all application fingerprints, catalog groups, Track 1, complete ledger
and original role attributes.

Only temporary LOGIN changes and termination of newly owned test connections are
authorized by this trial. Passwords, grants, role memberships, business rows,
application settings and endpoints are unchanged. No pooler restart, paid add-on,
deployment, push or merge occurs. The application connection plan remains the
shared session pooler on port 5432 with the private retained credentials.

The helper runs hidden with an atomic evidence journal so chat reconnects do not
interrupt recovery. No concurrent mutation trial may run. An interrupted or
nonterminal receipt remains held until access and the full baseline are reconciled.

## Local validation and release boundary

Thirty-four guard tests and 73 subtests pass. This includes the existing native
classification, explicit session setup, owned-signal identity and restoration
guards. New tests cover missing/non-boolean witnesses, role/OID/PID/start mismatch,
existing-session exclusion, accepted/unknown/transport responses, two-attempt
lookup requirements, distinct native classification, exact-hold interception,
failed recovery reconnection, arbitrary labels and independent peer paths.
The ordinary backend/browser suite was not rerun for this probe-only checkpoint.

Qualification proves only these bounded fresh requests after closing these owned
clients. It does not prove retirement of every application session, a managed cache
purge or successful combined credential rotation. The combined rotation/reconnect/
recovery probe retains its separate gate and existing held evidence. Do not publish
or merge on the strength of this comparison alone. Managed-service recovery,
browser/Data API, deployment and sequential PR checks remain separate.

Next: apply this narrow, versioned qualification to the combined credential
rotation/pool-reconnect/recovery probe, with its own local guards and hosted
receipt. Preserve old-password rejection as a distinct authentication check,
complete baseline capture before mutation, exact owned-session signalling and
original-password/LOGIN recovery on any hold. Existing held combined receipts
remain historical evidence; they cannot be relabeled as passed. Keep the current
private configuration and merge hold until the combined workflow is verified.

[Supabase's rotation guidance](https://supabase.com/docs/guides/troubleshooting/supavisor-error-password-authentication-failed-after-password-rotation)
describes cache delays and gradual new-role migration. Do not infer immediate
global revocation from NOLOGIN or repeat password rotations to bypass a hold.
