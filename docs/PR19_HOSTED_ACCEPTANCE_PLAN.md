# PR19 hosted editor acceptance plan

## Purpose and prerequisites

Verify the approved PR19 revision in the existing Render test app, using only
clearly labelled fictional Bert's records. Local tests and GitHub CI establish
code acceptance; the checks below establish deployed behavior. This plan does
not authorize a merge or claim hosted acceptance.

Before beginning, record the approved PR19 head, main merge commit, and both
Render deployment commits. Confirm the frontend and API are Live at the intended
revision. Stop on a failed deployment or mixed frontend/API revisions. Use two
owner-authorized browser tabs; these tests do not prove employee authorization.

Record the existing item identities and values, recipe identities and row counts,
and a fresh read-only October 1–8 Food Cost preview. The preserved control is
**$184 opening + $173 received food purchases − $145 closing = $212**. Current
prep explanation remains **84 observed depletion**, including **4 recorded
waste** and **80 service use or unrecorded loss**. Do not post receipts, counts,
batches, waste or sales as part of the editor checks.

## Item checks

Use `TEST ONLY Produce - UI 20261010`, control number `SB-002`, with restored
par **0**. Record its canonical item code from the saved catalog before editing.

1. Open the same item in both tabs. Tab A saves par 1. After Tab B refreshes its
   saved list, its retained par 2 must be refused. Confirm the saved par remains
   1 and Tab B's typed value remains 2.
2. In Tab B, choose **Reload latest and keep my changes**. A competing par change
   must be named and remain unsaved. Accept par 1 in the draft and repeat recovery;
   it may stage the reviewed value without writing until Save is clicked.
3. Repeat with independent changes: Tab A changes par while Tab B changes a
   labelled test note/name. Ordinary save must hold the changed item; explicit
   recovery must combine the independent changes and preserve canonical identity,
   saved supplier data and unknown conversions. Restore the original name and
   par afterward and read them back.
4. Open the item, then make an unrelated recipe save in the other tab. Saving
   the unchanged item must use the latest revision and preserve that recipe.

## Recipe checks

Create a dedicated **TEST ONLY Editor Acceptance** menu recipe using one portion
of the already labelled purchased protein item `WI-003`. Record its canonical
recipe ID, menu code and supplier/portion references. Keep it separate from the
verified prepared item and production recipe used by the prep control. Do not
change ingredients or yield on an existing verified production recipe.

1. Open the dedicated recipe in both tabs. Tab A changes its test price; Tab B
   changes its production note. After refresh, ordinary save must hold Tab B's
   retained copy. Explicit recovery must retain the newer price and local note;
   Save must update that same recipe ID.
2. Make competing price changes. Recovery must name the conflict, retain typing
   and leave the saved recipe unchanged until reviewed.
3. Make an unrelated item save while the recipe is open. Saving an unchanged
   recipe must preserve the latest item list and use the latest revision.
4. Confirm incomplete planning costs remain unknown and do not alter Track 1.
   Restore the recorded starting recipe fields after testing.

## Creation receipt checks

These checks concern a **confirmed** creation receipt arriving after newer
typing. Keep uncertain network outcomes in the separate retry acceptance record.

Use a dedicated TEST ONLY purchased item with complete fictional pack metadata,
and count, ordering and sales participation disabled. Use a dedicated TEST ONLY
menu recipe for the recipe case. Record row counts before each creation.

1. Submit the new record, then type a different labelled name while its save is
   still pending, if the real network delay allows this. Do not simulate timing
   by interrupting a hosted request. If the response is too fast, record timing
   as unexercised; local delayed-receipt tests are separate evidence.
2. After a confirmed receipt, the later typing must remain. Save must hold and
   require **Reload latest and keep my changes**, rather than append another row.
3. Recovery must read canonical fields, including assigned menu code and supplier
   identities/conversions. After reviewed Save, exactly one newly created record
   remains, using the same canonical ID/control number with the later name.
4. Where timing permits, repeat while navigating away and returning. A receipt
   must not attach its identity to a cancelled draft or a different loaded recipe.
5. Keep coupled pack/supplier and ingredient/yield changes held for review;
   do not force past a conflict or derive a conversion during this check.

## Server conflict and posting retry

If a real stale revision response occurs, record its error, retained draft and
fresh read. A changed target must refuse another write; an unchanged target may
retry at the reviewed current revision. Do not describe an editor's client-side
refusal as a proven server 409. Local tests already cover both paths.

Independent invoice/credit posting retry acceptance remains a separate workflow:
reuse the same command identity, confirm one persisted outcome through fresh
reads, and prove the unchanged $212 control. Retrying with a new command identity
does not establish idempotency. Do not interrupt a hosted write to manufacture
an ambiguous outcome without a separately reviewed test procedure.

## Record and close out

| Check | Result to record |
| --- | --- |
| Revision | Approved head, merged head, frontend and API deployment commits |
| Scope | Bert's, owner session, fictional item and recipe identities |
| Conflict | Changed fields, retained values, client refusal or server response |
| Recovery | Read revision, staged fields, explicit save receipt and fresh read |
| Creation | Before/after row counts, canonical ID/control number and assigned fields |
| Restoration | Original item par/name and recipe fields restored and read back |
| Accounting | Final read-only Food Cost preview remains $212 |
| Limits | Timing not exercised, session limits, or any failed/pending check |

Preserve the existing count, prep and reporting-period history. Retain all test
records as labelled build evidence until their reviewed cleanup before
operational use. Record hosted results separately from local tests and CI; a
partial walkthrough does not close the remaining posting retry or authentication
workflows. Broad UI and deployment/connection decisions remain deferred.
