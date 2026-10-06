# Catalog integrity foundation

Local implementation milestone, October 6, 2026. This completes the first part of the catalog/schema mapping work; shared product identity, recipe mapping and operating cutover remain open. No schema migration, live database write, real invoice import, commit, push or PR is part of this milestone.

Follow-up: [Shared catalog mapping](SHARED_CATALOG_MAPPING.md) now implements explicit cross-store product/SKU linkage, store-specific supplier prices/settings and aliases. R10 is fixed locally in that subsequent milestone. The remaining findings below record this earlier foundation checkpoint; use the cumulative review for current status.

## Accounting boundary

Track 1 remains purchased inventory only: opening physical count plus received purchases minus closing physical count, with explicit opening and closing inventory values. Received date is the purchase date of record. Taxes and fees are retained separately. Prep production, waste and POS sales explain variances; they do not update Track 1 facts or Food Cost. Catalog pack/portion metadata cannot replace reviewed native unit profiles or explicit physical count values.

## Supported catalog contract

| Field or action | Behavior |
| --- | --- |
| Canonical item code and supplier ID/SKU | Retained through the PostgreSQL/browser adapter. Descriptions do not generate identities. |
| Store active / count participation | Independent flags. Disabling counts does not deactivate the item. Retirement does not remove physical count participation. |
| Order and sales flags | Independent controls. Retirement disables both at the selected store. |
| New native order lines | Direct creation/edit requires store membership, active status and ordering enabled. Rejected lines roll back the transaction, including a new header. Historical orders remain. |
| Global catalog active | Returned separately as `catalogActive`; store editing does not write the global flag. |
| Supplier description | Original text, including spaces, is retained. The editor's existing `packDescription` field maps to this description; it is no longer regenerated from pack arithmetic. Null remains null on an untouched adapter round trip. |
| Supplier price | PostgreSQL NUMERIC -> decimal text or null -> browser string -> Decimal command. Unknown price remains null; explicit zero is valid. Negative/non-finite prices are rejected. This changes the catalog API price response from a JSON number to decimal text. |
| Price date/source | Ordinary edits and equal decimal values retain the existing provenance. A real manual change, including clearing a known price, changes date/source. A new unknown price has no fabricated date/source. |
| Catalog numeric metadata | Finite nonnegative pack, portion and par values; positive conversion factors when supplied. These metadata fields still use floats and are not the accounting fact representation. |
| Count actor / stock | Metadata saves leave database count actor/date/stock intact. The adapter retains a supplied count actor. Native actual-inventory mode deliberately hides legacy on-hand/count attribution and uses its dated physical count workflow. |
| Item retirement | Item, store association, stock, supplier identity, recipe lines and historical facts remain. `DELETE /api/pg/items/{store}/{code}` returns `retired`, `deleted: false` and the new revision. Items omitted from whole catalog replacement are retired. |
| Removed supplier choice | Marked unavailable and not preferred; its identity and historical references remain. |
| Catalog revision | Granular create/retire now bump the store collection revision in the same transaction. Supplied stale `If-Match` values reject the write. Invalid later items roll back the entire collection and revision. |

Retired records remain visible in Item Setup and available to explicit physical counting. Count scope removal needs its own reviewed boundary. Reactivation and order/sales participation use the separate controls; changing one flag does not silently change the others.

## Verification

The cumulative local review package contains the exact source files, patch, test outputs and earlier snapshot. Current frontend validation: 217 checks in 27 suites, including 15 new adapter/editor cases; production build passed with the same three existing hook warnings. Current disposable PostgreSQL validation: seven new catalog checks, plus 18 passing receiving/entry/recovery regression checks. All 23 offline route/migration checks also passed in their intended mock configuration. The first retirement test used an outdated revision after creating counts/purchases; the API rejected it correctly. The fixture was corrected and all seven catalog checks passed on rerun. Raw first-run and rerun evidence is retained.

Fresh synthetic recovery checks cover whole-database rows, schema/ACL, actual reports and write guards in the schema loaded by those fixtures. Earlier prep recovery proof is retained separately. These checks are not production or managed-service restore proof. Test PostgreSQL files remain outside the synced Documents workspace; real invoice samples were not imported.

## Remaining review findings and next milestone

- R05: finish independent unit contracts throughout legacy costing/prep/report readers. Catalog metadata is not a reviewed physical conversion.
- R10: `vendor_items` still assigns one global vendor/SKU to one item code. Global item/SKU edits can affect multiple stores while revisions are store-scoped. Supplier preference and availability are still global. Do not merge products by name or silently remap an existing SKU.
- R11: menu recipes and legacy cost recursion still require full validation and unknown/incomplete cost handling. A null catalog price alone does not fix readers that substitute zero.
- R12: catalog provenance corruption is fixed here; effective-dated price history and remaining unusual invoice/adjustment policy are still open.
- R15: the identified active/count, supplier text, price and actor losses are fixed here. A complete all-field/null/unit contract remains open: some editing paths still coerce empty pack metadata to zero.
- R18: purchased-item store retirement and unavailable supplier choices are implemented. Prep scope removal and broader retirement states remain open.
- R07/R17: direct legacy operating save contracts and comprehensive backend concurrency/idempotency remain separate work, including racing retirement/order transitions. This catalog revision change does not close them.

Next, define one stable global purchased-product identity with store-specific aliases/settings and reviewed supplier-product relationships. A supplier SKU should be usable by two stores with independent counts, pars and availability. Treat unconfirmed mappings as held for review. Freeze invoice facts independently of mutable catalog descriptions/prices, preserve received-date accounting, and prove cross-store edits cannot silently overwrite each other. There is no operational data to migrate, but keep explicit migration/version checks for future deployments.

## PR checkpoint

Recommend a draft PR after the shared supplier-product identity and remaining catalog contract milestone, before broad prep/task/count/container cutover. It provides a coherent foundation review and makes subsequent workflow changes easier to assess. This cumulative change set is already large; do not wait for Scheduling, Operations, analytics or Toast to join it. Preserve independently reviewable migration/feature-gate and testing boundaries if the cumulative PR is split. Publication requires the user's authorization; everything remains local for now.
