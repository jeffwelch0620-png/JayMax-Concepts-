# Current Hosting & Database Providers

## Where it runs today
- **Platform:** Emergent (managed containers on Kubernetes).
  - Base image: `fastapi_react_mongo_shadcn_base_image_cloud_arm` (see `.emergent/emergent.yml`).
  - Process manager: **supervisor** (frontend on :3000, backend on :8001).
  - Ingress routes `/api/*` → backend (:8001); everything else → frontend (:3000).
- **Preview URL (dev):** `*.preview.emergentagent.com`
- **Production (on publish):** `*.emergent.host`
- Secrets are injected as environment variables by the platform (not stored in the repo).

## Database
- **MongoDB** accessed via the async **Motor** driver.
- Connection is entirely env-driven: `MONGO_URL` + `DB_NAME` (from `backend/.env`).
- On Emergent, a managed MongoDB instance is provided to the container.
- Portable to **MongoDB Atlas** or any self-hosted MongoDB — just change `MONGO_URL`.

## Third-party services
- **Emergent Universal LLM key** (`EMERGENT_LLM_KEY`) → OpenAI GPT-4o via `emergentintegrations`
  (the AI assistant "Sous").
- **Emergent-managed Resend** (`EMERGENT_EMAIL_KEY`) → transactional supplier PO emails.

## Portability notes (moving off Emergent)
- Backend: any host that can run `uvicorn server:app` (Docker/VM/PaaS). Set all env vars.
- Frontend: `yarn build` → static hosting/CDN; set `REACT_APP_BACKEND_URL` at build time.
- Replace Emergent-managed integrations if you leave the platform:
  - LLM: point to your own OpenAI/Anthropic/Gemini key (code uses `emergentintegrations`;
    swap for the provider SDK or an OpenAI-compatible endpoint).
  - Email: use a direct Resend (or other provider) API key instead of the managed proxy.
- Set `PUBLIC_APP_URL` to the backend's public https origin so PO-PDF email links resolve.

## Collaboration deployment checklist
1. Use one production MongoDB database for the shared backend, with automated daily backups
   and a tested restore procedure. Keep demo data in a separate database.
2. Set `AUTH_REQUIRED=true`, a unique random `AUTH_SECRET`, and a one-time
   `BOOTSTRAP_TOKEN`; remove the bootstrap token after creating the first owner.
3. Set `CORS_ORIGINS` to exact HTTPS frontend origin(s), never `*` in production.
4. Bootstrap the owner, then create named manager, staff, and read-only users with only the
   locations they need. The frontend filters locations, while the backend enforces policy.
5. Put both origins behind HTTPS and keep `RATE_LIMIT_PER_MINUTE` enabled for AI/email.
6. Send the `If-Match` revision returned by `GET /api/state/{rid}` on state saves; a `409`
   means the user must reload before retrying.
