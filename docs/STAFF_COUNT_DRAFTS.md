# Staff quantity drafts and manager acceptance

Local build milestone, October 5, 2026. Default flags remain disabled. Apply
`20261005_staff_count_drafts.sql` after the native count, correction, scope and
physical-unit migrations in an isolated database first. No live application,
invoice import, deployment, commit, push or PR accompanies this milestone.

## Measured workflow

1. The manager issues a sheet from Actual Inventory's current purchased-item
   scope. Date, before/after receipt timing, raw inventory locations and the latest
   verified count-unit profiles are captured in an immutable sheet. Every item
   needs a current verified profile; no portion conversion or factor of one is
   guessed. An existing count or open sheet at the same scope/date/timing holds
   another issue. A rejected sheet may be replaced.
2. Staff open Counts through their existing location login or shared PIN. They
   enter quantities and evidence in the issued units. Blank is uncounted; a
   measured zero is entered as zero. They cannot supply values, change units/date,
   change scope, issue sheets or accept accounting counts.
3. A new submission creates a complete replacement set of draft quantities,
   retaining every earlier revision. It must match the exact latest review hash.
   Two counters cannot silently overwrite each other's submissions. Drafts,
   partial measurements and task completion do not write purchase/count facts.
4. The manager refreshes the latest submission, verifies all locations and
   quantities, enters each item's explicit total inventory value and confirms
   quantity/value evidence. Acceptance checks the current scope and profile
   revisions, complete quantities, exact item coverage and review hash. A changed
   catalog conversion, competing accounting count or later submission holds it.
5. Acceptance creates a complete accounting snapshot and its linked manager
   decision in one transaction. Failure rolls back both, including the count
   revision increment. Repeated requests use the same key/payload and return the
   saved result. Staff measurements remain linked to the accepted count. The
   manager may reject stale/unused sheets with a reason without creating a count.

The count date is the manager-issued physical measurement date; the server retains
submission timestamps separately. Current boundaries require counting before all
or after all receipts that day. A between-deliveries count needs a more precise
cutoff before period close. There is no assignment calendar in this milestone.

Count-unit factors retain up to 12 decimal places, matching native unit profiles.
Acceptance uses the original submitted quantities and issued conversion; managers
cannot quietly change the quantity in the value review form. Incorrect quantities
need a staff revision before acceptance. After acceptance, use the existing manager
recount/reopening workflow; staff cannot revise a finalized sheet.

## Accounting and isolation

Track 1 uses purchased items only. Draft submissions and rejection do not create
inventory value, received purchases, usage deductions or Food Cost. Only accepted,
explicit-value count snapshots can serve as opening/closing accounting counts.
Prep/waste and Toast sales remain separate explanatory tracks.

Staff writes are permitted only on the two new draft routes. Manager authorization
remains explicit on issue, history and decision routes, including development
configurations with blanket auth disabled. A token with the wrong role/location
cannot fall back to a PIN. PINs are neither retained nor included in audit hashes.
Counter names are self-reported with shared PINs; credential kind and signed-in
actor identity are retained separately. Login/PIN identity redesign remains a
future build and is not claimed as fixed here.

Store locks serialize issue/submission/acceptance against scope and unit-profile
changes. Acceptance also holds shared catalog rows while verifying units, because
item definitions can be edited from another store. Read views use one repeatable
read snapshot. Review records, quantities and decisions reject updates/deletes;
schema/table privileges are not granted to public clients. Database owners can
bypass application workflow by direct insertion; production role design remains
an operational enablement requirement.

New endpoints:

- `GET/POST /api/pg/actual-inventory/{store}/staff-sheets`
- `POST /api/pg/actual-inventory/{store}/staff-sheets/{sheet}/decision`
- `POST /api/pg/staff/{store}/count-drafts` (authorized sheet read)
- `POST /api/pg/staff/{store}/count-drafts/{sheet}/submit`

Frontend adapters map Papa Leoni's to the canonical `papa` store ID. Failed,
malformed or wrong-location reads show errors. Uncertain writes freeze their
payload and reuse the original key; a fresh read is required after a conflict.

## Validation and limits

Invented-data checks exercise immutable evidence, explicit-value acceptance,
partial versus zero counts, forbidden value/unit injection, stale scopes and
profiles, concurrent submissions/decisions, request-key replay/conflicts, role and
store isolation, rollback on failed review writes, shared-catalog edit contention,
and isolated SQL backup/restore of drafts plus accepted counts. UI checks cover
fixed units, manager review, failed reads, mismatched acknowledgments, exact retries
and late location responses. The cumulative review package distinguishes current
runs from preserved older evidence; no browser visual or managed-platform recovery
proof is claimed.

The whole-database native SQL backup includes these three new private tables.
Legacy JSON backup is not a substitute. Test database files remain outside the
synced workspace under Local AppData; the old stopped folder remains preserved.

This first workflow uses one full scope per sheet and one final decision. Splitting
locations between counters, merging partial assignments, assisted valuation and
scheduled count issuance need a separate design. Owner comparison rollups,
durable draft-order idempotency, operational recovery/roles, unusual invoice
policies and independent prep/waste/Toast ledgers remain pending.
