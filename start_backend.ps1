# FIR VisionAI — Backend Startup Script
# Starts the FastAPI backend (default http://localhost:8000). Output is also written to logs\backend.log.
# Normally launched by start_all.ps1, which picks a free port; can also be run on its own.
param([int]$Port = 8000)

$ErrorActionPreference = "Continue"
. "$PSScriptRoot\scripts\dev\common.ps1"
$Host.UI.RawUI.WindowTitle = "FIR VisionAI Backend :$Port"
Disable-QuickEdit

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  FIR VisionAI — Backend (FastAPI)      " -ForegroundColor Cyan
Write-Host "  http://localhost:$Port                " -ForegroundColor Cyan
Write-Host "  API Docs: http://localhost:$Port/docs " -ForegroundColor Cyan
Write-Host "  Log: $BackendLog"                      -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

if (-not $PythonExe) {
    Write-Fail "Python was not found (expected C:\Users\LENOVO\AppData\Local\Programs\Python\Python312\python.exe or python.exe on PATH)."
    exit 1
}
$env:PATH = "$(Split-Path $PythonExe);$(Split-Path $PythonExe)\Scripts;" + $env:PATH
$env:PYTHONUNBUFFERED = "1"

$owner = Get-PortOwner $Port
if ($owner) {
    if (Get-FirBackendHealth $Port) {
        Write-Ok "FIR VisionAI backend is already running on port $Port - not starting a second copy."
    } else {
        Write-Fail "Port $Port is already in use by another program: $(Format-Owner $owner)"
        Write-Info "Use another port, e.g.:  .\start_backend.ps1 -Port 8001   (start_all.ps1 does this automatically)"
    }
    exit 1
}

if (-not (Test-Path "$RepoRoot\.env")) {
    Write-Warn ".env not found in $RepoRoot - Supabase and AI keys are not configured; the local SQLite fallback will be used."
}

# Seed demo data only for a local SQLite setup with no database yet; never against Supabase
$usesSupabase = (Test-Path "$RepoRoot\.env") -and (Select-String -Path "$RepoRoot\.env" -Pattern '^\s*SUPABASE_DATABASE_URL\s*=\s*\S' -Quiet)
$dbPath = "$RepoRoot\data\fir_sahayak.db"
if (-not $usesSupabase -and -not (Test-Path $dbPath)) {
    Write-Info "Local database not found. Seeding demo data..."
    Push-Location $RepoRoot
    & $PythonExe scripts/seed_demo_data.py
    Pop-Location
}

Set-Location $BackendDir
Write-Info "Starting backend server on port $Port..."

# uvicorn writes logs\backend.log itself (console + file). It must NOT be piped through PowerShell:
# on Windows its --reload restarts the worker with a Ctrl+C event, which would abort a PowerShell pipeline
# and take the whole backend down on the first code change.
if (Test-Path $BackendLog) { Move-Item -Force $BackendLog "$BackendLog.previous" -ErrorAction SilentlyContinue }
$utf8 = New-Object System.Text.UTF8Encoding($false)
[IO.File]::WriteAllText($BackendLog, "=== started $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') port $Port ===`r`n", $utf8)
$logConfig = Join-Path $LogDir "uvicorn-log-config.json"
@{
    version = 1
    disable_existing_loggers = $false
    formatters = @{
        console = @{ "()" = "uvicorn.logging.DefaultFormatter"; fmt = "%(levelprefix)s %(message)s" }
        access  = @{ "()" = "uvicorn.logging.AccessFormatter"; fmt = '%(levelprefix)s %(client_addr)s - "%(request_line)s" %(status_code)s' }
        file    = @{ format = "%(asctime)s %(levelname)s %(name)s: %(message)s" }
    }
    handlers = @{
        console        = @{ class = "logging.StreamHandler"; formatter = "console"; stream = "ext://sys.stderr" }
        access_console = @{ class = "logging.StreamHandler"; formatter = "access"; stream = "ext://sys.stdout" }
        file           = @{ class = "logging.FileHandler"; formatter = "file"; filename = $BackendLog; encoding = "utf-8" }
    }
    loggers = @{
        "uvicorn"        = @{ handlers = @("console", "file"); level = "INFO"; propagate = $false }
        "uvicorn.access" = @{ handlers = @("access_console", "file"); level = "INFO"; propagate = $false }
        "httpx"          = @{ level = "WARNING" }
        "httpcore"       = @{ level = "WARNING" }
    }
    # Application loggers (e.g. app.errors with the error reference shown to users) go to console and file
    root = @{ handlers = @("console", "file"); level = "INFO" }
} | ConvertTo-Json -Depth 5 | ForEach-Object { [IO.File]::WriteAllText($logConfig, $_, $utf8) }

# --app-dir puts this checkout's path on the command line, so stop_all/diagnose can recognise the process
& $PythonExe -m uvicorn app.main:app --app-dir $BackendDir --reload --reload-dir "$BackendDir\app" --host 0.0.0.0 --port $Port --log-config $logConfig
$code = $LASTEXITCODE
[IO.File]::AppendAllText($BackendLog, "=== stopped $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') exit code $code ===`r`n", $utf8)
Write-StoppedBanner "backend" $code $BackendLog
