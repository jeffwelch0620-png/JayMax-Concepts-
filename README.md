# JayMax Restaurant Group — Inventory / Prep / Food Costing

## Now

Inventory serves Bert's, Rudd's and Papa Leoni's. PostgreSQL is authoritative
for catalog/units, purchases, counts, prep/production and stock effects.
**Actual purchased-item counts + received purchases − closing count** determine
Track 1 usage; count values are explicit. Prep/waste and sales explain variances
without rewriting that accounting baseline. Taxes/fees stay separate.

Accepted baseline: PR63 **0cba049**, tree-identical to tested 423bded. All four
[reviewed-head checks](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/40053598106)
and [merged-main checks](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/40054929392)
passed separately. The October 23 approved S1 check observed API PR59 and frontend
PR53 Live with source-equivalent service code. Owner sign-in and partial read-only
metadata succeeded; a metadata timeout stopped the attempt. PIN/role probes and
audit review remain incomplete. The [local diagnostic follow-up](docs/S1_LOCAL_DIAGNOSTICS_20261023.md)
now identifies operations and preserves completed private observations. PR61's
review amendment adds explicit audit coverage/truncation and envelope-expiry
diagnostics. PR62 accepted the [N3 disposable PostgreSQL collector test](docs/S1_COLLECTOR_POSTGRES_TEST_20261023.md).
The [F1/F2/M1 follow-up](docs/S1_TIMEOUT_METADATA_FOLLOWUP_20261023.md) separates
server/client timeout budgets, exposes capped metadata coverage, and corrects the
PIN fixture. PR63's merge and automatic test deployment were approved; runtime
acceptance was not inspected. The authorized local
[L1/L2/L3 follow-up](docs/S1_VISIBILITY_SESSION_FOLLOWUP_20261023.md) adds nullable
coverageComplete for aggregate visibility, one-observation session totals/groups with newest-first samples,
and consistent ledger total/maximum validation. All 1,620 C1 offline cases, the
overlapping 209-case focused profile and 21 disposable PostgreSQL module cases
(six real database methods) passed; owned local cleanup is verified.
PR64's C1 amendment separates aggregate coverage flags from informational record/
session sample limits; a truncated sample alone does not hold aggregate coverage.
Checkpoint/diagnostics v3 and a
fresh source-bound handoff are required before future live use. No hosted work in this slice.

## Next

- C1 and local validation are complete for existing draft PR64, with updated documentation.
  The owner approved pushing its updates; fresh amended-head CI and merge approval
  remain separate. A new
  S1 handoff/window requires separate approval. The prior attempt is closed.
- Review the [coordinated approval index](docs/PAR_SECURITY_APPROVAL_INDEX_20261023.md)
  and [security/identity/permissions plan](docs/SECURITY_IDENTITY_PERMISSIONS_PLAN_20261023.md).
  S1 verification comes first; a targeted S2a rotation packet no longer waits for
  the entire restricted-role redesign. All live approvals remain separate.
- The [par installation proposal](docs/PAR_INSTALLATION_PROPOSAL_20261023.md)
  owns the proposed 60-minute P1 schedule. A [pre-built P2 checklist](docs/P2_EXACT_PLAN_DECISION_CHECKLIST.md)
  binds the later fresh executable plan; no plan SHA/version is allocated here.
- R1 permission/dual-pool tests and shared-identity implementation are future
  local slices. This chat coordinates the queue; Companion is a bounded source
  reference. Supabase Auth is conditional, not selected or configured.

## Held

All hosted work/service pauses and credential, grant, schema, connection and
provider changes stay held. No draft PR is pushed before the owner's prompt.
Merge and automatic Render test deployment need separate approval. Ordering
remains manual, par editing frozen and operational release unapproved.

Personal owner/manager authority uses personal login. Shared-PIN identification
does not mint a session; a store without a configured PIN has its portal disabled.
The shared attempt budget can temporarily block all staff devices at that store.
These source fixes do not by themselves close deployed G04/security acceptance.

## Project references

| Area | Entry point |
| --- | --- |
| Current par status and historical provenance | [Hosted par plan](docs/HOSTED_REVIEWED_PAR_MIGRATION_PLAN.md) |
| Installation/recovery controls | [Runbook entry](docs/REVIEWED_PAR_INSTALLATION_RUNBOOK_20261022.md) |
| Non-executable permission design | [Delta](docs/RUNTIME_PERMISSION_DELTA_PROPOSAL_20261023.json) |
| Foundation, mappings and accounting relationships | [Foundation checkpoint](docs/INVENTORY_FOUNDATION_README.md) |
| Staff PIN security and limitations | [PIN security](docs/STAFF_PIN_SECURITY.md) |
| Current collaborator workflow | [JMAX workflow](https://chatgpt.com/space/page_1e9f0baababc8191a6f628ce4799af7a) |
| Dated implementation/deployment/test/setup record | [Verbatim README archive](README_HISTORY_20261023.md) |

The archive preserves all earlier milestones and setup text unchanged, including
obsolete PIN defaults, deployment claims and pending gates. It is dated evidence,
not a current setup/run command. Do not infer current hosting tier, source
coverage, permissions or table counts from it. Existing hosting is unchanged;
no paid IPv4 add-on is proposed. No secret values belong in Git or shared docs.
