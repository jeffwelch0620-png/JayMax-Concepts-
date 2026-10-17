# Retained single-item prep arithmetic

October 16, 2026. Owner-approved continuation after PR40 merge
`f33db6ee8b677e0834c0dc468789807d3acaf33b`. The new follow-up stays local until
the owner approves publishing a draft PR.

## PR40 deployment checkpoint

PR40 merged normally from reviewed head `4abf76e`, with no protection bypass.
All four [reviewed-head checks](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/38979626068)
and the [merged-main run](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/38983967887)
passed. The two Windows checks that timed out locally passed in CI.

Render's API deployment `dep-db9bj5rm8hqs73ac5hp0` and frontend deployment
`dep-db9bj63m8hqs73ac5i7g` were observed Live on the exact merge. Both deployed
automatically; no manual deploy or settings change was made. A fresh signed-in
ownership page loaded Bert's $145 last count, $182 received food and 13.0%
estimated recipe cost. This is a read-only smoke test, not a new historical
Food Cost reconciliation or a legacy-prep/tooltip hover test. The earlier $212
reconciliation belongs to [PR39's acceptance record](PR39_LIVE_BACKEND_ACCEPTANCE.md).

No hosted write, connection change, permission change, override or test relay
was used in this continuation. Retired prep writes remain held in the native app;
the hosted app was not switched into a legacy profile to exercise them.

## Local change

The retained PostgreSQL `_pg_deduct_item_and_stock` path previously performed
unchecked float multiplication, division and subtraction after checking its
supplier estimate. Finite operands could still overflow, or a nonzero product
could underflow to zero.

The helper now uses the existing finite planning-number functions for vessels,
portions, source units, planning cost and remaining legacy stock. Invalid or
unrepresentable results produce a range 422 before the first stock write.
Positive vessel quantity is required. Missing-price wording, genuine zero-price
behavior, finite-result rounding and the existing nonnegative stock clamp are
preserved. No planning-number helper is used to value native actual inventory.

This is a retained-path hardening change, not a return to automatic recipe
deductions in Track 1. Legacy cutover holds and transaction ownership are
unchanged. There is no SQL migration, frontend change, new native cost writer
or accounting rewrite.

## Validation and evidence

- Focused sanitized offline run: **78 reported cases passed** (14 methods and
  64 subtests), no failures/errors/skips. Seven new boundary cases use mocked
  connections with no-write assertions; no application DSN is loaded.
- **34 disposable PostgreSQL cases passed** (18 methods and 16 subtests), no
  failures/errors/skips in the corrected complete rerun. The selected set covers
  the real HTTP task command, overflow/underflow refusal before a stock-write
  tripwire, normal and zero-price completion, late-error rollback, native
  cutover holds and purchased-item accounting isolation.
- The first database run had four fixture failures: the default three-batch
  planning limit returned 400 before the extreme inputs reached arithmetic.
  The fictional plan was corrected to admit the test quantities, without
  changing the production limit check. That initial report remains retained.
- The loopback PostgreSQL server is stopped; database and role inventories match
  the original inventory. The runner used fictional data and no hosted DSN.
- Generated review contracts match source. Frontend tests/build were not rerun
  for this backend-only follow-up; PR40's green frontend CI is prior evidence,
  not a test of this candidate.

External evidence uses the `single-prep-arithmetic-` prefix for the reports,
source hashes and local database receipts. The deployed smoke text/screenshots
use `pr40-owner-smoke-20261016`; Render proofs use `pr40-render-*-live-20261016`.

## Remaining workflow

Local validation is complete. Commit this slice and prompt before publishing its
draft PR. Independent review, exact-head CI and owner merge approval remain separate.
Continue the remaining field/unit and missing-reference audit afterward. The
restricted runtime-role cutover stays open before operational use; authentication,
UI redesign and module integration remain separate workflows.
