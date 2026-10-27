# FIR VisionAI — Run All Tests Script
# Runs the full pytest suite and reports results.
# The tests create and change records, so they run against a temporary SQLite database with every cloud
# and AI credential blanked: they never touch the live Supabase database, storage bucket or AI quotas.

$pythonPath = "C:\Users\LENOVO\AppData\Local\Programs\Python\Python312"
$env:PATH = "$pythonPath;$pythonPath\Scripts;" + $env:PATH

$testDir = Join-Path $env:TEMP "fir_visionai_tests"
# Start from a fresh test database every run: records left by an earlier run change search rankings
Remove-Item -Recurse -Force $testDir -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path "$testDir\evidence", "$testDir\exports", "$testDir\backups" | Out-Null
$testDb = ($testDir -replace '\\', '/') + "/fir_test.db"

# Do not load .env at all (a missing file is ignored), and drop any credentials inherited from this shell.
# Note: in PowerShell `$env:X = ""` deletes X, so blanking variables would let .env values back in.
$env:FIR_ENV_FILE = "$testDir\no-credentials.env"
foreach ($name in "SUPABASE_DATABASE_URL", "SUPABASE_URL", "SUPABASE_KEY", "SUPABASE_SERVICE_ROLE_KEY", "GEMINI_API_KEY", "SARVAM_API_KEY") {
    Remove-Item "env:$name" -ErrorAction SilentlyContinue
}
$env:DATABASE_URL = "sqlite+aiosqlite:///$testDb"
$env:SYNC_DATABASE_URL = "sqlite:///$testDb"
$env:EVIDENCE_DIR = "$testDir\evidence"
$env:EXPORTS_DIR = "$testDir\exports"
$env:BACKUPS_DIR = "$testDir\backups"

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  FIR VisionAI — Test Suite             " -ForegroundColor Cyan
Write-Host "  Test database: $testDb"                 -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

if (-not (Test-Path "$testDir\fir_test.db")) {
    Write-Host "[INFO] Seeding the test database with demo data..." -ForegroundColor Yellow
    Push-Location $PSScriptRoot
    & python.exe scripts/seed_demo_data.py
    Pop-Location
}

Set-Location "$PSScriptRoot\backend"
& python.exe -m pytest tests/ -v --tb=short
$code = $LASTEXITCODE

Write-Host ""
if ($code -eq 0) { Write-Host "Tests complete: all passed." -ForegroundColor Green }
else { Write-Host "Tests complete: FAILURES (exit code $code)." -ForegroundColor Red }
exit $code
