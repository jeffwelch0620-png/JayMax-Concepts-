# Backend planning prices and location recipe aliases

October 16, 2026. Local follow-up from PR38 merge `3c58abd` and local live
acceptance checkpoint `5dc2450`. The owner authorized backend missing-price
parity and testing, with a prompt before pushing a new draft PR.

## Problem and resulting behavior

The backend `item_derived` calculator defaulted absent supplier planning prices
to zero. That made an unpriced ingredient look free in nested recipe estimates,
estimated waste, ownership summaries and AI context. The shared calculator now
retains null for absent/blank prices and no available supplier. Exact zero,
including `0E-10`, remains known zero. Known pack/portion quantities stay available
when only price is missing. A selected preferred supplier with no price is not
silently replaced by another supplier's price.

The derived result adds `priceMissing`. Missing prices and unsafe arithmetic
both retain null costs and `calculationUnavailable=true`; invalid nonblank
values are not mislabeled as missing. Existing recursive costs and totals
propagate those nulls, rather than returning a misleading partial estimate.
Formatting an unavailable estimate now says `Unknown`, since a null is not
necessarily a numeric range error.

The Postgres owner/AI projection also exposed a related identity mismatch:
catalog items used a location's control-number alias while recipe lines retained
the original item code. Recipe lookup could consequently skip the ingredient.
The read projection now maps recipe item codes through the same request's
catalog identities to location aliases. The former code-prefix fallback remains
for an unresolved item; broader missing-reference and recipe/unit compatibility
audits are still outstanding.

## Scope of the legacy helper and persisted prep costs

`_pg_item_derived` is used only by pre-cutover legacy prep writers. It now keeps
an absent price unknown, excludes unavailable suppliers and orders ties
deterministically. Existing writer preflight refuses the unknown cost before
any stock/log write. Existing feature/schema retirement guards and transactions
remain intact. Valid priced pre-cutover completion still works.

This helper retains its old global supplier-price and `base_per_purchase_unit`
divisor; it is not the location/recipe-portions read projection and must not be
reused for native costing. Active owner/AI reads use the location catalog via
`_pg_owner_view` and `item_derived`. No native prep-cost policy, historical prep
cost rewrite, missing-input zero valuation or new deduction rule is introduced.
Persisted native prep costs still need an explicit policy before a writer change.

Purchased-item physical counts, received purchase costs, explicit inventory
values, Food Cost, received-date rules, tax/fee separation and explanatory track
boundaries remain unchanged. No migration, hosted connection, permission,
credential or hosting change is included.

## Validation and evidence limits

| Run | Result |
| --- | --- |
| Focused offline price/range checks | 11 methods plus 49 subtests: **60 reported cases passed**, zero failures/skips. |
| Full selected offline profile | **804 of 806 reported cases passed**; two Windows PowerShell-dependent permission checks timed out. No skips. This is not an all-green run. |
| Focused disposable PostgreSQL rerun | 20 methods plus 13 subtests: **33 reported cases passed**, zero failures/skips. |
| Documentation/source contracts | Generated review guides match source; diff whitespace checks pass. |

The focused cases overlap the full offline profile and must not be added to it
as unique coverage. Pytest reports successful subtests separately; counts above
use the generated JUnit totals.

Fictional tests cover null/missing/whitespace prices, missing/unavailable vendors,
preferred-price preservation, zero and positive prices, invalid/overflow/tiny
values, nested recipe totals, estimated inventory/waste, native ownership totals
and AI text. Database checks cover a shared product's independent location price
and alias, no global-price fallback, zero/unknown/unavailable cost transitions,
unchanged Actual Food Cost reports, preflight tripwires for an unpriced later
ingredient, valid legacy completion and rollback after later SQL failures.
The selected runner includes the new offline module and four database cases so
CI exercises them.

The initial pre-fix regression run failed as expected, but also exposed a test
fixture's duplicate keyword construction. That fixture was corrected before the
passing focused run; the initial failures are retained as diagnostic evidence,
not counted as a clean regression baseline.

The two full-offline failures are:

- `BoundaryTests.test_private_directory_acl_and_no_overwrite_boundary`.
- `HostedAdapterGuards.test_private_input_acl_accepts_protected_windows_file_and_refuses_broad_grant`.

Both timed out starting the existing PowerShell ACL helper. Separate bounded
read-only probes of the bundled PowerShell and Windows PowerShell also timed out
on `Write-Output ready`. The operational permission helpers are unchanged. No
ACL bypass, mocked success or security-setting change was used to manufacture a
pass. Fresh Windows CI remains a gate before merge; these failures must stay
visible until resolved or independently validated.

The first broad database run was interrupted for progress diagnostics after
27 progress markers; it produced no final JUnit result and is not claimed as a
pass. The bounded rerun used live progress and completed all selected cases.
The interrupted run left one known disposable database. A separate guarded
cleanup verified its exact generated name, owner and absence of sessions,
removed only that database, and confirmed the database/role inventory matches
the original pre-test inventory. The owned local server is stopped. No hosted
connections were used by any tests or cleanup.

Evidence outside Git: `backend-price-parity-{before,targeted,offline}-*.log/xml`,
`backend-price-parity-db-*/database.log`, the completed run's `database.xml` and
`receipt.json`, `backend-price-parity-shell-startup-20261016.json`,
`backend-price-parity-disposable-cleanup-20261016.json`, and
`backend-price-parity-validation-20261016.json` with source hashes and test
receipts. Earlier passing frontend tests/build and PR38 hosted acceptance are
historical evidence. Frontend source is unchanged here; no new frontend build,
GitHub CI or hosted acceptance is claimed for this local candidate.

## Next gates

1. Prompt the owner before publishing this as a draft PR, including the two
   local environment failures in the review package.
2. Independent review and exact-head CI, including the existing Windows ACL
   checks and disposable database profile; owner merge approval remains separate.
3. After deployment, perform a scoped fictional backend-summary/AI-context
   acceptance check and compare protected accounting data. No external AI call
   is needed merely to inspect the supplied context.
4. Continue missing-reference handling, unit/cost compatibility, aliases, par
   basis and historical portion mapping. Structured conflict codes and runtime
   role cutover remain separate work. UI/authentication/shared integrations
   remain deferred as agreed.
