# Backend and frontend monetary planning completeness

October 17, 2026 (America/New_York). Baseline implementation: owner-approved
PR43 merge `0cf5464019592979e7f9242591c5ddaeea6eeec8`, plus the local PR43
live-acceptance documentation. The owner authorized auditing and fixing the
remaining F03/F03b monetary readers, local testing, and preparation of a draft
PR. Prompt before publishing that PR. Review, CI, merge and hosted acceptance
remain later gates.

## Findings and resulting behavior

| Evidence at the baseline | Local correction |
| --- | --- |
| Backend `calc_ppu` and shared frontend `calcPortionsPerUnit` divide incompatible measures numerically. Missing/zero quantities can become zero portions and zero cost. | Require positive pack and portion quantities and supported units in the same family. Unknown conversion stays unavailable, including with an explicit free supplier price. Valid free prices remain zero when conversion is complete. Each pack factor must be positive; two negative factors cannot cancel. |
| Backend `recipe_cost` skips missing item references and returns zero for missing/cyclic prep. Missing or zero prep yield defaults to one. | A read-only summary returns `totalCost`, `complete` and `issues`; missing/ambiguous sources, wrong source units/type, nonpositive quantities, cycles and depth over 100 hold the whole affected recipe estimate. The numeric wrapper remains for existing callers. |
| Backend owner projection erases null menu price and null/zero prep yield; recipe lines lose their canonical item key and explicit unit. | Preserve null/zero evidence and decimal text for price, yield and ingredient quantity. Retain canonical item identity and units. Supplied canonical keys are authoritative, including when a display alias is stale; an absent canonical key cannot fall back to an alias. Only unique scoped alias-only references resolve. |
| Owner summary can average only the menus with known selling prices, giving a partial percentage without coverage. AI context omits recipe-completeness reasons. | An incomplete percentage set has no average. Individual recipe rows retain completeness/reasons; context states Unknown and review reasons. Native accounting values continue to come directly from the native reader. |
| Unmapped adjustment records disappear from waste totals; nullable values can be added/formatted as zero in the legacy adjustment panel. | Unknown mapping, quantity, basis, reason or cost propagates to the relevant removal total. Preview, history and aggregate values show Unknown. Native historical adjustments remain unvalued and read-only. |
| Legacy report spending uses truthiness, replacing explicit zero extended price with quantity times price. Its quantity/cost arithmetic can also hide missing evidence. | Preserve explicit zero, use bounded nullable arithmetic, and retain unknown costs. Legacy recipe expansion refuses missing/ambiguous references and broken prep graphs; missing current-menu sales quantities stay unknown. Native PR43 expected-sales computation remains independent and quantity-only. |

Shared frontend recipe costing also isolates malformed ingredient records rather
than throwing, refuses duplicate identities, and no longer labels every missing
price as arithmetic overflow. Numeric planning inputs accept scalars, not arrays
or coercible objects. An estimate becoming Unknown does not edit its stored
catalog, recipe, supplier price, conversion or historical data.

## Boundaries and remaining audit work

These are current catalog/recipe planning estimates using bounded floating-point
arithmetic. They are not exact invoice accounting or historical consumption
snapshots. No new density conversion, physical factor, unit alias, par basis or
historical recipe version is inferred.

Native Track 1 remains purchased-item explicit opening value plus received food
purchases minus explicit closing value. Taxes/fees stay separate. Neither prep
nor sales deducts from or revalues that baseline. Legacy prep write holds and the
native dashboard/adjustment routing stay in place. Stricter shared helpers can
refuse an incomplete legacy prep cost before a write; they do not enable a writer.

Legacy reports retain their existing count/purchase-unit conventions and saved
period coverage limitations. They do not become native accounting or complete
Toast evidence. Legacy unmatched-sales recovery/source coverage is not promoted
to the native PR43 contract in this slice. F04 par basis, F05 explicit aliases,
F06 versioned Toast evidence, restricted operational runtime roles, and the later
UI/integration workflows remain separate. Existing build connections and the
credential-rotation deferral remain unchanged.

No hosted connection, database write, migration, deployment or new PR push was
used for this slice. PostgreSQL validation uses a dedicated disposable loopback
database with fictional data only.

## Validation and evidence

The final native-profile frontend run passed **994 tests across 79 suites**,
zero failures/skips. The strict production build passed (`main.f040d5a1.js`). CI
and ESLint are enabled and compiler warnings fail the build. The existing Node
`fs.F_OK` deprecation notice remains outside the compiler.

The final selected offline run passed **852/854 reported cases** (307 tests and
545 successful subtests), with zero skips. The two failures are unchanged Windows
ACL tests that time out launching PowerShell: `test_private_directory_acl_and_no_overwrite_boundary`
and `test_private_input_acl_accepts_protected_windows_file_and_refuses_broad_grant`.
Neither check was skipped, bypassed, weakened or counted as passed. Fresh GitHub
CI is required after publication; prior PR43 CI does not validate this candidate.

The initial disposable PostgreSQL run recorded **47/49 reported cases passing**;
two fixture assumptions failed. After supplying valid conversion metadata for
the existing free-price case and a selected supplier price for the new fixture,
the targeted rerun passed **6/6 reported cases** (two tests plus four subtests).
This resolves those initial failures; the original evidence is retained. Other
passed cases include legacy cutover/atomicity guards and explicit-value accounting
isolation. Both runs preserve database/role inventories and stop their owned
loopback server. No hosted connection is used.

External evidence uses `monetary-*` names in the sibling work directory and is
excluded from Git. Reports list tests and subtests separately; the totals above
do not represent distinct test methods or a newly rerun full database CI profile.
The final `monetary-validation-20261017.json` receipt records evidence/source
hashes, counts, fixture reruns and explicit limitations. Generated review guides,
updated relative documentation links and whitespace checks pass.

The owner dashboard's store and group purchase displays also preserve Unknown
versus zero. Both native and legacy display cases are checked; native accounting
readers and exact stored amounts are unchanged. Unit fields must be supported
strings rather than array/object coercions. The earlier 989-test run and strict
build (`main.df2df4c3.js`) passed before these final display/shape checks; that
earlier asset is not the final candidate.

Initial checks exposed a canonical-versus-stale-alias compatibility regression,
which was corrected while preserving canonical authority. A new component test
was moved to the repository's existing React DOM test harness instead of adding
a testing dependency. Existing backend test fixtures were made internally
consistent: unique local identity, explicit prep type/yield unit and adjustment
reason; a free-price assertion now supplies a valid conversion. The new database
fixture explicitly prices its selected location supplier before asserting a
complete estimate. Initial failed runs remain retained rather than overwritten.

The PR43 live checkpoint is separate evidence for the previously deployed code.
This new local source has not been deployed or live-tested.
