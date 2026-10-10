# PR19 review amendment

## Problem and corrected behavior

The deployed item editor allowed an old form to overwrite a newer item after
polling advanced the restaurant revision. The first PR19 fix held every older
form, including new items and editors affected only by unrelated activity.
Review also identified the same overwrite risk in Recipe & Menu Costing.

Both editors now retain a copy of the saved record when opened. An ordinary
save checks that record against the current saved record. If it is unchanged,
the editor builds its write from the latest collection and supplies that
collection's revision to the existing store/server guard. If that record changed
or disappeared, saving stops and keeps the draft. The server still rejects an
unseen race between the read and write.

## Response to the four review findings

| Finding | Amendment |
| --- | --- |
| Recipe editor could overwrite a newer recipe | Retain the original recipe snapshot through navigation; compare it before saving and forward the expected revision through App to the store. |
| Item recovery required discarding typing | Add **Reload latest and keep my changes** to both editors. It reads current saved data and reconciles the original, local and latest values. Recovery stages a draft; it does not save it. |
| New item unnecessarily blocked by an unrelated revision | Append to the latest catalog using its next available control number and current revision. New recipes likewise append to the latest recipe list. |
| Retry after a 409 was not covered | Test conflict, refresh and retry together. A changed target record refuses a second write; an unchanged target permits a guarded retry while preserving unrelated records. |

## Recovery boundaries

Independent field edits can be combined. Competing edits to the same field
remain visible as named conflicts; the draft is retained. A user can accept the
latest conflicting value in the draft and retry recovery, or explicitly discard
the draft by cancelling the item form or loading the saved recipe. Conflicting
local values are never silently preferred over newer saved values.

Item type, pack, portion and supplier details are reconciled as one group.
Activation and catalog participation flags form another group. Recipe type,
ingredients and batch yield are reconciled together. Supplier and ingredient
arrays are atomic, avoiding positional reassignment of row identities. These
groups deliberately refuse some edits that affect different fields but can
change the meaning of a conversion or recipe.

Recovery preserves latest noneditable metadata, exact supplier price strings,
and unknown supplier conversions. It never derives a conversion. Recipe
recovery revalidates against the latest ingredient and recipe collections. A
failed read, missing identity, changed identity, overlapping edit, or invalid
recipe leaves the draft intact. Late recovery reads cannot replace newer typing
or a remounted editor. Editor snapshots/revisions are private draft metadata and
are excluded from outgoing records. Confirmed recipe receipts retain canonical
database identities; later typing is not cleared by an older save receipt.

The store's revision refusal now refers to **latest saved data**, covering items,
recipes and periods without using period-specific wording.

## Validation

The focused amendment checks pass **125 tests across 7 suites**. They include
App-to-store revision forwarding, retained navigation, same-record and unrelated
409 retries, safe independent recovery, overlapping and coupled conflicts,
deleted records, fresh-read failure, canonical recipe identities, and late reads
or acknowledgements. All **553 tests across 65 suites** pass with the reviewed
native profile, and the strict production build passes with `CI=true` and ESLint
enabled. The live acceptance follow-up records release boundaries separately.

Initial new-test fixture failures and the corrected passing run remain in local
evidence; an older save-integrity test now verifies failure before polling and
refusal after a changed recipe arrives. No protection was relaxed to retain its
previous expectation that the stale recipe reached persistence.

## Release and remaining work

This amendment belongs to existing **draft PR19**. It does not approve a merge,
deployment, migration, hosting change or connection change. The original hosted
fictional tests and restored produce par remain recorded in the
[live acceptance follow-up](LIVE_ACCEPTANCE_CATALOG_EDITOR_FOLLOWUP.md).

After a separately approved merge and test deployment, repeat the two-tab item
check and add the equivalent recipe check. Include independent recovery,
same-field refusal, and an unrelated-refresh save. Independent posting retry
acceptance remains separate. Remove labelled fictional fixtures through a
reviewed cleanup before operational use, preserving the acceptance record.

Shared-PIN permissions, global revision scope, migration filename ordering,
operations tooling location, broad UI rework and deployment architecture remain
tracked in their existing workflows. This amendment does not establish that
every other writer is conflict-free: asynchronous legacy invoice closures and
same-field recipe metadata edits need their own focused review. The native
profile bypasses the legacy invoice purchase writer.

Track 1 remains the purchased-inventory accounting baseline, using received
purchase dates and explicit count values. Prep/waste and future sales analytics
explain that baseline without changing it; taxes and fees remain separate.
