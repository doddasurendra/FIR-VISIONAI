# FIR VisionAI — Diagnose "localhost refused to connect" and other startup problems.
# Read-only: it never starts, stops or changes anything. Prints what is wrong and what to do.
#   powershell -ExecutionPolicy Bypass -File diagnose.ps1      (or double-click diagnose.bat)
$ErrorActionPreference = "Continue"
. "$PSScriptRoot\scripts\dev\common.ps1"

$issues = New-Object System.Collections.Generic.List[string]
$fixes  = New-Object System.Collections.Generic.List[string]

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  FIR VisionAI — Diagnostics            " -ForegroundColor Cyan
Write-Host "  $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"  -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# ---- Environment ----
Write-Host "`n[1] Environment" -ForegroundColor Green
if ($PythonExe) { Write-Ok "Python: $PythonExe" } else { Write-Fail "Python not found"; $issues.Add("Python is missing") }
if ($NodeExe)   { Write-Ok "Node:   $NodeExe" }   else { Write-Fail "Node.js not found"; $issues.Add("Node.js is missing") }
if (Test-Path "$FrontendDir\node_modules\.bin\vite.cmd") { Write-Ok "Frontend dependencies installed" }
else { Write-Fail "frontend\node_modules missing"; $issues.Add("Frontend dependencies are not installed"); $fixes.Add("cd frontend; npm ci   (start_all.ps1 also does this automatically)") }
if (Test-Path "$RepoRoot\.env") {
    # Report which settings are present - never their values
    $names = Get-Content "$RepoRoot\.env" | Where-Object { $_ -match '^\s*([A-Z_]+)\s*=\s*\S' } | ForEach-Object { $Matches[1] }
    Write-Ok ".env found"
    foreach ($k in "SUPABASE_DATABASE_URL", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "GEMINI_API_KEY", "SARVAM_API_KEY") {
        if ($names -contains $k) { Write-Ok "$k is set" } else { Write-Warn "$k is not set" }
    }
} else {
    Write-Warn ".env not found - the backend will run on local SQLite without Supabase or AI keys"
}
$boot = (Get-CimInstance Win32_OperatingSystem).LastBootUpTime
Write-Info "Windows last started: $boot (dev servers do not start automatically after a restart)"

# ---- Backend ----
Write-Host "`n[2] Backend (FastAPI)" -ForegroundColor Green
$state = Read-DevState
$backendPort = Find-FirBackendPort
foreach ($p in $BackendPortRange) {
    $owner = Get-PortOwner $p
    if (-not $owner) { continue }
    if ($p -eq $backendPort) { Write-Ok "Port ${p}: FIR VisionAI backend - $(Format-Owner $owner)" }
    else { Write-Warn "Port ${p}: used by ANOTHER program - $(Format-Owner $owner)" }
}
if ($backendPort) {
    $ready = Get-FirReadiness $backendPort
    if ($ready.checks) {
        $db = $ready.checks.database; $st = $ready.checks.storage
        if ($db.ok) { Write-Ok "Database ($($db.engine)) answered in $($db.latency_ms) ms" }
        else { Write-Fail "Database ($($db.engine)): $($db.error)"; $issues.Add("Database check failed"); $fixes.Add("Check the internet connection and Supabase project status; see logs\backend.log") }
        if ($st.ok) { Write-Ok "Storage ($($st.backend)) reachable" }
        else { Write-Fail "Storage ($($st.backend)): $($st.error)"; $issues.Add("Storage check failed") }
    } else {
        Write-Warn "Readiness endpoint unavailable ($($ready.error)) - this backend may be an older version; restart it to get database checks."
    }
} else {
    Write-Fail "No FIR VisionAI backend is answering on ports $($BackendPortRange[0])-$($BackendPortRange[-1])"
    $issues.Add("Backend is not running")
    $fixes.Add("Run start_all.bat")
    if (Get-PortOwner $DefaultBackendPort) { Write-Info "start_all.bat will leave the program on port $DefaultBackendPort alone and use the next free port." }
    if ($state) { Write-Info "Last start used port $($state.backendPort) at $($state.updated)" }
}

# ---- Frontend ----
Write-Host "`n[3] Frontend (Vite) - http://localhost:$FrontendPort" -ForegroundColor Green
$fOwner = Get-PortOwner $FrontendPort
if (-not $fOwner) {
    Write-Fail "Nothing is listening on port $FrontendPort - this is exactly what causes ERR_CONNECTION_REFUSED in Chrome"
    $issues.Add("Frontend is not running")
    $fixes.Add("Run start_all.bat")
} elseif (Test-FirFrontend) {
    Write-Ok "FIR VisionAI frontend answering - $(Format-Owner $fOwner)"
    if (Get-FirBackendHealth $FrontendPort 15) { Write-Ok "Frontend /api proxy reaches the backend" }
    else {
        Write-Fail "Frontend is up, but its /api proxy does not reach a FIR VisionAI backend"
        $issues.Add("Frontend cannot reach backend")
        $fixes.Add("Run start_all.ps1 -Restart so both servers are started with matching ports")
    }
} else {
    Write-Fail "Port $FrontendPort is used by another program: $(Format-Owner $fOwner)"
    $issues.Add("Port $FrontendPort taken by another program")
    $fixes.Add("Close that program, then run start_all.bat")
}

# ---- Processes ----
Write-Host "`n[4] FIR VisionAI dev-server processes from this folder" -ForegroundColor Green
$procs = @(Get-FirProcesses)
if ($procs.Count -eq 0) { Write-Info "None running" }
foreach ($p in $procs) { Write-Info "PID $($p.ProcessId) $($p.Name) started $($p.CreationDate)" }
if (($procs | Where-Object Name -eq "python.exe") -and -not $backendPort) {
    $issues.Add("Backend process exists but is not answering (hung or still starting)")
    $fixes.Add("Run start_all.ps1 -Restart")
}

# ---- Logs ----
Write-Host "`n[5] Logs ($LogDir)" -ForegroundColor Green
foreach ($log in $BackendLog, $FrontendLog) {
    if (-not (Test-Path $log)) { Write-Info "$(Split-Path $log -Leaf): not created yet"; continue }
    $stopped = Select-String -Path $log -Pattern "^=== stopped" | Select-Object -Last 1
    $errors = @(Select-String -Path $log -Pattern "Traceback|ERROR|Error:|EADDRINUSE|address already in use|10048" | Select-Object -Last 5)
    Write-Info "$(Split-Path $log -Leaf): last written $((Get-Item $log).LastWriteTime)"
    if ($stopped) { Write-Warn "Server recorded that it stopped: $($stopped.Line)" }
    if ($errors.Count -gt 0) {
        Write-Warn "Recent error lines:"
        $errors | ForEach-Object { Write-Host "    $($_.Line)" -ForegroundColor DarkYellow }
    }
    if ($stopped -or $errors.Count -gt 0) { Show-LogTail $log 15 }
}

# ---- Verdict ----
Write-Host "`n========================================" -ForegroundColor Cyan
if ($issues.Count -eq 0) {
    Write-Host "  All checks passed. Open http://localhost:$FrontendPort" -ForegroundColor Green
    exit 0
}
Write-Host "  Problems found:" -ForegroundColor Red
$issues | Select-Object -Unique | ForEach-Object { Write-Host "   - $_" -ForegroundColor Red }
Write-Host "  What to do:" -ForegroundColor Yellow
$fixes | Select-Object -Unique | ForEach-Object { Write-Host "   - $_" -ForegroundColor Yellow }
exit 1
