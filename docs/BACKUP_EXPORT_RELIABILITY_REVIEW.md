# Encrypted backup export reliability — local review package

## Problem and resulting behavior

The October 14 maintenance attempt produced a passing encrypted export and local
restore, but its authenticated migration keys used Windows backslashes. The
unchanged hosted adapter correctly refused the archive as installation evidence.
A separately corrected recapture stalled during fingerprinting; per-query/tool
timeouts did not bound the export as a whole. The window closed with services
restored and no index application.

The CLI now captures `relative_to(repo).as_posix()` keys for both migration roots.
The Windows regression passes those actual CLI-collected hashes into an encrypted
fictional manifest and through the real adapter's `load_evidence` guard. The same
guard still refuses historical backslash keys and a changed reviewed SQL hash.
No existing archive is rewritten or normalized during authentication.

## Deadline, progress and ownership

- Every export has a default maximum of **600 seconds**, measured with monotonic
  time from the export entry point. `export --timeout-seconds N` permits a shorter
  positive integer budget, at most 600 seconds. Invalid budgets refuse before
  a database connection or creation of private export directories.
- Phase transitions and five-second heartbeats emit fixed labels, elapsed
  seconds and a generated 32-character hex export reference. The CLI sends
  progress JSON lines to stderr and the result to
  stdout. No relation name, row, query, DSN, key, path or raw subprocess diagnostic
  is emitted in progress. A broken progress sink is recorded without exposing
  its exception text or replacing a backup failure.
- Each export's connection gets a fresh `jaymax-backup-<random>` application name;
  its suffix is the export reference in progress and result diagnostics. Its
  database tool uses a related label. This allows a future operator to correlate
  retained evidence with an abandoned session without exposing credentials.
  Cancellation stops the worker and gracefully closes the exact connection
  object it created. The driver's cancellation request can interrupt an active
  server query; transport abort alone can leave a query alive until completion.
  Worker cleanup and the supervisor share one bounded close task. A failed or
  timed-out graceful close falls back to transport termination and stays held.
  It never searches for or terminates sessions by role, PID pattern or location.
- PostgreSQL tools are owned `Popen` children. Cancellation or tool timeout kills
  and waits for that exact child before cleanup can remove a file it was writing.
  The previous cancelled `to_thread(subprocess.run)` could outlive its caller.
- Snapshot rollback, connection close and child reap each have a **five-second
  cleanup allowance**, including rollback after transport termination fails.
  Failure to reap holds partial-file removal; a retained key/partial is diagnostic
  evidence, not an accepted backup. Original SQLSTATE, rollback, close, terminate,
  subprocess and file-cleanup categories remain distinct and secret-safe.
  An operator interrupt returns exit 130 and preserves the cancelled export's
  safe artifact/diagnostic evidence when supplied by `asyncio.run`.
- The worker checks elapsed time again immediately before final publication.
  Synchronous encryption/filesystem work cannot make an expired export publish
  success merely because the asyncio timer has not resumed yet. Authenticated
  readback, archive listing, close and partial cleanup still precede publication.

The budget is an export budget, not authorization to consume a maintenance
window. Reserve time for bounded cleanup, a separate restore, plan preparation,
owner review and service recovery. An asyncio timer cannot preempt OS suspension,
an uninterruptible filesystem operation or an unkillable OS process; elapsed-time
rechecking prevents acceptance after such a delay, and failed cleanup stays held.
Pooler-side cleanup must still be observed in a future approved hosted rehearsal;
local transport tests do not prove that hosted behavior or identify the original
stall's cause. No persistent server limits or runtime app connections changed.

## Validation checkpoint

The focused checks cover CLI/adapter binding, deadline cancellation with bounded
rollback, operator cancellation, preservation of an original SQLSTATE during a
stalled rollback, stalled connection close, synchronous overrun, invalid budgets,
safe progress and real child-process termination before partial cleanup.

The initial broad run passed **721 offline cases**. Its database report contains
**62 passed methods and 11 passed subtests**, with four failures: the three new
session-test subcases used a fictional database identifier longer than PostgreSQL
permits, and the existing active-writer reconciliation test rejected its expired
20-minute review window after a long execution gap. The gap's cause is not
established. The broad run is retained as failed evidence, not a clean acceptance
baseline. Its local test server was stopped.

Both backup fixtures now use UUID source database names below the identifier
limit, and the session test always cancels and awaits its export task on fixture
failure. Product name/authority/window guards were not relaxed. The final source
passes **724 offline cases (281 methods and 443 subtests)** with zero failures,
errors or skips. This includes the added rollback bound, reference handling and
interrupt-evidence checks. The first fresh PostgreSQL rerun passed idle cleanup,
encrypted restore and the fresh writer guard, but exposed the active-query
transport-abort gap. That led to the graceful driver cancellation mechanism now
tested for both deadline and operator cancellation of busy/idle sessions.
The final source-frozen run completed **October 14 at 10:21:51 p.m. EDT
(2026-10-15T02:21:51Z)**. All **7 targeted PostgreSQL cases (3 methods and 4
subtests)** passed with zero failures, errors or skips:

- Deadline and operator cancellation each stop both a running 60-second query
  and an idle transaction. The exact labelled backend disappears, the observer
  remains usable, no accepted backup is published, and fictional source rows
  remain unchanged.
- Real `pg_dump`, encryption/authenticated readback, real `pg_restore`, exact
  restored fingerprints and two fictional rows pass; close failure still refuses
  publication and removes export partials.
- The active-writer reconciliation guard passes with a fresh review window.

This final run rechecked every previously failing database path and the affected
real backup lifecycle. The broader database selection was not repeated in full
after the final exporter changes; its earlier failed report remains separate.
Full GitHub CI is still required after pushing and before merge. Frontend code is
unchanged; no new frontend/build or GitHub CI evidence is claimed locally.

The source hashes stayed fixed throughout the final 724-case offline and 7-case
database run. Before/after local role and database inventories match, the owned
test server is stopped, no hosted connection was used and no real invoice was
imported. The JUnit reports, original failed runs and source-hash receipt are
retained locally for review. Only existing dependency deprecation warnings remain.

Final source-hash receipt SHA-256:
`35b72c54097e7ef4f12e92e8a60142921c415e5f85ef808a516389d0e80f4d11`.

## Scope and next approval

The PR will also carry the preceding local read-only diagnostics, backup and
closed-window documentation checkpoints after merged PR30. These are historical
observations, not renewed writer-stop or index-application authorization.

No hosting, Supabase connection, credentials, SQL migrations, permissions, index,
operational inventory data or Companion code changes are included. Fictional test
databases are loopback-only and separately created and removed.

After local verification, prompt the owner before pushing a new **draft** PR.
Independent review, merge approval, a new maintenance window with refreshed
writer inventory/drain, a new correctly labelled backup/restore, and exact-plan
approval before hosted index application are still separate steps. The closed
October 14 control pointer must not be reused. Refresh the private operator
runner's source pins against the accepted merged code and reuse the canonical
collection behavior; the historical runner's old commit pins are not an approved
execution path for the next window.
