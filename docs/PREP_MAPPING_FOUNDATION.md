# Reviewed prep identities, units and recipe versions

Local implementation milestone, October 5, 2026. This implements the first step
of [the separate prep/waste design](PREP_WASTE_LEDGER_DESIGN.md): definitions and
reviewed legacy mappings. It does not record production, waste, prepared counts,
cost estimates or sales consumption. No operational migration or import has been
run. Existing prep/task/container writers are not yet replaced by this service.

## What is saved

`migrations/20261005_prep_mapping_foundation.sql` adds seven private tables:

| Table | Authority and relationship |
|---|---|
| `prep_inventory.products` | Stable store-specific prepared identity with a fixed canonical physical unit; separate from purchased raw item identities. |
| `product_versions` | Approved labels/evidence, predecessor and revision. Renaming appends a version; the identity and base unit cannot change through it. |
| `unit_profiles` | Explicit measured conversion for one prepared product version and measurement label. Updating a factor appends a version. |
| `recipe_versions` | Approved output identity/profile, entered usable yield, exact base yield, method, complete review snapshot/hash and predecessor. |
| `recipe_lines` | Exactly one purchased raw item or an approved prepared recipe/profile, entered quantity/unit, explicit factor, exact base quantity and source evidence. |
| `promotion_decisions` | Reviewer, time, matching review hash and frozen prepared ancestry graph. |
| `legacy_crosswalks` | Immutable complete legacy source snapshot/hash and its reviewed native recipe mapping. A source cannot silently switch to a different prepared identity. |

All definitions are immutable. Composite foreign keys confine relationships to
the store and product version. Revisions follow their predecessors without gaps
or forks. Recipe headers, all ingredient rows, promotion and any crosswalk commit
in one transaction. Deferred checks require a complete promotion and ingredient
rows matching the reviewed snapshot. Later ingredient/decision/crosswalk inserts
are refused, including after restore. Definition retries return the original
result only when both the request key and payload match.

Recipe approval locks the store and temporarily holds shared locks on legacy
item/recipe tables while validating and capturing source snapshots. This also
blocks a different store's edit to a shared catalog item until capture commits.
The lock can briefly delay legacy setup edits; remove this bridge only after all
relevant writers follow the native locking contract.

## Unit and yield policy

Prepared `each` is tied to its own product identity: a bag of eight appetizers is
not one individual purchased appetizer. Custom prepared measurement labels such
as bag or pan require an explicitly entered positive factor and evidence. There
is no default conversion of one. Nominal container capacity does not establish
actual fill; production/container recording remains a later step.

Purchased ingredients require an existing verified fixed unit in
`purchasing.item_bases`. This first step accepts physical ingredient units in the
same dimension only. The conversion must match the declared units, expressed to
12 decimal places. US liquid gallons/fluid ounces are the declared customary
basis. A nonterminating conversion must be explicitly entered at that precision;
the source quantity, declared factor and exact product remain frozen together.
No hidden quantity rounding occurs during multiplication. Purchase cases,
density-based weight/volume conversion and arbitrary raw container units are held
for a separate measured profile workflow; recipe portions are not substituted.

Prepared ingredients reference an approved producing recipe and a matching
product/unit profile. New reviews require current versions. Recursive ancestry
is preserved by immutable IDs; it is not flattened into another raw withdrawal.
A recipe graph returning to its own prepared identity is rejected, including a
return through an older recipe version. Mixed input dimensions are not summed
into one artificial mass-balance figure.

Review-needed status also follows the complete producing ancestry. If a raw
mapping, prepared unit, producing recipe or linked legacy source changes anywhere
in that chain, dependent recipes show the gap and new approvals are held until
the producing definitions are reviewed. An unchanged subrecipe ID alone is not
proof that its mappings remain current.

Missing, nonfinite, zero or negative yields/ingredient quantities are held. A
legacy recipe's missing unit or invalid numeric value remains visible in its
source snapshot, with an unresolved review issue. It is never repaired by an
assumed unit, zero quantity or yield of one.

## Manager workflow and API

Behind the prep setup flag, Item Setup has a **Prepared items and recipe review**
panel. Create a prepared identity, verify its units, then build explicit ingredient
lines and preview the usable yield. Approval requires separate confirmation of the
returned preview. Editing the form removes that confirmation. Network uncertainty
holds the form for an exact retry; stale/invalid reviews require correction or
refresh. A successful acknowledgment must match the identity/location and, for
units, the exact decimal factor; recipes must match the reviewed hash.

The panel shows legacy source gaps, changed source mappings, current recipe review
issues and prior identity/unit/recipe versions. Source hashes changing do not
rewrite earlier recipes. They mark definitions for a new review. Original legacy
rows and balances remain unchanged. Menu dishes are retained in the source review
but cannot be promoted as prep mappings; their sales mapping comes later.

All endpoints use `/api/pg/purchases/{store_id}` and existing explicit location and
manager/owner authority. Readonly users may inspect setup/history but cannot save
or preview approvals; staff and shared PINs cannot edit definitions. Login/PIN
redesign remains deferred.

| Method and suffix | Purpose |
|---|---|
| GET `prep-setup` | Current native definitions, stale review issues and complete legacy source snapshots; repeatable read. |
| GET `prep-products/{id}/history` | All identity, unit and recipe versions for the same-store prepared identity. |
| POST `prep-products` | Create an identity or append a name/evidence version with the current predecessor; request key required. |
| POST `prep-unit-profiles` | Append a confirmed unit conversion with the current predecessor; request key required. |
| POST `prep-recipes/preview` | Resolve exact identities/conversions/yield, source snapshot and ancestry; no writes. |
| POST `prep-recipes` | Confirm that preview hash and atomically save the approved version; request key required. |

## Enablement, accounting separation and recovery

Apply the foundation migration only after native purchased inventory and physical
unit migrations. For a build pilot, backend `USE_PG`, `PURCHASE_IMPORT_ENABLED` and
`PREP_SETUP_ENABLED` must be true; frontend native purchases and
`REACT_APP_PREP_SETUP` must align. New prep flags default to false. Missing schema
or disabled configuration gives an explicit unavailable result, with no legacy
fallback. This milestone has only applied the migration to disposable test databases.

Foundation writes never add or change actual purchase facts, physical counts,
explicit count values, legacy stock, prep logs or sales. The store coordination
row is used for locking. Track 1's existing count/received-purchase report remains
the accounting authority. Cost-source selection is still open and is unnecessary
for saving these definitions. Taxes/fees remain separately retained.

The backup implementation already covers every application schema dynamically.
Fresh invented-data recovery checks include all seven prep definition tables,
two recipe versions, promotion decisions and an original legacy crosswalk. Source
and restored setup agree, catalog/data checks agree, and immutability survives
restore. This is local PostgreSQL recovery proof, not a managed-platform rehearsal.

## Next step and remaining gates

The subsequent local quantity-only batch pilot is documented in
[PREP_BATCH_JOURNAL.md](PREP_BATCH_JOURNAL.md). It records production, nested source
lots and append-only corrections behind its own disabled flag. Waste, prep
physical counts and complete operational cutover are still pending. The rest of
this document describes the preceding definition-only milestone.

Build the atomic production event service against these approved versions. Then
add waste, prepared counts and aligned variance reports, replace every legacy
prep/task/container writer, rehearse event recovery and only then enable native
prep operations. The current setup flag enables definitions alone; it does not
turn legacy production activity into native events or certify its old balances.

Cross-store transfer accounting, business-day boundaries, raw container/density
profiles, container fill, batch cost-source policy, Scheduling/Operations handoffs
and Toast mappings remain explicit future work. Prior financial count policy and
Jeff/Jay/Rudd ownership boundaries are unchanged.
