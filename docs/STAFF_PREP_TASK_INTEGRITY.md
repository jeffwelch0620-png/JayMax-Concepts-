# Staff prep access and assignments — local checkpoint, October 7, 2026

Managers can review and assign included, positive tasks from the currently
released native dated plan. Staff can read that plan using a location-authorized
bearer credential or the existing location PIN. Every read selects a date and
daily/bulk track explicitly; there is no fallback to an older released list.

This is the assignment/read milestone. Staff production submissions and staff
completion writes are pending. Managers continue to record measured native
production and link/review its task progress using the existing execution
workflow. No assignment records a batch, consumes an ingredient, resets a count,
posts a purchase or changes Track 1 inventory/Food Cost.

## Identity and permissions

- An assignment uses the roster UUID, not an editable name as a key. Its reviewed
  snapshot retains the name, role and active status at assignment time.
- Assignment, reassignment and unassignment are manager/owner commands with
  location authorization, required preview and explicit confirmation. Readonly
  accounts can inspect the manager view; staff cannot call its write commands.
- A shared PIN establishes location access. Selecting a roster name is claimed
  identity; it does not verify the employee, restrict confidentiality to that
  employee or grant any manager permission. The optional roster filter is a
  convenience filter, not employee authorization. A bearer subject establishes
  account access but is not automatically mapped to a roster employee.
- The native staff portal selects roster identities locally and does not invoke
  the legacy shared-PIN `owner_admin` session-elevation endpoint. That direct
  legacy endpoint and the broader login/PIN redesign remain deferred in the
  security review; this checkpoint does not claim to fix them.
- PIN values are supplied only in staff read requests and are not retained in
  assignment bodies, fingerprints, snapshots or draft caches.

## Version, date and quantity contracts

Assignments are append-only per task with a predecessor and monotonically
increasing revision. Task identity pins the saved plan version, product, recipe,
units and exact planned quantities. Preview also pins the released execution
event/revision and current reviewed task progress. A changed roster, assignment,
plan or linked production invalidates an older preview. Finished tasks or changed
production requiring reconciliation cannot receive new assignments.

Changing a roster name or deactivating someone does not rewrite earlier
assignments. Current reads report the change beside the original history.
Referenced roster identities cannot be deleted; archive them by setting inactive.
New assignments and optional staff filters require an active local member.
Unassignment is a new revision and requires an existing assignment.

Staff readbacks label the selected date and track, planned output in its pinned
source unit, and measured manager-reviewed output in its canonical base unit.
Planned output is theoretical. Production links remain whole-batch references;
assignment does not divide output, attribute physical use to sales, or establish
a completed task. A reopened plan has no released staff tasks. Replacing its
dated draft creates new task IDs; assignments do not silently migrate to them.

## Retry and SQL boundaries

The request key binds the complete reviewed command, actor, location, date and
track. Same-key retries return the original saved assignment, that task's complete
immutable assignment history and the current plan. This remains confirmable after
reassignment, reopening or replacement of the draft. Reusing a key for another
actor/body is rejected. Competing saves serialize through location coordination;
only one fresh revision can win.

The additive migration checks current released task identity, exact progress,
roster snapshot, predecessor and submitted assignment fields at the database
boundary. Cross-location task/member relationships have composite foreign keys.
Updates/deletes of assignment history are blocked and tables/functions remain
private to backend database access. Existing production, purchase and count facts
are unchanged.

The manager UI validates previews and acknowledgements against the exact request
and saved immutable history. Uncertain saves retain the same body/key across view
navigation/remount; a known rejection permits explicit revision followed by new
review. Draft retention lasts for the current app session, not reload/logout.
Late location/date/session callbacks cannot clear or resurrect another draft.
Staff reads ignore superseded responses and hold failed/mismatched readbacks
rather than representing them as a successful empty or older plan.

## Installation and legacy scope

Install `20261007_staff_prep_tasks.sql` after native dated tasks, execution and
progress. `STAFF_PREP_TASKS_ENABLED=false` and
`REACT_APP_STAFF_PREP_TASKS=false` remain the example defaults. Enabling requires
the existing native prep/execution foundations. No operational migration or
enablement has been performed.

After schema installation, old PostgreSQL staff prep-sheet reads and completion
commands are held even when the new feature flag is false. Original legacy task
rows stay preserved by the earlier dated-plan migration; there is no conversion
of them into native tasks. General staff inbox tasks, notifications, Mongo-only
paths and other legacy surfaces are outside this milestone. No emails, push
notifications or external staff messages were sent.

## Validation and remaining work

Tests use invented data in disposable local PostgreSQL databases, with volatile
database files outside Drive-synced storage. They exercise assignment history,
same/different-key races, stale roster and production previews, role/location
checks, claimed identity, explicit dates/tracks, direct SQL forgery and immutable
history, unchanged accounting/production, flags-off legacy holds, and whole SQL
restore with exact retry/private ACL preservation. Frontend checks cover strict
review/acknowledgement, retained retry, late callbacks, explicit staff date/filter
reads, failed readbacks and avoidance of legacy PIN elevation/prep-sheet calls.
Final counts and evidence files are recorded in the review package and README.

Next: atomic direct container waste linked to measured contents and the existing
waste journal, with reversals and no double allocation. After that, add immutable
staff production submissions and manager decisions using these stable tasks and
assignment histories; define account-to-employee mapping before claiming verified
employee attribution. Verified consumption/POS, complete operating cutover,
supplier outbox, platform deployment/recovery and future Toast work remain open.
