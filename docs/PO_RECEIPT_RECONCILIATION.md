# Reconcile an order comparison after an invoice correction

This local implementation follows native physical units and invoice-linked order
receiving. It does not import operational invoices, migrate a live database or
enable default feature flags. Apply `20261005_po_receipt_reconciliation.sql` after
the seven earlier native migrations.

## What reconciliation changes

Invoice corrections already adjust Track 1 through immutable purchase reversals
and replacements. This workflow updates the linked order comparison independently.
It never posts another purchase, writes a count, changes legacy stock, adopts an
order price as food cost or reopens an accounting period.

For example, an order expects 80 lb. Its original delivery was recorded as 40 lb,
then the invoice was corrected to 60 lb. Reconciliation retains the original
40 lb review and appends a reviewed 60 lb replacement. The next 40 lb delivery
compares against 100 lb received, not 140 lb. The ordered quantity and original
verified conversion remain frozen at the first delivery.

## Review process

1. Complete the invoice correction in Invoice Master. The affected order shows
   that its linked comparison is stale.
2. Open **Reconcile corrected invoice** for that delivery, including completed
   orders. The screen loads the current posted version of the same invoice.
3. Match every current purchased-food receipt to the same frozen order item/unit,
   or explicitly retain it as an off-order extra. Earlier matches are not accepted
   automatically. Explain the corrected receipt and review its variances.
4. Preview the old/current delivery amounts, cumulative received quantity, frozen
   ordered quantity and resulting shortage or overage. Confirm the exact review.
5. Reconcile any other stale linked invoices before linking another delivery.

If a correction reclassifies all receipts as nonfood, the screen explicitly warns
that the order comparison will lose its earlier food delivery quantity. An empty
reviewed food-line list is valid in this case; the original invoice and delivery
history remain retained. It can also retain every corrected food line as an
off-order extra when none belongs to the frozen order anymore. Neither case
changes Track 1 through this workflow.

The order's completion status and completion timestamp remain unchanged. This
step does not automatically reopen completed orders or move an invoice between
orders. Separate returns/credits, mixed/nonfood order matching and invoice splits
still need their respective workflows.

## History, conflict and retry safeguards

`purchasing.po_receipts` continues to reserve each invoice for one order. New
`po_receipt_reconciliations` and `po_receipt_reconciliation_lines` retain a sealed
revision chain. `effective_po_receipts` selects only the latest revision for each
original link. Receiving and staleness checks use that effective review; they do
not sum old and replacement generations.

Each revision records the reviewer, confirmation time, reason, prior revision,
current invoice version/correction, exact source-line mappings and comparison
snapshot. The original receipt is not overwritten. Database constraints prevent
branching chains, cross-order links, partial line saves, child-row additions after
commit and history edits/deletes. Nonempty current food receipts must be retained
exactly once, even when they are extras.

Preview hashes include all linked effective review states. A concurrent invoice
correction, another reconciliation or a changed order status invalidates the
preview. Confirmation locks the invoice identity, store, order and original
receipt, then appends the revision atomically. A duplicate request with the same
UUID key/body returns its already saved revision, even after later corrections.
Different bodies under the same key are rejected.

The UI freezes an interrupted save for an exact retry and requires a complete
server acknowledgement before announcing success. A confirmed conflict permits
refreshing the current source and a fresh review. A failed list refresh remains
distinct from a successful reconciliation.

## API and verification

- `GET /api/pg/purchases/{store}/orders/{ref}/receipts/{receipt}/reconciliation-setup`
- `POST .../reconciliation-preview`
- `POST .../reconciliations`, with an exact preview hash and UUID `Idempotency-Key`

Reconciliation endpoints require the eighth migration. Earlier schema versions
retain the original receiving behavior and expose no reconciliation button.
Existing native backup includes the new tables/view automatically; recovery must
still be rehearsed on the intended deployment platform before operational use.

Invented PostgreSQL tests verify partial/completed orders, current quantities,
successive and competing revisions, exact retry, stale parallel previews, supplier
reissued source lines, zero-food corrections, invoice/order/location isolation,
sealed history, closed-period accounting invariance and full native recovery.
Frontend interaction tests verify fresh line review, preview/confirmation, safe
retry, rejected acknowledgements, conflict refresh, empty food receipts, visible
history and successful saves followed by list-refresh failures.

Remaining accounting cutover work includes staff/legacy purchase entry, mixed or
unmapped orders, unnumbered receipts and uncommon adjustments, production roles,
legacy reconciliation and managed-platform recovery. Prep/waste and Toast remain
independent explanation ledgers. The original code review and baseline snapshot
are preserved for a possible later PR; this local step does not create one.
