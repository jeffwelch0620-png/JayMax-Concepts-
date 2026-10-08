# Hosted staff assignment and production checkpoint

October 8, 2026. Local continuation after `fa1d001` on
`codex/deployment-reconciliation-review`. No push, merge, publication, on-disk
feature-flag change or hosted permission change occurred in this step.

## Workflow and accounting boundary

The actual FastAPI application and middleware ran locally against the designated
Supabase build database, using the already retained, explicitly synthetic location.
Signed invented identities exercised the routes. Login, startup hooks, scheduled
jobs, vendor imports and POS calls were not invoked. This proves application-route
behavior with hosted PostgreSQL; it does not prove a deployed browser or login.

A reviewed daily target of four portions was released and assigned to one invented
active roster member. Concurrent identical assignment retries retained one assignment.
The staff plan reported the roster identity as claimed, with `identity_verified=false`.
Wrong-location, read-only and staff-to-manager attempts returned 403.

The task received two immutable production submissions, including a final staff
revision with measured output **2.000000000001** and **2.5 lb** purchased input.
Concurrent identical staff retries retained one revision. Pending submissions
created no production batch. Changed bodies on the same request key and stale
revision requests returned 409. The original submitting manager, the claimed
roster identity and the staff caller could not approve the production. An independent
manager accepted the partial measured batch, creating one batch and one task link.
Acceptance explicitly left the task in progress. A separate, reviewed manager
finish command then completed that same task without creating another batch.

The hosted verification recovered from its time budget as described below. Through
a completely new pool, the original submission and acceptance keys replayed the
same immutable receipts and batch, while reporting the current completed task.
Staff responses concealed private audit identities; stored attribution remained
intact, and the submitted review snapshot contained no PIN.

All eight fixture Track 1 fact-set fingerprints and the full Food Cost report
remained unchanged across completion and restart. The physical purchased-inventory
calculation remains **$60 opening + $40 received purchases - $45 closing = $55**.
Prep production and task completion explain use; neither deducts, revalues nor
replaces the physical accounting track. This trial does not establish complete
sales coverage or real Toast ingestion.

## Interrupted attempts and reconciliation

The first probe process stalled without producing its own progress receipt. A
separate read-only connection verified all original 40-table projections and all
54 migration records, with no production submissions, decisions or planning rows.
Only that verified probe process was stopped. Its precise stall cause is unproved.
The held attempt and independent reconciliation are retained as separate evidence.

The subsequent probe completed assignment, pending-submission checks, independence
denials and two successful acceptance responses, then reached its 240-second
budget before the finish/checkpoint completed. Its receipt remains **held**;
it has not been rewritten as a passing uninterrupted run.

A separate read-only reconciliation established exactly two submissions, one
accepted decision, one batch, no automatic finish, and partial progress of
2.000000000001. All **41 physical-accounting and purchasing table fingerprints**
still matched the earlier durable native checkpoint. All original 40-table
projections and 54 full migration-record hashes also matched.

The continuation reconstructed the original request keys and bodies from those
immutable synthetic journals, replayed the existing acceptance, reviewed and issued
only the explicit finish command, then verified fresh-pool replay and preservation.
It did not create a second production submission or acceptance. Progress receipts
were written before the finish commit so another interruption could be reconciled.
Synthetic roster, production and activity records remain labelled audit evidence.

## Local regression and nonowner permissions

Three selected local cases cover the full owner workflow, the nonowner workflow
and exact synthetic roster exclusions. The nonowner case uses a unique disposable
database and a role with no ownership, superuser, RLS-bypass, database-create or
role-create authority. It verifies original-store invisibility under public RLS,
blocked catalog updates, rejected private schema alteration and rejected journal
deletion, as well as the application workflow and restart.

The first permission prototype failed at the assignment trigger: ordinary roster
SELECT succeeded, but `SELECT ... FOR SHARE` could not see the row without a
scoped UPDATE policy. The local prototype now provides that fixture-scoped policy;
the trigger and independence checks remain intact. This is an important deployment
requirement, not a grant change on Supabase. Read the
[runtime permission assessment](RUNTIME_ROLE_PERMISSION_ASSESSMENT.md).

The preservation helper now accepts only explicitly named, canonical synthetic
roster UUIDs in addition to its existing exact store/item/activity exclusions.
The regression proves that changing an original staff row is still detected.
The probe adds bounded connection/command waits and persists accounting fingerprints
and additional acceptance/finish stages. These improve observability; they do not
establish the cause of the earlier stall.

## Evidence and remaining gates

The immutable review package contains committed source/diff, selected-test XML,
held attempts and redacted receipts:

- `hosted-production-stalled-attempt-20261008.json`
- `hosted-production-stalled-process-reconciliation-20261008.json`
- `hosted-staff-production-20261008T192055773309Z.json`
- `hosted-production-timeout-reconciliation-20261008.json`
- `hosted-production-reconciled-completion-20261008.json`
- `hosted-production-final.xml`, with the earlier diagnostic runs retained

After completion, preservation again matched all 40 original-table projections
and 54 migration records. Exclusions identify only the two previously retained
invented stores/items, exact invented activity actors and this one new roster UUID.
No original staff, invoice, count or journal record was removed. The protected
40-path original worktree remains byte-for-byte matched to its saved snapshot.
Private credentials and database archives are excluded from the review package.

The hosted connection still uses the privileged `postgres` owner role. Ordinary
hosted runtime-role readiness remains open despite the passing local prototype.
The browser controller timed out before reading the Supabase dashboard. Actual
Data API exposure/settings, the deployed staff portal, full managed platform
recovery and matched deployment flags remain separate gates. The existing local
application restore proof does not cover managed Auth/Storage/Vault/settings.

Next: finish the reviewed runtime permission model, validate it for all enabled
workflows, then test a dedicated hosted backend role; verify browser/Data API
configuration and complete recovery/release checks. Keep PR14–16 unmerged while
the continuation is unpublished and these checks remain open. The intended order
is PR14, retarget/revalidate PR15, then PR16, then the reviewed continuation.
Deferred login redesign and future Scheduling, Operations, analytics and Toast
integration retain their own scope. This checkpoint does not close the historical
review list wholesale.
