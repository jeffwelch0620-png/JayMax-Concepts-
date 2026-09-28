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
