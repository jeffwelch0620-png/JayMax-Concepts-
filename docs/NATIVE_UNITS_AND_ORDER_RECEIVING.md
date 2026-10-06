# Physical units and invoice-linked order receiving

This is the next local implementation step, after native source capture, actual
counts, invoice corrections and native recovery. It has not been enabled on a
hosted database. Supplied invoices are not imported; fixtures are invented.

## Accounting boundary

The purchase invoice records received quantities, received dates and verified food
amounts once. Purchase-order receiving links that recorded purchase to its order.
It does not post another purchase, add to legacy stock, change item prices or use
the order's estimated prices as food cost. Track 1 continues to use purchased-item
physical counts and explicit opening/closing values. Prep, waste and future Toast
sales remain independent explanations of that baseline.

## Reviewed physical conversions

Apply `20261005_native_order_receiving.sql` after the six earlier native migrations.
The three added private tables are `purchasing.unit_profiles`, `po_receipts` and
`po_receipt_lines`. Include them in native database recovery.

Invoice Master has a verified-unit setup for raw purchased items. Choose the fixed
physical inventory unit and enter the physical amount in one count container or
supplier purchase unit, with evidence and an explicit confirmation. Existing
catalog factors and pack sizes are references; they are not accepted automatically.
For example, a 4 x 5 lb case contains 20 lb regardless of how many recipe portions
it produces. Changing recipe portions must not rewrite physical inventory factors.

Each review creates an immutable revision against a snapshot of its item and,
where relevant, supplier product. Catalog changes mark affected suggestions stale.
Fresh profiles prefill physical count and invoice review forms, but those forms
still require their own confirmation. A prior count or posted invoice retains its
own conversion snapshot. A fixed inventory unit cannot be changed through profile
setup once assigned. Reconcile any existing mislabelled units before cutover;
there is no automatic legacy backfill or silent conversion of historical facts.
Missing catalog count or purchase units show source-specific setup issues; other
valid sources remain available. Fix the affected item setup before verification.

The compatibility item adapter preserves global item codes, supplier IDs, physical
units and count activation. New physical pack metadata does not use portion counts;
unknown or incompatible physical units fail explicitly. Item-save failures restore
the previous visible state when no newer update superseded that attempt.

## Receiving a sent order

1. Capture the supplier document in Invoice Master. Verify received-date food
   mappings, tax/fee/nonfood separation and totals, then post the purchase once.
2. In Purchase Orders, open the sent or partially received order's delivery review.
   Choose a current posted invoice from that location and supplier.
3. Match each purchased-food receipt line to the same inventory item on the order,
   or explicitly leave it as an off-order extra. At least one line must match.
4. Review the physical ordered/received quantities, overages and shortages. Explain
   the review, then preview and confirm the exact comparison.
5. Leave completion unchecked for another delivery. Explicitly finish the order
   only when no further deliveries are expected, including reviewed shortages.

The first delivery freezes the ordered quantity and verified purchase conversion.
Later deliveries compare cumulatively to that snapshot even if the supplier pack
changes. Each invoice is linked to at most one order; several invoices may serve
one order. One invoice cannot be split across orders in this initial version.
Extras are retained in the invoice and receipt history, with no second posting.
Order `received_at` is the completion confirmation time; invoice received dates
remain the accounting dates of record.

Received order details, receipt plans and receipt lines are sealed. A preview hash
guards against intervening invoice/order changes. Linking is transactional, scoped
to the location and idempotent. Interrupted saves retry the same request and key.
A confirmed conflict permits refreshing the changed source and reviewing again.
The old stock-addition and apply-order-prices routes are blocked in native mode.

## Corrections and remaining work

An invoice correction updates Track 1 through its existing reversal/replacement
workflow. It marks an older order comparison stale without blocking accounting.
The stale history remains visible; additional deliveries for that order are held
until reconciliation. A reviewed append-only replacement workflow is now available
locally; see [order receipt reconciliation](PO_RECEIPT_RECONCILIATION.md). Original
receipt history and frozen ordered quantities remain retained.

This measured path requires registered purchased-food items, supplier products and
verified purchase-unit profiles for all order lines. Mixed/nonfood orders and
unmapped lines require a further policy and workflow. Returns/credits continue in
Invoice Master. Other remaining cutover work includes staff/legacy entry routing,
unnumbered receipts, uncommon adjustments, production roles and managed-platform
restore verification. The Mongo-shaped compatibility layer remains elsewhere in
the app; it is not a second native purchase ledger, and this step does not remove
every Mongo reference or replace all legacy stock displays.

## API and validation

- `GET /api/pg/purchases/{store}/unit-setup`
- `POST .../unit-profiles` with a UUID `Idempotency-Key`
- `GET /api/pg/purchases/{store}/orders/{ref}/receipt-setup`
- `POST .../orders/{ref}/receipt-preview`
- `POST .../orders/{ref}/receipts` with a preview hash and UUID key

The native integration tests exercise real disposable PostgreSQL transactions,
partial deliveries, frozen pack conversions, duplicate/concurrent retries,
preview invalidation, store/supplier isolation, sealed history, closed-period
accounting invariance and native recovery of profiles, receipt plans and source
bytes. Frontend tests cover physical-unit preservation, review/confirmation,
interrupted retry, conflict refresh and replacement of the old receiving form.
Default feature flags remain disabled pending operational cutover work.
