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
  refresh can supersede that request. The bounded state-read policy below now
  ensures a stalled latest request releases that hold.

## PR20 review amendment: bound stalled state reads

The external review identified a remaining reliability gap: a transport that
never settles could hold polling indefinitely, or leave initial loading without
an error or Retry button. The earlier release tests covered requests that
eventually succeeded or failed, not a never-settling request.

`fetchState` now has one **60-second deadline for the complete operation**:
the shared-state request and subsequent PostgreSQL item, recipe, prep and
compatibility invoice reads. Every dependent request shares that operation's
AbortSignal. The timer does not restart when the PostgreSQL reads begin. This
is a conservative build-time allowance for the existing Render test service,
not a measured hosting latency guarantee; assess it during hosted acceptance.

At the deadline, the operation rejects with a connection/retry diagnosis and
cancels unfinished transports. The store's existing `finally` releases the
polling hold, so the next scheduled interval can retry. Initial loading exposes
the existing error and Retry button. Mid-session failures retain the last
confirmed snapshot and drafts; recovery receives no unconfirmed baseline.
Repeated failures use the existing single-notification guard. A late completion
cannot replace the settled timeout, start later child reads after an expired
initial request, or overwrite a newer confirmed snapshot.

Ordinary failure also cancels sibling reads and clears the timer while keeping
the original error. Successful completion clears the timer. The cancellation
and deadline are private to this state read: no global Axios timeout, mutation
timeout, automatic save retry, invoice posting change, backend change or
database migration is introduced.

Regression coverage exercises the real state adapter with mocked transport,
including a stalled initial request and each PostgreSQL child, the single
operation budget, cancellation, late completion and unchanged purchase-post
request identity. Hook and App checks use the real deadline helper with
fictional never-settling reads to verify resumed polling, preserved confirmed
state, failure notification suppression and the initial Retry button.

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

The original polling correction's local validation passed **144 focused tests across 7 suites**, all
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

The timeout amendment adds **16 regression cases**: 12 state-adapter checks,
three hook checks and one App initial-loading/retry check. Amended local
validation passes **181 focused tests across 11 suites**, all **588 frontend
tests across 66 suites**, and the strict native-profile production build with
`CI=true` and ESLint enabled. No tests failed or were skipped. Its safe evidence
is retained outside Git as `state-read-focused-timeout-first-tests.json`,
`state-read-full-timeout-final-tests.json` and the matching logs/validation
receipts. These are mocked local tests, not deployed network acceptance.

## Review and remaining acceptance

This follow-up is prepared on `codex/editor-recovery-read-integrity` after the
hosted-acceptance documentation commits. Local validation was recorded at
`9f0aa7d`; the original published head `97340fe` changed its publication note
only. The user subsequently approved the review recommendations, including this
bounded-read amendment to draft PR20. Merge and deployment require
separate approval. Existing Render hosting, Supabase schema/connections and the
previously verified $212 fictional accounting control remain untouched.

Next, review the draft PR and its GitHub checks. After an approved merge
refreshes the test deployment, exercise both editor recovery actions across a
polling interval with labelled fictional drafts and confirm persisted records.
Also stall a read using browser network controls and verify that timeout,
retry and subsequent polling recover. Confirm the timeout fits the service's
observed startup time before treating it as an operational setting.
Record hosted acceptance separately from these local tests. Deployed HTTP
posting replay, lost-response recovery, independent employee authorization,
broad UI rework and fixture cleanup retain their separate review boundaries.
