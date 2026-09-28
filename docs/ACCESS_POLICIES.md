# Access Policies & Auth Model

## Current model (as-shipped)
- **No authentication / authorization** on the main REST API. Any client that can reach
  the backend can read and mutate all data (items, dishes, purchase orders, owner rollups,
  vendor contacts, apply-prices, state replacement).
- The **only** access control is a **staff PIN** (`settings.staffPin`, default `1234`) that
  gates the read-only **Staff Prep Sheet** view (`StaffSheet.js`) — it does not protect the API.
- `check_rid()` validates that the `restaurantId` path/param is one of the 3 known ids.
  This is input validation, **not** tenant isolation or authz.

This is a **deliberate, deferred product decision** (RBAC — Ownership / Manager / Staff —
is on the roadmap). Treat every deployed/preview URL as sensitive and share only with
trusted people until RBAC lands.

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
