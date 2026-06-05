$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

# The FastAPI startup hook calls init_db() which runs ``alembic upgrade
# head`` itself. Running alembic here as a separate process would
# briefly hold a SQLite write lock and race with the server, so we let
# the app own schema upgrades. If init_db fails, the server crashes
# loudly on startup.

& ".\apps\api\.venv\Scripts\python.exe" -m uvicorn app.main:app `
  --reload `
  --host 127.0.0.1 `
  --port 8000 `
  --reload-dir apps\api `
  --reload-exclude "apps\\api\\data" `
  --reload-exclude "apps\\api\\storage" `
  --reload-exclude "apps\\api\\alembic\\versions" `
  --app-dir apps\api
