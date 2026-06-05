$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

& ".\apps\api\.venv\Scripts\python.exe" -m uvicorn app.main:app `
  --reload `
  --host 127.0.0.1 `
  --port 8000 `
  --app-dir apps\api
