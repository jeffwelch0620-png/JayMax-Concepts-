# PR60 review amendments — D1 / N1 / N2

This amendment changes documentation and non-executable design only. No runtime
metric, SQL, grant, credential, account, provider or connection change is made.
All hosted work remains held. PR60 stays draft and requires fresh exact-head CI,
independent review and separate owner merge approval.

| Item | Disposition |
| --- | --- |
| D1 | Public plans/index/review notes and the earlier current workflow reference use package-level credential-retirement wording. Detailed scope, evidence and review period remain in an access-verified owner record, outside the public repository and shared progress summaries. Current PR description/downloads are reconciled. No sharing permissions or Git history are rewritten. |
| N1 | P1 and both P2 rows use one rule: 600 s work + 15 s cleanup + 600 s restoration + 45 s closing margin = **1,260 s**, or **1,215 s plus 45 s closure**. Apply starts by relative 39:00 in the 60-minute window. |
| N2 | Add future R1 audit-failure visibility: bounded process counter/equivalent alert, authenticated authorized operator readiness, process/reset context, no anonymous-health or sensitive-data change. Post-cutover proof remains one controlled request producing exactly one attributable audit row. No runtime implementation is included. |

The three original Git archives remain byte-identical to accepted c3b429a, with
their dated text intact. New wording does not revoke earlier copies or replace
the separately approved S2a process. Restricted record addresses and operational
credential details are excluded from this public review record.

Validation: [amendment receipt](PR60_REVIEW_VALIDATION_20261023.json). The earlier
[local document receipt](PAR_SECURITY_DOCUMENT_VALIDATION_20261023.json) and
19b1636 CI are retained as dated evidence, not fresh checks for this amendment.
