# Vercel deployment notes

Vercel auto-detects Next.js once **Root Directory** is set to `apps/web`.
The `apps/api/*` -> `/api/*` rewrite is handled by
`apps/web/next.config.mjs` (which reads `process.env.BACKEND_URL`).

`vercel.json` is intentionally minimal — only the framework pin.
Anything more belongs in the Vercel dashboard so it never has to be
parsed by their JSON loader.

## Environment variables to set in the Vercel dashboard

| Key | Example | Notes |
|---|---|---|
| `BACKEND_URL` | `https://script-workshop-api.onrender.com` | Filled after Render deploys |
| `NEXT_PUBLIC_API_BASE` | `/api` | Keep as `/api` |
| `NEXT_PUBLIC_SUPABASE_URL` | `https://<project-ref>.supabase.co` | Supabase Project URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | `sb_publishable_...` | The publishable key |

## Do NOT set in Vercel

* `SUPABASE_SERVICE_ROLE_KEY` (and any other backend-only secret).
  The Next.js client can read `NEXT_PUBLIC_*` env vars, so anything
  not prefixed `NEXT_PUBLIC_` is *not* shipped to the browser, but
  it's still a leak to your Vercel logs and any collaborator with
  read-only access.
* `DATABASE_URL` / `KEY_ENCRYPTION_KEY` — these are backend-only.

## Why not put rewrites in vercel.json?

We tried. The backend URL isn't known at the time `vercel.json` is
parsed, and `${BACKEND_URL}` placeholders aren't expanded by Vercel
for that field. Keeping the rewrite in `next.config.mjs` lets the
runtime resolve it from `process.env.BACKEND_URL`.
