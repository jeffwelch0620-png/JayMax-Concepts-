# Exact invoice and credit replay acceptance

The four original TEST ONLY Bert's postings replay correctly against the existing
hosted Supabase database. **Sixteen exact retries return their original posting
batches**, and **eight conflicting retries return HTTP 409 in the in-process
route harness**. All 79 protected purchasing, Actual Inventory, prep and store
state tables retain their original row counts and whole-row hashes. The complete
accounting report is unchanged: **$184 opening + $173 received food purchases
- $145 closing = $212 Actual Food Cost**.

## Method and evidence boundary

The reviewed `purchase_api.py` and `actual_inventory_api.py` are unchanged from
merged revision `b2f529f`. Their real FastAPI purchase router runs locally in an
ASGI harness against hosted PostgreSQL using the retained restricted inventory
LOGIN. Every pool acquisition verifies both authenticated and current database
identities; no SET ROLE or administrator fallback is used for route execution.
Application authorization is a fixture-only harness callback. These results do
not establish independent employee authorization, deployed Render HTTP replay,
or recovery after a lost browser response.

The request bodies were reconstructed from the original mappings. Each body
must reproduce the stored request fingerprint exactly before execution. The
original command key, document version and batch identity are retained. No
vendor sample file is imported, no replacement command is created, and no new
purchase, credit, count, prep or reporting-period outcome is posted.

Each fixture receives two concurrent exact retries through the first restricted
pool and another two through a newly authenticated second pool. Responses must
return the original batch ID and posted document version. A changed review note
with the original key, and the original body with a different key, each require
409 refusal rather than another posting.

Every route pool acquisition runs inside an outer rollback guard. Successful
acquisitions compare posting batches/lines, mappings, reconciliation checks,
item bases and store state **before rollback**. This prevents rollback from
concealing an unexpected replay mutation. All **56 pre-rollback comparisons**
pass. Two independent read-only administrator connections compare all 79
protected tables before and after the complete scenario, along with migration
ledger identities and the full Food Cost report.

The first preparation attempt held before any replay because the restricted
runtime login cannot read the migration ledger. That is the intended permission
boundary. Independent baseline/postflight reads use an administrator connection
explicitly restricted to read-only transactions. Route execution remains under
the ordinary inventory login; no permissions or connection settings changed.

## Original fixture outcomes

| Document | Original posting batch | Lines | Outcome retained |
| --- | --- | --- | --- |
| TEST-ONLY-PFG-20261010-03 | 255d8fda-d967-4ba6-91d8-9e0465fc4cd9 | 2 | 40 lb protein / $140 and 100 each appetizers / $25 |
| TEST-ONLY-USFOODS-20261010-04 | 6dfd17b8-b5b7-4bf5-9014-ac6ac5ba9c78 | 1 | 20 lb produce / $50 |
| TEST-ONLY-PFG-RETURN-20261010-05 | c95fe8cf-de7c-4013-ac5f-355fd509a1ad | 1 | Physical return: -10 lb / -$35 |
| TEST-ONLY-PFG-PRICECREDIT-20261010-06 | a1bb1165-ac62-4602-b22c-a05892393fa8 | 1 | Linked price credit: zero quantity / -$7 |

Each document retains its one original batch and line graph. Received dates,
explicit physical values, price-credit links, closed-period history and prep
history remain unchanged. Separate source taxes and fees remain outside food
purchase cost. Prep and future sales continue to explain the accounting track
without replacing it.

A third, independently authenticated read-only inventory connection confirmed
one persisted batch per document, with 2/1/1/1 posting lines and matching food
facts. All 79 protected table fingerprints still match. That readback is retained
as `posting-retry-readback-20261011T022813736112Z.json`.

The safe receipt is `posting-retry-20261011T022436922592Z.json`, captured during
the October 10 evening session in America/New_York (October 11 UTC). It records
exact fixture identities, request fingerprint verification, all replay/refusal
results, source hashes, table fingerprints and before/after accounting reports.
The read-only preparation and initial held receipt are retained separately.
Private credentials remain outside Git and shared artifacts.

## Remaining work

Exact replay of an already persisted outcome is established at the API/database
boundary. Concurrent *first* posting, Render HTTP transport, expired sessions
and response-loss/browser recovery are not separately exercised in this run.
No hosted request was interrupted to manufacture uncertainty. Those scenarios
remain distinct from the completed replay checks and existing local tests.

Next, characterize the intermittent editor fresh-read refusals with a controlled
local regression before selecting a fix. Source review identifies overlapping
poll/explicit reads as a possible cause: a superseded `refresh()` can return no
data even when another read succeeds. This is a hypothesis, not a confirmed
cause of the hosted symptom. Preserve revision, scope and pending-write guards.
The missing-price display belongs to deferred UI work. Independent employee
authorization, UI rework, connection architecture and reviewed fictional
fixture cleanup remain separate workflows.
