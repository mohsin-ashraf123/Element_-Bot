# Import local_db_export.sql into Railway (or any remote) Postgres
param(
    [Parameter(Mandatory = $true)]
    [string]$DatabaseUrl,

    [string]$DumpFile = ""
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
if (-not $DumpFile) {
    $DumpFile = Join-Path $root "backend\data\local_db_export.sql"
}
if (-not (Test-Path $DumpFile)) {
    throw "Dump not found: $DumpFile — run scripts/export-local-db.ps1 first"
}

$psql = Get-Command psql -ErrorAction SilentlyContinue
if (-not $psql) {
    $candidates = Get-ChildItem "C:\Program Files\PostgreSQL\*\bin\psql.exe" -ErrorAction SilentlyContinue |
        Sort-Object { [int]($_.Directory.Parent.Name) } -Descending
    if ($candidates) { $psql = $candidates[0].FullName }
}
if (-not $psql) {
    throw "psql not found. Install PostgreSQL client tools."
}

# Railway gives postgres:// — psql accepts both
$url = $DatabaseUrl
if ($url -match '^postgresql\+psycopg2://') {
    $url = $url -replace '^postgresql\+psycopg2://', 'postgresql://'
}

Write-Host "Importing $DumpFile ..."
& $psql $url -v ON_ERROR_STOP=1 -f $DumpFile
if ($LASTEXITCODE -ne 0) { throw "psql import failed (exit $LASTEXITCODE)" }

Write-Host "Done. Link DATABASE_URL to your Railway backend service and redeploy."
