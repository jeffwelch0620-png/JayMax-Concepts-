# PR35 hosted source-capture checkpoint

October 15, 2026. The owner explicitly approved merging PR35 and continuing live
recovery acceptance on the existing Render/Supabase build deployment. Tests use
labelled fictional sources in Bert's, without posting them into inventory.

## Merge and deployment

- PR: https://github.com/jeffwelch0620-png/JayMax-Concepts-/pull/35
- Reviewed/amended head: `7ae28dabb589075902d22d171baff910d1d12db4`.
- Merge: `edbf2321769ce9a6343d28483af8dbcee903a885`, October 15 at 20:50:47 UTC.
- [Amended-head CI](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/38791749350)
  and [merged-main CI](https://github.com/jeffwelch0620-png/JayMax-Concepts-/actions/runs/38805231168)
  completed successfully. The amended-head four required jobs passed. Local
  implementation evidence remains 789 frontend tests/71 suites, strict build,
  741 offline cases, and 38 manual/native cases (34 database + 4 parser).
- Render API service `srv-dauimuugekts73ek9lr0` is Live on the merge, deployment
  `dep-db8jpa4s728c73drp0kg`; frontend `srv-dauh8qid0e5s73fo9e40` is Live on the
  merge, deployment `dep-db8jpacs728c73drp130`.
- Fresh normal browser asset: `main.daae9d22.js`, 1,269,965 bytes, SHA-256
  `af40dbd8207755e4dceb6765a2db633c05e7fbe9a9d22f5c179525b1cb35d7cd`.
  An older tab still held the previous bundle; acceptance used a fresh tab with
  the verified current asset. Existing unsubmitted drafts were preserved.

## Completed normal capture and reload

The actual deployed UI captured `TEST-ONLY-PR35-%22A%22-20261015.csv` for invoice
`TEST-ONLY-PR35-LITERAL-20261015-01`. This checks a literal percent-encoded-looking
filename, not an actual double quote in a Windows filename. File bytes: 792;
SHA-256 `85f264f72a8345c32774de0d4c551cb4f06133002940d185c6f4ec393d146143`.

The request appeared in retained recovery before submission. Automatic saved
lookup opened the source and cleared that exact pending record. Reload did not
resubmit it; reopening the captured-file entry recovered the same source and
fingerprint. The fictional fixture has a $1 line and a $4 supplier total; it
correctly remains held for the unexplained $3 difference. Capture success does
not imply purchase approval. No received date, mapping or purchase confirmation
was submitted.

Read-only hosted verification confirmed:

- File `58667e21-bb5f-4c7c-bf1f-1a6645cd03fc`, exactly one upload attempt;
  version `b34a885b-5225-457e-909d-98ac7b0647ba`, no posting batch.
- One added row in each of the nine expected source-capture tables; all earlier
  row hashes retained. All other protected relation hashes unchanged, across
  82 protected tables in total.
- Purchase facts and store-state payloads unchanged. Historical Food Cost still
  $212.00; live report hash
  `e85c53b4edb66eb34f0ffa5c52f40bbdbbc72557e8d05f212d5b70e703321d66`
  and the complete historical report match the baseline. Its immutable stored
  closure hash is separately `b90d4c7d0326bb7193b74cc81cbeab95bf6a53ca7378222bfed3138282b180de`.
- Source index still present and migration ledger still 55 entries. Observer
  sessions use TLS verification and read-only transactions and are closed.

Evidence is under the private local build `work` directory:

- `pr35-hosted-baseline-20261015T205329959268Z.json`, SHA-256
  `1929ead499d660de44b9d8f526203dcc7a75f70805e3c55db01e15d29dcb04a2`.
- `pr35-live-normal_csv-20261015T211119511049Z.json`, SHA-256
  `7a500d957d21453d563b702d4a515e34540e8709a9d10dfa894860bf95a38fb9`.
- `pr35-live-normal-csv-dom-20261015.txt`, normal UI screenshot
  `pr35-live-normal-csv-20261015.png`, and
  `pr35-live-reload-normal-dom-20261015.txt`.

The observer initially stopped on an incorrectly cased SQL alias and a posting
field that is derived rather than stored on document versions. Those operator
script errors caused no hosted writes. The corrected complete observation above
passed; failed receipts are retained and are not acceptance evidence.

## Controlled manual transport case

The owner enabled Chrome's pinned Local Override and its yellow PR35 marker was
verified on October 15. The fresh read-only pre-transport checkpoint
`pr35-live-before_transport-20261015T225006035221Z.json` confirmed the earlier
normal capture and all protected accounting data remained unchanged.

The manual case used `TEST-ONLY-PR35-MANUAL-20261015`, registered supplier
`other`, one fictional $1 line, and no attachments. The first command was
physically truncated before forwarding: the API received zero capture requests.
Its actual status read returned no complete capture. Reload restored the tab's
manual request without automatically sending it or displaying a retry action.
An explicit new status read was required to expose retry.

The operator armed one retry and clicked the retained request's retry action.
The relay confirmed identical original JSON wire bytes and request key
`ceb8d9a6-1083-4843-95f5-7dfe8ba8e6c4`. The API returned HTTP 200, but only one
byte of its 4,094-byte acknowledgement reached Chrome before disconnection.
The subsequent actual saved-status read succeeded; the UI validated/opened the
manual invoice and cleared the pending record. One capture was forwarded, no
purchase posting route was available, and no second capture was needed to
recover the lost acknowledgement.

Transport receipt: `pr35-capture-relay-20261015T225001668967Z.json`; UI evidence:
`pr35-manual-before-reload-dom.txt`, `pr35-manual-after-reload-dom.txt`, and
`pr35-manual-recovered-dom.txt`. Independent post-case table/accounting
verification is a separate observation, not inferred from HTTP 200. It passed
at `pr35-live-manual_completed-20261015T225432980994Z.json`, SHA-256
`9a9bc7e22d61824ac72a007fe681d9e546b89bf443893270f48637ef015a9870`.
Manual file `06b96c21-4725-437f-8d9f-0f882eccbffd` has exactly one upload
attempt and source fingerprint
`b08df3ae5825a456721ee2c63872929a4d007adbc09767c6b227e818e0d7c2db`.
Version `9a5ef535-db10-40c7-8f2a-2889f00f461a` is unposted. Exact added-row
counts match just the earlier CSV plus this manual source; existing rows across
all 82 protected relations, purchase facts, store-state payloads and the complete
historical $212.00 Food Cost report are unchanged. The read-only connections closed.

## Remaining prepared transport tests

A temporary client-only override is pinned to the exact public bundle above.
Only four named fictional source-capture/status requests for Bert's can route
through an owned loopback relay. Purchase posting, other sources, other stores
and normal reads continue to the deployed API. The relay additionally checks
exact fictional file bytes or manual JSON, original UUID keys, allowed route,
origin and host, bounded attempts, and explicitly armed retries. Authorization
remains in memory only and is forwarded only to the original TLS-verified API.
No secrets are embedded in fixtures, public override or receipts.

Preparation passed 20 routing guards, JavaScript syntax, and 13 offline relay
gate tests. This is operator-tool validation, not additional product-suite or
live transport acceptance. The initial preparation started no listener. During
execution, an initial noninteractive launch stopped immediately on standard-input
EOF with zero requests; the subsequent owned interactive listener ran the manual
case above and has a 30-minute expiry.

The owned listener was explicitly stopped at **23:00:30 UTC** while awaiting
the CSV selection. Its receipt records `listenerClosed: true`, one forwarded
manual capture and zero file-capture attempts. No temporary listener remains.
Resume must preserve the recorded completed manual case and run only the three
remaining fictional file cases; do not repeat it with a new key. Chrome's
override remains a pending test setup, not a hosted deployment change.

### File before-save/sign-in case in progress

The owner subsequently selected the fictional file through Chrome's app control.
The enabled capture control and displayed filename were verified. The relay's
resume mode validates the SHA-256 of the stopped manual receipt and preserves
its key, counters and completed events. Fourteen offline relay guard tests now
pass, including refusal to repeat the completed manual capture. The new receipt
is `pr35-capture-relay-20261015T231936261165Z.json`, linked to its immutable
stopped predecessor; its listener started at 23:19:36 UTC with another 30-minute
expiry. This is a local test relay, not a new hosted maintenance window.

The actual file submission matched `TEST-ONLY-PR35-BEFORE-20261015.csv` and its
790-byte fixture fingerprint
`e563b73f4eb50e480d7441fd3a8e5c26b6840fbaac87bea0b5b1914c1a0f9721`.
Original key: `ac62fff6-ff76-4f7a-aa99-716614546aa1`. The relay dropped the first
command before forwarding; the real status route returned HTTP 200 and the UI
displayed its negative-read/same-request retry guidance. The recovery region
is saved in `pr35-file-before-signout-dom.txt`. Normal sign-out reached the
existing owner sign-in screen. Same-owner sign-in and exact reselection/retry
remain pending at this checkpoint.

The independent pre-retry observation passed:
`pr35-live-file_before_unforwarded-20261015T232146787666Z.json`, SHA-256
`5d4875d627c8fccf895caeb899c37526a69b29833972e2f4edfd73eb1034a78f`.
Its exact fixture set remains only the earlier normal CSV and manual source,
each with one upload attempt and no posting batch. The dropped BEFORE file has
no server-side file/attempt/version. All pre-existing row hashes across 82
protected relations, purchase facts, store-state payloads and the complete
historical $212.00 Food Cost report remain unchanged; read-only sessions closed.

Remaining cases: file loss before forwarding with same-owner sign-in and exact
reselection; file commit with lost
acknowledgement/status followed by reload; and a scoped fictional filename
mismatch with failed-then-confirmed local discard. Each must preserve inventory
facts and historical accounting, and no retry or rekey may occur automatically.

The in-app browser cannot intercept requests. Chrome Local Overrides were
enabled by the operator for these cases. Chrome's extension refuses automated
file selection. The owner reported enabling its file-URL permission, but
automation still refused selection; that permission state is not independently
verified. Browser security policy also blocked opening the extension settings
page. No alternate browser/internal API was used to bypass that block. The owner
was asked to select the exact fictional CSV through the app's own file control
and confirm its visible filename; an earlier reported manual selection left the
actual input empty and no file request was sent. Restore the temporary file-URL
permission along with the other test settings during cleanup.
Any temporary local-service permission
must be handled by the owner, then reset after testing. Stop the owned relay,
disable overrides, verify the normal deployed asset and record cleanup. Until
then full controlled-file acceptance remains pending.

## Scope and next gate

The earlier maintenance window is closed. No index application, migration,
writer suspension, hosting/connection change, role cutover or credential rotation
is part of this work. UI redesign and integration remain separate workflows.
Track 1 uses purchased-item counts and received purchases with explicit count
values; prep/waste and sales explain it, and taxes/fees remain separate.

Continue the controlled acceptance, record exact outcomes and any safe holds,
then prepare a focused fix only if a defect is demonstrated. Prompt the owner
before creating any subsequent draft PR.
