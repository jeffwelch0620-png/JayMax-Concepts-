# Deployed item setup and fictional acceptance checkpoint

October 10, 2026. The user selected **Bert's with clearly labelled fictional
items and count history** for the next live walkthrough. These are build controls,
not real opening stock or operational vendor imports. Broad UI redesign belongs
in a later workflow; functional save and review blockers are corrected here.

## Completed live source checkpoint

The existing owner session retained two labelled manual sources at Bert's.
`TEST-ONLY-UI-20261010-01` remains held because its source amounts and PFG identity
are incomplete. Missing amounts remain unknown; duplicate extra-field labels
and an empty value survive. Re-entering the identical source with a new request
key kept one document version. Full reload retained both source files.

`TEST-ONLY-UI-20261010-02` contains a fictional $25 nonfood line, separate $3 fee
and $5 tax. Posting and a reviewed nonfood-to-fee correction retained the original
and replacement dispositions. Neither contributed food quantity or Food Cost.
Read-only database checks corroborated one posting, one correction and unchanged
source fingerprints. Owner-session location switching hid these sources at
Rudd's and restored them at Bert's; this does not accept staff permissions.

The separate hosted rollback rehearsal matched **$212 Actual Food Cost** and
restored all 118 application-table fingerprints. That backend result does not
substitute for a completed deployed food/count/close/reopen walkthrough.

## Item setup blockers and local correction

The attempted item `TEST ONLY Protein - UI 20261010` was not confirmed. A read-only
database check found no matching saved item. No count scope or count history was
created. Two defects were reproduced locally before the fixes:

1. Three sibling panels shared a restaurant-only React key. Typing five name
   changes produced six physical-count panels and repeated reads; the live DOM
   had 14 panels. Each panel now has a distinct key that still remounts when the
   restaurant changes. The regression checks one panel and one initial read,
   then one fresh read for the second restaurant.
2. Item change comparison normalized every existing supplier row. An explicitly
   unknown purchase conversion was treated as absent and recalculated, blocking
   an unrelated item save when its pack metadata was missing. A read-only check
   confirmed that the existing `berts_OF-001-unconfirmed` SKU has a null factor,
   pack count and pack quantity. The adapter now preserves explicit null and
   positive stored factors; it derives a factor only when the field is undefined.
   An ordinary edit cannot turn an unconfirmed conversion into an inferred one.
   New UI supplier rows with empty packs still fail physical validation.

The changed item route retains its reviewed revision, sends only the new or
edited definitions and leaves unrelated unconfirmed supplier rows untouched.
No schema migration, connection change or authentication redesign is included.

## Validation and remaining acceptance

The focused adapter/setup checks pass **36 tests in three suites**, including
the new save and panel regressions. All **509 frontend tests in 62 suites pass**
with the native build feature profile. The optimized production build passes
with the two existing hook-dependency warnings in PurchaseOrdersTab and StaffTab.
Before-fix failures are retained in local
review evidence; one initial new-row fixture used null instead of the UI's empty
string and was corrected before the passing run.

The fixes are local on `codex/native-item-setup-save-integrity`. No new PR, merge
or deployment has occurred at this checkpoint. The live session subsequently
expired; the existing browser-filled owner sign-in recovered it. The test app
is open again, with no new count scope or count history configured.

**Publication update:** After the user approved draft publication, the local fix
commit `da9a917` was pushed as
[draft PR18](https://github.com/jeffwelch0620-png/JayMax-Concepts-/pull/18).
It remains unmerged; the deployed frontend has not received these fixes.

Next, publish/review the small fix PR and authorize its merge into the existing
Render test deployment. Then repeat the failed save through the deployed UI,
establish the labelled three-item purchased-inventory test scope, and complete
opening/closing counts with explicit values, received purchases, return/credit,
period close/reopening, prep explanations, staff submissions and manager review.
Independent posting retries and concurrent edits remain open. Track 1 stays
independent of prep/waste and future sales explanations. Operational mappings,
final connection/access architecture and broader UI rework remain later work.

Progress and editable controls are maintained under JMAX in
[Inventory App Integration Workflow](https://chatgpt.com/space/page_1e9f0baababc8191a6f628ce4799af7a)
and its linked accounting-control page.
