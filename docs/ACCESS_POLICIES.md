# Access Policies & Auth Model

## Collaboration model
- Accounts are created with `POST /api/auth/bootstrap` (one time) and then
  `POST /api/auth/users` by an owner. Passwords are PBKDF2-hashed and sessions are
  signed with `AUTH_SECRET`.
- Every API request except health and login/bootstrap requires a signed session when
  `AUTH_REQUIRED=true`.
- Users have `owner`, `manager`, `staff`, or `readonly` roles and a selected location
  list. Owners can see all locations; other users are denied server-side when a route
  contains a location they do not have.
- Managers can operate assigned locations, staff are limited to prep/count workflow,
  and read-only collaborators can view dashboards/reports without mutations.
- Authenticated requests are recorded in `activity_log`. State snapshot writes use
  `If-Match` revisions and return `409` when another collaborator saved first.

The former staff PIN endpoints remain for compatibility with existing clients, but new
deployments should provision named staff users and stop distributing the shared PIN.

## Security audit summary (latest)
| ID | Sev | Status | Summary |
|---|---|---|---|
| SEC-001 | HIGH | **FIXED** | PO supplier-email built its "Download PDF" link from the spoofable `X-Forwarded-Host` header (host-header injection → phishing link in a trusted-brand email). Now derived only from server-configured `PUBLIC_APP_URL`; the email endpoint no longer reads request headers. |
| CORS | — | **FIXED** | `allow_credentials` set to `False` (no cookie auth in use). |
| SEC-002 | HIGH | **ACCEPTED / DEFERRED** | No authn/authz on order/owner/state/apply-prices/vendor-contacts endpoints. Product decision (PIN-only). Approval separation is not enforced server-side. |
| SEC-003 | MED | **OPEN** | Unauthenticated, unrated LLM (`/api/ai/chat`) and email endpoints — potential cost/DoS abuse. Needs auth + rate limiting. |

## Email safety (Resend)
- Bodies are built server-side from templates (`_po_email_html`); callers pass ids, not markup.
- A guardrail (`_assert_safe_email`) rejects forms/inputs and non-https / shortener / IP /
  credential-bearing links.
- The embedded PO-PDF link is derived from `PUBLIC_APP_URL` only (`_pdf_link`).
- Recipient is the stored `vendor_contacts.orderEmail` or a manager-typed override.

## Hardening backlog (see KNOWN_GAPS.md)
- Add RBAC (named logins; creator ≠ approver enforcement on PO approve/send).
- Rate-limit `/api/ai/chat` and `/api/orders/{rid}/{oid}/email`; cap message/context size.
- Force per-store PIN provisioning (remove the `1234` default).
- Explicit CORS origin allowlist in production.
- Coerce/validate untyped dict/date bodies to prevent NoSQL operator injection.
