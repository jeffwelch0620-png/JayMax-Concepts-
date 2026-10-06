# Save acknowledgements and restaurant drafts

This local milestone addresses original review R07 (false save success) and R20
(polling and delayed responses). It changes frontend save handling. It does not
change database schemas, inventory facts, Food Cost, invoice dates, or prep/sales
accounting authority. Native feature flags remain disabled in the examples.

## Saved state

`useStoreState` owns each selected restaurant/session generation. It captures
the restaurant and revision before issuing a write. Switching A → B → A creates
a new generation, so an old A response cannot update the returned A screen or
revision. Old callbacks cannot start a new write after switching restaurants.
Returning to a restaurant with an older request outstanding waits for completion
and then fetches that restaurant again.

The app applies collection values only after an object acknowledgement with a
valid integer revision. It rejects missing, negative, string, older-revision,
and explicitly unsuccessful acknowledgements. Errors return `null`; collection
callers must check confirmation before clearing a form or announcing success.
Supplier contacts use their separate `{ok, vendor, orderEmail}` acknowledgement.

The client refuses overlapping whole-store writes rather than queuing stale
replacement arrays. Sequential saves use the newly confirmed revision. Polling
skips an outstanding write and discards reads overtaken by writes, newer reads,
restaurant changes, or session changes. A lower server revision cannot regress
the selected saved state. “Refresh saved data” explicitly reloads saved values.

## Drafts

Item setup, storage areas, supplier emails, recipes, adjustments, prep settings,
and sales drafts are held in the signed-in App instance, keyed by restaurant and
form. Navigation retains them. Logout/session expiry and app reload clear them;
this is not a durable offline queue. Inputs are not included in backups until
the server confirms their save. A confirmation only clears the submitted version,
so typing performed during the request survives.

Sales edits debounce for 700 ms. Polling cannot replace a dirty draft. The draft
retains its original revision; a changed saved revision blocks replacement until
the user reviews/discards the draft. Completed timers are cleared. Unmount cancels
a pending timer without sending another request; the user explicitly saves the
retained draft on return. A response received after unmount does not announce
success or silently discard the draft. Typing during an acknowledged save advances
only to that write's revision and schedules the newer draft once.

Closing a legacy sales period validates its dates before writing and requires
both working-period and snapshot confirmations. Loading/starting another period
first confirms the current entries; failure preserves the previous working data.
Prep par/frequency edits now use an explicit “Save prep settings” action rather
than sending a whole collection on each keystroke.

## Legacy and remaining limits

Legacy invoice history and catalog-price updates remain separate requests. A
price failure after history is saved is disclosed as partial, retains the form,
and blocks further imports in that mounted screen. Operators must review history
and repair catalog prices; retrying the import is not a recovery procedure.
Native invoice import remains the supported transactional replacement.

This client boundary does not supply granular backend revision coverage, durable
idempotency for every legacy writer, cross-user field merging, or transactions
across legacy restore/invoice/prep requests. Those remain under R03/R17 and the
operating-workflow cutover. Legacy prep task/count/container screens still need
that cutover and their own draft/error contract; R07 is not closed for the entire
legacy operating surface. The current changes do not establish production or
managed-platform deployment/restore proof.

Automated verification covers failed/malformed acknowledgements, saved-state
isolation, polling, delayed reads/writes, A → B → A, concurrent client requests,
draft navigation, debounce/unmount, edits during saves, invoice partial failures,
supplier contact loading, and recipe/adjustment/item saves. The full frontend
suite and production build are recorded in the accompanying local review package.
