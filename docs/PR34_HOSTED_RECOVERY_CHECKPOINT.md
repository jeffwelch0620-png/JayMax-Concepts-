# PR34 hosted correction recovery checkpoint

October 15, 2026. The owner lifted the broad hosted-test hold and signed in to
the build app. This supersedes earlier hold wording for these scoped tests,
without approving maintenance, index installation or connection changes.

## Deployed source

[PR34](https://github.com/jeffwelch0620-png/JayMax-Concepts-/pull/34) merged as
`ce7eb273d56b14a80b5c2af7c8e7284bbfc6b6b7`, from reviewed head
`21e5d05b1e448ccd51ae3b92c1e12488ca00bfa1`. Its
[reviewed-head CI](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/38770563149)
passed all four jobs. Refreshed Render views showed that merge live on both:

- [Frontend deployment](https://dashboard.render.com/static/srv-dauh8qid0e5s73fo9e40/deploys/dep-db8g70nlk1mc73f1f61g).
- [API deployment](https://dashboard.render.com/web/srv-dauimuugekts73ek9lr0/deploys/dep-db8g70nlk1mc73f1f5j0).

Public API health returned HTTP 200 with the database connected. No deployment
or configuration change was initiated in this acceptance run.

## Live results

All writes used the ordinary signed-in owner UI, limited to Bert's fictional
invoice `TEST-ONLY-PR34-CORRECTION-20261015-16` and existing item
`berts_SH-003` / `TEST ONLY Appetizer - UI 20261010`. Received date was
October 15, outside the protected closed period. Both manual sources contain
one fictional $1 line with verified zero tax/fees; revision two changes only
the fictional supplier SKU from R1 to R2. No operational invoice was imported.

| Scenario | Observed result |
| --- | --- |
| Initial capture and receipt | Complete source JSON retained; one initial purchase, 1 each, $1.00. |
| Newer source invalidates an earlier preview | Previewed 3 each before capturing revision two. Submitting the stale preview was rejected with “Review the latest captured source version”; no correction was written. |
| Held request after same-tab reload | Reason, date, quantities, conversion and comparison returned in the retained panel. Explicit status read reported held; retry stayed disabled. |
| Cancel, then confirm held-request discard | Cancel kept the request. Reopening and confirming performed fresh status reads. Only the local retained request cleared; current source had to be reopened. No accounting/source record was deleted. |
| Competing correction | Two previews shared the initial predecessor. The 4-each correction saved first; the older 3-each submission was rejected. Reload and explicit status identified another request; retry stayed disabled. |
| Confirm competing-request discard | Reason and comparison remained visible; a fresh confirmation check preceded clearing only the stale local request. |
| Fresh review after discard | Reopening revision two loaded 4 each. A new preview for 5 each saved with a distinct request key and the first correction as predecessor. |

Final fixture: **one initial batch, two source versions, two corrections and
four correction lines**. Current facts are **5 each / $1.00**, received October
15. Source bytes, reversals and both decisions remain retained. Neither
rejected 3-each request became a correction.

Eight successful SELECT-only stage observations checked exact source fields,
fixture counts, quantities and costs. Across 82 protected relations, all
**630 pre-existing rows** were preserved, with store-state revision checked
separately. Added rows matched only the fictional fixture graph. Store payloads
remained equal; Bert's revision advanced 52 to 55 for one receipt and two saved
corrections; other store revisions stayed equal. Observer hosted write commands
were zero. Ordinary app audit activity is outside this accounting/prep inventory.

The full historical October 1–9 Actual Inventory report remains equal to its
baseline, with **$212.00** Food Cost and current report hash
`e85c53b4edb66eb34f0ffa5c52f40bbdbbc72557e8d05f212d5b70e703321d66`.
The immutable stored closure hash remains separately
`b90d4c7d0326bb7193b74cc81cbeab95bf6a53ca7378222bfed3138282b180de`.
The migration ledger stays 54 rows; the source-lookup index remains absent.

## Evidence and limits

Receipts live outside Git in the existing `usin/work` folder. Bound baseline:
`pr34-hosted-baseline-20261015T171657603560Z.json`, SHA-256
`c616aa76cd649d6877ba4c9861f88afc859cacb596e7ce4fb94a924c114cfbfd`.
Final readback: `pr34-live-fresh_review_saved-20261015T173318508287Z.json`, SHA-256
`caa0637c95ed01eed05ba3da7ff955394fc5a75ccf924eecba18ced92a8208b5`.
`pr34-hosted-acceptance-manifest-20261015.json` binds successful receipts, UI
snapshots, screenshots and observer source; SHA-256
`a8218ad1af86f118a0dbe76b010408929a619327fa702a69aa6aa8e5c7a90608`.
No private configuration is included in Git.

Two observer defects were corrected before acceptance: a live-report hash was
initially mistaken for the stored closure hash, and a SQL alias was read with
the wrong case. Failed receipts are retained and excluded from the eight passed
checkpoints. These were read-only observer errors, not app/database fixes.
A transient Invoice Master network error cleared through ordinary navigation.
Date inputs were verified from rendered DOM values after native entry.

This validates **live rejected-request, reload, status, discard and fresh-review
behavior**. It does not reproduce a dropped response after a successful commit,
an in-flight discard race, owner sign-out/sign-in recovery, browser restart,
tab closure, or distinct employee/manager identities. Prior local/CI results
are not live transport proof. No relay, Local Overrides, browser permission,
runtime source or SQL change was needed. Suites were not rerun for this
documentation-only checkpoint.

## Next steps and gates

1. Complete dropped-response correction testing only with supported, scoped
   transport controls and a reviewed fictional fixture plan.
2. Before the hosted index rehearsal, obtain a **new maintenance window**,
   stop confirmed writers and verify drain. Three activity samples showed zero
   write locks/counter changes, not a complete drain. Both Toast cron jobs remain
   enabled and the API remains running. Companion is local-only per the owner.
3. In that window, take a fresh encrypted backup, validate a disposable local
   restore, then present the exact additive-index plan for separate approval.
   Old backup/window evidence does not authorize index application.
4. Continue source-capture/manual-entry recovery and the remaining schema mapping
   audit. Preserve Track 1 independence, explicit count values, received-date
   posting and separate tax/fees. Prep/sales remain explanatory tracks.

Keep deployment/connections unchanged during build. Credential rotation and the
restricted deployed-role cutover remain separate deferred gates. Broad UI,
login/PIN redesign and Companion integration stay in separate workflows.
Prompt before pushing a new draft PR.
