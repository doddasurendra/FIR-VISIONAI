# FIR VisionAI — Stop the dev servers started from THIS folder.
# Only processes whose command line identifies them as this checkout's uvicorn (app.main:app) or Vite
# server are stopped. Other programs - including anything else on ports 8000/5173 - are never touched.
$ErrorActionPreference = "Continue"
. "$PSScriptRoot\scripts\dev\common.ps1"

$procs = @(Get-FirProcesses)
if ($procs.Count -eq 0) {
    Write-Info "No FIR VisionAI dev servers from $RepoRoot are running."
    exit 0
}
foreach ($p in $procs) {
    $kind = if ($p.Name -eq "node.exe") { "frontend (Vite)" } else { "backend (uvicorn)" }
    Write-Info "Stopping $kind PID $($p.ProcessId)"
    # /T also ends the uvicorn reload worker / child processes of this server
    & taskkill.exe /PID $p.ProcessId /T /F | Out-Null
    if ($LASTEXITCODE -eq 0 -or -not (Get-Process -Id $p.ProcessId -ErrorAction SilentlyContinue)) { Write-Ok "Stopped $kind" }
    else { Write-Fail "Could not stop PID $($p.ProcessId) (exit code $LASTEXITCODE)" }
}
