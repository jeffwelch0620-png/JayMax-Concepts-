# PR38 live planning-price and supplier-pack acceptance

October 16, 2026. The owner approved PR38 merge and then authorized the fictional
live pricing/pack checks. Only the existing labelled Bert's catalog fixture was
edited. No purchase, count, prep, source-capture, migration, connection, hosting
or credential change was made by this test.

## Reviewed source and deployment

- [PR38](https://github.com/jeffwelch0620-png/JayMax-Concepts-/pull/38), reviewed
  head `50e290d52388c1500aa234401047acd8800ff99f`, merged through the normal
  protected path as `3c58abd0c1e5ee2893a8a99e6d0c6cd0c186563a`.
- [Approved-head CI](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/38952935696)
  and [merged-main CI](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/38956045976)
  completed successfully. Earlier local validation: 879 frontend tests across
  75 suites, including 138 focused cases, and strict production build.
- Render frontend deploy `dep-db97p13m8hqs73e69q20` was observed Live on the
  exact merge. The fresh app loaded `main.69f13db5.js`.
- API was observed Live on PR37 merge `91a89f7`. Backend, `render.yaml` and
  `.github` have no diff from that revision to PR38 merge. No manual deployment
  was triggered and no Render skip event is claimed.

## Fictional fixture and observed results

Fixture: `berts_SB-005`, `TEST ONLY Catalog Inputs - PR37 20261016 - renamed`,
US Foods SKU `TEST-ONLY-CATALOG-PR37-20261016`. Count, ordering and sales
participation remain off. It is a numeric test fixture, not an operational
pack or portion specification.

| Case | Observed result |
| --- | --- |
| Clear supplier planning price | Preview shows Unknown and explains the missing supplier planning price. Save completes; database stores null. |
| Fresh document after blank save | List shows Unknown, editor retains a blank price and known portions. No missing-price-as-zero display in this tested path. |
| Enter explicit `0E-10` | Preview shows $0.00. Save completes; database and fresh editor retain known zero, displayed as `0.0000000000`. |
| Change supplier Qty / Pack with zero price retained | Server refuses the save. UI says to clear the planning price, then review the new price and physical conversion; draft remains retained. |
| Refusal integrity | Draft retains `3.234567890123456789` and the original zero price. All protected relation hashes and revisions match the immediately preceding checkpoint. No automatic clear, retry, price event or conversion update occurred. |
| Cleanup | Cancel discards the refused pack draft. Final saved supplier quantity remains `2.234567890123456789`, planning price is zero, and original catalog/count factors remain unchanged. |

Fresh page reads used separate new documents, each visibly starting at the
Ownership Dashboard before selecting Bert's and Item Setup. The browser reload
call returned the same existing state without evidence of document replacement;
therefore an in-place reload pass is not claimed. The refusal's corrected
two-step pack save was covered by local tests; it was not repeated live here.

## Independent database observations

Seven SELECT-only checkpoints passed: before, blank, blank fresh read, zero,
zero fresh read, refusal and final cleanup. Each connects with certificate
verification, read-only default and read-only transactions; the observation
connections were closed. The observer issued no hosted write commands.

- The protected relation set remained at 82. All relations outside the explicitly
  permitted catalog/revision/history set match the baseline exactly.
- Unrelated catalog rows, pre-existing price events, legacy store-state payloads,
  other-location revisions, receipt totals, closures, migration ledger and index
  presence were preserved.
- Bert's revision increased exactly twice, for the blank and zero saves. Fixture
  price-history events increased from seven to nine. The refused edit and cleanup
  added none.
- Exact pack/portion/par values, participation flags and stored physical/catalog
  conversion factors were preserved; no global supplier price was introduced.
- The full historical Actual Food Cost report still matches the earlier pinned
  report, including **$212.00** Food Cost, count identities and report hash.

The first baseline attempt stopped before connecting because PowerShell startup
timed out during private-input ACL verification. A temporary external observer
then checked the same current-user owner and current-user/System-only allow
policy through read-only Win32 security APIs. Private path/reparse and target/TLS
guards remained active; unknown ACL formats fail closed. No ACL, credential,
global shell setting or repository operational helper was changed.

Evidence outside Git: `observe_pr38_catalog_live.py`, `pr38_readonly_acl.py`,
seven successful `pr38-catalog-<phase>-*.json` reports, the retained initial
held baseline report, and `pr38-blank-price-fresh-read-20261016.png`,
`pr38-zero-price-fresh-read-20261016.png`, `pr38-pack-refusal-20261016.png`.
The combined `pr38-live-acceptance-receipt-20261016.json` pins each successful
report's SHA-256. External evidence is not bundled into a public fixture or PR.

## Remaining sequence

1. Review backend `item_derived` and `_pg_item_derived` missing-price defaults
   and recipe/summary/AI consumers. Establish explicit unknown-cost parity;
   define persisted prep-cost behavior before changing any writer.
2. Coordinate typed conflict codes with safe compatibility for staggered
   deployment; other actionable catalog conflicts need the same contract.
3. Continue expected-sales completeness, unit/cost compatibility, aliases, par
   basis and historical portion mapping. Restricted runtime-role deployment
   remains required before operational release.

No follow-up production code, new PR, hosted schema application or broader
integration is included. UI redesign and authentication remain separate work.
