# PR44 live monetary completeness acceptance

October 17, 2026 (America/New_York; evidence timestamps use October 18 UTC).
The owner approved merging PR44 and continuing the live acceptance tests.

## Merge, CI and deployment

Reviewed head `8cb88863fb414625f6a6a7915472c6b46a5aaf7c` passed all four
[PR CI jobs](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/39092439592).
The draft was marked ready and merged normally with an exact-head guard as
`1729ecf91f0e0c6162c7b178cd9406bf7d47de47`. All four
[merged-main CI jobs](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/39093626977)
passed. No administrative bypass or manual deployment was used.

Render automatically deployed both services on that exact merge:

| Service | Live deployment | Observed result |
| --- | --- | --- |
| Frontend | `dep-dba3oou1egvs73dalrhg` | Live, 33.6 seconds |
| `jaymax-api` | `dep-dba3oou1egvs73dalrsg` | Live on `1729ecf` |

Existing owner sign-in worked in a fresh in-app document. No credentials,
connection standards, permissions, hosting settings or migrations were changed.

## Fictional scope and observations

All writes used the normal revisioned owner UI at Bert's. The only new recipe is
**GR-002, TEST ONLY PR44 Monetary Completeness - 20261017**, server ID
`1574e193-8642-4649-bb45-3d234ef45bfe`. Its description labels it fictional
acceptance evidence rather than POS activity. It uses **2.5 portions** of existing
`berts_SB-006`, TEST ONLY PR43 Expected Sales - 20261017. That item's supplier
planning price remains unknown; no catalog or supplier price was edited.

| Case | Live evidence |
| --- | --- |
| Missing supplier price | Ingredient unit/extended cost, estimated plate cost, food-cost percentage and suggested price show Unknown with named guidance. |
| Save and fresh document | The new saved row retains Unknown menu price and cost. Loading it in another document preserves blank price and 2.50 portions. A SELECT-only database read confirms `price IS NULL`, quantity text `2.5`, canonical item `berts_SB-006` and `uom=portion`. |
| Explicit zero menu price | A normal save stores price text `0`, and the saved list shows $0.00. Ingredient-dependent cost remains Unknown. This verifies a zero selling price, not a free ingredient. |
| Restore unknown price | A normal save clears the fictional menu price; final independent database read confirms NULL again. The ingredient and decimal quantity remain unchanged. |
| Blank fictional sales | The affected item has Unknown usage and names the new menu; blank quantities are not treated as zero. |
| Three fictional sales | 3 sales produce 7.5 expected portions without needing a supplier price. Unrelated blank-sales items remain Unknown; the overall incompleteness warning remains. |
| Independent sales read | A fresh document loads saved quantity 3 and 7.5 portions, with no unsaved-draft controls. |
| Final confirmed zero | The fixture is left at saved sales quantity 0 and 0.0 expected portions. Existing five menu inputs stay blank and the working period remains October 14–20. The database confirms the only saved sales key is this new menu's zero. |
| Ownership completeness | Bert's estimated recipe percentage is unavailable and the catalog/portion/price review warning is visible. Known recipe ranking rows remain visible. Received-food total stays $182.00 and valid zero estimated waste stays $0.00. Other location summaries remain separate. |

The initial browser save snapshot preceded the acknowledgement; a subsequent
visible toast and fresh-document/database reads confirmed success. A click aimed
at the transient sales draft-save control found it already gone after autosave;
no second save was submitted. A navigation/reload attempt on an older test tab
did not establish a fresh document, so the acceptance uses independently created
documents instead. No cancelled navigation is counted as a successful reload.

No purchase, physical count, unit profile, prep production/waste, period close,
reopening or deletion was submitted. The labelled menu remains available as
reference, with unknown menu price and confirmed zero fictional sales.

## Independent accounting comparison

Bounded certificate-verified, read-only transactions captured **82 relation
fingerprints** before and after the UI tests. Each connection verified
`transaction_read_only=on` and closed. Observer scripts issued zero hosted write
commands.

**81 protected relations are identical**, including catalog/supplier records,
purchasing, actual inventory and native prep facts. The expected changed
relation is `public.store_state`, containing Bert's analytical sales save and
revision. Other locations' state payloads/revisions are unchanged. This 82-table
set does not include `public.dishes`/`public.dish_lines`; the intentionally added
recipe is verified separately by its exact ID and line readback.

Purchase totals, active closures, migration ledger count, installed source index
and the historical full live accounting control are unchanged. Food Cost remains
**212.00 USD**. The independent live-report hash remains
`e85c53b4edb66eb34f0ffa5c52f40bbdbbc72557e8d05f212d5b70e703321d66`.
The saved closure/UI fingerprint remains
`b90d4c7d0326bb7193b74cc81cbeab95bf6a53ca7378222bfed3138282b180de`.
These identify different report representations and are compared separately.
The browser still shows 24 lb produce / 54.00, 220 each appetizer / 45.00,
and 40 lb protein / 113.00.

## Limits and next work

This accepts the deployed native recipe/projection, owner-summary and quantity
paths exercised above. Legacy prep writes remain retired/held. Legacy dashboard
variance/waste styles, conversion refusals, malformed graphs, incompatible units,
range cases and AI-context construction retain their local/CI coverage; they
were not forced through inactive live modes or a paid AI request. No malformed
hosted record was inserted to make a negative test possible.

Next is F04: select the par basis (purchased supplier units versus physical count
units), then make labels and conversions consistent without silently changing
existing values. Explicit aliases (F05), versioned Toast evidence/coverage (F06),
operational runtime roles, credential rotation and the later UI rework retain
their separate workflows. See the [field/unit audit](FIELD_UNIT_REFERENCE_AUDIT.md).

## Retained evidence

Private screenshots/text and SELECT-only reports remain outside Git in the
sibling work directory under `pr44-*`. The comparison and evidence-hash receipt
is `pr44-live-monetary-acceptance-20261017.json`. It records deployment/CI IDs,
the single recipe identity, final zero sales, null/zero price observations and
the accounting comparison. No screenshot or database report is published in Git.

This continuation changes documentation only. Relative-link checks, generated
review guides and whitespace checks pass; source suites were not rerun for the
notes. Reviewed-head and merged-main CI above validate the implementation.
