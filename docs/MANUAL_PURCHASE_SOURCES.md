# Manual purchases and other suppliers

This build step extends native PostgreSQL purchase capture. It does not enable a
live import, apply a live migration or change Track 1's accounting rules.

## Workflow

1. Register the supplier in Vendor Master. Select its existing supplier ID; do not
   create a second supplier to work around a duplicate invoice.
2. Retain an original receipt, PDF, photo, unsupported CSV or other source using
   the **Other invoice / receipt source** upload option. The bytes are preserved
   exactly, with the existing location/hash and upload-retry protections. No OCR
   or automatic parsing is claimed for this upload option.
3. Enter the supplier's printed invoice/receipt number, document date, line
   extensions and stated total components. Add source evidence and attach retained
   files. If no document exists, the entered source record and its evidence note
   are the retained record; the reviewer is responsible for its completeness.
   A missing traceable invoice/receipt reference is held. Generating an internal
   reference for otherwise unnumbered purchases still needs an agreed policy.
4. Retain the entry for review. The complete submitted JSON is an immutable source
   file, including entered blanks, duplicate extra-field labels, leading zeroes,
   multiline text, addresses, unknown fields and attachment identifiers. Saving
   this record does **not** create any purchase/inventory facts.
5. Review every line using the same screen and rules as native vendor CSVs.
   Classify food, nonfood, tax and fee lines; confirm canonical inventory units,
   actual received quantities/conversions, the received date and USD currency.
   The supplier's document date never substitutes for a received date.
6. Post only a balanced, completely reviewed document. Posted source changes
   require the existing reversal/replacement preview and confirmation. Closed
   inventory periods must be reopened before affected facts can change.

The UI accepts the common invoice and line fields and ordered additional fields.
The API also accepts the checked-in typed header/party/line fields from
`backend/purchase_fields.json`. Additional fields remain queryable source JSON
until a future mapping is added; attached binary documents remain original bytes.
PDF/photo source content is not automatically extracted or indexed. A misspelled
typed field is retained but holds the projection; additional source labels do not
pretend to be mapped fields.
Numeric manual projections support up to 28 significant digits and 12 decimal
places. Unsupported precision remains in the original record and holds review.
Invoice reconciliation uses exact arithmetic with an 80-digit limit and holds an
overflow instead of rounding an unexplained difference away.

## Accounting and identity

Track 1 uses purchased items only, explicit opening/closing count values and the
received-date signed purchase ledger. Prep, waste and sales do not write this
ledger. A price-only credit changes cost without changing quantity; a physical
return changes quantity and cost on its verified movement date. Price credits
need a matching effective receipt from the same supplier/location/item/unit.

All printed source-line amounts must reconcile with the supplier's total. Header
tax and fee figures represent amounts **outside** those lines. Do not also add a
printed fee/tax line to the header component. Reviewers classify printed fee/tax
lines separately; neither header components nor nonfood/tax/fee lines enter food
cost. Blank components remain unknown. Invoice-level discounts and unexplained
adjustments are held pending an allocation/interpretation policy.

Supplier/location/document type/number and the source branch/customer/account
namespace are shared with CSV imports. PFG and US Foods manual entries need their
actual branch/customer identifiers to match their CSV identities. Other suppliers
can retain unstated branch/account/customer fields as blanks with an evidence
note; no placeholder supplier facts are invented. An already-posted number under
another namespace is held by application and existing database posting guards.
The same source body deduplicates, and an interrupted capture or posting retries
its exact request key/body. A changed body cannot reuse the old request key.

## Schema and recovery

Apply `migrations/20261005_manual_purchase_sources.sql` **after** the existing five
native purchasing/count/correction migrations in a disposable database first.
This sixth migration adds one private immutable attachment-link table and a
composite file/location key. Its foreign keys reject cross-location links. Its
insertion trigger requires each attachment to be named in the original retained
manual JSON; update/delete are forbidden. It creates no second purchase ledger.

The manual endpoints remain behind the existing disabled-by-default native
purchase flags and report `manualReady` only when the sixth migration exists.
Normal vendor CSV capture continues to work with the earlier schema. Public
clients receive no privileges on the new table/function.

Native full-database recovery automatically includes the new table, retained JSON,
original attachment bytes, source projections and postings. The synthetic tests
rehearse recovery and compare both source/API details and the physical-count report.
This remains local application recovery proof, not managed-platform certification.

## API

- `GET /api/pg/purchases/{store}/vendors`: active registered suppliers.
- `POST .../sources`: multipart original bytes, with an `Idempotency-Key` UUID.
- `POST .../manual-records`: string-valued source fields, ordered extra fields,
  attachment UUIDs, `verified_source: true`, and a nonblank evidence note; same
  header requirement. Raw source commits before projection, as in CSV capture.
- Existing file/source/row/document endpoints expose retained data. Existing
  posting, correction and count/report endpoints perform accounting work.

Source capture and projection are separate from posting. If projection or link
creation fails, the retained original remains available and retrying the unchanged
request completes that source step. A source-capture error never acknowledges an
inventory posting. The screen freezes interrupted submissions for exact retry.

## Remaining before accounting cutover

Verified physical-unit setup and invoice-linked purchase-order receiving are now
implemented locally; see [units and receiving](NATIVE_UNITS_AND_ORDER_RECEIVING.md).
Corrected-invoice order reconciliation is now implemented locally; see
[receipt reconciliation](PO_RECEIPT_RECONCILIATION.md). Complete mixed/nonfood orders and remaining
staff/manual legacy entry routing before cutover. Reconcile existing legacy
records if any appear before cutover. Agree on unnumbered-receipt references,
document-number reuse, discounts/uncommon adjustments and dependent-credit/return
correction bundles. Rehearse the intended deployment's recovery and role policy.
Toast and prep should then be added as independent explanation ledgers with
versioned recipe/item relationships, never as writers to Track 1.

The supplied PFG and US Foods invoices are not imported. Tests use invented source
records and attachments only. The original review and earlier milestone packages
remain preserved for a possible later GitHub PR.
