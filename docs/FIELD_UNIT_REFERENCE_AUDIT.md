# Field, unit and missing-reference audit

October 16, 2026 (EDT). Audited source baseline: PR41 merge
`84cb3816e6780c6acc799fc0920b89aff3285af5`. This is a targeted audit of catalog,
recipe, sales-expansion and order-planning boundaries, not a declaration that
every legacy field or future integration is complete.

## Current continuation

The owner selected explicit purchased-inventory par units and review status,
aligned native Setup/order references and manual ordering. The local
[reviewed-par implementation](REVIEWED_INVENTORY_PARS.md) retains ambiguous old
numbers as unconfirmed, stores a fixed physical target with its verified count
profile, and requires re-review after count-profile changes. All 1,026 frontend
tests, the strict build and 62 corrected PostgreSQL cases pass. Broad offline
checks pass 884/886 with two unchanged Windows ACL startup timeouts, retained in
the serialized guard rerun. The requested draft-push prompt is pending; fresh
CI, merge approval and hosted schema application remain separate.

PR44 merged with owner approval as `1729ecf` from `8cb8886`; reviewed-head and
merged-main CI pass and both Render services are Live. The scoped
[monetary acceptance](PR44_LIVE_MONETARY_ACCEPTANCE.md) passes native recipe,
null/zero/decimal projection, owner-warning and saved-sales checks. An independent
database comparison verifies 81 protected relations unchanged, with the expected
analytical state change and unchanged $212.00 historical control. Legacy-only and
malformed negative cases retain local/CI evidence. Earlier gates below are history.

The owner authorized the [PR44 review amendment](MONETARY_PLANNING_COMPLETENESS.md):
S1 now reuses per-item sales completeness in legacy reports/table, N1/N2 tighten
legacy conversion refusal and guidance, and N3 exposes Unknown variance/waste.
Amendment validation passes 1,008 frontend tests, 130 focused backend cases and
52 disposable PostgreSQL cases. Broad offline checks pass 874/876 with two
unchanged Windows ACL startup timeouts; the strict build passes (`main.b379d347.js`).
Push is authorized, merge is not. The earlier original-head checkpoint follows.

The owner-authorized [F03/F03b monetary follow-up](MONETARY_PLANNING_COMPLETENESS.md)
is local: strict compatible conversion and positive metadata, explicit recipe
completeness, preserved adapter evidence and nullable monetary aggregates.
Validation passes 994 frontend tests and the strict build. The linked record
retains the corrected database fixture rerun and two unchanged Windows ACL
startup failures; publication requires the requested owner prompt and fresh CI.
This does not qualify legacy reports as native accounting or resolve par basis,
unit aliases, historical versions or Toast coverage.

PR43 subsequently merged with owner approval as `0cf5464` from `79b40ad`, with
reviewed-head and merged-main CI green. Its frontend is Live and the core
[expected-sales UI checks](PR43_LIVE_EXPECTED_SALES_ACCEPTANCE.md) passed.
Owner-approved deletion of only the new test menu enabled unmatched hold,
removal and reload checks, which passed. Live cancellation was not observed;
direct database fingerprints were not obtained. The displayed $212 saved control,
usage lines and fingerprint match before/after. Earlier PR42/PR43 draft checkpoints below are
historical; F03/F03b and later integration work remain open.

PR42 merged with owner approval as `c926217` from reviewed head `b9b4f79`.
[Reviewed-head CI](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/38996499994)
and [merged-main CI](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/38997332845)
passed. Render frontend deployment `dep-db9eb5dg1s2s73ace54g` is Live on the exact
merge; the unchanged API remains Live on PR41 `84cb381`. The deployed fictional
editor check [passed after owner sign-in](PR42_LIVE_SETUP_ACCEPTANCE.md): specific
mismatch guidance, no numeric preview, cancellation and original values after
reload. No save or hosted configuration change was submitted.

F01 now has a [native expected-sales implementation](EXPECTED_SALES_USAGE_COMPLETENESS.md)
in owner-authorized [draft PR43](https://github.com/jeffwelch0620-png/JayMax-Concepts-/pull/43).
Its owner-authorized review amendment adds confirmed recovery for meaningful
unmatched sales entries and preserves the distinction between current-menu
unknowns and blank orphan keys. New-head CI and merge approval remain separate.
It resolves canonical item keys, distinguishes missing sales from confirmed zero,
validates prep expansion and returns explicit unavailable quantities. This is
current-period quantity planning only. F03/F03b monetary readers, legacy-mode
expansion, par basis, unit aliases and historical/source coverage remain open.
The review and draft/merge language below records the earlier PR42 checkpoint.

## PR42 review amendment

Original draft head `592dbd9` passed all four Inventory CI checks. The owner
authorized addressing both low review notes on the same branch. Incompatible
units now show their specific measure-type warning in the unavailable preview
branch; the unreachable warning inside the numeric branch is removed. A real
Setup component case checks the exact fictional 5 lb / 4 fl oz example, no
numeric portions/cost and no save. F03b below explicitly records the frontend
counterpart of F03, including native-mode reachability limits.

Amendment validation passed: **889 frontend tests across 75 suites**, with no
failures/skips, and the strict production build with CI/ESLint enabled and
compiler warnings treated as errors. Local asset `main.fb7f266b.js` is not
deployed. Generated review contracts and whitespace checks passed. The existing
Node `fs.F_OK` deprecation notice remains outside the compiler. The local build
was slow but completed successfully without intervention. Original-head CI and
the earlier 888-test run are prior evidence; fresh exact-head CI is required
after the authorized push. This remains draft, with merge approval and hosted UI
acceptance separate. No shared calculator, backend, schema or hosted data change
is introduced by either amendment.

## PR41 deployment checkpoint

PR41 merged with owner approval from reviewed head `ebdef34`. All four
[reviewed-head checks](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/38986103304)
and [merged-main CI](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/38987139220)
passed. The independent review reported no findings.

API automatic deployment `dep-db9c61oae00c738np400` is Live on the exact merge,
duration 1m47s. The unchanged frontend remains Live on PR40 merge `f33db6e`;
no frontend deployment was forced for this backend-only merge. A fresh signed-in
ownership page loaded Bert's $145 last count value, $182 received food and
13.0% recipe-cost estimate. This smoke check does not re-prove the older $212
historical report or exercise the held legacy prep writer.

No hosted data, schema, connection, permission, credential or hosting setting
was changed. No real invoice sample or employee data was imported. The local
fix described below is in draft PR42; the owner separately authorized pushing
the review amendment to that same branch.

## Confirmed ownership and mapping boundaries

| Fact | Mapping inspected | Boundary that must remain |
| --- | --- | --- |
| Purchased product identity | `items.code` -> browser `itemCode`; store `control_number` -> `controlNumber` | Canonical key identifies the product; alias is local display identity. No name matching or automatic product merge. |
| Count and supplier units | `countUnit`/`basePerCountUnit` are distinct from supplier `purchaseUnit`/`basePerPurchaseUnit` | Preserve explicit stored factors and null supplier factors; catalog metadata is not a verified physical profile. |
| Physical accounting conversion | `purchasing.unit_profiles` snapshots source, factor, store, actor and revision | Fixed native base and independently verified decimal factor; pack edits make evidence stale instead of rewriting receipts/counts. |
| Catalog decimal fields | Adapter retains decimal text for pack counts, quantities, portions, factors, pars and prices | An unrelated save must not round or derive a replacement factor. Existing editor/adapter tests cover these targeted fields. |
| Supplier planning price | Local supplier setting and price provenance; available supplier selection | Unknown differs from zero. Planning prices do not value explicit Track 1 counts. |
| Recipe ingredient identity | API adapter retains canonical `itemCode` plus resolved local alias; prep uses recipe ID | Recipe writes validate store membership, source type, positive quantities, units, yield and cycles. Readers still need explicit completeness handling. |
| Native ordering | Reviewed order quantities use the selected supplier purchase unit; the new separate par reference retains its saved stocking/count unit and fixed base quantity | Old numeric pars have unconfirmed units. No suggested live on-hand or order quantity is inferred from dated counts/legacy stock. |
| Actual accounting | Received purchase facts plus purchased-item explicit opening/closing counts | Prep/waste and sales explain usage; neither deducts from or revalues Track 1. |

Source entry points: `frontend/src/lib/api.js` (`pgItemToMongoItem`,
`mongoItemToPgBody`, `pgLineToMongoLine`), `backend/native_units.py`,
`backend/menu_contract.py`, `frontend/src/components/NativeOrderPlanner.js`.
These are source findings and existing test contracts; no new hosted write or
whole-schema migration/restore test was performed for this audit.

## Findings and disposition

| ID / priority | Evidence and impact | Disposition |
| --- | --- | --- |
| F01 / medium | `rawPortionsForRecipe` matches local aliases only, skips missing prep references, returns zero on cycles and defaults zero/missing yield to one. The active expected-sales table previously summed this output without completeness. | Native current-period handling shipped in PR43; PR44 shares the helper with legacy table/report callers. Native scoped live acceptance and CI pass; legacy behavior is covered locally/CI. Price is not required for portions. Historical/source coverage remains F06. |
| F02 / medium | Item Setup uses permissive `itemDerived` while the recipe editor uses strict `itemPlanningCost`. A fictional 5 lb pack, 4 fl oz portion and $20 price gives 1.25 portions/$16 in Setup despite incompatible families; strict recipe costing is Unknown. Missing portion data gives a misleading zero list cost. | Bounded client fix implemented locally: Setup list and preview use strict cost; unsupported/mismatched/missing unit and nonpositive pack/portion quantities cannot show an invented portion total. Valid zero prices remain zero. Shared calculators and writes are unchanged. |
| F03 / medium | Backend `calc_ppu` has the same cross-family numeric fallback; `recipe_cost` returns/skips zero for missing items/prep/cycles. This can understate planning summaries/context for retained malformed definitions, despite write-time recipe validation. | Corrected in merged/deployed PR44: strict compatible conversion, explicit recipe completeness/reasons, retained adapter evidence and nullable summary/context values. CI and scoped native live checks pass. Negative/AI-context cases retain local/CI coverage; held legacy writers and native accounting remain independent. |
| F03b / medium, frontend planning reads | Shared frontend `itemDerived` / `calcPortionsPerUnit` retain the cross-family numeric fallback outside Setup. `buildPeriodReport` cost fields, `adjustmentValue` / `wasteByReason` and the legacy sales actual-portion calculation can therefore use the fictional 1.25-portions/$16 estimate. | Corrected in PR44: unavailable conversion and missing monetary evidence propagate to planning totals/display; genuine zero stays zero. Scoped native live checks and CI pass; legacy variance/waste UI remains local/CI coverage. Legacy count-unit conventions and historical/source coverage are not promoted to native accounting. |
| F04 / low, design | Setup labelled par as purchase units, while native order planning labelled the same par with `countUnit`; count bags and supplier cases may differ. | Owner-approved local implementation adds explicit reviewed stocking/count units and fixed physical targets with immutable history. Both native screens use the same reference. Old numbers remain unit-unconfirmed; no backfill or suggested order. Validation, independent review, migration approval and live acceptance remain separate gates; see reviewed-par record. |
| F05 / low, compatibility | Planning uses `fl oz`/`ct`; native physical units use `fl_oz`/`each`, with an explicit adapter bridge. Unsupported catalog labels remain possible. | Define accepted aliases at explicit boundaries, retain original labels, and refuse ambiguous weight/volume conversions. Existing alias differences alone do not prove physical-profile drift. No bulk relabeling. |
| F06 / future integration | Working sales store dish IDs/quantities, while expansion uses current recipe/portion definitions. Saved working entries are not versioned historical consumption evidence. | Before Toast variance history: retain recipe/portion version, location, business period, source identity and coverage/completeness. This is a separate design step; no historical rewrite or new integration is included here. |

The canonical-only F01 probe is a helper-contract gap, not proof that every
ordinary app read loses identity: the current API adapter normally supplies the
matching alias. The missing-reference, cycle, zero-yield and range probes are
also fictional/local; no assertion is made that current hosted rows contain
those defects. Server write validation reduces new malformed definitions but
does not justify silently accepting incomplete read evidence.

F03b's reachability is narrower than an accounting defect: `App.js` selects
`ActualInventoryTab` instead of the legacy `DashboardTab` in native accounting
mode, and native sales hides the old actual/variance columns. The shared
calculator gap remains relevant to legacy analytical consumers and future
integration; it is not evidence of a changed native Food Cost or posted count.

## Local fix and verification limits

Only `SetupTab.js` behavior changes. It reuses `itemPlanningCost`; no new unit
conversion formula, physical profile, stored catalog value or API request field
is introduced. A compatible pack can still show its portions while its price is
unknown. Incomplete quantity/unit metadata gives Unknown cost in the list;
invalid conversion details give review guidance instead of a numeric preview.
Incomplete items can still be saved for later review under existing server rules.

Component regressions cover incompatible families, unsupported matching units,
missing units, negative factors, missing/nonpositive portions, valid cost and
known zero. They also assert no save on rendering and preservation of canonical
identity, exact price and stored conversions through an unrelated rename.

Original-head full native-profile validation passed: **888 tests across 75 suites**,
zero failures/skips, and the strict production build with CI/ESLint enabled and
compiler warnings treated as errors. Local asset: `main.7084275c.js`; it is not
deployed. An existing Node `fs.F_OK` deprecation notice was emitted outside the
compiler. The initial 886-test run also passed before adding the missing-unit/
negative-pack cases. Generated review contracts and whitespace checks passed.
Backend/PostgreSQL tests are not rerun for this client-only change;
PR41's green CI is prior evidence, not candidate CI or hosted acceptance.

Evidence retained outside Git:

- `field-unit-audit-probes-20261016.json`: 13 local frontend calculation
  observations at the audit baseline, including strict versus permissive values.
- `field-unit-backend-probes-20261016.json`: six pure-function observations;
  app/configuration is never imported and no database connection is used.
- `field-unit-setup-final-*`: final frontend/build reports after strengthened
  unit/pack checks. These probes are observations, not 19 new passing tests.
- `pr42-amend-full-*` and `pr42-amendment-validation-20261016.json`: separate
  amendment test/build evidence and source hashes; original reports are retained.
- `pr41-render-api-live-20261016.png` and `pr41-owner-smoke-20261016` text/image.

## Sequence from here

F02 shipped in PR42, F01 in PR43 and the shared legacy reader amendment in PR44;
F03/F03b shipped in PR44. Their scoped acceptance and local/CI limits are linked above.
Next select the F04 par basis before changing labels or stored interpretations.
Resolve explicit F05 aliases and F06 historical versions before integrating Toast analytics.
O1 restricted deployed
runtime roles remain required before operational use; current build connections,
credential rotation deferral, separate auth/UI workflows and native holds remain.
