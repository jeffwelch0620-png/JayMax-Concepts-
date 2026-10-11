# Deployed posting retry preflight

Read-only preflight passed on October 11, 2026. The approved deployed HTTP test
is waiting for the operator to sign in through the private local prompt.
**Zero invoice or credit HTTP posting requests have been sent.**

## Deployment and source

The Render dashboard confirms the existing `jaymax-api` service is Live at
`b2f529fc59f2c10eb62376884ebc3a7a5fe22601`, serving
`https://jaymax-api.onrender.com`. Its health endpoint returned HTTP 200 and
reported the database connected. The accepted frontend asset
`main.7e3cd424.js` returned HTTP 200, matched its recorded SHA-256, and contains
the expected API origin.

The purchase and Actual Inventory sources at that deployed commit match the
prepared checkout after CRLF-to-LF normalization only. Raw working-copy and
Git-blob hashes are retained separately. An initial strict raw-byte comparison
held before any posting because Windows checkout line endings differed;
inspection confirmed no other source difference. Preflight was rerun successfully.
No backend redeployment or connection change was needed.

## Preserved controls

Fresh read-only transactions confirm the four original fictional Bert's document
versions, command keys and request fingerprints, one original batch per document,
and the expected **2/1/1/1 posting lines and food facts**. All **79 protected
purchasing/count/prep/store-state tables**, migration identities and the complete
October 1-8 report match the accepted baseline:

**$184 opening + $173 net received food purchases - $145 closing = $212.**

The prepared JSON request bodies reproduce their stored fingerprints after
serialization and model validation. Original request material remains local,
outside Git; no real supplier file was imported.

## Runner checks and remaining step

Five offline transport checks pass: retaining original identities and expected
responses, stopping after transport uncertainty, stopping after changed database
rows, refusing to post after cancelled sign-in, and read-only default execution.
All test HTTP traffic uses an in-memory mock transport. These are runner checks,
not evidence of a deployed posting response.

The private prompt uses the normal Inventory login endpoint. Password and token
stay in process memory and are excluded from receipts, Git and logs. Once the
operator signs in, the runner rechecks the baseline immediately before posting,
then follows the [deployed retry procedure](DEPLOYED_POSTING_RETRY_PLAN.md): eight
exact original-key retries and eight conflicting retry refusals. Each request
requires independent database preservation checks and a deployed document read.

The read-only preflight receipt is
`deployed-http-replay-20261011T164225956709Z.json`. The source and screenshot
hashes plus offline checks are recorded in `deployed-http-runner-validation.json`,
retained outside Git. Live replay remains pending; browser lost-response and
independent employee authorization remain separate acceptance workflows.
