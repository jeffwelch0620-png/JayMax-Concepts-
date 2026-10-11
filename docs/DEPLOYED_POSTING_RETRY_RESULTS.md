# Deployed invoice and credit retry results

The existing Render API passed the approved fictional Bert's replay on
October 11, 2026, completing at approximately 1:15 PM EDT. **Eight exact
original-key retries returned HTTP 200 with the original batch and document;
eight conflicting retries returned HTTP 409.** Independent readback after
every request and at completion preserved the accounting control:

**$184 opening + $173 net received food purchases - $145 closing = $212.**

## Execution and responses

The [prepared procedure](DEPLOYED_POSTING_RETRY_PLAN.md) ran against
`https://jaymax-api.onrender.com`, the existing Render service verified Live at
`b2f529fc59f2c10eb62376884ebc3a7a5fe22601`. The accepted frontend was
`4855ba6`, serving `main.7e3cd424.js`. The operator signed in through the normal
owner login endpoint using the private local prompt. Credentials and token
stayed in process memory and are absent from the receipt and Git.

All four original document versions, request bodies, fingerprints and command
keys were verified before posting. Two sequential rounds used separate HTTP
client connections. Each original then received a changed-note probe with its
original key and an unchanged-body probe with a distinct key. There were exactly
**16 HTTP posting requests**; no transport retry or concurrent extension ran.

| Original document | Exact responses | Changed body | Changed key | Saved batches | Lines / food facts |
| --- | --- | --- | --- | --- | --- |
| TEST-ONLY-PFG-20261010-03 | 2 x 200 | 409 | 409 | 1 | 2 / 2 |
| TEST-ONLY-USFOODS-20261010-04 | 2 x 200 | 409 | 409 | 1 | 1 / 1 |
| TEST-ONLY-PFG-RETURN-20261010-05 | 2 x 200 | 409 | 409 | 1 | 1 / 1 |
| TEST-ONLY-PFG-PRICECREDIT-20261010-06 | 2 x 200 | 409 | 409 | 1 | 1 / 1 |

Every successful retry returned the original batch identity. After each response,
a fresh read-only PostgreSQL transaction verified all four original outcome
graphs, and a deployed document GET confirmed the original version, posted
status and batch. The production routes used normal owner authorization.

## Preservation evidence

All **79 protected purchasing, Actual Inventory, prep and public store-state
tables** retained their row counts and whole-row hashes. Migration ledger
identities and the complete October 1-8 report matched the accepted baseline
before the requests, after each response and at final readback. The full-report
SHA-256 remained
`e85c53b4edb66eb34f0ffa5c52f40bbdbbc72557e8d05f212d5b70e703321d66`.

The checks preserve received dates, physical-return and price-credit links,
explicit count values, separate taxes/fees and prep/history records. Each
document retains one original batch and its expected 2/1/1/1 lines and food
facts. **No new invoice, credit, count, prep or purchase outcome was created.**
The 79-table comparison does not claim coverage of every catalog or
authentication table; normal sign-in is outside that protected scope.

The local receipt, retained outside Git, is
`deployed-http-replay-20261011T164444405480Z.json` (33,902 bytes), SHA-256
`0a448e0c1116529a091369468bb6a6e8c89890cb21ea7d41157dd4b4e58ccea0`.
It contains all 16 responses, independent per-request preservation checks,
deployed document readback flags and the final accounting comparison.
The default runner remains read-only; its five offline control checks are
recorded separately from these deployed results.

## Remaining acceptance

This completes deployed HTTP replay of existing outcomes. It does not establish
browser recovery after a lost first-post response, concurrent first posting,
session-expiry recovery or independent employee authorization. The browser trial
needs a separately reviewed fictional unposted fixture and a controlled method
that loses the response after server commit. Disconnecting before transmission
would test an unsent request instead. Already-posted documents cannot exercise
the initial review form, and the four accounting controls must remain intact.

The next step is to prepare that fixture, its expected accounting effect and
the response-loss method for review before creating or posting it. Current
Render hosting, Supabase connections, schema and database roles are unchanged.
Broad UI rework, connection architecture and reviewed fixture cleanup remain
separate workflows. These results and the README are saved locally; no new PR
or push accompanies this checkpoint.
