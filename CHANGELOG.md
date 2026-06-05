# Changelog

All notable changes to 剧本工坊 are documented here.

## Unreleased
### Added
- Added project dashboard, project detail pages, script version metadata, version restore, and current version tracking.
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
- Added named script snapshots in the editor version panel with a direct rollback action.
- Replaced the text-based app mark with a minimal script-document icon and matching favicon.
- Added JSON and Markdown script exports for latest and historical script versions.

### Fixed
- Collapsed script export actions into a single format menu, fixed the editor toolbar dropdown so it is not clipped by the workspace header, and made the menu close when users click elsewhere.
- Fixed scene directory numbering so generated titles like "第 1 场" are renumbered by their actual scene order in the editor.
- Added project deletion from the dashboard and changed failed or previously generated projects to show a regenerate action.
- Reworked the web workspace layout for wider editor pages, clearer project navigation, and fewer internal identifiers in the writing UI.
- Contained the script editor inside the viewport with independent scroll areas for resources, editing, and side panels, and fixed the dark background color banding during long-page scroll.
- Compacted the script editor toolbar so the main editing canvas starts higher and has more vertical room.
- Fixed whole-script Agent scope so the web editor sends every current scene id instead of an empty scene selection.
- Fixed Agent acceptance refresh so accepting one suggestion does not immediately reopen another pending suggestion in the review card.
- Increased Agent review typography and removed tiny monospace patch text so adaptation diffs stay readable.
- Hid internal generation-run notes from script snapshot cards.
- Added a close control to editor success notifications.
- Hid the Agent instruction placeholder while the input is focused.
- Reloaded the canonical script snapshot after structured editor saves so UI state matches backend normalization and validation.
- Kept the selected scene id in sync after loading, restoring, or saving versions whose scene ids changed.
- Made Markdown exports read like a writer-facing script draft with Chinese sections, resolved role/location names, and filtered empty action/dialogue lines.
- Separated Next.js dev and production build directories to prevent stale chunk errors after switching between `next dev` and `next build`.
- Added API key sanity checks and clearer generation failure messages for invalid or expired model keys.
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
