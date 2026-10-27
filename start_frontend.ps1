# FIR VisionAI — Frontend Startup Script
# Starts the Vite dev server on http://localhost:5173 and proxies /api to the backend on -BackendPort.
# Output is also written to logs\frontend.log. Normally launched by start_all.ps1.
param([int]$BackendPort = 0)

$ErrorActionPreference = "Continue"
. "$PSScriptRoot\scripts\dev\common.ps1"
$Host.UI.RawUI.WindowTitle = "FIR VisionAI Frontend :$FrontendPort"
Disable-QuickEdit

if ($BackendPort -eq 0) {
    # Not given: use the running FIR backend if there is one, else the default
    $found = Find-FirBackendPort
    $BackendPort = if ($found) { $found } else { $DefaultBackendPort }
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Magenta
Write-Host "  FIR VisionAI — Frontend (React/Vite) " -ForegroundColor Magenta
Write-Host "  http://localhost:$FrontendPort        " -ForegroundColor Magenta
Write-Host "  API proxy -> http://127.0.0.1:$BackendPort" -ForegroundColor Magenta
Write-Host "  Log: $FrontendLog"                     -ForegroundColor Magenta
Write-Host "========================================" -ForegroundColor Magenta
Write-Host ""

if (-not $NodeExe) {
    Write-Fail "Node.js was not found (expected C:\Users\LENOVO\AppData\Local\Programs\PortableTools\node\node.exe or node.exe on PATH)."
    exit 1
}
$env:PATH = "$(Split-Path $NodeExe);" + $env:PATH

if (-not (Test-Path "$FrontendDir\node_modules\.bin\vite.cmd")) {
    Write-Fail "Frontend dependencies are not installed (frontend\node_modules is missing)."
    Write-Info "Install them once with:  cd frontend; npm ci"
    exit 1
}

$owner = Get-PortOwner $FrontendPort
if ($owner) {
    if (Test-FirFrontend) {
        Write-Ok "FIR VisionAI frontend is already running on port $FrontendPort - not starting a second copy."
    } else {
        Write-Fail "Port $FrontendPort is already in use by another program: $(Format-Owner $owner)"
    }
    exit 1
}

if (-not (Get-FirBackendHealth $BackendPort)) {
    Write-Warn "The FIR VisionAI backend is not answering on port $BackendPort yet. Pages will show 'backend not reachable' until it is up."
}

$env:VITE_API_PROXY_TARGET = "http://127.0.0.1:$BackendPort"
Set-Location $FrontendDir
$code = Invoke-LoggedProcess $FrontendLog { & $NpmCmd run dev }
Write-StoppedBanner "frontend" $code $FrontendLog
