# Starts backend (FastAPI) and frontend (Vite) in separate PowerShell windows

param(
  [switch]$NoBackend,
  [switch]$NoFrontend
)

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$workspace = Split-Path -Parent $root

function Start-Backend {
  Write-Host "Starting backend on http://127.0.0.1:8000" -ForegroundColor Cyan
  $backend = Join-Path $workspace 'backend'
  $envFile = Join-Path $backend '.env'
  if (-not (Test-Path $envFile)) {
    Write-Warning "backend/.env no existe. Copia backend/.env.example a backend/.env y coloca tus claves."
  }
  # Ejecuta en el directorio correcto para que 'app.main' se resuelva
  Start-Process -WindowStyle Minimized -WorkingDirectory $backend pwsh -ArgumentList \
    "-NoLogo","-NoProfile","-Command","uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"
}

function Start-Frontend {
  Write-Host "Starting frontend on http://localhost:5174" -ForegroundColor Green
  $web = Join-Path $workspace 'web'
  $envFile = Join-Path $web '.env.local'
  if (-not (Test-Path $envFile)) {
    Write-Warning "web/.env.local no existe. Copia web/.env.local.example a web/.env.local y configura VITE_*"
  }
  Start-Process -WindowStyle Minimized -WorkingDirectory $web pwsh -ArgumentList \
    "-NoLogo","-NoProfile","-Command","npm run dev -- --port 5174 --strictPort"
}

if (-not $NoBackend) { Start-Backend }
if (-not $NoFrontend) { Start-Frontend }
