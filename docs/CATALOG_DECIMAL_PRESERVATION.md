# Exact catalog decimal preservation

October 15, 2026. Local follow-up to PR35 and the remaining field/unit audit.
The owner authorized the decimal fix and local testing, with a prompt before
publishing a new draft PR. No draft has been pushed, merged or deployed.

## Problem and resulting behavior

Catalog NUMERIC values previously passed through Python floats, JavaScript
numbers and the item editor before saving. For example, a stored conversion
`1.123456789012345678` became `1.1234567890123457`. An unrelated item edit could
rewrite that value at a single location, or fail shared-product/pack checks.
Verified unit-profile fingerprints could consequently become stale without an
intentional physical-conversion change.

Item and supplier catalog reads now return decimal text for:

- Item `packCount`, `unitQty`, `portionSize` and store `basePerCountUnit`, `par`.
- Supplier `basePerPurchaseUnit`, `packCount`, `unitQty`.

The corresponding write models use Decimal and bind directly to existing
NUMERIC columns. Optional blanks remain null; an explicit zero stays distinct
from unknown. Positive count/supplier conversion guards and nonnegative metadata
guards remain in place; booleans and nonfinite values are refused.

The compatibility adapter preserves decimal text through item writes, including
very large/small finite decimal exponents that cannot be represented by a
JavaScript Number. Planning calculators still make their own numeric copies;
those copies never replace retained metadata. No menu price, recipe quantity or
native physical-profile calculation policy is changed here. New catalog factors
derived from pack metadata retain the earlier calculation path; they do not
become verified native conversions.

Item Setup retains text when reading and editing these fields, and accepts the
stored decimal precision without a two-decimal input step. Draft reconciliation
normalizes legacy numeric form values to text before comparison, so an old
numeric `1` and entered `"1"` do not create a false conflict. No broad UI
redesign, par-unit policy or sales-expansion change is included.

## Compatibility and accounting boundary

Legacy JSON numeric inputs remain accepted. They cannot restore digits that an
older client already rounded. Deploy frontend/backend from this change together,
then refresh the browser before editing catalog metadata. Decimal text is the
new read contract; consumers must use explicit numeric copies only where an
estimate is required. No data backfill or silent rounding of existing values is
performed. The SQL files, schema snapshot and migration history are unchanged.

This does not change native item bases, reviewed profile factors, posted purchase
facts, count snapshots, closed reports, received-date rules or separate tax/fee
amounts. Prep and sales remain explanatory tracks. Existing credentials,
connections, hosting settings and the closed maintenance window are unchanged.

## Validation

- Full native frontend profile: 802 tests in 71 suites passed.
- Offline review profile: 744 reported cases passed (288 test methods and 456
  subtests), zero failures/errors/skips. Five existing dependency/lifecycle
  deprecation warnings remain.
- Strict production build passed with CI warnings treated as errors and ESLint
  enabled. An existing Node fs.F_OK deprecation notice was emitted outside the
  compiler; there were no compiler/lint warnings.
- Catalog/receiving validation: 40 distinct test methods plus five subtests
  passed across the broad run and final targeted rerun. The broad run reported
  44 cases, with one test expectation corrected; the final three-case run passed
  that correction, the strengthened precision case and a price-history case.
  Overlapping reruns are not added to the distinct count. Both database/role
  inventories match their initial state, and each owned local server stopped.

New checks cover exact model/serializer values, null versus zero, rejection of
invalid metadata, legacy/native adapter modes, extreme finite exponents,
unrelated-save payload selection and the actual item editor. The PostgreSQL
case round-trips API text through a single-location rename and a shared-product
local edit, with supplier-price history installed. It checks stored metadata,
unchanged supplier events/projections, profile fingerprints and an unchanged
explicit-value Food Cost report that includes a posted fictional receipt.
It is included in the database
CI profile; model checks are included in the offline profile.

Initial frontend checks found older numeric expectations and a real draft
comparison mismatch between numbers and text; these were corrected before the
full passing run. The first offline run had a test-format expectation for
`0.000000000000000001` versus its exact equivalent `1E-18`; the assertion now
uses the serializer's Decimal representation and the full profile passed.
Initial evidence is retained rather than overwritten.
The broad catalog/receiving run also caught an assertion incorrectly changed
to expect API text from a raw database row; its Decimal expectation was restored
and the final targeted case passed. No product change was needed for that test.

Operator evidence is retained outside Git under the build workspace's `work`
directory:

- `catalog-decimal-full-initial-20261015.json`: 802/802 frontend tests.
- `catalog-decimal-offline-final-20261015.xml`: 744 reported offline cases.
- `catalog-decimal-build-20261015.log`: successful strict production build.
- `catalog-decimal-tests-20261016T021416773900Z`: broad catalog/receiving log,
  XML, before/after inventories and shutdown receipt, including initial failure.
- `catalog-decimal-final-tests-20261016T022535734347Z`: final three-case pass,
  unchanged inventories and shutdown receipt.
- `catalog-decimal-validation-20261015.json`: combined evidence/source hashes.

The UTC October 16 database receipt names refer to October 15 evening EDT.
Only fictional fixtures and disposable loopback databases were used. GitHub CI
and a hosted walkthrough have not run for this local branch.

## Remaining workflow

Independent review and CI remain gates after an owner-approved draft push.
Merge/deployment and a fictional hosted catalog walkthrough require their own
approval. No hosted database was queried or changed for this fix. Remaining audit
items are canonical/complete expected-sales expansion, strict Item Setup cost
preview, explicit unit aliases and a selected par basis. Historical cross-track
integration still requires recipe/portion versions and a reviewed prep cost
policy. See [the workflow reconciliation](WORKFLOW_RECONCILIATION_20261015.md).
