$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

$Port = 3000
$Listener = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue |
  Where-Object { $_.State -eq "Listen" } |
  Select-Object -First 1

if ($Listener -and $Listener.OwningProcess -ne 0) {
  $Process = Get-CimInstance Win32_Process -Filter "ProcessId = $($Listener.OwningProcess)"
  $CommandLine = $Process.CommandLine
  $RootText = $Root.Path
  if ($CommandLine -like "*$RootText*" -or $CommandLine -like "*apps\web*") {
    Write-Host "Stopping existing project web server on port $Port (PID $($Listener.OwningProcess))..."
    Stop-Process -Id $Listener.OwningProcess -Force
    Start-Sleep -Seconds 1
  } else {
    Write-Error "Port $Port is already in use by PID $($Listener.OwningProcess): $CommandLine"
  }
}

$env:NEXT_DIST_DIR = ".next-dev"
if (-not [Environment]::GetEnvironmentVariable("BACKEND_URL", "Process")) {
  $env:BACKEND_URL = "http://127.0.0.1:8000"
}
if (-not [Environment]::GetEnvironmentVariable("NEXT_PUBLIC_API_BASE", "Process")) {
  $env:NEXT_PUBLIC_API_BASE = "/api"
}

Write-Host "Starting web with BACKEND_URL=$env:BACKEND_URL"

$NextDir = Join-Path $Root "apps\web\$env:NEXT_DIST_DIR"
if (Test-Path $NextDir) {
  Write-Host "Clearing stale Next.js cache..."
  Remove-Item -LiteralPath $NextDir -Recurse -Force
}

pnpm --dir apps/web dev
