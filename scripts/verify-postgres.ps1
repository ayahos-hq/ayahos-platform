[CmdletBinding()]
param(
    [string]$DatabaseUrl = $env:TEST_DATABASE_URL,
    [string]$ContainerName = "goblin-dual-lineage-postgres-local",
    [int]$HostPort = 55432,
    [switch]$KeepContainer
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
$createdContainer = $false

function Invoke-Docker([string[]]$Arguments) {
    & docker @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Docker command failed ($LASTEXITCODE): docker $($Arguments -join ' ')"
    }
}

try {
    if (-not $DatabaseUrl) {
        if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
            throw "Docker CLI is required when TEST_DATABASE_URL is unset. Install/start Docker Desktop, then rerun scripts/verify-postgres.ps1."
        }

        & docker info *> $null
        if ($LASTEXITCODE -ne 0) {
            throw "Docker engine is unavailable. Set TEST_DATABASE_URL to a reachable PostgreSQL database or start Docker Desktop, then rerun scripts/verify-postgres.ps1."
        }

        $DatabaseUrl = "postgresql://dual_lineage:dual_lineage@127.0.0.1:$HostPort/dual_lineage_test"
        $existing = (& docker ps -aq --filter "name=^$ContainerName$").Trim()
        if ($existing) {
            Invoke-Docker @("rm", "-f", $ContainerName)
        }
        Invoke-Docker @(
            "run", "-d", "--name", $ContainerName,
            "-e", "POSTGRES_USER=dual_lineage",
            "-e", "POSTGRES_PASSWORD=dual_lineage",
            "-e", "POSTGRES_DB=dual_lineage_test",
            "-p", "$HostPort`:5432",
            "postgres:18"
        )
        $createdContainer = $true

        for ($attempt = 1; $attempt -le 30; $attempt++) {
            & docker exec $ContainerName pg_isready -U dual_lineage -d dual_lineage_test *> $null
            if ($LASTEXITCODE -eq 0) { break }
            if ($attempt -eq 30) { throw "PostgreSQL container did not become ready within 30 seconds." }
            Start-Sleep -Seconds 1
        }
    }

    if (-not (Test-Path $python)) {
        throw "Repository virtualenv not found at $python. Create it or set up the documented API environment first."
    }

    $env:TEST_DATABASE_URL = $DatabaseUrl
    Push-Location $repoRoot
    try {
        & $python -m dual_lineage.db migrate --database-url $DatabaseUrl
        if ($LASTEXITCODE -ne 0) { throw "Database migration verification failed." }
        & $python -m pytest -q `
            apps/api/tests/test_database_migrations.py `
            apps/api/tests/test_operational_postgres.py `
            apps/api/tests/test_rate_limit_postgres.py `
            apps/api/tests/test_spine_postgres.py
        if ($LASTEXITCODE -ne 0) { throw "PostgreSQL durability tests failed." }
    }
    finally {
        Pop-Location
    }
}
finally {
    if ($createdContainer -and -not $KeepContainer) {
        & docker rm -f $ContainerName *> $null
    }
}
