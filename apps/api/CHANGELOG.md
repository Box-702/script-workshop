# Changelog (API)

> Backend changelog for `apps/api` (FastAPI + Pydantic v2 + SQLAlchemy + Alembic).
> Cross-cutting changes (monorepo, deployment, shared types) are tracked in
> the root `CHANGELOG.md`.

## Unreleased
### Added
- Added encrypted user model key storage with list, active lookup, test, and revoke endpoints.
- Settings now supports cloud-saved model keys while keeping browser-local BYOK mode.
- Project generation can use a saved active model key when no request header key is present.
- New project creation now accepts either a browser-local key or a cloud-saved active key.
- Added edit event persistence for manual saves and restores, plus a project edit history endpoint.
- Added a minimal Agent adaptation flow that creates reviewable patches and saves accepted changes as new versions.
- Added Agent diff review details with patch before/after previews and a reject flow that leaves the current version unchanged.
- Added model-backed Agent adaptation patches for selected scenes, with local fallback suggestions when no model key is available.
- Added partial Agent patch acceptance so users can save only selected adaptation changes.
- Added Agent suggestion retry so users can regenerate a patch from the same prompt, base version, and scene scope.
- Added Agent run history loading in the editor so pending suggestions survive page refreshes.
- Improved the Agent panel with adaptation-focus presets, constraint chips, and readable action/dialogue patch previews.
- Improved Agent review context with the original user request, normalized current-scene labels, duplicate-safe prompt chips, clear prompt reset, and character-name dialogue previews.
- Generation requests can now pass temporary LLM settings through headers; the backend uses them for the current background run without persisting API keys.
- Project creation now supports local `.md` and `.txt` uploads in addition to pasted text and the built-in sample.
- Added project deletion from the dashboard and changed failed or previously generated projects to show a regenerate action.

### Fixed
- Fixed whole-script Agent scope so the web editor sends every current scene id instead of an empty scene selection.
- Fixed Agent acceptance refresh so accepting one suggestion does not immediately reopen another pending suggestion in the review card.
- Added API key sanity checks and clearer generation failure messages for invalid or expired model keys.
- Removed stale documentation that described no-key generation as an offline mock path.
- Tightened explicit chapter parsing so inputs with fewer than 3 declared chapters are rejected instead of being silently split by length.
- Changed chapter persistence to a `(project_id, id)` composite key so multiple projects can each use stable ids such as `chapter_001`.
- Persisted generation run progress at each generation callback update and capped per-scene progress below validation.
- Added duplicate id checks for characters, locations, and source chapter ids.
- Made YAML repair return a clear no-op result for unparseable YAML instead of raising a server error.
- Cleaned Alembic migration formatting so the full backend Ruff check passes.
- Tolerated percent-encoded characters in `DATABASE_URL` for both alembic and runtime, and switched the API config to load `.env` from the repo root.

## [0.1.0] - 2026-06-05
### Added
- FastAPI app skeleton with routers: projects, scripts, agent, model_keys, validate.
- 8-stage AI pipeline: chapter split → summary → story bible → character extraction → scene planning → per-scene script → schema validation → repair → YAML.
- OpenAI-compatible LLM provider abstraction with stage-level model overrides.
- SQLAlchemy models, Alembic migrations, SQLite default (now superseded by Supabase Postgres in production).
- `schema/script.schema.json` and `docs/yaml-schema.md` initial draft.
