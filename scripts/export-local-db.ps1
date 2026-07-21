# Export local PostgreSQL (same data you use in dev) for Railway import
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $root "backend\.env"

if (-not (Test-Path $envFile)) { throw "Missing backend/.env" }
$vars = @{}
Get-Content $envFile | ForEach-Object {
    if ($_ -match '^\s*#' -or $_ -notmatch '=') { return }
    $k, $v = $_ -split '=', 2
    $vars[$k.Trim()] = $v.Trim()
}

$pgDump = Get-Command pg_dump -ErrorAction SilentlyContinue
if (-not $pgDump) {
    $candidates = Get-ChildItem "C:\Program Files\PostgreSQL\*\bin\pg_dump.exe" -ErrorAction SilentlyContinue |
        Sort-Object { [int]($_.Directory.Parent.Name) } -Descending
    if ($candidates) { $pgDump = $candidates[0].FullName }
}
if (-not $pgDump) {
    throw "pg_dump not found. Install PostgreSQL client tools or add bin to PATH."
}

$out = Join-Path $root "backend\data\local_db_export.sql"
New-Item -ItemType Directory -Force -Path (Split-Path $out) | Out-Null

$env:PGPASSWORD = $vars.DB_PASSWORD
& $pgDump -h $vars.DB_HOST -p $vars.DB_PORT -U $vars.DB_USER -d $vars.DB_NAME `
    --no-owner --no-acl --clean --if-exists -f $out

if ($LASTEXITCODE -ne 0) {
    throw "pg_dump failed. Ensure local PostgreSQL is running."
}

Write-Host "Exported to $out ($((Get-Item $out).Length) bytes)"
Write-Host ""
Write-Host "Import to Railway Postgres:"
Write-Host '  .\scripts\import-railway-db.ps1 -DatabaseUrl "postgresql://user:pass@host:port/railway"'
