# FIR VisionAI — Launch Full Application (Backend + Frontend)
# Starts each server in its own window, waits until each one really answers, and only then reports success.
# Servers that are already running and healthy are reused, never duplicated.
#   .\start_all.ps1             start whatever is not running
#   .\start_all.ps1 -Restart    stop this checkout's dev servers first, then start fresh (recovery)
#   .\start_all.ps1 -NoBrowser  do not open the browser at the end
param([switch]$Restart, [switch]$NoBrowser, [int]$TimeoutSec = 120)

$ErrorActionPreference = "Continue"
. "$PSScriptRoot\scripts\dev\common.ps1"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  FIR VisionAI — Startup               " -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

function Stop-WithError([string]$Message, [string]$LogPath) {
    Write-Fail $Message
    if ($LogPath) { Show-LogTail $LogPath }
    Write-Host ""
    Write-Host "FIR VisionAI did NOT start completely." -ForegroundColor Red
    Write-Host "  Diagnose: powershell -ExecutionPolicy Bypass -File `"$RepoRoot\diagnose.ps1`"" -ForegroundColor Yellow
    Write-Host "  Logs:     $LogDir" -ForegroundColor Yellow
    exit 1
}

function Wait-ForService([string]$Name, [scriptblock]$IsUp, [string]$LogPath) {
    # Polls $IsUp until it is true. Fails fast if the server's log says it stopped. No restarts.
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        if (& $IsUp) { return $true }
        if ((Test-Path $LogPath) -and (Select-String -Path $LogPath -Pattern "^=== stopped" -Quiet)) {
            Stop-WithError "$Name exited during startup. See its window and the log below." $LogPath
        }
        Start-Sleep -Seconds 2
    }
    Stop-WithError "$Name did not become ready within $TimeoutSec seconds." $LogPath
}

# ---- 0. Pre-flight -------------------------------------------------------------------------------
Write-Host "[0/3] Pre-flight checks" -ForegroundColor Green
if (-not $PythonExe) { Stop-WithError "Python not found (C:\Users\LENOVO\AppData\Local\Programs\Python\Python312)." }
if (-not $NodeExe)   { Stop-WithError "Node.js not found (C:\Users\LENOVO\AppData\Local\Programs\PortableTools\node)." }
Write-Ok "Python: $PythonExe"
Write-Ok "Node:   $NodeExe"
if (-not (Test-Path "$FrontendDir\node_modules\.bin\vite.cmd")) {
    Write-Warn "frontend\node_modules is missing - installing the locked dependencies once (npm ci)..."
    $env:PATH = "$(Split-Path $NodeExe);" + $env:PATH
    Push-Location $FrontendDir
    & $NpmCmd ci --no-audit --no-fund
    $npmCode = $LASTEXITCODE
    Pop-Location
    if ($npmCode -ne 0) { Stop-WithError "npm ci failed (exit code $npmCode). Check the network connection and run 'cd frontend; npm ci' manually." }
}
Write-Ok "Frontend dependencies installed"
if (Test-Path "$RepoRoot\.env") { Write-Ok ".env found" }
else { Write-Warn ".env not found - Supabase and AI keys are not configured; the backend will use local SQLite." }

if ($Restart) {
    Write-Info "Restart requested - stopping this checkout's dev servers first."
    & "$RepoRoot\stop_all.ps1"
    Start-Sleep -Seconds 2
}

# ---- 1. Backend ----------------------------------------------------------------------------------
Write-Host "[1/3] Backend (FastAPI)" -ForegroundColor Green
$backendPort = Find-FirBackendPort
if ($backendPort) {
    Write-Ok "Already running and healthy on port $backendPort - reusing it."
} else {
    $stale = @(Get-FirProcesses | Where-Object { $_.Name -eq "python.exe" })
    if ($stale.Count -gt 0) {
        Stop-WithError ("A FIR VisionAI backend process is running (PID $(($stale.ProcessId) -join ', ')) but does not answer health checks. " +
            "It may be hung or still starting. Recover with:  .\start_all.ps1 -Restart") $BackendLog
    }
    foreach ($p in $BackendPortRange) {
        $owner = Get-PortOwner $p
        if (-not $owner) { $backendPort = $p; break }
        Write-Warn "Port $p is used by another program (left untouched): $(Format-Owner $owner)"
    }
    if (-not $backendPort) { Stop-WithError "No free backend port in $($BackendPortRange[0])-$($BackendPortRange[-1])." }
    if ($backendPort -ne $DefaultBackendPort) { Write-Warn "Starting the backend on port $backendPort instead of $DefaultBackendPort." }

    # Keep the last run's log; a stale "=== stopped" line must not be mistaken for this start failing
    if (Test-Path $BackendLog) { Move-Item -Force $BackendLog "$BackendLog.previous" -ErrorAction SilentlyContinue }
    Start-Process powershell -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-File", "`"$RepoRoot\start_backend.ps1`"", "-Port", $backendPort | Out-Null
    Write-Info "Started in a new window 'FIR VisionAI Backend :$backendPort'. Waiting for it to answer (up to $TimeoutSec s)..."
    Wait-ForService "Backend" { [bool](Get-FirBackendHealth $backendPort) } $BackendLog | Out-Null
    Write-Ok "Backend is answering on http://127.0.0.1:$backendPort"
}
Save-DevState $backendPort

$ready = Get-FirReadiness $backendPort
$problems = @()
if ($ready.checks) {
    $db = $ready.checks.database; $st = $ready.checks.storage
    if ($db.ok) { Write-Ok "Database ($($db.engine)) answered in $($db.latency_ms) ms" }
    else { Write-Fail "Database ($($db.engine)) check failed: $($db.error)"; $problems += "database" }
    if ($st.ok) { Write-Ok "Storage ($($st.backend)) reachable" }
    else { Write-Fail "Storage ($($st.backend)) check failed: $($st.error)"; $problems += "storage" }
} else {
    Write-Warn "Readiness check unavailable ($($ready.error)); database and storage were not verified."
    $problems += "readiness check"
}

# ---- 2. Frontend ---------------------------------------------------------------------------------
Write-Host "[2/3] Frontend (Vite)" -ForegroundColor Green
$owner = Get-PortOwner $FrontendPort
if ($owner) {
    if (-not (Test-FirFrontend)) {
        Stop-WithError "Port $FrontendPort is used by another program (left untouched): $(Format-Owner $owner). Close that program and run start_all again."
    }
    Write-Ok "Already running on port $FrontendPort - reusing it."
} else {
    if (Test-Path $FrontendLog) { Move-Item -Force $FrontendLog "$FrontendLog.previous" -ErrorAction SilentlyContinue }
    Start-Process powershell -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-File", "`"$RepoRoot\start_frontend.ps1`"", "-BackendPort", $backendPort | Out-Null
    Write-Info "Started in a new window 'FIR VisionAI Frontend :$FrontendPort'. Waiting for it to answer..."
    Wait-ForService "Frontend" { Test-FirFrontend } $FrontendLog | Out-Null
    Write-Ok "Frontend is answering on http://localhost:$FrontendPort"
}

# ---- 3. Frontend -> backend ----------------------------------------------------------------------
Write-Host "[3/3] Frontend -> backend connection" -ForegroundColor Green
if (Get-FirBackendHealth $FrontendPort 15) {
    Write-Ok "http://localhost:$FrontendPort/api reaches the backend"
} else {
    Stop-WithError ("The frontend on port $FrontendPort cannot reach the backend on port $backendPort through its /api proxy " +
        "(it was probably started for a different backend port). Recover with:  .\start_all.ps1 -Restart") $FrontendLog
}

Write-Host ""
if ($problems.Count -eq 0) {
    Write-Host "FIR VisionAI is running and verified:" -ForegroundColor Cyan
} else {
    Write-Host "FIR VisionAI is running, but these checks FAILED: $($problems -join ', ')." -ForegroundColor Yellow
    Write-Host "Pages load, but features that need them will show errors. Run diagnose.ps1 for details." -ForegroundColor Yellow
}
Write-Host "  Frontend: http://localhost:$FrontendPort" -ForegroundColor Yellow
Write-Host "  Backend:  http://localhost:$backendPort  (API docs: http://localhost:$backendPort/docs)" -ForegroundColor Yellow
Write-Host "  Logs:     $LogDir" -ForegroundColor Yellow
Write-Host "  Keep the two server windows open; closing one stops that server." -ForegroundColor Gray
if (-not $NoBrowser) { Start-Process "http://localhost:$FrontendPort" }
if ($problems.Count -gt 0) { exit 2 }
exit 0
