# Database Schema / Collection Definitions

MongoDB (single database, name from `DB_NAME`). Most documents use application-generated
string ids (e.g. `po_ab12cd34ef`, `dish_...`, uuid hex) stored in an `id` field; the
BSON `_id` is never returned to clients. `items` is the exception — it's keyed by
`controlNumber` (+ `restaurantId`), not a separate `id`. Every record is scoped by
`restaurantId` (one of the registry ids: `berts`, `rudds`, `papa_leonis`).

Datetimes are stored as ISO-8601 strings (UTC). Money is USD floats. Quantities are
floats in the item's purchase unit unless noted.

> There are no formal schema migrations — collections are schemaless and created on first
> write. The registry and default storage areas are seeded at startup (see `server.py`
> `RESTAURANTS`, `DEFAULT_AREAS`). The `scripts/` folder holds the data-ingest jobs that
> populate `items` and `purchases` from spreadsheets/CSVs (treat these as migrations).
>
> **This doc is generated from `server.py` as of the fields it actually reads/writes —
> keep it that way.** An earlier version of this file (and `sample-data/demo_dataset.json`,
> which was written against it) described an older shape that no longer matches the code
> (e.g. `menuPrice`/`recipe[]` instead of `price`/`lines[]`, `recipeUnit` instead of
> `portionSize`/`portionUOM`, a flat one-doc-per-area `areas` shape instead of one
> `{restaurantId, list}` doc). Loading data in the old shape doesn't error — it just
> silently produces $0 costs and empty area lists. If you regenerate seed/demo data,
> cross-check against the Pydantic models and `_item()`/`_pur()`/`_prep()` seed helpers
> in `server.py`, not just this file.

## Registry (in code, not a collection)
`RESTAURANTS = [{id, name, short, location, accent}]` → ids: `berts`, `rudds`, `papa_leonis`.

---

## `items` — inventory catalog
Keyed by `(restaurantId, controlNumber)` — no separate `id` field.

| field | type | notes |
|---|---|---|
| controlNumber | str | area prefix + sequence, e.g. `WI-001`; primary key with `restaurantId` |
| restaurantId | str | scope |
| name | str | item name |
| storageArea | str | area name (see `areas`) |
| active / countActive / orderEnabled / salesTracked | bool | visibility/behavior toggles |
| itemType | str | `portion` (recipe-costed) or `usage` (consumable, no portion costing) |
| purchaseUnit | str | case, bag, each, … (the unit ordered/counted in) |
| packCount | float | number of sub-units per purchase unit (e.g. 8 in an "8/5lb" case) |
| unitQty | float | quantity per sub-unit (e.g. 5 in "8/5lb") |
| unitUOM | str | UOM of `unitQty` (lb, oz, fl oz, each, …) |
| portionSize / portionUOM | float / str | size of one recipe "portion" of this item, in the item's own UOM family — drives `costPerPortion` |
| par | float | target on-hand, in `purchaseUnit` |
| currentStock | float | on-hand, in `purchaseUnit`; incremented on PO receive, decremented by prep deduction |
| lastCounted | str | ISO date of last count |
| vendorSkus | array | see below |
| needsReview | bool | set by import scripts for manual review; cleared on save |

`vendorSkus[]`: `{id, vendor, vendorSku, packDescription, purchaseUnit, packCount, unitQty, unitUOM, price, priceUpdatedAt, priceSource, available, preferred}`. `preferred_sku()` picks the `preferred: true` entry (or the first) for costing.

## `purchases` — invoice/purchase history (Invoice Master)
| field | type | notes |
|---|---|---|
| id | str | `pl_...` |
| restaurantId | str | |
| invoiceId | str | |
| invoiceNumber | str | used by PO receipt-matching (`_match_invoice`) |
| invoiceDate | str | ISO date — **not** `date`; `store_summary`/`build_ai_context` filter 30-day spend on this exact field name |
| vendor | str | US Foods / PFG / … |
| controlNumber | str | links to `items` |
| itemName | str | |
| qty | float | quantity on the invoice line |
| unit | str | purchase unit on the line |
| unitCost | float | |
| extendedCost | float | qty × unitCost |

## `dishes` — menu items AND prep recipes (same collection)
| field | type | notes |
|---|---|---|
| id | str | `dish_...` / `prep_...` |
| restaurantId | str | |
| recipeType | str | `menu` or `prep` — prep recipes feed the Prep module, not the menu |
| name | str | |
| menuCategory | str | |
| menuCode | str | |
| description / photoUrl / procedure / equipment / shelfLife / portionNote | str | |
| price | float | menu price (menu recipes only; **not** `menuPrice`) |
| targetPct | float | target food-cost % |
| yieldQty / yieldUOM | float / str | how much one batch produces (prep recipes) |
| lines | array | see below — **not** `recipe[]` |
| prepPar / frequency | float / str | prep recipes only: standing par + `daily`\|`biweekly`\|`weekly` |

`lines[]`: `{sourceType: "item"|"prep", controlNumber, qty}` for an item line, or `{sourceType: "prep", recipeId, qty}` for a sub-recipe line. `qty` is a count of the *source's portions* (item: `portionSize` units; sub-recipe: `1/yieldQty` of a batch), not a raw quantity+uom pair.

## `areas` — storage areas
**One document per restaurant**, not one per area:
`{restaurantId, list: [{name, prefix}, ...]}` — seeded from `DEFAULT_AREAS` (Salad Bar Room/SB, Shed/SH, Office/OF, Prep Room/PR, Walk-in/WI, Counter/CT). Written wholesale via `PUT /api/state/{rid}/areas`.

## `prep_items` — standing prep items (inventory item or prep recipe → standard vessel)
`{id, restaurantId, name, sourceType: "item"|"prep", controlNumber, recipeId, vesselName, vesselCapacity, parVessels, schedule: "daily"|"oneoff", note, createdAt}`

## `prep_lists` — generated daily prep lists
`{id, restaurantId, date, status: "draft"|"released", tasks: [...], generatedFrom, generatedFromDate, generatedAt, releasedAt, releasedBy}`

`tasks[]`: `{id, recipeId, prepItemId, taskType: "batch"|"vessel", name, yieldUOM, yieldQty, par, counted, uncounted, neededUnits, batchesPlanned, batchesDone, doneBy, doneAt, note, vesselName, vesselCapacity, controlNumber, removed}`

## `prep_stock` — current prepped on-hand
`{restaurantId, recipeId | prepItemId, name, onHand, yieldUOM, containers: [{id, label, size, count, createdAt}]}`

## `prep_count_sessions` — nightly count sessions (staff)
`{id, restaurantId, date, status: "open"|"submitted", countedBy, entries: [...], submittedAt, revision, revisions: [...], createdAt}`

`entries[]`: `{recipeId, prepItemId, onHand, note, savedAt, savedBy}` — one entry per prep recipe or prep item, keyed by whichever of `recipeId`/`prepItemId` is set. `onHand: null` means "not yet counted" (blank ≠ zero).

## `prep_logs` — production log (`PrepLog` model)
`{restaurantId, kind: "batch"|"sales_usage"|"container_use", recipeId, prepItemId, name, batches, produced, yieldUOM, usage: [...], containers: [...], totalCost, date, createdAt}`

## `prep_overrides` — one-off/par overrides for a specific date
`{id, restaurantId, date, type: "add"|"par"|"remove", recipeId, prepItemId, customName, par, batches, note, createdBy, createdAt}`

## `purchase_orders` — PO approval chain ← core of the Orders module
| field | type | notes |
|---|---|---|
| id | str | `po_...` |
| restaurantId | str | |
| vendor | str | |
| status | str | `draft → pending → approved → sent → received` (or `rejected`) |
| createdBy / approvedBy | str | approval requires `by` distinct (case-insensitive) from `createdBy` |
| lines | array | `[{controlNumber, name, vendorSku, qty, purchaseUnit, unitCost, lineTotal, receivedQty}]` |
| total | float | |
| note / rejectedReason | str | |
| createdAt/submittedAt/approvedAt/sentAt/receivedAt | str | ISO timestamps |
| emailedTo / emailedAt | str | supplier email audit |
| invoiceNumber | str | entered at receipt |
| receiptMatch | obj | `{invoiceNumber, invoiceFound, flaggedCount, matchedAt, lines:[{controlNumber, receivedQty, poUnitCost, invoiceQty, invoiceUnitCost, qtyDiff, priceDiff, flagged, onInvoice}]}` |
| history | array | `[{status, at, by, note}]` |

## `vendor_contacts` — supplier order emails
`{restaurantId, vendor, orderEmail}` — default recipient for PO emails; one doc per vendor.

## `sales_periods` — current sales-tracking period (one doc per restaurant)
`{restaurantId, periodStart, periodEnd, dishSales: {dishId: qty}, itemCounts: {controlNumber: qty}}`

## `projected_sales` — manual daily sales projections
`{restaurantId, date, amount, note, enteredBy, updatedAt}` — **not** `projectedNetSales`.

## `par_recommendations` — AI par-advisor output
`{id, restaurantId, recipeId, recipeName, currentPar, recommendedPar, reasoning, status: "pending"|"applied"|"dismissed", createdAt, appliedAt}`

## `adjustments` — manual stock adjustments
Key fields read by `adj_value()`/`ADJ_DIRECTIONS` in `server.py`: `{controlNumber, qty, qtyBasis: "unit"|"portion", reason, date}`, where `reason` is one of `waste, spoilage, employee_meal, comp, prep_loss, transfer_out, transfer_in, count_correction_remove, count_correction_add, other_remove, other_add`. Additional fields (`id`, `by`, `note`, etc.) are written by the frontend form and round-tripped as-is.

## `chat_messages` — AI assistant transcript (`ChatMessage` model)
`{restaurantId, role, content, ts}`

## `settings` — per-restaurant settings
`{restaurantId, key: "staff", staffPin}` — `staffPin` gates the read-only staff prep sheet (default `1234` when unset).
