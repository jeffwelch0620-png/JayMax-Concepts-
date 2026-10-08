# Menu recipe identity, validation and planning cost

Local continuation of draft PR #14, October 6, 2026. Baseline commit:
`a472c8674a7e3f173e838907e1b9d13d7665a028`. These changes remain on
`codex/inventory-workflow-continuation`; they are not published in PR #14.

## Completed behavior

Recipe ingredient mappings retain the canonical purchased-product code and separately resolve
the restaurant's current display alias. A shared product no longer becomes a fabricated
`restaurant_alias` key when read or saved. A canonical ingredient that is no longer linked to
the destination restaurant is held before the browser sends a recipe replacement. Newly added
lines retain their canonical identity immediately; no name-based matching occurs.

Menu definition commands validate finite positive ingredient quantities, exactly one source,
recipe type, nonnegative price/par, and an optional target percentage greater than zero and at
most 100. A prep definition requires an explicit positive yield and supported unit. Menu
definitions represent one serving (yield 1 each). Empty recipes, invalid numbers, cross-store
sources, duplicate recipe IDs/temporary IDs, missing retained sub-recipes, and cycles are held
with actionable errors. Unknown prices remain allowed in a structurally valid definition;
they do not make it a fully costed recipe. Changed definitions, their transitive dependencies,
and their retained dependents need ingredients and valid prep yields. An unrelated incomplete
legacy recipe does not block a targeted edit and is not rewritten. A new parent cannot
legitimize an incomplete child. Whole-collection replacement still validates the entire graph.

The submitted graph is resolved before any header, line or revision changes. Temporary IDs are
allocated for all new recipes before writing, allowing unsorted nested prep/menu definitions in
one transaction. All headers exist before their lines are inserted. Replacement preserves
input order and retains canonical IDs. Definitions omitted together can be deleted without
stranding internal references; retained operating-history references still prevent deletion,
rolling back headers, lines, and revision together.

Create/update, replace, and delete share a per-store menu-definition transaction lock and bump
the store revision. Supplied stale `If-Match` values reject writes. This prevents the tested
granular recipe mutation from being overwritten by a stale collection replacement. It does
not implement general draft-order replay or version every unrelated metadata writer.

The collection adapter now sends changed definitions and explicit deleted IDs to
`POST /api/pg/dishes/{store_id}/changes`, which requires `If-Match`. A fresh comparison read
does not replace the caller's expected revision; concurrent changes still reject the save.
The server validates the affected dependency graph, writes only changed definitions, and
returns the saved collection plus temporary-to-canonical IDs in one transaction. The editor
uses the acknowledged ID for its next edit. Retained-recipe errors name the recipe and ID.
Catalog and recipe-list reads batch related rows; no process-wide cache is introduced.

## Quantity and cost boundaries

This retained menu-definition schema uses **inventory portions** for raw ingredient quantities
and **the selected prep definition's yield unit** for prep ingredient quantities. A non-null
raw-line `uom` must say `portion`; a non-null prep-line `uom` must match the child's yield unit.
These explicit fields survive read/write round trips. Existing null unit fields retain the
legacy implicit basis; they do not certify a reviewed physical conversion. New editor lines
record their basis. Explicit conflicting units are held rather than reinterpreted.

The planning calculator requires a known finite nonnegative price from the selected available
supplier choice, positive pack/portion quantities, and compatible weight/volume/count families.
It does not convert weight to volume or assume an unknown pack has quantity one. Explicit free
price zero remains valid. Missing ingredients, missing/cyclic sub-recipes, invalid yields,
unavailable prices, bad conversions, and numeric overflow produce incomplete/unknown cost.
Incomplete children make their parent total unknown; a known partial subtotal is not advertised
as the complete cost. Missing selling price leaves contribution and food-cost percentage unknown.

Menu Costing, production recipe cards, menu profitability, and prep task estimates use these
completeness checks. Unknown totals do not become `$0.00`, a profitable contribution, or a
suggested sale price. Unknown profitability sorts after known values, including verified zero.
Missing prep yield fields stay visibly unknown and use controlled empty form values.
The editor retains invalid drafts and sends no write or success toast;
valid but unpriced recipes can still be saved. Recipe nesting is limited to 100 levels and
whole replacement requests to 1000 definitions to avoid unbounded recursion/work.

These are current-catalog **planning estimates**. They do not select a native prep batch-cost
policy, mutate native prep journals, or replace actual accounting. Track 1 remains purchased-item
physical counts with explicit values and received-date purchases; taxes/fees remain separate.
Native prep batch cost remains `null` / `not_calculated`.

## Validation and retained review

Final verification passed: 264 frontend checks in 31 suites; production build with the three
existing hook dependency warnings; 28 selected backend test functions plus 21 menu validation
subcases; and 23 offline route/migration checks. The nine menu functions and their 21 subcases
were rerun after the final explicit-unit and retained-yield guards; these overlap the broader run. Current results
and source hashes are retained in `JayMax-menu-integrity-2026-10-06-review-package.zip` outside Git.
The initial backend run had one fixture failure (an invalid synthetic prep-log kind), corrected
before passing runs. An initial frontend run without native test flags failed four pre-existing
native-mode adapter checks; configured final runs passed. Initial results are retained.

Coverage includes shared canonical IDs versus aliases, null price/yield/unit
round trips, explicit zero price, incompatible unit families, invalid quantities and sources,
unsorted nested creation, cycles, omitted referenced recipes, retained operating history,
concurrent revisions, dirty/save-failure drafts, and unchanged actual count/purchase reports.

Only invented fixtures and disposable local PostgreSQL are used. Test database files remain
outside the synced Documents workspace. No real invoice import, operational migration, feature
enablement, merge, or deployment is part of this milestone. Component tests/build and selected
database checks do not constitute production/browser or managed-platform proof.

R05, R11, R15 and R17 remain open with narrower residual scope. Full physical/menu field
contracts, exact historical costing policy, legacy backend cost/stock recursion, all direct
operating screens, broad metadata/status-transition versioning, and durable command idempotency
still require work. This change adds API validation, not new database constraints or a complete
legacy-loader/operating cutover. Existing malformed definitions are not automatically rewritten.
New features, including Toast, continue to use the separate native fact/mapping contracts.

The next step is effective-dated supplier planning prices and their provenance, followed by
the remaining shared metadata/order transition controls and prep/task/count/container cutover.
