# Native expected-sales quantity completeness

October 16, 2026 (EDT). Baseline: PR42 merge
`c9262170ea5ff4817507f272e1b0d4686dd08d7c`.
This is a follow-up for audit F01. After the requested prompt, the owner approved
pushing a new draft PR for independent review. It does not import Toast data or
establish historical sales completeness. Merge approval remains separate.

## PR42 merge and deployment

The owner approved merging PR42 from reviewed head
`b9b4f79a9ad30e5a60a6461721fab10264b01dbe`. Normal merge with an exact-head
guard produced the baseline above. All four
[reviewed-head checks](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/38996499994)
and [merged-main CI](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/38997332845)
passed. No administrative bypass or manual deployment was used.

Render frontend `dep-db9eb5dg1s2s73ace54g` is Live on the exact merge. The
unchanged API remains Live on `84cb381`, deployment
`dep-db9c61oae00c738np400`. No backend deployment was forced. The new Inventory
tab initially reached normal sign-in; the owner reported a Chrome login rejection.
On October 17, the owner confirmed in-app sign-in and the scoped fictional
unit-mismatch editor check [passed](PR42_LIVE_SETUP_ACCEPTANCE.md). No credential
or authentication setting was changed. The Chrome issue is not resolved by
this check, and no fresh accounting database comparison is claimed.

## Behavior and boundaries

`expectedSalesUsage` computes only recipe portions for sales-tracked purchased
items in the current restaurant and working period. It does not read prices,
supplier factors, physical profiles, inventory counts, purchases or waste.
No estimate reduces stock or revalues Track 1. Existing sales draft retention,
revisioned saves and debounce behavior stay in place; rendering does not save.

- A supplied canonical `itemCode` must resolve uniquely. It overrides a stale
  alias; a missing/ambiguous canonical key cannot fall back to an alias. Legacy
  alias-only ingredients must resolve uniquely within this restaurant.
- Item recipe quantities are portions. Prep references must resolve uniquely
  to a retained prep recipe with positive finite yield and supported yield unit;
  an explicit reference unit must match. Cycles, invalid source types, mixed
  identities and nesting beyond 100 levels are unavailable.
- Blank, omitted, negative, malformed, overflowed or underflowed quantities are
  unknown. Explicit numeric/string zero contributes zero. A zero-sale menu does
  not expand an unused malformed definition; it contributes no usage.
- A valid recipe with unknown sales invalidates only the tracked items it uses.
  Independently mapped items can retain known totals. A broken recipe graph
  cannot establish which items are affected, so it conservatively holds all
  tracked totals rather than displaying partial totals. Nonzero/unknown sales
  without a matching menu also hold the totals. An orphan confirmed zero adds
  no usage.
- Finite arithmetic guards refuse overflow and nonzero underflow. These remain
  planning numbers, not exact monetary or historical inventory snapshots.
- Native Sales Tracking displays Unknown plus review reasons and leaves its
  sales editor usable. It bypasses the legacy schema normalizer so malformed
  ingredient lists reach completeness guidance instead of crashing first.

Legacy `actualMode=false` calculations are unchanged. Shared monetary readers
and backend completeness remain F03/F03b work; this helper must not be presented
as fixing their cost estimates. Future Toast coverage needs explicit location,
business period, source identity, recipe/portion versions and completeness.
Working manual quantities alone cannot prove a complete POS import.

## Validation

The final native-profile run passed **942 frontend tests across 77 suites**,
zero failures/skips, and the strict production build (`main.f27f8605.js`). CI and
ESLint are enabled; compiler warnings fail the build. The existing Node
`fs.F_OK` deprecation notice is outside the compiler. Generated review contracts
and whitespace checks passed.

The initial run passed 935 tests and the strict build (`main.5ed424bd.js`).
Source review then strengthened malformed ingredient/scalar and supported-unit
guards. Both runs passed; initial reports are retained separately. The final
component cases include a null ingredient and a non-array ingredient list to
verify that native rendering bypasses the permissive legacy normalizer.

All fixtures are fictional. No SQL migration, hosted database test/write,
connection/hosting change or operational import is part of this slice.
Backend/PostgreSQL checks will run in fresh CI after an approved draft push;
PR42's green CI does not validate this new candidate.

External evidence is under the sibling work directory: `expected-sales-full-*`,
`expected-sales-final-*`, PR42 Render text/image captures and the
source-hash receipt. Evidence files and generated assets are not committed.

## Remaining sequence

1. Publish the owner-approved draft PR; keep it draft for independent review.
2. Independent review and fresh exact-head CI, then separate merge approval.
3. PR42's scoped fictional editor check is complete; later accept deployed
   expected-sales behavior independently of local component tests.
4. Address backend/frontend monetary completeness (F03/F03b), par basis and
   explicit unit aliases. Retain current build connections and native holds.
5. Design versioned Toast sales evidence and cross-track period/unit comparisons
   before integration. Track 1 remains purchased-item physical accounting with
   explicit count values; prep/waste and sales explain it.
