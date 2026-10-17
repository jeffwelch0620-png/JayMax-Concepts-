# PR42 scoped live Item Setup acceptance

October 17, 2026 (owner timezone: America/New_York). Deployed frontend baseline:
PR42 merge `c9262170ea5ff4817507f272e1b0d4686dd08d7c`; the unchanged API remains
on PR41 `84cb381`. Reviewed-head and merged-main CI/deployment evidence are in
[the field/unit audit](FIELD_UNIT_REFERENCE_AUDIT.md).

The owner completed normal owner sign-in in the Codex in-app browser. Reloading
the prepared test tab restored its authenticated session. The earlier Chrome
login rejection is separate and remains unresolved; no password, login policy,
permission or connection setting was changed.

## Fictional check

Used only Bert's existing `TEST ONLY Protein - UI 20261010`, local control
`WI-003`, supplier SKU `TEST-ONLY-PROTEIN-20261010`.

| Step | Observed result |
| --- | --- |
| Open saved editor | One 20 lb pack, 4 oz portion, supplier price 70; preview 80.0 portions per case and $0.88 per portion. |
| Change only unsaved Portion Unit to fl oz | Specific warning: "size unit and portion unit aren't the same measure type". The preview says portions and cost unavailable, with no numeric portion/cost result. Supplier price and stored catalog conversion remain displayed independently. |
| Cancel | Edit closes and blank New Item form returns. No Save Changes or Add Item was submitted. |
| Reload and reopen the same fictional item | Original 20 lb pack, 4 oz portion, price 70, 80.0 portions and $0.88 preview remain. |
| Final cleanup | Cancelled the reopened editor; no edit remains open. No relay, override, file access or temporary permission was used. |

The loaded Setup page also displayed the existing explicit count value 145.00
USD and net received food purchases 182.00 USD. These are UI observations, not
a fresh protected-relation comparison or a re-proof of the historical $212
Food Cost control. The check exercises a preview and cancellation, not saving
an incompatible item, every supported unit family or concurrent writers.

## Evidence and boundary

Text and screenshots remain outside Git in the sibling work directory:

- `pr42-fictional-mismatch-20261017.txt` and `.png`;
- `pr42-fictional-original-after-reload-20261017.txt` and `.png`;
- earlier PR42 frontend/API Render deployment text and frontend screenshot.

No application write command was submitted in this check, and no direct hosted
database access was used. This does not substitute for independent database
fingerprint verification. Track 1's implementation and data were not edited.
The next draft's expected-sales behavior is covered locally by 942 frontend
tests and a strict build; it is not deployed or live-accepted by this check.
