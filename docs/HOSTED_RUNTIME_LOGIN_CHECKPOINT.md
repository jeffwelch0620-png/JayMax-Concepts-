# Hosted catalog reconciliation and ordinary database login

October 8, 2026. Extends local commit `7ba524975d6bbe75eb39c533fcb08628d03d8ca8`.
This is a build-database trial, not a production connection change, browser
acceptance test, migration replay, PR push or merge.

## Independently reconciled catalog

The read-only refresh on the designated Supabase build project finds PostgreSQL
17.6 and 54 migration identities. Compared with the unchanged local frozen
reference, no objects are missing and no shared relation fingerprints differ.
The hosted catalog has 96 functions and 127 relations; the local reference stays
at 94 functions and 123 relations.

The exact differences are:

- Additional relations: three `integrations.toast_*` tables and
  `public.item_price_history`.
- Additional functions: `jmax_toast_enable_daily_sync(text)` and
  `jmax_toast_read_day(text,date)`.
- Different existing definitions: the Toast start/store/finish helpers and
  `jmax_touch_updated_at()`.

These differences match an independent loopback reconstruction from the retained
pre-native schema-only export plus the exact 29 reviewed native migration files.
The complete reconstructed function and relation sets equal the refreshed hosted
sets. The target is never accepted as its own reference. No hosted table or
function is rewritten to make the comparison pass; no Toast function is called.

The schema export is pinned to
`b41b50cdec7eeef316c2df94249855aeff89a78c4255df8b79cfcbd70bfffbf3`.
The catalog-only function/relation digest is
`dd7729de33e17a26b6b5f9c75b5f5484618e847a185e36c5c25232fe94313302`.
The private SQL export is excluded from Git and review packages.

`runtime_permissions.contract` and `inspect` now require an explicit
`reference='hosted_build'` to select the separate registered contract. The default
remains `local`. The hosted variant is bound to the unchanged parent reference,
source profile, public reference, permission matrix, PostgreSQL major, retained
export and full catalog digest. Wrong anchors, changed approved function contents
or unreviewed objects hold the assessment. No automatic target-learning mode exists.

The current hosted ACL metadata also confirms that PUBLIC, `anon` and
`authenticated` cannot execute any of the five retained Toast definer helpers.
There are no policies addressed to database PUBLIC in the assessed application
schemas. This is catalog privilege evidence, not a live REST/Data API test.

## Local validation

Three selected static tests pass with five tampering subtests. They retain the
94/123 default, verify the exact 96/127 variant, reject an unknown selection,
and reject changed parent/export/matrix anchors, approved function content and
additional relation identities.

The separately rebuilt empty local schema passes the complete permission
assessment through both an administrator reader and a selected nonowner role.
Role application stays restricted to a unique loopback database; the local-only
fixture is not widened into a hosted installer. Both assessments remain read-only
and leave release and hosted LOGIN approval false. Temporary local databases and
roles are removed and the dedicated server stops after validation.

The first reconstruction held because its local browser-role prerequisites were
absent. The corrected fixture creates and removes only its own temporary NOLOGIN
browser identities. The held metadata receipt remains retained. No operational
rows are imported into either local reconstruction.

## Temporary hosted LOGIN trial

The trial uses a fresh random server-only LOGIN, bounded connection count and
short credential lifetime. Only the exact candidate table/function/schema grants
and per-verb policies addressed to that role are applied. The password stays in
memory. Ordinary browser roles gain no permissions; application credentials and
feature files are not changed.

The trial opens five authenticated clients using the application's pool sizes,
disabled statement cache and JSON codec, with TLS required and a read-only session
default for this canary. Read-only state is explicitly set on every acquisition
so it is reestablished after connection resets, rather than relying on a startup
setting being forwarded through the pooler. It checks `current_user` and `session_user` directly;
there is no owner login followed by SET ROLE. The first pool performs the complete
registered catalog/privilege assessment. A second newly constructed client pool
rechecks all five identities and bounded forecast, AI-history and native-journal
reads. Pool recreation does not imply Supavisor allocates new server processes.

After closing both pools, cleanup removes only the exact trial policies and
grants, then drops the trial role. It does not delete business rows or alter
function bodies, triggers, migration records or existing client grants. Grants
and revokes can normalize the textual representation of an ACL; this is not a
claim that its raw catalog text remains byte-identical.

The retry **passes** through the hosted session pooler. All ten acquired clients
across two newly constructed application-style pools have the trial role as both
`current_user` and `session_user`, read-only state on, and the expected JSON codec.
The first client's complete catalog/privilege assessment passes against the
registered hosted reference. Both pools can read the forecast/history tables and
selected purchase, physical-count and prep journals. No business writes are made.

The passing receipt records removal of the temporary policies/grants and role.
An independent read-only connection confirms both recorded trial roles are absent,
no candidate policies remain, the complete pinned hosted catalog still matches,
and all 54 migration identities remain unchanged. None of the five Toast definer
helpers becomes executable by PUBLIC, `anon` or `authenticated`.
The password is never saved. No permanent runtime credential is configured.

Retained metadata evidence in the local review package:

- `hosted-runtime-reference-20261009T021243606178Z.json`: independent schema reconstruction.
- `hosted-runtime-local-role-20261009T021902037943Z.json`: two complete local permission assessments.
- `hosted-runtime-login-20261009T022337145283Z.json`: held first LOGIN attempt and cleanup.
- `hosted-runtime-login-20261009T022807475576Z.json`: passing ten-client LOGIN/pool trial and cleanup.
- `hosted-runtime-cleanup-20261009T023438707731Z.json`: independent final cleanup and catalog verification.
- `hosted-runtime-reference-static.xml`: three passing static checks and five passing tampering subtests.

The first attempt is retained as held at the combined identity/read-only
assertion; its observed values were not saved, so the precise original mismatch
is not established. Its role and grants were removed. The retry records identity
values separately and explicitly reestablishes read-only state on every acquire.
The revised trial also reconciles a fresh role independently if grant COMMIT
acknowledgement is unavailable, rather than assuming no cleanup is needed.

The catalog-only inspector still reports LOGIN/release approval false on its own.
The surrounding actual LOGIN/pool trial is the separate evidence proving login;
neither result silently clears the deployment inspector's independent owner gate.

## Remaining release gates

Even a passing temporary LOGIN does not deploy a permanent runtime account or
prove complete application workflows under it. Browser acceptance, Data API
exposure, matched compiled/server flags, managed Auth/Storage/Vault/role recovery
and sequential PR stack revalidation remain open. Application sign-in design is
a separate future build topic; this checkpoint concerns PostgreSQL login.
Keep holding merges until the remaining release checks pass.

The candidate intentionally excludes `app_users` and push-subscription access.
Existing sign-in and notification queries need their separate connection or
permission decision before switching the saved backend URL. The already removed
temporary trial role is not a deployment credential.

Supabase documents [custom role usernames and session pooling](https://supabase.com/docs/guides/database/connecting-to-postgres)
and [custom LOGIN support without separate pooler registration](https://supabase.com/docs/guides/troubleshooting/fatal-password-authentication-failed).
