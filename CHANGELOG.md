# Changelog

> Project-level changelog for **剧本工坊** (Script Workshop).
> Per-module changes live in:
>
> - Web frontend → [`apps/web/CHANGELOG.md`](./apps/web/CHANGELOG.md)
> - API backend → [`apps/api/CHANGELOG.md`](./apps/api/CHANGELOG.md)
>
> Frontend and backend are managed as **separate subprojects** under this
> monorepo: each has its own dependency manifest, deployment configuration
> (`apps/web/vercel.json` / `apps/api/render.yaml`), and changelog.

## Unreleased
### Added
- Added a Vercel + Render + Supabase deployment guide with production environment variables and an acceptance checklist.
- Added `render.yaml` (Render Blueprint) and `vercel.json` to make one-click deploys for the API and web app independent of each other.

### Fixed
- Updated documentation to distinguish current MVP behavior from planned Monaco/visualization enhancements.
- Corrected Docker build contexts so API images include `schema/` and web images can use the monorepo pnpm lockfile.

## [0.1.0] - 2026-06-05
### Added
- Day 1 scaffold: monorepo with `apps/web` (Next.js) and `apps/api` (FastAPI)
- AI generation flow skeleton: chapter split → summary → story bible → character extraction → scene planning → per-scene script → schema validation → repair → YAML export
- Pluggable LLM provider abstraction with OpenAI default
- `schema/script.schema.json` and `docs/yaml-schema.md` initial draft
- Sample novel + expected YAML output under `samples/`
- Makefile + docker-compose for one-command local dev
