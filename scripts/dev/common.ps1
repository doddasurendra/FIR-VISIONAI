# FIR VisionAI — shared helpers for the Windows start / stop / diagnose scripts.
# Dot-source it:  . "$PSScriptRoot\scripts\dev\common.ps1"

$script:RepoRoot     = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$script:BackendDir   = Join-Path $RepoRoot "backend"
$script:FrontendDir  = Join-Path $RepoRoot "frontend"
$script:LogDir       = Join-Path $RepoRoot "logs"
$script:BackendLog   = Join-Path $LogDir "backend.log"
$script:FrontendLog  = Join-Path $LogDir "frontend.log"
$script:StateFile    = Join-Path $LogDir "dev-state.json"

$script:FrontendPort       = 5173
$script:DefaultBackendPort = 8000
# Ports tried, in order, when 8000 is already used by another application
$script:BackendPortRange   = 8000..8010

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Resolve-Tool([string]$Name, [string]$PreferredPath) {
    if ($PreferredPath -and (Test-Path $PreferredPath)) { return $PreferredPath }
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    return $null
}

$script:PythonExe = Resolve-Tool "python.exe" "C:\Users\LENOVO\AppData\Local\Programs\Python\Python312\python.exe"
$script:NodeExe   = Resolve-Tool "node.exe"   "C:\Users\LENOVO\AppData\Local\Programs\PortableTools\node\node.exe"
$script:NpmCmd    = if ($NodeExe) { Join-Path (Split-Path $NodeExe) "npm.cmd" } else { $null }

function Write-Ok([string]$m)   { Write-Host "  [ OK ] $m" -ForegroundColor Green }
function Write-Warn([string]$m) { Write-Host "  [WARN] $m" -ForegroundColor Yellow }
function Write-Fail([string]$m) { Write-Host "  [FAIL] $m" -ForegroundColor Red }
function Write-Info([string]$m) { Write-Host "  [INFO] $m" -ForegroundColor Gray }

function Get-PortOwner([int]$Port) {
    # Returns $null if nothing listens on the port, otherwise the owning process (Id, Name, CommandLine)
    $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $conn) { return $null }
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$($conn.OwningProcess)" -ErrorAction SilentlyContinue
    [pscustomobject]@{
        Id          = [int]$conn.OwningProcess
        Name        = if ($proc) { $proc.Name } else { "<unknown>" }
        CommandLine = if ($proc) { $proc.CommandLine } else { "" }
        Address     = $conn.LocalAddress
    }
}

function Format-Owner($owner) {
    $cmd = $owner.CommandLine
    if ($cmd.Length -gt 160) { $cmd = $cmd.Substring(0, 160) + "..." }
    "PID $($owner.Id) ($($owner.Name)) on $($owner.Address) - $cmd"
}

function Get-FirBackendHealth([int]$Port, [int]$TimeoutSec = 3) {
    # The health JSON of FIR VisionAI, or $null if the port is closed or serves a different application
    try {
        $r = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/v1/health" -TimeoutSec $TimeoutSec -ErrorAction Stop
        $names = $r.PSObject.Properties.Name
        # "app" marker is new; older FIR backends are recognised by their health fields
        if ($r.app -eq "fir-visionai" -or (($names -contains "database_details") -and ($names -contains "storage_details"))) {
            return $r
        }
    } catch { }
    return $null
}

function Get-FirReadiness([int]$Port, [string]$BaseUrl = "", [int]$TimeoutSec = 25) {
    # Deep readiness report (database + storage). 503 still carries the report body.
    if (-not $BaseUrl) { $BaseUrl = "http://127.0.0.1:$Port" }
    try {
        $resp = Invoke-WebRequest -UseBasicParsing -Uri "$BaseUrl/api/v1/health/ready" -TimeoutSec $TimeoutSec -ErrorAction Stop
        return ($resp.Content | ConvertFrom-Json)
    } catch {
        $r = $_.Exception.Response
        if ($r) {
            try {
                $reader = New-Object System.IO.StreamReader($r.GetResponseStream())
                $body = $reader.ReadToEnd()
                if ($body) { return ($body | ConvertFrom-Json) }
            } catch { }
            # 404 = an older backend without the endpoint
            return [pscustomobject]@{ status = "unavailable"; error = "HTTP $([int]$r.StatusCode)" }
        }
        return [pscustomobject]@{ status = "unavailable"; error = $_.Exception.Message }
    }
}

function Test-FirFrontend([int]$Port = $FrontendPort, [int]$TimeoutSec = 3) {
    try {
        $r = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/" -TimeoutSec $TimeoutSec -ErrorAction Stop
        return ($r.StatusCode -eq 200 -and $r.Content -match "<title>FIR VisionAI")
    } catch { return $false }
}

function Find-FirBackendPort {
    # Port of an already-running, healthy FIR VisionAI backend, or $null
    foreach ($p in $BackendPortRange) {
        if (Get-PortOwner $p) { if (Get-FirBackendHealth $p 2) { return $p } }
    }
    return $null
}

function Get-FirProcesses {
    # Dev-server processes started from THIS checkout: uvicorn (app.main:app) and Vite. Verified by command line.
    $root = [regex]::Escape($RepoRoot)
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        $_.CommandLine -and (
            ($_.Name -eq "python.exe" -and $_.CommandLine -match "uvicorn" -and $_.CommandLine -match "app\.main:app" -and $_.CommandLine -match $root) -or
            ($_.Name -eq "node.exe" -and $_.CommandLine -match "vite" -and $_.CommandLine -match $root)
        )
    }
}

function Show-LogTail([string]$Path, [int]$Lines = 25) {
    if (Test-Path $Path) {
        Write-Host "  --- last $Lines lines of $Path ---" -ForegroundColor DarkGray
        Get-Content $Path -Tail $Lines | ForEach-Object { Write-Host "  | $_" -ForegroundColor DarkGray }
        Write-Host "  --- end of log ---" -ForegroundColor DarkGray
    } else {
        Write-Info "No log file yet at $Path"
    }
}

function Save-DevState([int]$BackendPort) {
    @{ backendPort = $BackendPort; updated = (Get-Date).ToString("s") } | ConvertTo-Json | Set-Content -Path $StateFile -Encoding UTF8
}

function Read-DevState {
    if (Test-Path $StateFile) { try { return (Get-Content $StateFile -Raw | ConvertFrom-Json) } catch { } }
    return $null
}

function Invoke-LoggedProcess([string]$LogPath, [scriptblock]$Command) {
    # Runs a native command, showing its output in this window AND writing it (UTF-8, no colour codes) to $LogPath.
    # Returns the command's exit code.
    if (Test-Path $LogPath) { Move-Item -Force $LogPath "$LogPath.previous" -ErrorAction SilentlyContinue }
    # Decode the child's output as UTF-8 (Vite prints non-ASCII symbols; Python is told to emit UTF-8)
    [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
    $env:PYTHONIOENCODING = "utf-8"
    $writer = New-Object System.IO.StreamWriter($LogPath, $false, (New-Object System.Text.UTF8Encoding($false)))
    $writer.AutoFlush = $true
    $writer.WriteLine("=== started $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ===")
    try {
        & $Command 2>&1 | ForEach-Object {
            $line = "$_"
            Write-Host $line
            $writer.WriteLine(($line -replace "\x1b\[[0-9;]*[A-Za-z]", ""))
        }
        $code = $LASTEXITCODE
    } finally {
        $writer.WriteLine("=== stopped $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') exit code $LASTEXITCODE ===")
        $writer.Dispose()
    }
    return $code
}

function Disable-QuickEdit {
    # A click inside a console with QuickEdit on starts a text selection, and every write to that console then
    # blocks until Enter/Esc - which silently freezes the server process logging to it. Turn it off for this window.
    try {
        Add-Type -Namespace FirDev -Name ConsoleMode -MemberDefinition @'
[DllImport("kernel32.dll", SetLastError = true)] public static extern IntPtr GetStdHandle(int nStdHandle);
[DllImport("kernel32.dll", SetLastError = true)] public static extern bool GetConsoleMode(IntPtr h, out uint mode);
[DllImport("kernel32.dll", SetLastError = true)] public static extern bool SetConsoleMode(IntPtr h, uint mode);
'@ -ErrorAction Stop
        $h = [FirDev.ConsoleMode]::GetStdHandle(-10)   # STD_INPUT_HANDLE
        $mode = 0
        if ([FirDev.ConsoleMode]::GetConsoleMode($h, [ref]$mode)) {
            # clear ENABLE_QUICK_EDIT_MODE (0x40), keep ENABLE_EXTENDED_FLAGS (0x80) so the change applies
            [void][FirDev.ConsoleMode]::SetConsoleMode($h, (($mode -band (-bnot 0x40)) -bor 0x80))
        }
    } catch { }
}

function Write-StoppedBanner([string]$Service, $ExitCode, [string]$LogPath) {
    Write-Host ""
    Write-Host "==================================================================" -ForegroundColor Red
    Write-Host "  FIR VisionAI $Service has STOPPED (exit code $ExitCode)." -ForegroundColor Red
    Write-Host "  The application is NOT running any more." -ForegroundColor Red
    Write-Host "  Log:      $LogPath" -ForegroundColor Yellow
    Write-Host "  Diagnose: powershell -ExecutionPolicy Bypass -File `"$RepoRoot\diagnose.ps1`"" -ForegroundColor Yellow
    Write-Host "  Restart:  double-click start_all.bat (or start_all.ps1 -Restart)" -ForegroundColor Yellow
    Write-Host "==================================================================" -ForegroundColor Red
}
