# Changelog

All notable changes to Script Workshop are documented here.

## Unreleased
### Added
- Added project dashboard, project detail pages, script version metadata, version restore, and current version tracking.
- Added encrypted user model key storage with list, active lookup, test, and revoke endpoints.
- Settings now supports cloud-saved model keys while keeping browser-local BYOK mode.
- Project generation can use a saved active model key when no request header key is present.
- New project creation now accepts either a browser-local key or a cloud-saved active key.
- Added edit event persistence for manual saves and restores, plus a project edit history endpoint.
- Added a minimal Agent adaptation flow that creates reviewable patches and saves accepted changes as new versions.

### Fixed
- Removed stale documentation that described no-key generation as an offline mock path.
- Tightened explicit chapter parsing so inputs with fewer than 3 declared chapters are rejected instead of being silently split by length.
- Changed chapter persistence to a `(project_id, id)` composite key so multiple projects can each use stable ids such as `chapter_001`.
- Persisted generation run progress at each generation callback update and capped per-scene progress below validation.
- Added duplicate id checks for characters, locations, and source chapter ids.
- Made YAML repair return a clear no-op result for unparseable YAML instead of raising a server error.
- Corrected Docker build contexts so API images include `schema/` and web images can use the monorepo pnpm lockfile.
- Updated documentation to distinguish current MVP behavior from planned Monaco/visualization enhancements.
- Replaced stale legacy UI references with the Script Workshop project name.

### Added
- Added a browser-side model settings entry for BYOK usage, including provider selection, OpenAI-compatible API key, base URL, and model.
- Generation requests can now pass temporary LLM settings through headers; the backend uses them for the current background run without persisting API keys.
- Project creation now supports local `.md` and `.txt` uploads in addition to pasted text and the built-in sample.
- Home, settings, and generation progress pages now use Chinese-facing labels for the main workflow.

## [0.1.0] - 2026-06-05
### Added
- Day 1 scaffold: monorepo with `apps/web` (Next.js) and `apps/api` (FastAPI)
- AI generation flow skeleton: chapter split → summary → story bible → character extraction → scene planning → per-scene script → schema validation → repair → YAML export
- Pluggable LLM provider abstraction with OpenAI default
- `schema/script.schema.json` and `docs/yaml-schema.md` initial draft
- Sample novel + expected YAML output under `samples/`
- Makefile + docker-compose for one-command local dev
