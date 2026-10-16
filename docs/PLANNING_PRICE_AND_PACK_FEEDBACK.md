# Missing planning prices and supplier pack feedback

## Merged and live acceptance — October 16, 2026

PR38 merged as `3c58abd` from reviewed head `50e290d`, with approved-head and
merged-main CI successful. The frontend is Live on the merge; the API remains
Live on unchanged backend revision `91a89f7`. Scoped fictional blank/zero,
fresh-document persistence and retained pack-refusal checks passed. Seven
read-only checkpoints preserve accounting and the historical $212.00 control.
See [live acceptance evidence and remaining work](PR38_LIVE_PLANNING_PRICE_ACCEPTANCE.md).
The candidate/publication/deployment wording below records the earlier local
checkpoint, rather than current deployment status.

## Original local implementation checkpoint

October 16, 2026. Local follow-up to PR37 live catalog acceptance on merged
`91a89f7`, continuing from documentation checkpoint `379891a`. The owner
authorized these two fixes and testing, with a prompt before a new draft PR is
pushed. Publication, CI, merge and hosted acceptance are separate gates.

## Resulting behavior

Item Setup previously treated a missing supplier planning price as zero. The
shared item-derived calculation now retains null for a blank/missing price or
absence of an available supplier. Known portion quantities remain visible, and
the editor/list show Unknown cost. The editor explains that the supplier price
is unknown instead of incorrectly describing a missing price as a calculation
range error. Explicit `0`, numeric zero and `0E-10` remain known zero prices.
Unsafe calculations still remain unavailable even when a price is also missing.

Dependent planning costs retain unknown values, including estimated inventory
value and order exposure in the shared working-period report. That report's
separate no-supplier/blank-price fallback is removed too. This is planning display
and calculation behavior; purchased-item counts, received purchases and native
Actual Food Cost are unchanged. Other legacy price displays and missing or
incompatible portion/unit metadata remain part of the subsequent mapping audit.

The known item-save HTTP 409 refusal now explains: clear the planning price
when changing a supplier pack, then review the new price and physical conversion.
The draft and exact price/pack values remain retained. No price is automatically
cleared and no save is automatically retried. An explicit corrected save still
uses the reviewed location revision and the ordinary server command.

Only that exact known server instruction, for the items collection, receives
this treatment. Genuine revision races, unknown or structured 409 details, and
other collections retain the existing generic conflict recovery. Replaced
location/session guards and failed-receipt behavior remain intact. Server pack
policy, authorization, conversion checks and transaction boundaries are unchanged.
The exact-string match is deliberately narrow: a future server-message change
falls back safely to generic conflict recovery; a structured error-code contract
can be considered in a later coordinated API change.

## Validation

Focused validation passed 138 tests across five suites. Checks cover missing,
blank and unavailable supplier prices, genuine zero, preserved quantities and
exact source data, unknown dependent totals, range safety, real editor/list
display, specific pack-refusal feedback, draft retention and an explicit
price-clear retry with the original stored conversion factors and revision.
Other collections and unrecognized 409 details keep generic conflict handling.

The initial pre-fix regression run failed; its evidence is retained. Two cases
had a Jest table-shape mistake and three component assertions expected `80`
instead of the existing display `80.0`. The first post-fix run passed 133 tests
and failed those five test assumptions. Correcting the fixtures/assertions
produced the complete 138-test pass without further production changes.

Final full validation passed **879 frontend tests across 75 suites**, with no
failures or skips, using the reviewed native feature profile. The strict
production build passed with CI enabled, ESLint enabled and compiler warnings
treated as errors. The existing Node fs.F_OK deprecation notice is outside the
compiler. The build's frontend asset is `main.ef6f8f90.js`; it is not deployed.
Generated review guides match source and `git diff --check` passed.

No backend/database suite is claimed for these client-only changes. Backend,
SQL, CI/deployment configuration, connections, credentials and hosted records
are unchanged; no browser or hosted write test was performed for this candidate.

Evidence outside Git: `planning-price-pack-before-20261016.log`,
`planning-price-pack-targeted-20261016.log`,
`planning-price-pack-targeted-rerun-20261016.log`, and
`planning-price-pack-targeted-20261016.json`,
`planning-price-pack-full-frontend-20261016.json`,
`planning-price-pack-full-frontend-20261016.log`,
`planning-price-pack-strict-build-20261016.log`, and the combined source-hash
receipt `planning-price-pack-validation-20261016.json`. Local Node is v24.19.0;
the existing CI workflow uses Node 22. Earlier PR37 live and CI counts remain
historical evidence; exact-head CI for this unpublished candidate is pending.

## Next gates

1. Local validation, final diff review and documentation are complete.
2. Prompt the owner before pushing a new draft PR for independent review.
3. After publication, assess exact-head CI and obtain separate merge approval.
4. After deployment, exercise blank versus explicit zero and a refused supplier
   pack edit using the labelled Bert's fixture, then compare protected accounting
   data. Preserve the existing two-step pack/price review.
5. Continue expected-sales completeness, cost/unit compatibility, aliases, par
   basis and historical portion mapping. UI redesign, authentication and shared
   integrations remain separate workflows.
