# Supplier planning price history — local continuation, October 6, 2026

This work follows the unpublished [menu integrity milestone](MENU_RECIPE_INTEGRITY.md).
It remains on `codex/inventory-workflow-continuation`, after draft PR #14's
`a472c8674a7e3f173e838907e1b9d13d7665a028` checkpoint. It is uncommitted and
reserved for a later PR. The original PR and published branch are unchanged.

## Accounting boundary

Actual Inventory still uses purchased-item counts, explicit count values and
received-date purchase facts. Catalog prices, prep and sales do not change those
facts or Food Cost. Invoice posting retains its own costs and does not update
planning prices automatically. Taxes and fees remain separate retained components.

## Implemented behavior

- An additive migration records an append-only price event for each store and
  supplier SKU. Events retain an exact decimal amount or unknown/null, effective
  date, recorded time, actor, source, pack snapshot and review evidence.
- Existing catalog amounts and provenance are retained as baseline events. Their
  business effective dates are unknown; an old update timestamp is not presented
  as a verified received date. The original source/time remain in the baseline
  evidence. No earlier history is invented.
- Manual amount changes and clears are recorded atomically with item saves, using
  the manager/owner identity. Unchanged amounts and availability/preference edits
  keep the existing event. Explicit zero remains a known zero; blank means unknown.
  Manual effective dates use the server's UTC calendar day, and recorded timestamps
  remain separate. Location business-date configuration is still a future decision.
- Item Setup provides a separate supplier history and receipt review panel. It is
  hidden while an item edit is open, so adopting a price cannot be followed by
  saving that open editor's old price. Saving a price refreshes the catalog through
  the existing reload callback. Review notes remain in the session draft on failure.
- Invoice candidates use current posted dispositions only, with matching store,
  vendor, exact SKU and purchased product. Adoption requires USD, a positive
  received quantity and a current reviewed physical purchase-unit conversion in
  the same fixed inventory unit. Returns, price-only credits, tax/fee rows and
  unposted invoices do not become receipt-price candidates.
- The planning amount is **retained inventory cost / received base quantity ×
  verified base units per supplier purchase unit**. This is a receipt-average cost
  per current supplier unit, not necessarily the printed unit-price field. Exact
  source amounts, quantities, profile and pack are retained; division uses 50
  significant decimal digits when a ratio repeats. UI planning calculations remain
  approximate JavaScript numbers; they do not value accounting inventory.
- Receipt prices use the received date, independent of invoice and import dates.
  A receipt older than a known current price is held. Same-day candidates require
  an explicit reviewer choice; no automatic last-import-wins rule is introduced.
  A known baseline has no certified effective date, so its first adoption requires
  the explicit review rather than an inferred ordering. An unknown price can be
  filled from a reviewed receipt. A current identical source/profile cannot be
  adopted twice; a later receipt can supply new provenance even at the same amount.
- The preview hashes the source, current price and unit review. Adoption takes the
  catalog lock before the store revision lock, validates the preview again, appends
  an event and updates its projection/revision in one transaction. Concurrent
  retries with the same request key return the original event; changed payloads,
  stores or SKUs cannot reuse that key. The client checks the event, source, amount,
  date, request key and revision before reporting success. Uncertain saves retain
  the same request for retry. Reload/logout persistence is not promised.
- If the adopted invoice is corrected, its physical profile is replaced/stale,
  or its supplier pack changes, planning readers show unknown until reviewed
  again. The original event remains intact. Supported item pack edits with a
  nonblank price are held; clearing the price allows a pack change without carrying
  an old amount into a new pack.
- Native backup verification now reads identity sequence next-value state without
  assuming sequences have a composite row type. It compares `last_value` and
  `is_called`; internal WAL cache state is not a restored business value. Sequence
  state is not MVCC and requires quiescent writes for meaningful backup comparison,
  as already disclosed by the native recovery workflow.

## Enablement and remaining work

Apply `20261006_supplier_price_history.sql` after shared catalog and native order
receiving, with corrections/current-posting views installed. The existing native
purchase, actual inventory and shared catalog flags govern these endpoints. No
flags or operational migrations were enabled here. Before this migration, existing
manual catalog behavior continues; the history endpoint returns an explicit hold.
Once installed, database triggers record supported price writes and reject in-place
event/provenance rewrites. Schema rollback is not a switch to legacy global prices.

History pages contain 100 events with older/newer navigation. The receipt review
shows the newest 100 matching current receipt lines; older sources remain retained
in purchase records. This is a current-price review workflow, not an as-of historical
recipe valuation engine. General order transitions, full physical/menu mapping,
operating task/count/container cutover and Toast remain subsequent work.

R12 remains open: effective history and older-receipt guards now cover the planning
price portion, but unusual discount/allowance allocation and the original full
multi-pack invoice acceptance still need broader end-to-end verification. The
original review remains 6 fixed within scope, 13 open and 1 intentionally deferred.

## Validation

Final local validation passed: 271 frontend checks in 32 suites; 34 selected
backend test functions plus 21 menu validation subcases; 23 offline route/migration
checks; and the production build with the same three existing hook warnings.
The backend run includes nine supplier-price functions and regression coverage
for catalog/shared identity and menu definitions. A whole disposable SQL backup
and restore matched the price history, current projection and review candidates.
Initial fixture/mock failures are retained. The first recovery run exposed the
sequence inspection defect described above; the repaired final recovery passed.

Final results and source hashes are recorded in the local review package. Only
invented invoices and disposable loopback PostgreSQL are used. Database files stay
outside synced Documents/Drive folders. No real invoice was imported, and no
operational database, PR, merge or deployment was changed. Component/build and
selected database checks are not browser or managed-platform production proof.

Next: finish remaining metadata and order transition integrity, then the retained
prep/task/count/container operating workflow before Toast integration.
