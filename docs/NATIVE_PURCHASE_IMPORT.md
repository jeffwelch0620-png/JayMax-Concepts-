# Native PostgreSQL purchase foundation

Review branch: `codex/postgres-invoice-capture`, based on main
`1a5e97243009a922d38596d6559c6d9be7f6b5f3` (2026-10-04).

This is a disabled-by-default build step, not an operational cutover. It provides
original-file capture, invoice review and initial purchase posting in PostgreSQL.
The original data-integrity review and baseline snapshot remain separate evidence;
this change does not resolve the entire review or retire all legacy adapters.
The follow-on [actual inventory step](ACTUAL_INVENTORY.md) now connects these
purchase facts to purchased-item physical counts and explicit count values.
Reviewed zero-balance item-list transitions are described in
`ACTUAL_INVENTORY_SCOPE_HANDOFFS.md`; they preserve purchase and count history.

## Accounting contract

- Track 1 remains physical opening inventory + net purchases - physical closing
  inventory. Received date is the date of record for receipts. Supplier invoice
  date, ordered date and shipped date remain separate source facts.
- Prep, waste and sales explain actual usage. This purchase path never writes
  prep logs, prep stock, sales usage, recipe portions or estimated inventory.
- A fixed inventory unit belongs to the store/item. Recipe yield and portion
  units must not redefine it. Quantities, conversion factors and supplier line
  extensions are exact decimals; no binary floating-point costing is used.
- Tax and fees remain retained on the invoice, outside food purchase amounts.
  Nonfood, tax and fee line dispositions have zero food-inventory effects.
- Only reviewed USD supplier profiles are supported for initial posting. A reviewer
  explicitly confirms USD. The supplier files do not state currency in their
  mapped headers; USD is a profile assumption, not a claimed source field.
- Physical returns require negative actual quantities and their confirmed return
  date. Price-only credits have zero quantity, a confirmed inventory record date,
  and a link to an existing receipt for the same vendor, store, item and base unit.
  Active closed periods block late postings. Reviewed native reopening permits
  them, followed by linked replacement reports; see `ACTUAL_INVENTORY_CORRECTIONS.md`.

## Capture and review

`purchasing.import_files` retains exact original bytes and a database-checked
SHA-256, even if parsing crashes afterwards. A separate upload attempt records
the filename, actor and request key. Re-uploading identical bytes at a store
reuses the captured file. Original files are limited to 12 MB per request.

Positional header and cell arrays retain blanks, duplicate headers, unknown
fields, leading zeros and unequal row widths. The checked-in field contract
projects all 97 column positions from the supplied PFG and US Foods formats into
typed document, party and line facts. Unknown fields remain accessible through
raw-source inspection and exact original-file download. An unsupported format is
captured and held; it is never interpreted as a valid purchase.

Stable document fingerprints preserve repeated SKU rows and reuse an identical
invoice across reordered/overlapping exports. Changed source content appends a
new immutable version. A superseded unposted version cannot post. A changed
version of an already posted invoice is held for linked correction review.
The fifth migration adds the reviewed reversal/replacement workflow described in
[POSTED_INVOICE_CORRECTIONS.md](POSTED_INVOICE_CORRECTIONS.md). Initial posting
still rejects a second batch for the same invoice identity.
Account/branch changes cannot bypass an already posted invoice number without
identity review. No repeated invoice total is added once per row.

Reviewers explicitly confirm every line's classification, item, actual quantity,
quantity unit, conversion and note. Shipped quantities are displayed as initial
suggestions; they are not accepted as actual quantities until reviewed. SKU
matches are suggestions, not automatic financial decisions. Source descriptions,
packs and historical amounts are frozen independently of editable item setup.

Supplier totals must reconcile exactly. Missing totals/components, conflicting
repeated metadata, malformed fields, nonzero invoice-level discounts, unexplained
differences and unverified US Foods delivery adjustments remain held. The observed
US Foods $1.23 difference is not written off or relabeled as tax/fees.

## Atomic posting and duplicate protection

The API records mappings, fixed units, reconciliation, one purchase batch and all
batch lines in one transaction. A failed line rolls back every posting change;
the earlier source capture survives. The API verifies the saved line count before
commit and returns a fresh posted-document read-back before the UI claims success.

Upload and post requests require UUID request keys. Repeating an identical post
with its original key returns the same batch. Reusing that key with a changed
review is rejected. A unique initial batch per document and shared invoice locks
prevent concurrent duplicates. Frozen mapping IDs preserve the interpretation
used by each posted line, even if a later mapping version is appended.

When enabled, the old PostgreSQL invoice POST endpoint returns 410. The migration
also guards the legacy invoice table against re-entering an invoice already
posted natively, including an older app build. Existing legacy invoices block
native posting until reconciled. Source facts and postings reject update/delete.
Manager/owner write access, read-only access and store boundaries are checked
explicitly using the existing signed-token contract; login is not redesigned.

## Disposable setup and validation

1. Provision an empty **disposable** PostgreSQL database with the app's public
   schema. `supabase/schema.sql` is a dated reference suitable for local tests,
   not a migration to apply over a running database.
2. Apply `migrations/20261004_native_purchase_import.sql` explicitly. This is
   transactional, one-time DDL; no startup or request runs migrations.
3. Set backend `USE_PG=true`, `PURCHASE_IMPORT_ENABLED=true`, and a test-only
   `DATABASE_URL`, preserving the existing authentication configuration.
4. Build the frontend with `REACT_APP_NATIVE_PURCHASES=true` and the test backend
   URL. Leave both purchase flags false in the operational application.
5. Run the synthetic integration tests with `NATIVE_PURCHASE_TEST_DSN` pointing
   to loopback and a `native_purchase_test_*` control database. The test role must
   be able to create/drop test databases. Tests create a fresh database per case,
   load the complete public snapshot plus migration, and remove each database.

```text
python -m pytest --noconftest backend/tests/test_native_purchases.py -q
npm test -- --watchAll=false --runInBand PurchaseImportsTab.test.js
npm run build
```

Tests refuse non-loopback/non-test database targets and use invented supplier
rows only. The two supplied original invoice files are not loaded into a database,
checked into source, or included in the code review package. Source fixtures retain
their column names but contain no supplier/customer operational values.

## Remaining cutover gates

The new food purchase history stays separate from the legacy `purchases` adapter.
When actual-inventory flags are enabled, the new dashboard uses these purchase
facts with physical purchased-item counts and explicitly confirmed values. The
old report calculators still mix units/current prices and are not the native
accounting path. When actual-inventory flags are disabled, the purchase review
screen states that the accounting connection is awaiting enablement.

Before operational enablement:

1. Confirm each store's purchased-food scope, physical locations and count
   conversions. Prepared items are excluded by the user's confirmed policy.
2. Verify explicit count values and before/after receipt-day boundaries. A count
   between deliveries needs additional cutoff precision before period close.
3. Native period reopening and linked count/report replacements are implemented.
   Posted-invoice reversals/replacements are now implemented. Specify
   discount allocation, uncommon adjustments and verified invoice-number reuse.
4. Reconcile/backfill any legacy purchases and verify operational entry adapters.
   Native purchase-entry and staff handoff boundaries now reject old purchase
   saves and, when actual inventory is enabled, old purchased-item count saves.
   The history tab reads signed native food entries. See
   [entry boundaries](NATIVE_ENTRY_BOUNDARIES.md). Stock/owner/AI readers and
   manual order planning now use native facts; see
   [operating views](NATIVE_OPERATING_VIEWS.md). Scoped staff quantity drafts and
   explicit manager acceptance are implemented; see
   [staff count drafts](STAFF_COUNT_DRAFTS.md). Independent consumption explanations
   remain pending.
   Native manual-entry and other-supplier source review now share this ledger;
   see [manual purchase sources](MANUAL_PURCHASE_SOURCES.md). Unnumbered receipts
   and uncommon adjustments still need an agreed policy before accounting cutover.
   Physical-unit setup and invoice-linked order receiving are now implemented;
   see [units and receiving](NATIVE_UNITS_AND_ORDER_RECEIVING.md) for their limits.
5. Verify the actual deployment schema, service-role privileges, backup coverage
   (both private `purchasing` and `actual_inventory` schemas must be included)
   and restore in isolation.
   Public clients receive no schema/table/function privileges. The database owner
   can bypass application workflow by inserting directly; production role design
   remains a deployment gate, not a claimed completed login fix.
6. Connect prep and Toast through separate explanation ledgers and versioned item /
   recipe mappings. Neither may write actual purchase/count facts.

The current public period/state workflow must continue to take its store revision
lock when closing a period. Direct administrative period writes are outside this
API's concurrency guarantee. No live migration, real invoice import, GitHub push,
pull request or deployment accompanies this local review branch.
## Separate prep definition foundation

The latest local Track 2 step is [PREP_WASTE_AND_COUNTS.md](PREP_WASTE_AND_COUNTS.md):
standalone measured waste and complete physical prep observations, with no actual
purchase/count/value or Food Cost writeback. It is also disabled by default.

The following production milestone is the separate quantity-only
[PREP_BATCH_JOURNAL.md](PREP_BATCH_JOURNAL.md), also disabled by default. It explains
gross prep inputs and usable outputs without purchase/count or Food Cost writes.

The next local implementation is documented in [PREP_MAPPING_FOUNDATION.md](PREP_MAPPING_FOUNDATION.md).
It adds reviewed prepared identities, physical unit/recipe versions and preserved
legacy crosswalks behind disabled-by-default flags. It does not post production,
waste, sales, purchases or actual counts. Operational prep writer cutover remains
a later gate.
