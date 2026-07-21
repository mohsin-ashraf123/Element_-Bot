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
    throw "Dump not found: $DumpFile - run scripts/export-local-db.ps1 first"
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

# Railway gives postgres:// - psql accepts both
$url = $DatabaseUrl.Trim()
if ($url -notmatch '^(postgres(ql)?(\+psycopg2)?://)') {
    throw @"
Invalid DatabaseUrl. You passed a host/port only.

Copy the FULL DATABASE_URL from Railway:
  pairflow-db -> Variables -> DATABASE_URL

It must look like:
  postgresql://postgres:PASSWORD@sakura.proxy.rlwy.net:13305/railway

Then run:
  .\scripts\migrate-local-to-railway-db.ps1 -DatabaseUrl "postgresql://postgres:PASSWORD@sakura.proxy.rlwy.net:13305/railway"
"@
}
if ($url -match '^postgresql\+psycopg2://') {
    $url = $url -replace '^postgresql\+psycopg2://', 'postgresql://'
}
if ($url -match '^postgres://') {
    $url = $url -replace '^postgres://', 'postgresql://'
}

if ($url -match '\.railway\.internal') {
    throw @"
This DATABASE_URL uses Railway private networking (pairflow-db.railway.internal).
It only works INSIDE Railway, not from your PC.

For local import, use the PUBLIC TCP proxy from Railway:
  pairflow-db -> Settings -> Networking -> TCP Proxy

Replace the host in DATABASE_URL, for example:
  postgresql://postgres:PASSWORD@sakura.proxy.rlwy.net:13305/railway

Keep the same username, password, and database name - only change host and port.
"@
}

Write-Host "Importing $DumpFile ..."
Write-Host "Target: $($url -replace '://([^:@/]+):([^@/]+)@', '://***:***@')"
& $psql $url -v ON_ERROR_STOP=1 -f $DumpFile
if ($LASTEXITCODE -ne 0) { throw "psql import failed (exit $LASTEXITCODE)" }

Write-Host "Done. Link DATABASE_URL to your Railway backend service and redeploy."
