# Run the FastAPI backend on its own, without the monorepo root.
#
# This is the API-only equivalent of the root scripts\dev-api.ps1.
# It reads .env from the repo root and serves uvicorn on port 8000.
#
# Usage (PowerShell):
#   .\apps\api\scripts\dev-api.ps1
#
# Environment overrides (optional):
#   $env:API_PORT    default 8000
#   $env:API_HOST    default 127.0.0.1
$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..\..")
Set-Location $RepoRoot

$Host = if ($env:API_HOST) { $env:API_HOST } else { "127.0.0.1" }
$Port = if ($env:API_PORT) { $env:API_PORT } else { "8000" }
$Reload = if ($env:API_RELOAD -eq "false") { @() } else { @("--reload") }

& ".\apps\api\.venv\Scripts\python.exe" -m uvicorn app.main:app `
  @Reload `
  --host $Host `
  --port $Port `
  --app-dir apps/api
