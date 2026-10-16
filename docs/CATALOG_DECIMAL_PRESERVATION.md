# Exact catalog decimal preservation

October 15, 2026. Local follow-up to PR35 and the remaining field/unit audit.
The owner authorized the decimal fix and local testing, then approved publishing
[draft PR36](https://github.com/jeffwelch0620-png/JayMax-Concepts-/pull/36).
Original head `84a1747` passed all four Inventory CI checks. The owner subsequently
authorized the independent-review amendment, tests and push; merging and hosted
acceptance remain separate approvals. PR36 remains draft and unmerged.

## Independent-review amendment: bounded exact values

The review correctly identified that exact Decimal input alone accepts exponents
outside PostgreSQL/driver limits. The common `CatalogDecimal` contract now guards
all nine fields (the eight metadata fields below plus supplier price) before
encoding, with equivalent frontend checks for metadata and prices:

- At most 512 integer digits and 512 decimal places.
- At most 1024 coefficient digits and 2048 input characters.
- Existing nonnegative/positive, unknown/null, finite-value and boolean rules.

These are generous representation/resource limits, not a financial ceiling such
as $1 trillion. Inputs outside the contract are rejected, never rounded or
truncated. Compact exponent/digit metadata is checked before expanding numbers.
The browser never passes the value through Number to validate its range; only
the already bounded exponent is inspected as an integer. A test checks that the
backend constants and browser limit file agree. Existing legacy JSON numbers,
18-place precision, large precise supplier prices and supported exponents remain
accepted. Numeric planning estimates retain their separate completeness rules.

Before selecting the limits, a certificate-verified aggregate-only hosted query
profiled the affected item, store and supplier fields, including local supplier
prices. The repeatable-read transaction verified read-only mode and closed its
connection. Current fields have at most four decimal places and three integer
text digits, with no nonfinite values. No IDs, raw values or credentials are
included in the evidence. This is a point-in-time compatibility profile, not a
hosted test or change. Evidence: `pr36-decimal-profile-20261016T024409751691Z.json`,
SHA-256 `c364915cc9d4a97962fbbd5701e22349061ef5684ddb0e04eafe6d6b5d3780af`.

Catalog reads now show fixed notation, including supplier price:
`1E-7` becomes `0.0000001`, and `0E-10` becomes `0.0000000000`.
Trailing-zero scale is retained. This formatter is confined to the catalog API;
stored profile snapshots and fingerprint serialization are unchanged.

Amendment validation is recorded below before the authorized push. GitHub CI
must pass on the amended head; original-head green checks are not that evidence.

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
supported large/small finite decimal exponents that cannot be represented by a
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
then refresh **every open Inventory frontend tab after both services are Live**
before editing catalog metadata. Preserve unsubmitted drafts before refreshing.
Decimal text is the
new read contract; consumers must use explicit numeric copies only where an
estimate is required. No data backfill or silent rounding of existing values is
performed. The SQL files, schema snapshot and migration history are unchanged.

This does not change native item bases, reviewed profile factors, posted purchase
facts, count snapshots, closed reports, received-date rules or separate tax/fee
amounts. Prep and sales remain explanatory tracks. Existing credentials,
connections, hosting settings and the closed maintenance window are unchanged.

## Original-head validation (`84a1747`)

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
Only fictional fixtures and disposable loopback databases were used for these
local tests. Original-head GitHub CI subsequently passed; a hosted walkthrough
has not run for PR36.

## Amendment validation

The full native frontend profile passes 826 tests in 72 suites. The offline
profile passes 746 reported cases (290 methods and 456 subtests), with zero
failures/errors/skips. The strict production build passes with ESLint enabled
and compiler warnings treated as errors. Five existing backend dependency and
lifecycle deprecation warnings, and Node's existing fs.F_OK notice outside the
compiler, remain. New checks cover all nine fields, rejected
exponents/lengths, accepted range boundaries, fixed notation and zero scale.
HTTP rejection cases assert 422 and unchanged catalog tables/revision; the
accepted-boundary case verifies exact NUMERIC storage and fixed API output.
The existing precise shared-product case also retains price events/projections,
unit profiles and the complete actual Food Cost report.

The final targeted PostgreSQL run passes all three cases: precise shared-product
round-trip, extreme-input rejection, and supported-boundary round-trip. An
earlier passing three-case run also covered supplier-price history, for four
distinct methods across the two runs; overlapping reruns are not added to the
count. Both runs used fictional fixtures and disposable loopback databases;
database/role inventories were unchanged and each owned server was stopped.

Amendment operator evidence is retained outside Git in the same `work` directory:

- `pr36-amend-frontend-20261015.json`: 826 frontend tests, 72 suites.
- `pr36-amend-offline-final-20261015.xml`: 746 reported offline cases.
- `pr36-amend-build-20261015.log`: strict production build.
- `pr36-amend-db-tests-20261016T024807460446Z`: first three-case database pass.
- `pr36-amend-final-db-tests-20261016T025237569894Z`: final three-case pass,
  unchanged inventories and server-shutdown receipt.

An initial boundary check exposed Pydantic's generic finite validator converting
an annotated Decimal through a float. The common validator now checks Decimal
finiteness directly; it still refuses NaN/Infinity/booleans and oversized values
before driver encoding. Initial evidence is retained with the passing reruns.

## Remaining workflow

Independent re-review and amended-head CI remain gates after the authorized push.
Merge/deployment and a fictional hosted catalog walkthrough require their own
approval. The only hosted access for the amendment was the read-only aggregate
numeric profile above; no hosted data or settings changed. Remaining audit
items are canonical/complete expected-sales expansion, strict Item Setup cost
preview, explicit unit aliases and a selected par basis. Historical cross-track
integration still requires recipe/portion versions and a reviewed prep cost
policy. See [the workflow reconciliation](WORKFLOW_RECONCILIATION_20261015.md).
