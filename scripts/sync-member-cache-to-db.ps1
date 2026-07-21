# Import local member_feed_cache.json into PostgreSQL (included in pg_dump for Railway)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "backend"
$venvPy = Join-Path $backend "venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) { $venvPy = Join-Path $backend ".venv\Scripts\python.exe" }
if (-not (Test-Path $venvPy)) { $venvPy = "python" }

Push-Location $backend
try {
    & $venvPy -c "from pathlib import Path; from app.services.room_feed_cache_db import import_json_file; from app.core.config import settings; p=Path(settings.matrix_e2ee_store_path).resolve().parent/'member_feed_cache.json'; n=import_json_file(p); print('Imported', n, 'messages from', p)"
} finally {
    Pop-Location
}

Write-Host ""
Write-Host "Re-export DB for Railway:"
Write-Host "  .\scripts\export-local-db.ps1"
Write-Host "  .\scripts\import-railway-db.ps1 -DatabaseUrl `"YOUR_RAILWAY_DATABASE_URL`""
