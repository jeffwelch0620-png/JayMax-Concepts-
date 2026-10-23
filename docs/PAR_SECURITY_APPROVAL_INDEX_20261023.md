# Par, security and integration — current approval index

## Now

PR59 c3b429a is the accepted baseline; reviewed-head and merged-main CI passed
separately. October 23's individually approved health and read-only calibration
attempts passed within their scopes. Those approvals are consumed. This slice
amends local documentation/checklists and JMAX only; no hosted work is authorized.

## Next

| Package | Concrete next decision | Still excluded |
| --- | --- | --- |
| S1 | Separately approve the amended bounded 15-minute security/configuration verification: at most 18 app requests, six asset reads, three owner-handled personal sign-ins, two read-only database connections/120 s combined work, and at most 200 minimized audit records covering the period identified in the owner record where retained evidence permits. Includes temporary Bert's PIN lockout and changed-header test. | No account/PIN/credential/grant/schema/provider/configuration edits, service controls, retries or external business actions. |
| S2a | After S1 inventories consumers, prepare the targeted credential-retirement packet independently of R1; scope and evidence stay in the owner record. Recommended before P1, outside its window. | No rotation now; final consumers, new-connection revocation proof, pooler behavior, recovery operator and separate live approval are required. |
| P1 | Separately approve a new 60-minute window: only API/Toast 3/4 temporary controls, strict drain, encrypted backup, disposable restore and full qualification. | No SQL, grants, credentials or app-connection change. No active clock until fresh approval is acknowledged with passing resources/writers. |
| P2 | Later approve the freshly generated exact plan SHA, version, target, full backup/restore bindings and par-only additive/security delta. Use the pre-built checklist. | No plan SHA/version has been generated here; a document hash cannot substitute. |
| P3 | Later approve exact labelled Bert's fixture identities, baseline, writes and transport controls for save/reload/recovery. | No real business rewrite/history deletion or operational release. |
| R1 / S2 / I1 | Complete local permission matrix/dual-pool tests, reviewed restricted cutover and canonical identity implementation. | No live grants, role creation, cutover, account links or provider adoption. |

The S1 → S2a → P1/P2/P3 sequence is the recommendation for owner decisions,
not an implicit credential approval or a newly invented installer prerequisite.
R1/I1 local development can proceed alongside it. If Supabase Auth is selected,
its live adoption follows S2a and reviewed R1; selection is not assumed.

## Held

All hosted execution/service pauses and credential, grant, schema, connection
or provider changes remain held. No new PR push before owner authorization;
CI, independent review, merge and automatic deployment remain separate gates.
Ordering manual; par editing frozen; Track 1 independent. G04/G13/O1 and managed
recovery remain open. No approval package is activated by this document.

## Current documents

- [P1 proposal and single window schedule](PAR_INSTALLATION_PROPOSAL_20261023.md)
- [P2 exact-plan decision checklist](P2_EXACT_PLAN_DECISION_CHECKLIST.md)
- [Security, identity and permissions plan](SECURITY_IDENTITY_PERMISSIONS_PLAN_20261023.md)
- [Non-executable permission delta](RUNTIME_PERMISSION_DELTA_PROPOSAL_20261023.json)
- [Current hosted-plan summary and archive](HOSTED_REVIEWED_PAR_MIGRATION_PLAN.md)
- [Review disposition and local validation](PAR_SECURITY_DOCUMENT_AMENDMENTS_20261023.md)
