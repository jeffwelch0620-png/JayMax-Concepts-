# PR19 hosted editor acceptance results

## Deployment and scope

PR19 merged at `b2f529fc59f2c10eb62376884ebc3a7a5fe22601`, incorporating
reviewed head `a6d7494`. All required PR checks and
[merge-commit Inventory CI](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/38096873955)
pass. The [frontend deployment](https://dashboard.render.com/static/srv-dauh8qid0e5s73fo9e40/deploys/dep-db5d2krrjlhs73ammcr0)
and [API deployment](https://dashboard.render.com/web/srv-dauimuugekts73ek9lr0/deploys/dep-db5eob5ckfvc739v2dc0)
were verified **Live at b2f529f**.

The API's `backend/` root correctly skipped this frontend-only auto-deploy.
There were no backend differences between PR18 and PR19. A normal manual deploy
of the merged commit aligned the deployment records without changing settings,
connections, schema or dependencies declared in the repository.

The walkthrough used two owner-signed-in Chrome tabs at Bert's and only clearly
labelled fictional item/recipe records. No invoice, credit, physical count,
reporting period, prep batch, waste or sales record was posted during these checks.
The current test session followed the October 10 merge and deployment; Render
displayed the API deployment at October 10, 2026, 9:53:48 PM EDT.

## Observed results

| Check | Hosted result |
| --- | --- |
| Original item overwrite | Two drafts opened produce at par 0. A saved 1; B retained 2 after refresh. Ordinary Save refused B. Explicit recovery named `par` as a conflict and kept the draft. |
| Independent item recovery | A saved par 1; B retained a labelled name edit. Ordinary Save held; explicit recovery staged both values. Save updated SB-002. Original name and par 0 were restored and read back. |
| Unrelated recipe activity | An unchanged item saved after recipe creation/update and refresh without losing that recipe. |
| Recipe creation receipt | Typing ` - LATE` during real creation survived its confirmed receipt. Another Save held for explicit recovery. Recovery preserved assigned code GR-001; the reviewed save retained one recipe, using the same canonical ID. Saved recipes increased from 6 to 7 only. |
| Independent recipe recovery | A saved price 12; B retained a production note at price 10. Ordinary Save held. Explicit recovery staged price 12 with the local note; a fresh read confirmed both under the same ID. |
| Competing recipe prices | A saved 14; B retained 15. Ordinary Save held. Explicit recovery named `price` as a conflict, retained typing and left saved price 14 unchanged. Accepting 14 allowed review. |
| Unrelated item activity | The unchanged dedicated recipe saved after new item activity and refresh, preserving the new catalog row. |
| Item creation receipt | Typing ` - LATE` during real creation survived its confirmed receipt. Another Save held. Navigation away/return retained the draft and saved identity. Recovery obtained the canonical supplier ID; the reviewed save retained one SB-003 row. Catalog items increased from 11 to 12 only. |
| Missing planning price | Adding SB-003 to the dedicated recipe draft showed Unknown line, plate and Food Cost percentage values with an explicit missing-price notice. This unsaved probe was removed/discarded; saved ingredients stayed unchanged. |
| Final accounting control | Fresh October 1-8 preview remained **184 opening + 173 net received food purchases - 145 closing = 212 actual Food Cost**. Active and superseded closed history both remained 212. |

Item and recipe refusals above are observed editor refusals; these checks do not
claim a hosted server 409. Local regression tests cover 409-refresh-retry paths.

## Retained fixture identities and restoration

| Fixture | Saved identity and final values |
| --- | --- |
| Original produce | SB-002; TEST ONLY Produce - UI 20261010; par 0; original purchased pack and supplier fields retained in the editor. |
| Dedicated menu recipe | `79087291-095b-4083-b478-d58b25186e2a`; GR-001; TEST ONLY Editor Acceptance - UI 20261010; price 10; notes TEST ONLY baseline; one original WI-003 portion. |
| Dedicated purchased item | SB-003; TEST ONLY Editor Receipt - UI 20261010; 1 pack x 1 lb, portion 1 lb; US Foods SKU TEST-ONLY-EDITOR-20261010; supplier `a1f18b66-1c9c-4ca5-bda8-218038db8cfe`; count, order and Toast participation all disabled; supplier price unentered. |

The new fixtures remain labelled build evidence for reviewed cleanup before
operational use. They were not added to the confirmed three-item count scope.
The dedicated recipe was never linked to the verified prepared item or batch
used by the existing prep control.

## Limits and remaining work

Fresh-read recovery sometimes refused with "Latest ... data could not be
confirmed" while retaining the draft. Later explicit reads succeeded. An initial
item restoration save also held and was resolved through a fresh read/recovery;
its cause was not established. Browser-control timeouts required inspecting
visible state before continuing; a timeout was never treated as proof of failure
or permission to repeat a successful creation. Record these reliability symptoms
for a focused follow-up without changing authentication or hosting in this work.
Item Setup's list displayed $0.00 for the new unpriced item, while Recipe Costing
correctly reported Unknown. Keep that presentation inconsistency in the deferred
UI work; the unentered price was not replaced with a confirmed zero price.

Creation timing was exercised in the active editor for both record types. Item
navigation was tested after the receipt, before recovery. Navigation while the
request was pending, cancelled/different-draft receipts, deleted-record recovery,
and coupled-field conflicts remain covered by local tests and were not separately
exercised in this hosted walkthrough. No hosted request was interrupted to
manufacture an uncertain outcome.

Independent invoice/credit posting retry acceptance remains the next workflow.
It must reuse the same command identity and prove one persisted outcome through
fresh reads. Independent employee authorization, broad UI rework, connection
architecture and reviewed fixture cleanup remain separate. Track 2/3 continue to
explain Track 1 without changing its accounting values.

Screenshots and the final full DOM report are retained in local acceptance
evidence. Database-wide canonical metadata equality was not independently audited
in this UI pass. These results establish the stated deployed editor behavior,
not completion of every remaining inventory workflow.
