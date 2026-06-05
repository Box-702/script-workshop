# Changelog

All notable changes to ScriptForge AI are documented here.

## [0.1.0] - 2026-06-05
### Added
- Day 1 scaffold: monorepo with `apps/web` (Next.js) and `apps/api` (FastAPI)
- AI pipeline skeleton: chapter split → summary → story bible → character extraction → scene planning → per-scene script → schema validation → repair → YAML export
- Pluggable LLM provider abstraction with OpenAI default and deterministic mock fallback
- `schema/script.schema.json` and `docs/yaml-schema.md` initial draft
- Sample novel + expected YAML output under `samples/`
- Makefile + docker-compose for one-command local dev
