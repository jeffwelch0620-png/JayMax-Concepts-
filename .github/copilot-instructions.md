# Copilot review instructions

Review guidance for JMAX (restaurant inventory, prep and staff app for Bert's, Rudd's and Papa's).

1. Focus on correctness, security, data integrity and concurrency. Skip style, naming and formatting nits unless they hide a bug. Report each real problem once, with a concrete failing scenario.
2. Access control: every route must check the caller's store (location) and the permission it needs from `backend/positions.py` (`PERMISSIONS` / `can()`). Flag any route a lower role or another store can reach, and any read that exposes costs, wages, invoices or staff data to staff sessions. Wages are visible to GM and above only.
3. Staff sign-in: personal staff sessions (kind "staff") must reach only the employee screens. PINs must never be stored, logged, fingerprinted or returned in plain text.
4. Data integrity: fact tables are append-only (corrections are new rows, never updates or deletes). Writes that can be retried must use the `Idempotency-Key` header, lock on that key before checking for a prior request, and refuse a reused key with a different body. Times written inside a store lock use `clock_timestamp()`.
5. Migrations: new tables go in an existing schema covered by backups (for example `prep_inventory`). Each new migration must be added to `backend/deployment_readiness.py` `MIGRATIONS`, and the migration count tests and `migrations/APPLY_ORDER.md` updated. Revoke access from PUBLIC, anon and authenticated.
6. Tests: new behaviour needs tests, and database tests must be registered in `tools/run_review_tests.py`. If a docs file covered by `tools/review_contracts.py` changes, the generated review guides must be regenerated.
7. Privacy: no real staff names, wages, phone numbers, emails, sales or supplier prices in code, tests, fixtures or docs. Test data must be invented. No secrets or keys anywhere.
8. Feature flags come in backend/frontend pairs (`X_ENABLED` and `REACT_APP_X`) and must default to false in the `.env.example` files.
9. Frontend: forms must not double-submit, retries must reuse the same idempotency key for the same request, and a late response must not overwrite newer data on screen.
10. Keep each finding short and in plain English, with the file and line, the scenario that breaks, and a suggested fix.
