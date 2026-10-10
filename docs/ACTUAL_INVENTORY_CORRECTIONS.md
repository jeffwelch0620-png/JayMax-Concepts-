# Reopening actual-inventory periods without rewriting history

This local follow-on implements corrected physical counts, late received-date
purchase postings and linked supplier price credits in native Track 1. Purchased
items only and explicit total count values remain the confirmed policies. Prep,
waste explanations and sales do not write actual inventory or Food Cost.

All existing flags remain disabled by default. No real supplier sample is loaded,
no operational migration is applied and no GitHub write is made by this step.

## Review and replace a closed period

1. Open the actual-inventory dashboard and expand an active closed report. Choose
   **Review correction / reopening**. The preview identifies that report and all
   later active closed reports at the same store, with their original totals.
2. Record the correction reason and confirm the entire affected chain. The
   reason, actor, timestamp, original report fingerprints and affected IDs are
   retained in an immutable reopening event. A stale preview cannot reopen a
   different chain. Repeated submissions return the same recorded event.
3. In Enter Counts, append linked recounts as needed. They retain the original
   scope, physical date and before/after receipt boundary, with new confirmed
   quantities, conversions, total values and evidence. Original counts remain.
   Recounts cannot fork: correct the latest replacement if a further correction
   is needed. Historic scopes are returned with the count for recount entry.
4. Post a held late invoice or a linked supplier credit through the native
   purchase review screen, if relevant. Received dates remain unchanged. Original
   purchase facts are never edited, removed or copied into a replacement ledger.
5. Preview and close each replacement report, oldest first. Each identifies the
   original reopened closure it replaces. Its count references must be the
   original counts or their linked recount descendants. Count continuity and
   frozen explicit values still carry into the next period.

Reopening a period reopens its entire later active suffix because a changed
closing count affects the next opening count. If correcting an opening count
shared with an earlier active period, reopen that earlier period first. The
system blocks a recount while any active closed period still references it.

A reopened report is historical and awaits replacement. The dashboard labels
these reports separately from active closed reports and shows the oldest
unresolved interval. New periods cannot be closed ahead of unresolved reopened
periods. Reclosing an unchanged count pair is supported for late purchases;
the replacement is a new report, not a duplicate of the preserved original.

An active replacement can itself be reopened later. Every generation remains
linked to its predecessor. Only active closures should feed an eventual rollup;
summing all historical closures would count earlier versions more than once.

## What happens to actual Food Cost

Example: the original first period has $60 opening value, $40 received food
purchases and $45 closing value: **$55 Food Cost**. The next period opens at $45
and closes at $30, with no purchases: **$15 Food Cost**.

Correcting the shared middle count to $30 gives **$70** in the first period and
**$0** in the second. The combined $70 is unchanged; the corrected count moves
the period allocation. Both original reports retain $55/$15 in history. A newly
posted $40 late invoice adds $40 to the corrected chain; a linked $5 price credit
reduces that by $5 without inventing physical movement.

Totals change only through confirmed count facts and additional actual purchase
facts. The process never subtracts prep, sales or waste again from count-based
depletion, and never recomputes count values from current item or supplier prices.

## Storage and concurrency

Apply the versioned migrations in order to a disposable database:

1. `20261004_native_purchase_import.sql`
2. `20261004_actual_inventory_counts.sql`
3. `20261004_actual_inventory_corrections.sql`
4. `20261004_actual_inventory_scope_bridges.sql`

The third migration preserves existing counts and closed report JSON. It adds
`supersedes_closure_id`, append-only `reopen_events`, `active_period_closures`
and `pending_reclosures` views. It replaces the initial no-reclosing constraint
with single-predecessor replacement and active-period overlap/continuity guards.
It refuses an existing forked recount history; inspect such data before migration.

Reopening, recounts, purchase posting and closing lock the same store revision
row. Database guards enforce the whole same-store suffix and oldest-first
replacement, preserving period boundaries and count ancestry. A concurrent
new close either wins first and makes the reopen preview stale, or reopening
wins first and holds the new close. Neither outcome can omit an affected period.

Purchase guards apply to active closed intervals. Reopening permits late native
posting in the affected windows; reclosing seals them again. The separate legacy
`public.reporting_periods` guard remains in force. Reopening this native chain
does not reopen a legacy period or reconcile legacy purchases automatically.

Reports continue to use immutable source purchase facts, reviewed conversions
and explicit values. Reopening does not replay purchases. Original count children
remain sealed even after reopening; correction is a new linked snapshot. A retry
of an earlier close returns its persisted reference and identifies it as
historical if it has since been reopened, preventing a false current-close claim.

Existing manager/owner store authorization protects reopening and recounts.
Readonly and staff cannot use the write or correction-preview routes. Login
redesign is outside this step. Direct database-owner actions remain subject to
the existing deployment least-privilege gate.

## Limits of this step

- Reopening covers the native accounting report and permits late invoices,
  linked supplier price credits and same-boundary count corrections.
- The fifth migration adds reviewed posted-invoice reversals/remapping, balanced
  reissued documents, classification and received-date corrections. See
  `POSTED_INVOICE_CORRECTIONS.md`. Reopening alone never edits posted facts;
  the complete reversal and replacement require a separate reviewed transaction.
- Count-date/timing changes and nonzero historical scope reconciliation remain
  unavailable. Reviewed zero-balance scope handoffs are implemented separately
  in `ACTUAL_INVENTORY_SCOPE_HANDOFFS.md`. Reopening their anchor invalidates the
  old handoff and requires a reviewed rebuild after the old-period replacement.
- Manual/other-vendor capture, operational/staff/PO unit adapters, legacy
  reconciliation and deployment/backup checks still precede operational use.
- A complete native backup must retain both private schemas, reopening events,
  report generations and source bytes. The legacy in-app backup is insufficient.

## Verification

Use the loopback disposable test database specified in `ACTUAL_INVENTORY.md`:

```text
python -m pytest --noconftest backend/tests/test_native_purchases.py backend/tests/test_actual_inventory.py backend/tests/test_actual_inventory_corrections.py backend/tests/test_actual_inventory_scope_bridges.py -q
npm test -- --watchAll=false --runInBand PurchaseImportsTab.test.js ActualInventoryTab.test.js
npm run build
```

Correction checks use invented data and cover shared-count propagation, unchanged
count-pair replacement after late invoices/credits, retry concurrency, stale
previews, preserved reports, history generations, store/role boundaries, recount
lineage, partial-suffix rejection, close/reopen races, delayed close retries and
upgrading a database with an already closed period.
