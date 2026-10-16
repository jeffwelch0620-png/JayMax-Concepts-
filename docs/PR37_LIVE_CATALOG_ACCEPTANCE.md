# PR37 merge and live catalog acceptance checkpoint

October 16, 2026. The owner approved merging PR37 and continuing the labelled
save/reload walkthrough. The approved head was `64531d0f2b50b7b019e404574e09db60b40f49a9`;
it was marked ready and merged normally as
`91a89f73141c8965a9784579aac9bc2de51da468` at 05:02:33 UTC. No merge bypass was
used. All four approved-head checks passed, and all four
[merged-main checks](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/38853713570)
subsequently passed too.

## Deployment verified

Both Render services were observed Live on the merge:

| Service | Deployment | Trigger | Duration |
| --- | --- | --- | --- |
| JayMax-Concepts- frontend | `dep-db8qvqrncjis73f0tri0` | Auto-Deploy | 33.7s |
| jaymax-api | `dep-db8qvqrncjis73f0tr3g` | Auto-Deploy | 1m52s |

The public API health request returned `status: ok` and `database: connected`.
A fresh Inventory page at `?pr37=91a89f7` loaded `/static/js/main.e7b26ed1.js`
and displayed the native owner summary. The older PR36 page still loaded
`main.dd9e36a7.js` after attempted refresh; existing-tab navigation reported
`ERR_ABORTED`. No successful all-tab refresh is claimed. The owner was asked to
preserve drafts, then refresh or close the older Inventory tabs.

## Acceptance continuation

The owner clarified that the sign-in rejection was in Chrome and the in-app
browser was working. Refreshing the PR37 in-app page restored the owner session.
The refreshed 17:48 UTC baseline again preserved 82 protected relations and the
historical $212.00 report, with no PR37 fixture. All later writes use the ordinary
owner UI and only the explicitly labelled Bert's fixture below.

The exact ordinary-decimal creation, large-pack amendment with price cleared,
separate large-price save, fresh-page read and name-only save passed their
independent comparisons. All seven large fields returned the exact 401-digit
fixed representation of `1e400`, using text inputs. Planning remained unavailable
without Infinity or NaN. Both stored catalog conversion factors remained
`2.510440466668191`; these are existing catalog factors, not new verified
physical inventory profiles. Count/order/sales participation remains off.

The first all-fields large save and its one explicitly reviewed retry were
refused with a generic conflict message. The unchanged database retained one
price event and the original item. Source review identified the existing
supplier-pack safeguard: a pack change requires a null planning price, followed
by separate price review. Saving with the price cleared succeeded. The generic
409 text obscures this actionable instruction and is a follow-up UI/error
mapping finding, not a reason to weaken the server guard. Later pack amendments
follow the same two-step workflow. No extra successful save is counted for the
refused attempts. In-place reload calls did not visibly reset the existing
workspace; the persistence evidence uses a newly opened app instance explicitly.

All seven tiny values returned exact 402-character fixed representations of
`1e-400`; they remained positive in PostgreSQL. Planning stayed unavailable,
without Infinity/NaN. The `1e-513` par was refused twice, retained exactly in the
draft, and exposed the specific 512-place resource-limit message. One visible
Sonner notification was captured on the second refusal. Independent rejected
checkpoint comparisons match the tiny checkpoint's complete protected relation
hashes and store revisions. Ordinary metadata and scaled-zero par were then
restored with the price cleared, followed by a separate `0E-10` price save.
A fresh app instance returned the original exact pack/portion decimals and
10-place zeros for par and supplier price, with all three participation flags
false. The known-zero preview displayed $0.00 without a range notice. Its
unmodified inspection draft was cancelled; the saved fixture remains for reviewed
cleanup. The tests use fresh-page persistence; successful in-place reload is
not claimed.

Ten successful read-only checkpoints, including the final fresh read at
18:10:08 UTC, covered the baseline and nine subsequent stages. The single held
large-save expectation and two earlier baseline reads remain separate evidence.
The final expected delta is exactly eight successful catalog revisions and
seven immutable supplier-price events, including three price-clear events.
All pre-existing protected rows across 82 relations, other locations, legacy
store payloads, physical unit profiles, purchase/prep/count history, the exact
source-index presence, 55-row ledger count and complete historical $212.00 report
are unchanged. These checkpoints do not re-prove ledger identities or the full
index definition; the separate maintenance postflight records those checks.
No purchase, stock movement, physical count or prep operation was submitted.

Final fixture: `berts_SB-005`, name
`TEST ONLY Catalog Inputs - PR37 20261016 - renamed`, US Foods SKU
`TEST-ONLY-CATALOG-PR37-20261016`, supplier identity
`e4ded40c-de56-4f53-928d-a1604f831aa1`. Item/supplier pack count is
`1.123456789012345678`, quantity per pack `2.234567890123456789 lb`, portion
`0.0000001 oz`, par `0.0000000000`, local planning price `0.0000000000`.
The global supplier price/source remain null. No verified native physical
conversion or inventory scope was added.

This completes the scoped decimal-input/feedback walkthrough, with the two
remaining findings below. Legacy batch atomicity/retirement are local/CI evidence;
they were not exercised by reopening hosted legacy routes. Chrome login remains
unresolved; the owner confirmed it was separate from the working in-app session.

## Follow-up findings

The owner subsequently authorized the focused local fixes and testing in
[Missing planning prices and supplier pack feedback](PLANNING_PRICE_AND_PACK_FEEDBACK.md).
Local validation passed; publication and hosted acceptance remain separate.
The findings below preserve what the deployed PR37 walkthrough established.

1. **Supplier-pack refusal reason is hidden.** Every HTTP 409 currently becomes
   the generic collaborator-conflict message in `useStoreState`. The applicable
   supplier-pack guard instead needs the user to clear the price and review the
   new pack and price. Preserve the refusal while exposing safe, actionable
   server guidance; retain generic conflict recovery for actual revision races.
2. **Missing planning price still displays as known zero.** With the ordinary
   pack restored and the supplier price blank, both the editor's cost-per-portion
   preview and item list showed `$0.00`. DOM readback confirms the input was blank,
   with no unsupported-range notice. `itemDerived` calls
   `planningNumber(pref.price, 0)`, or uses zero when no preferred supplier exists.
   This is the remaining missing-cost consistency issue, separate from PR37's
   overflow/underflow protection. Unknown price must remain distinct from an
   explicitly entered `0E-10`. Actual purchased-inventory accounting did not change.

These are recorded recommendations only; no production fix was made during
the live acceptance task. Evidence includes the blank-price screenshot and
the retained invalid-input/single-notification screenshot outside Git.

## Earlier interruption and read-only sign-in diagnosis

The fresh page opened the Bert's workspace. Browser control timed out while
opening Item Setup, before any fictional data was entered or submitted. After
reconnection the same PR37 page showed the normal expired-session sign-in
screen. Owner sign-in was requested, with credentials kept out of chat.
No PR37 fictional item, supplier, price event or inventory transaction has
been created by this walkthrough at this checkpoint.

The owner subsequently reported an incorrect-login/password message. Read-only
diagnostics at 17:43 UTC confirmed the API health endpoint remained connected
and the expected owner account existed exactly once with its owner role and a
structurally valid password verifier. This does not verify the submitted password
or prove the verifier is unchanged. No password material was emitted, and no
credential was reset. PR37 did not change login/password verification. The
accessible PR37 tab still showed only the expired-session notice; the exact
rejection and browser where it occurred need confirmation before diagnosing the
cause. Live writes remain pending successful owner sign-in.

The first read-only baseline covered 82 protected relations and confirmed
the unchanged historical $212.00 Food Cost report. It found no PR37 fixture.
Because the browser interruption caused a substantial delay, that baseline
must be refreshed before later test writes. Read-only observations verify TLS,
designated project, read-only transactions and closure of their own connections.
The baseline was refreshed at 17:38 UTC with the same 82 protected relations,
unchanged $212.00 historical report, and zero PR37 fixtures or price events.

## Planned sequence and controlled adjustment

1. Complete owner sign-in and resolve older tabs; verify the PR37 asset again.
2. Take a fresh protected-row/count/purchase/prep/unit-profile baseline.
3. Through the UI only, create one Bert's item named
   `TEST ONLY Catalog Inputs - PR37 20261016`, supplier SKU
   `TEST-ONLY-CATALOG-PR37-20261016`. Keep count, order and sales flags off.
4. Check ordinary exact decimals and scaled zero; then save large supported
   values, re-read, and perform an unrelated name edit without losing metadata
   or stored conversion factors. Check tiny positive values remain exact and
   planning estimates are unavailable rather than false zero.
   Supplier-pack changes clear the planning price first, then save its reviewed
   new price separately. This adds three successful saves and corresponding
   price-clear events to the original five-save/four-event plan: final expected
   delta is eight revisions and seven price events.
5. Submit an out-of-range literal such as `1e-513`: confirm specific feedback,
   a retained draft, one visible notification, and unchanged rows/revision.
6. Restore ordinary fictional pack/portion metadata and a known zero planning
   price; verify its meaning and clear test drafts. Re-read after reload or a
   fresh app page, distinguishing those two evidence types accurately.
7. Compare protected rows, price-event provenance, verified physical profiles
   and the complete historical $212.00 report after each relevant step.

No retired prep endpoint will be reopened for hosted testing; SQL failure
injection and atomicity acceptance remain disposable-test evidence. No
credential, connection, hosting setting or schema change is part of this task.

Evidence outside Git: `pr37-merge-receipt-20261016.json`,
`pr37-merged-main-ci-20261016.json`, `pr37-catalog-before-*.json`,
`observe_pr37_catalog_live.py`, and `pr37-live-signin-required-20261016.png`.
The external observer now checks exact numeric values for each phase, expected
row/event/revision counts, unchanged pre-existing row hashes, unchanged prior
price events and stored factors, separate global/location price provenance,
all other restaurants and legacy store payloads, and the complete original
closed-period report. Evidence for the refused large-save expectation is retained
as held; it is not counted as a passing large-value save.

Combined offline-verified receipt: `pr37-live-catalog-acceptance-20261016.json`,
SHA-256 `cefbc287b7a775ea2cb4608fdb3af253089de671c27f55350033d659d570150d`.
It pins all ten passing observations and their hashes; an offline pass also
verifies the exact numeric values, original item/supplier identity, final name,
revisions and event counts in the retained reports. Browser evidence is
`pr37-live-ui-evidence-20261016.json`; screenshots include
`pr37-restored-catalog-readback-20261016.png`,
`pr37-invalid-decimal-held-20261016.png` and
`pr37-blank-price-preview-20261016.png`. These artifacts remain outside Git.
No frontend/backend suite was rerun for this documentation-only continuation;
the merge CI counts above remain the code-validation evidence. `git diff --check`
and local evidence checks cover this record.

## Shared progress report

At the owner's request, [Inventory App Integration Workflow](https://chatgpt.com/space/page_1e9f0baababc8191a6f628ce4799af7a)
was refreshed through PR37 with PR27–37 changes since its October 14 update,
backup/index execution, scoped recovery results, current CI/deployment and
remaining gates. The build-progress hub points to that current report. Targeted
readback verified the updates and unchanged historical workflow blocks.
