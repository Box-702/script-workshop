# Screenshots & Recordings

This directory holds the visual assets referenced from `README.md`. The
project ships without binary blobs; the table below lists the screenshots
and recordings that *should* be produced before a public demo, plus the
exact steps to capture each one.

| Asset | Type | How to capture |
|---|---|---|
| `theme-switch.gif` | 5s animated GIF | See step 1 below |
| `dashboard.png` | Screenshot | See step 2 |
| `agent.png` | Screenshot | See step 3 |
| `editor.png` | Screenshot | See step 4 |

## Recording environment

```bash
# 1. Boot both services
.\scripts\dev-api.ps1
.\scripts\dev-web.ps1

# 2. Open Chrome on http://127.0.0.1:3000

# 3. For dark vs light, toggle the StyleSwitcher in the top right
```

## 1. Theme switch (5s GIF)

1. `pnpm --dir apps/web start` (production server, so animations run smoothly)
2. Open DevTools → Performance → set CPU throttling to 4x to make the
   transitions obvious in the recording
3. Use LICEcap (Windows) or `ffmpeg` + `xdotool` (Linux) to record
4. Click `Paper` in the StyleSwitcher
5. Click `Studio` to switch back
6. Save as `docs/screenshots/theme-switch.gif`

## 2. Dashboard screenshot

1. Log in (use a test account with at least 3 projects)
2. Navigate to `/dashboard`
3. Make sure the table is populated
4. Capture the viewport (1280×800 minimum)

## 3. Agent adaptation screenshot

1. Open a project that has a finished script version
2. Open the editor at `/projects/<id>/edit`
3. In the right-hand AI 改编助手 panel, fill in a prompt
4. Click "生成改编建议"
5. Wait for the patch to arrive
6. Capture the viewport showing the diff preview

## 4. Editor screenshot

1. Same project as step 3
2. Click on a scene in the left scene list
3. Capture the viewport showing the structured editor (middle column)
4. The scene card on the left, the AI panel on the right should both
   be visible

## Why no binaries in the repo

Keeping binary assets out of git keeps `git clone` fast and the
diff history small. The `RECORDING.md` steps above let any contributor
regenerate the assets on demand.
