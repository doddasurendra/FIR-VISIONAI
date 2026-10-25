# FIR VisionAI — Launch Full Application (Backend + Frontend)
$pythonPath = "C:\Users\LENOVO\AppData\Local\Programs\Python\Python312"
$nodePath = "C:\Users\LENOVO\AppData\Local\Programs\PortableTools\node"
$gitPath = "C:\Users\LENOVO\AppData\Local\Programs\PortableTools\git\cmd"

$env:PATH = "$gitPath;$nodePath;$pythonPath;$pythonPath\Scripts;" + $env:PATH
$env:PYTHONPATH = "$PSScriptRoot\backend"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  FIR VisionAI — Startup Check  " -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# 1. Start Backend
Write-Host "[1/2] Starting FastAPI Backend on http://127.0.0.1:8000..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-File", "$PSScriptRoot\start_backend.ps1"

# Wait for backend to become ready
$attempts = 0
while ($attempts -lt 15) {
    Start-Sleep -Seconds 1
    try {
        $res = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/health" -TimeoutSec 2 -ErrorAction Stop
        if ($res.status -eq "healthy") {
            Write-Host "[SUCCESS] Backend is healthy!" -ForegroundColor Green
            break
        }
    } catch {
        $attempts++
    }
}

# 2. Start Frontend
Write-Host "[2/2] Starting Vite Frontend on http://localhost:5173..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-File", "$PSScriptRoot\start_frontend.ps1"

Write-Host ""
Write-Host "FIR VisionAI is ready:" -ForegroundColor Cyan
Write-Host "  Frontend: http://localhost:5173" -ForegroundColor Yellow
Write-Host "  Backend:  http://localhost:8000" -ForegroundColor Yellow
Write-Host "  Docs:     http://localhost:8000/docs" -ForegroundColor Yellow
