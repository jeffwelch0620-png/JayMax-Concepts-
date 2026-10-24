# JayMax Restaurant Group — Inventory / Prep / Food Costing

## Now

Inventory serves Bert's, Rudd's and Papa Leoni's. PostgreSQL is authoritative
for catalog/units, purchases, counts, prep/production and stock effects.
**Actual purchased-item counts + received purchases − closing count** determine
Track 1 usage; count values are explicit. Prep/waste and sales explain variances
without rewriting that accounting baseline. Taxes/fees stay separate.

Accepted baseline: PR64 **f4235f7**, tree-identical to tested 502519e. All four
[reviewed-head checks](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/40057721329)
and [merged-main checks](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/40058597235)
passed separately. The October 24 approved S1 v3 attempt observed API PR64 and
frontend PR53 Live with finite service source proofs. Its two-connection read-only
collector completed in 11.391 seconds: 13 scoped relations, ledger 55 and 17,468
recorded owner/manager audit entries with a retained 200-row sample. Aggregate
coverage was complete; the sample was truncated and is not exhaustive security
review. Both owned database clients closed. PIN/role probes remained NOT EVALUATED:
the attempt stopped before any controlled API/PIN request because the required
protected-input request transport was unavailable. That window is closed and
its approval consumed. Existing app/service/credential settings remained unchanged.

The authorized [local transport design and rehearsal](docs/S1_PROTECTED_REQUEST_TRANSPORT_20261024.md)
now uses isolated anonymous/personal contexts, legitimate fictional logins,
strict route/response/time limits, one-use request slots and minimized receipts.
It deliberately has **no hosted mode**. Local validation, independent review,
hosted activation and a fresh live approval remain separate gates. The
[collector history](docs/S1_VISIBILITY_SESSION_FOLLOWUP_20261023.md) remains dated
evidence; this slice does not change collector or application behavior.

## Next

- Complete local transport validation and JMax readback, then prompt before a new
  draft PR push. After independent review, prepare a separately reviewed activation
  adapter and fresh exact S1 packet: up to 18 probes plus three explicit personal
  logins, durable source/approval/claim guards and private operator handoff. No live
  execution is enabled or authorized by this local slice.
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
