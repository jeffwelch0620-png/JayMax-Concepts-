# Catalog decimal inputs and save feedback

## PR37 review amendment — October 16, 2026

PR37 is published as a draft. Original head `f827f15` passed all four
[Inventory CI checks](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/38848164390).
The owner authorized the review recommendations, amendment, testing and push
to the existing branch. Merge approval and live acceptance remain separate.
Earlier local-only and frontend-only statements below describe the original
checkpoint; this amendment also changes backend planning consumers.

The review's overflow finding was confirmed, including positive decimal
underflow and the active owner-summary calculation path. Dedicated Python and
JavaScript planning helpers reject non-finite conversions, nonzero decimals
that become zero, and overflowing/underflowing products and quotients. Unknown
inputs poison dependent totals. A genuine zero price remains a known zero.
The generic backend `f()` fallback is unchanged; it is not suitable for optional
planning costs.

Guards cover catalog-derived portions/costs, nested recipe costs, adjustments,
legacy period estimates, planning order exposure and owner/AI summaries. Setup
shows "Outside supported calculation range"; monetary planning views show
"Unknown". Newly inferred conversion factors cannot silently fall back to one
after unsafe arithmetic. Existing exact stored factors and decimal metadata
remain preserved. Missing metadata and incompatible-unit policies are separate
audit work; this change does not certify them as verified conversions.

The store and form use the same error-toast ID, scoped by user/location/message.
Existing current-session/current-location guards still suppress stale callbacks.
Specific failure messages, retained drafts and confirmed-revision requirements
remain intact.

Track 1 is unchanged: explicit purchased-item counts and received purchase costs
remain the accounting basis, with taxes/fees separate. Tests compare the same
actual period report before and after extreme planning-price edits. Native
ownership totals retain their exact decimal strings even when linked recipe and
waste estimates are unavailable. Legacy prep deduction entry points keep their
existing retirement checks; no retired endpoint is reopened to return success.
Disposable tests verify the existing read holds and 409 write refusals.

Final amendment validation passed:

- 861 frontend tests in 74 suites; strict production build passed.
- 765 offline reported cases: 293 methods and 472 subtests; no failures,
  errors or skips.
- Nine disposable PostgreSQL methods: exact catalog/actual-report protection
  and all five legacy prep cutover tests. Database/role inventories matched
  before and after; the owned loopback server was stopped.

The initial amendment run passed 858 frontend tests, the strict build and 762
offline cases. A final rerun includes the additional unsafe-derived-factor and
owner-display regressions plus three more backend decimal scenarios; counts
above are final totals, not sums of repeated runs. Existing dependency and
FastAPI lifecycle deprecations remain; compiler warnings still fail the build.

Amendment validation and source hashes are recorded in the external
`pr37-amend-validation-20261016.json` receipt. New-head CI must be checked after
push; the original green run above is historical evidence only. No hosted
database, migration, credential, connection or hosting changes accompany this
amendment. Restricted runtime-role cutover remains open before operational use.

After separate merge approval: verify both Render services Live, preserve drafts,
refresh every Inventory tab, then run labelled normal/unsafe-input save and
reload acceptance. Do not treat local fixtures as hosted proof. Continue the
field/unit audit afterward: expected-sales completeness, missing/incompatible
cost metadata, unit aliases, explicit par basis and historical portion meaning.

## Original local checkpoint

October 15, 2026, Eastern. Local follow-up to merged PR36 (`0e263ce`), whose
amended head was `aaef97f`. The owner authorized these two fixes and testing,
and requested a prompt before publishing a new draft PR. This slice is local;
no new PR, deployment, hosted data write, SQL, credential or setting change is
authorized by this record.

## What the live check established

The labelled Bert's item `berts_SB-004`, supplier SKU
`TEST-ONLY-DECIMAL-PR36-20261015`, retained its entered precision, scaled zero
and fixed small portion after a name-only save and a fresh page read of
`main.dd9e36a7.js`. Its count, order and sales flags are off. Five read-only
database checkpoints preserved pre-existing protected data across 82 tables,
all historical purchase/count/prep facts, the existing unit profiles and the
complete $212.00 historical Food Cost report. Its one new manual planning-price
event was unchanged by later edits; the global supplier price remained null.

In-place automation navigation aborted, so persistence acceptance used a newly
opened app page rather than claiming uninterrupted in-place reload. One early
test exponent was sanitized to blank by the number input and followed the
existing blank-par-to-zero path on this fictional item. The original scaled
zero was restored before the independent name-only edit. Four successful UI
saves occurred: creation, sanitized blank-par save, restoration and rename.
The retained out-of-range `1e-513` was subsequently refused without a database
or revision change. The final test drafts were cleared.

Evidence outside Git: `pr36-live-catalog-acceptance-20261015.json`, with the
five individual checkpoint paths and SHA-256 hashes. This proves the tested
precision cases, not the entire supported browser input range. The two gaps
below were identified by that same live test.

## Exact input text

Chrome's number input cleared both `1e400` and its 401-digit fixed equivalent,
although both fit the accepted catalog decimal contract. An unrelated edit
could therefore replace such a value through an empty/default path.

All seven editable catalog decimal controls in Item Setup now use text inputs
with a decimal keyboard hint: par; item pack count, pack quantity and portion
size; supplier pack count, pack quantity and price. No input-length truncation
or numeric browser coercion is introduced. The existing shared decimal-string
checker still enforces nonnegative/finite/bounded input before HTTP; unknown
optional values, zero scale, existing positive stored factors and supported
exponent text keep their meanings. The two non-editable stored conversion
factors retain their earlier safeguards. Legacy on-hand controls and planning
estimates are outside this change. Newly derived catalog factors still follow
their earlier calculation path; they are not verified native unit profiles.

## Specific failures without false acknowledgements

Previously the store displayed a specific error but returned null. Form
confirmation then replaced that explanation with a generic unconfirmed-save
message. Current-scope save failures now return `{ok:false,errorMessage}` with
no revision. Form confirmation preserves that message and cannot accept the
result as a successful receipt. Success still requires a nonnegative integer
revision and `ok` other than false before updating saved state or clearing the
matching submitted draft. Inactive location/session callbacks still return
null and do not disclose their old error or mutate the current scope.

Pending-load/save and stale-revision refusals use the same explicit failure
shape. Structured server validation details are reduced to field locations and
messages; submitted input and validation context are not echoed. Conflict
guidance remains the existing review-before-retry instruction.

The caller audit found two truthiness checks: legacy app-file restore and
legacy prep recommendation application. Both now require a confirmed revision,
so a failure object cannot count as restored or mark a recommendation applied.
Sales working-period and snapshot saves preserve specific failures too. No
additional write, automatic retry or restoration policy is introduced.

## Validation and publication gates

Final local validation passed:

- 849 frontend tests in 73 suites, zero failures.
- 746 reported offline cases: 290 methods plus 456 subtests, zero
  failures/errors/skips.
- Strict production build with ESLint enabled and compiler warnings treated as
  errors. Existing backend dependency/lifecycle warnings and Node's fs.F_OK
  deprecation notice outside the compiler remain.

Evidence outside Git: `catalog-input-feedback-full-frontend-20261015.json`,
`catalog-input-feedback-full-build-20261015.log`,
`catalog-input-feedback-offline-20261015.xml`, and the combined
`catalog-input-feedback-validation-20261015.json` receipt with committed source
hashes. Backend, SQL and deployment files are unchanged; database tests were
not rerun for this frontend-only slice.

Component tests exercise the real editor with all seven fields containing
large exponent/fixed values, tiny values, scaled zero and the maximum supported
coefficient. Real store/editor integration checks retained invalid text,
specific validation errors and no transport write. Store tests cover conflict,
server failure, corrected retry and replaced-session isolation. Additional
checks prevent failure objects from clearing drafts, passing restore or
applying prep advice.

The initial targeted run passed 138 cases and failed two older tests whose
selectors still required number inputs. Those selectors now identify the
labelled pack field; no production change was needed for that correction.
Initial evidence is retained. These local tests do not claim hosted
acceptance of the new input controls or CI on an unpublished head.

After owner-approved draft publication: independent review and current-head CI,
then separate merge approval, both Render services Live, preserve drafts and
refresh all Inventory frontend tabs, and run the labelled browser acceptance
against the newly deployed input and failure-feedback behavior. The remaining
field/unit audit then returns to expected-sales completeness, strict cost
preview, unit aliases and an explicit par basis.
