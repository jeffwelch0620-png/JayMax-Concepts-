# Purchase entry and physical-count boundaries

Local build milestone, October 5, 2026. Default native purchase/actual-inventory
flags remain disabled. No live migration, invoice import, deployment or PR.

## Purchase entry

Invoice Master is the common entry point for original vendor CSV capture, retained
attachments and manually entered supplier sources. It keeps all source fields,
including unmapped fields, separately from the manager's posting decision. Capture
does not add accounting purchases, legacy stock or supplier catalog prices.

The exported `InvoicesTab` now routes to that screen whenever native purchases are
enabled. A missing restaurant shows a handoff message rather than a legacy form.
The app supplies the restaurant explicitly and remounts on a location change.

The purchase-snapshot adapter rejects every native-mode save before reading old
invoices or making writes. Empty inputs and already-known invoice arrays cannot
silently announce success. The direct public-invoice client also rejects. Backend
public-invoice and purchase-state writes return 410. Existing native-mode PO
receiving and price-application guards continue to reject legacy stock additions.

These are routing safeguards; they do not migrate or delete old public invoices.
When native flags are off, the earlier workflows remain available. Frontend and
backend flags must agree for cutover: an older client reaching an enabled backend
gets a rejected legacy save, not a second purchase ledger.

## Staff handoff and counts

There was no staff purchase-entry form to migrate. The staff portal now directs
invoices, receipts and credits to the manager's Invoice Master. Shared-PIN staff
receive no new purchase capture, posting or actual-inventory permissions. Source
entry remains restricted to the existing manager/owner purchasing workflow.

When actual inventory is enabled, the older staff count form is replaced with a
handoff to the manager's Actual Inventory screen. The client and backend reject
old purchased-item count writes, including the manager's old count submission
route, before they can change legacy on-hand quantities. The old staff count read
route is also held. With purchase review enabled but actual inventory disabled,
the previous count workflow remains available.

Staff quantity drafts now use manager-issued native scopes and verified unit
profiles. Counter/time/evidence remain separate from manager values and final
acceptance; see [staff count drafts](STAFF_COUNT_DRAFTS.md). The old count routes
remain held in actual mode. Prep count and waste ledgers remain a separate Track 2
design. Existing prep and task screens continue to use their existing APIs.

## Posted purchase history

In native purchase mode the app's history tab reads the native signed food ledger.
It displays received/inventory date, supplier, invoice, purchased item, quantity,
unit and food amount. Original postings, reversals and replacements remain visible
as separate events; summing signed food amounts gives net purchases. Exact decimal
strings are displayed without a price-per-case inference or browser aggregation.
Tax and fees remain available in Invoice Master outside food amounts.

Failed or malformed history reads show an error with refresh. They cannot fall
back to old purchase arrays or turn a failure into a "no purchases" message.
Late responses from an earlier restaurant are ignored.

This view does not replace Food Cost: Track 1 still uses explicit opening value
plus net received food purchases minus explicit closing value, with purchased-item
counts only. Prep, waste and sales explain that result without writing its facts.

## Validation and remaining work

Disposable PostgreSQL checks exercise the real server's retired routes, manager
manual capture/posting, rejected staff/readonly/PIN purchase entry, and flag-off
count compatibility. Frontend interaction checks cover native invoice routing,
staff handoffs, signed corrections, failed reads, location changes and adapter
guards, together with the previous native UI suites. The review package separates
current focused checks from the earlier full 115-case native regression/recovery
run; that entire slow suite is not represented as rerun for this routing change.

Still pending before operation:

- Native stock displays, owner/AI summaries and manual order planning now use
  dated counts and received purchase facts; see
  [operating views](NATIVE_OPERATING_VIEWS.md). Native comparison rollups and
  independent consumption explanations remain pending.
- Design split-location staff assignments/merging and scheduled count issuance
  if desired; full-scope staff drafts and explicit manager acceptance are implemented.
- Decide historical backfill, unnumbered receipts, unusual credits/discounts,
  mixed/nonfood orders, invoice splits and order reopening/reallocation.
- Rehearse recovery on the managed platform and agree service-role/config/storage
  and operational backup policies before enabling flags.
- Build separate, versioned prep/waste and Toast explanation ledgers.

The original review and cumulative baseline-relative patch are retained for a
possible future PR. Nothing is pushed by this milestone.
