# Changelog

> Project-level changelog for **剧本工坊** (Script Workshop).
> Per-module changes live in:
>
> - Web frontend → [`apps/web/CHANGELOG.md`](./apps/web/CHANGELOG.md)
> - API backend → [`apps/api/CHANGELOG.md`](./apps/api/CHANGELOG.md)
>
> Frontend and backend are managed as **separate subprojects** under this
> monorepo: each has its own dependency manifest, deployment configuration
> (`vercel.json` / `render.yaml`), and changelog.

## Unreleased
### Added
- Added a Vercel + Render + Supabase deployment guide with production environment variables and an acceptance checklist.
- Added `render.yaml` (Render Blueprint) and `vercel.json` to make one-click deploys for the API and web app independent of each other.
- Deployed production to Vercel + Render + Supabase:
  - Frontend: `https://script-workshop-web.vercel.app`
  - Backend: `https://script-workshop-api.onrender.com`
  - Verified frontend homepage, backend `/api/healthz`, Vercel `/api/healthz` proxy, and unauthenticated `/api/projects` 401 behavior.

### Fixed
- Updated documentation to distinguish current MVP behavior from planned Monaco/visualization enhancements.
- Corrected Docker build contexts so API images include `schema/` and web images can use the monorepo pnpm lockfile.
- Documented Vercel SSO deployment protection and `COMMIT_AUTHOR_REQUIRED` deployment blocking encountered during production setup.

## [0.1.0] - 2026-06-05
### Added
- Day 1 scaffold: monorepo with `apps/web` (Next.js) and `apps/api` (FastAPI)
- AI generation flow skeleton: chapter split → summary → story bible → character extraction → scene planning → per-scene script → schema validation → repair → YAML export
- Pluggable LLM provider abstraction with OpenAI default
- `schema/script.schema.json` and `docs/yaml-schema.md` initial draft
- Sample novel + expected YAML output under `samples/`
- Makefile + docker-compose for one-command local dev
