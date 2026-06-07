# Changelog (Web)

> Frontend changelog for `apps/web` (Next.js 14 App Router + TypeScript + Tailwind).
> Cross-cutting changes (monorepo, deployment, shared types) are tracked in
> the root `CHANGELOG.md`.

## Unreleased
### Added
- Added a field-level Agent patch comparison for script-flow beat suggestions, highlighting type, speaker, text, line, emotion, and subtext changes before users accept them.
- Added a header UI style switcher with two themes: studio (dark) and paper (light). All ink and accent colors are now driven by CSS variables and follow the selected theme, including Tailwind utility classes.
- Added a dedicated danger panel and "确认删除" flow on the dashboard so destructive actions show inline instead of a `window.confirm` dialog.
- Added project dashboard, project detail pages, script version metadata, version restore, and current version tracking.
- Added named script snapshots in the editor version panel with a direct rollback action.
- Replaced the text-based app mark with a minimal script-document icon and matching favicon.
- Added JSON and Markdown script exports for latest and historical script versions.
- Added a version diff endpoint and editor-side snapshot comparison panel for comparing historical snapshots against the current script version.
- Added direct YAML/JSON script-source import so exported scripts can be restored as editable projects without starting AI generation.
- Added a browser-side model settings entry for BYOK usage, including provider selection, OpenAI-compatible API key, base URL, and model.
- Home, settings, and generation progress pages now use Chinese-facing labels for the main workflow.

### Fixed
- Made the editor workspace more usable on smaller screens, added screenplay-like styling for script-flow beats, and added Agent patch summaries with a sticky accept area.
- Realigned the project detail info cards so labels and values share the same font size and vertical baseline, and made the status pill compact so it no longer pushes the row height.
- Replaced hardcoded `border-white/10` and `bg-white/[0.02]` usages in the editor and project detail with theme-aware `surface-line` and `surface-soft` tokens so both UI styles render consistently.
- Reworked paper-theme color tokens to invert the ink scale, so high-index numbers now mean "deeper text" and low-index numbers mean "background", restoring legibility in the light theme.
- Collapsed script export actions into a single format menu, fixed the editor toolbar dropdown so it is not clipped by the workspace header, and made the menu close when users click elsewhere.
- Fixed scene directory numbering so generated titles like "第 1 场" are renumbered by their actual scene order in the editor.
- Reworked the web workspace layout for wider editor pages, clearer project navigation, and fewer internal identifiers in the writing UI.
- Contained the script editor inside the viewport with independent scroll areas for resources, editing, and side panels, and fixed the dark background color banding during long-page scroll.
- Compacted the script editor toolbar so the main editing canvas starts higher and has more vertical room.
- Increased Agent review typography and removed tiny monospace patch text so adaptation diffs stay readable.
- Hid internal generation-run notes from script snapshot cards.
- Added a close control to editor success notifications.
- Hid the Agent instruction placeholder while the input is focused.
- Reloaded the canonical script snapshot after structured editor saves so UI state matches backend normalization and validation.
- Kept the selected scene id in sync after loading, restoring, or saving versions whose scene ids changed.
- Made Markdown exports read like a writer-facing script draft with Chinese sections, resolved role/location names, and filtered empty action/dialogue lines.
- Separated Next.js dev and production build directories to prevent stale chunk errors after switching between `next dev` and `next build`.
- Replaced stale legacy UI references with the Script Workshop project name.

## [0.1.0] - 2026-06-05
### Added
- Initial Next.js app router shell with dashboard, project detail, new-project, run-progress, structured editor, YAML source mode, and model settings pages.
- Tailwind config with ink/accent palettes; later migrated to CSS-variable-driven palette.
