# Editor recovery reads and background polling

## Problem and resulting behavior

Item Setup and Recipe Costing use `useStoreState.refresh()` to obtain a fresh
baseline for **Reload latest and keep my changes**. Previously, a scheduled
15-second poll could start while that explicit recovery request was pending.
The poll advanced the hook's read sequence, so the otherwise valid recovery
response was discarded and returned no data to the editor. The editor safely
retained its draft but reported that latest data could not be confirmed.

A controlled local regression reproduces this behavior through both App editor
callbacks. This establishes a code defect consistent with the intermittent
[hosted symptoms](PR19_HOSTED_ACCEPTANCE_RESULTS.md); it does not establish the
cause of every hosted refusal or session-related failure.

Scheduled polls now skip the latest active read. Explicit refresh remains able
to supersede an older pending poll or explicit read. Only completion of the
latest read releases the polling hold: an obsolete request cannot release a
newer recovery, or keep polling paused after that newer recovery completes.
The next scheduled interval resumes polling after success, failure or a
discarded response. This does not automatically retry the editor action.

## Integrity boundaries

- Restaurant/session identity, read order, write generation and pending-write
  checks still discard obsolete responses and return no recovery baseline.
- Invalid collections and revisions remain refused. A lower revision cannot
  replace current saved state or become a recovery baseline.
- Editor conflict detection, retained drafts, confirmed-save receipts and
  server revision checks are unchanged. Recovery reads do not write data.
- The change introduces no cached-data fallback, field auto-merge, altered
  authentication, backend route, migration or connection configuration.
- Polling pauses while the latest request remains pending. A further explicit
  refresh can supersede that request; request timeout policy is unchanged.

## Validation and evidence

Ten regression cases were added: eight hook checks and the two App editor
callbacks. Existing write-overtaken-read coverage also verifies that no
recovery data is returned after a write invalidates the request.

The original implementation failed five targeted checks: both editor callbacks,
explicit recovery return values, overlapping slow polling, and recovery failure
reporting. A first candidate passed the focused suite, but an additional test
showed that counting all unresolved requests could stall polling behind an
obsolete request. Tracking only the latest read resolves that edge while
preserving the opposite case, where obsolete completion must not release a
newer recovery.

Final local validation passes **144 focused tests across 7 suites**, all
**572 frontend tests across 65 suites**, and the production build with the
reviewed native feature profile, `CI=true` and ESLint enabled. No tests failed
or were skipped. The build reports `Compiled successfully`; Node's `fs.F_OK`
runtime deprecation notice is separate from compilation diagnostics.

The safe local evidence files live beside this checkout, outside Git:

- `editor-recovery-repro-before-tests.json`: original five failing cases.
- `editor-recovery-repro-stale-poll-edge-tests.json`: the rejected first
  candidate's obsolete-poll stall.
- `editor-recovery-focused-final-tests.json` and matching log/receipt:
  final focused checks.
- `editor-recovery-full-final-tests.json`, test/build logs and validation
  receipt: final native-profile suite and production build.
- `editor-recovery-local-checkpoint-final.json`: verified totals, local commit
  and SHA-256 hashes of the six changed source/documentation files.

These tests use mocked fictional state; they do not contact the hosted database.
App tests exercise the actual store hook and editor callback wiring while
mocking panels; existing component suites cover draft/conflict recovery.
Backend/database behavior is unchanged and is not revalidated by this run.

## Review and remaining acceptance

This follow-up is committed locally on `codex/editor-recovery-read-integrity`
after the local hosted-acceptance documentation commits. It is not pushed,
merged or deployed. Existing Render hosting, Supabase schema/connections and
the previously verified $212 fictional accounting control remain untouched.

Next, publish a draft PR for review when authorized. After an approved merge
refreshes the test deployment, exercise both editor recovery actions across a
polling interval with labelled fictional drafts and confirm persisted records.
Record hosted acceptance separately from these local tests. Deployed HTTP
posting replay, lost-response recovery, independent employee authorization,
broad UI rework and fixture cleanup retain their separate review boundaries.
