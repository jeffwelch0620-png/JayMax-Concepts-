# PR43 live expected-sales checkpoint

October 17, 2026 (owner timezone America/New_York). The owner approved merging
PR43 and continuing live expected-sales tests. This checkpoint distinguishes
completed browser acceptance from pending recovery and database comparisons.

## Merge and deployment

Approved head `79b40ad5de60d91455ea2e642be053f80d86e3c5` passed all four
[reviewed-head CI checks](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/39079691163).
The draft was marked ready and merged normally with an exact-head guard as
`0cf5464019592979e7f9242591c5ddaeea6eeec8`. All four
[merged-main checks](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/39081925755)
passed. No administrative bypass or manual deployment was used.

Render automatic frontend deployment `dep-dba0tvvlk1mc73cdtd00` is Live on the
exact merge (28.9 seconds). The unchanged API remains Live on PR41 `84cb381`,
deployment `dep-db9c61oae00c738np400`. The existing Render session resumed through
normal GitHub sign-in; no permission, credential or hosting setting was changed.

## Fictional fixtures and completed cases

All edits use the normal owner UI at Bert's. No invoice, purchase, count,
physical profile, prep production/waste or period-close command was submitted.
The existing working period remains October 14 through October 20, 2026; all
pre-existing menu quantity fields remain blank as originally observed.

| Fixture | Identity and scope |
| --- | --- |
| Purchased catalog item | New local `SB-006`, `TEST ONLY PR43 Expected Sales - 20261017`; supplier SKU `TEST-ONLY-PR43-SALES-20261017`. Pack 1 each, portion 1 each, purchase unit each, supplier price blank/Unknown. Count and ordering flags off; sales tracking on. No physical stock or value was entered. |
| Menu | New `GR-002`, `TEST ONLY PR43 Sales Recovery - 20261017`; server ID `c3aa7f3c-7871-494d-9eaa-a0793e07edc9`. Two portions of SB-006 per sale. Description explicitly labels fictional test evidence, not POS data. Menu price and planning cost remain Unknown. |

| Case | Observed result |
| --- | --- |
| Original current-menu blanks | Existing mapped usage is Unknown, with named quantity guidance. Native sales has no physical-count or period-close controls. |
| New menu with blank sales | SB-006 expected usage is Unknown; its menu is named in the guidance. |
| Explicit zero | SB-006 shows 0.0. The unsaved-draft controls clear after acknowledgement; reload retains quantity 0 and usage 0.0. |
| Three fictional sales | SB-006 shows 6.0 portions. The save acknowledgement clears the draft controls without an alert. |
| Fresh-document read | A separate new document loads saved quantity 3 and usage 6.0. Other menu blanks remain Unknown. This proves the portion estimate does not require the fixture's supplier price. |

## Accounting evidence and its limits

Two SELECT-only database baseline attempts failed before relation fingerprints
were obtained: a TimeoutError, followed by InterfaceError. The second attempt
confirmed its own connection closed. No credentials, connection standard,
timeouts, services or security settings were changed to bypass the failures.
The observer submitted zero hosted write commands.

The live Actual Inventory history loaded the active October 1 to before October 9
closed control at **212.00 USD**, with saved report fingerprint
`b90d4c7d0326bb7193b74cc81cbeab95bf6a53ca7378222bfed3138282b180de`.
Its lines remain 24 lb produce / 54.00, 220 each appetizer / 45.00 and 40 lb
protein / 113.00. This is a browser before/after control, not an independent
82-relation database comparison. A separate fresh document read after the catalog,
recipe and sales saves returned the same 212.00 USD, exact saved fingerprint and
all three usage/value lines. Both screenshots/text are retained. This verifies
the displayed saved control, not all underlying live relations.

## Pending recovery case and cleanup

The saved fictional quantity 3 is intentionally retained for the next case.
To create a real unmatched menu ID through the UI, only the newly created
GR-002 menu and its ingredient line would be deleted. The application has no
normal menu restore action, so browser rules require separate confirmation at
the time of permanent deletion. The owner has been prompted with that exact
name and ID; no delete command has been submitted.

After confirmation: remove that test menu, verify its unmatched entry holds the
totals, cancel the first entry-removal prompt and verify preservation, then
confirm removal through the normal revisioned sales save. Reload to verify the
key is gone and unrelated menu values/dates remain unchanged. Record the final
accounting control. Do not delete any pre-existing menu or catalog item.

Live blank-orphan, malformed graph, lost-response and competing-save cases are
not claimed. Their named local component/helper checks and green CI remain
separate evidence. No new relay, local override, file access or temporary
browser permission is used in this test.

## Evidence

Retained outside Git in the sibling work directory:

- `pr43-render-frontend-live-20261017` screenshot/text and API deployment text;
- `pr43-sales-ui-before-20261017` screenshot/text;
- `pr43-accounting-ui-before-20261017` screenshot/text;
- `pr43-accounting-ui-after-core-20261017` screenshot/text;
- `pr43-fictional-item-saved-20261017.txt` and recipe saved text;
- `pr43-sales-blank-20261017`, zero/reloaded text, six-portions screenshot/text,
  and fresh-document screenshot/text;
- `pr43-fictional-menu-delete-review-20261017.png` for the exact pending action;
- `pr43-sales-before-20261018T002330936046Z.json` and
  `pr43-sales-before-20261018T002447506046Z.json`, preserving the failed database
  attempts. These filenames use UTC; the owner-facing date above is Eastern.

No source implementation change or new PR push is part of this live checkpoint.
