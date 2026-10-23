# Local par/security document amendments — October 23, 2026

Scope: owner-approved local documentation, checklists and JMAX reconciliation.
No runtime, test implementation, SQL migration, permission candidate, source-pin,
hosting, credential, grant, schema, provider or operational-data change. GitHub
publication is held for the owner's push decision; no fresh CI is claimed before
publication. Dated PR59 CI is linked separately in the README/current plans.

## Review disposition

| Item | Amendment / correction |
| --- | --- |
| A1 / B8 | Replace current README/hosted-plan/runbook entry text with short now/next/held routing. Preserve each entire original Git blob verbatim in a same-directory dated archive so relative links retain their base. Preserve JMAX historical prose/links in verified dated snapshots before reconciliation; keep distinct accounting, module and collaborator content. |
| A2 | Add the pre-filled P2 yes/no decision checklist: exact three digests, named objects and limits; blank fresh plan/version/archive/manifest/restore/ledger/drain/window fields; timely approval and 1,200 s work/restoration plus separate cleanup margin. |
| A3 | Add preparation target 1.3 GiB; retain hard 1 GiB/15% loaded gate, existing monitoring and stop thresholds. Record timezone and actual-date UTC/Eastern conversion, avoid staff/Toast starts, and require no merges to main throughout the window. |
| A4 | Correct to 17 constraints (three FKs / 12 internal FK triggers). Capture actual dashboard Free versus Blueprint starter discrepancy without changing hosting/billing. |
| B1 | Change the already-budgeted blocked wrong-PIN request's synthetic X-Forwarded-For. First request has bounded 90 s total timeout/no retry. Record restart/state continuity and do not call reset-state success expiry proof. App activity logs are not complete authentication or direct-DB-session evidence. |
| B2 | Add activity_log primary INSERT and RLS dependency. Existing candidate already requires SELECT/INSERT; no product read route found, so justify/reduce SELECT only in R1. Correct negative test: middleware catches logging failures, so HTTP may succeed while the audit row is missing; test the denied write/missing row/error, not an assumed failed request. Fail-closed audit behavior is a separate product decision. |
| B3 | Record source-expected RLS false for unit_profiles/item_bases, true for store_state/activity_log; installed state is unverified. Test actual caller grant/policy paths, not imaginary policies on RLS-disabled tables; FK integrity checks bypass RLS. No RLS/policy change here. |
| B4 | Preserve existing per-table UPDATE-based SHARE lock candidate for six named catalog tables. Do not blanket-substitute MAINTAIN: it also permits maintenance/broader locks. Keep par MAINTAIN denied; future privilege change must include candidate/validator/catalog and route/immutability tests. |
| B5 | Specify detection of DATABASE_URL-only cutover with auxiliary unset, both actual actors, same-target checks, invalid/empty auxiliary refusal and pool restart. No new account-pool implementation in this slice. |
| B6 | Separate targeted S2a rotation after S1 consumer inventory from the full R1 redesign; keep it outside P1 and regenerate affected private config/approval packets afterwards. Extend audit scope to the known exposure date or explicitly document unavailable/capped coverage. Rotation is still held for its exact packet. |
| B7 | If selected, live Supabase Auth adoption follows S2a and reviewed R1. Local identity design continues; no provider selection, settings or account linking is inferred. |

## Evidence and authority

Review is based on accepted c3b429a and the October 23 local proposal bundle,
current Inventory source and JMAX snapshots. Existing actual role/grant state,
writer inventory, dashboard plan and deployment are dated evidence until their
separately approved checks. Local source comparisons do not refresh hosted state.

Public references: [PostgreSQL 17 lock privileges](https://www.postgresql.org/docs/17/sql-lock.html),
[MAINTAIN privileges](https://www.postgresql.org/docs/17/ddl-priv.html), and
[row security / referential integrity](https://www.postgresql.org/docs/17/ddl-rowsecurity.html).

The [archive manifest](APPROVAL_DOCUMENT_ARCHIVES_20261023.json) binds preserved
Git history bytes. The generated [local validation receipt](PAR_SECURITY_DOCUMENT_VALIDATION_20261023.json)
records documentation/link/preservation/source checks; it does not claim runtime
or PostgreSQL tests, CI, hosted readiness or live approval.

The initial local document check also matched the explicitly historical
"45-minute" wording in the new archive disclaimer. The assertion was corrected
to inspect the active Now/Next/Held section, retaining the disclaimer unchanged;
the corrected run passed. This was a validation-scope correction, not a runtime
or database failure.
