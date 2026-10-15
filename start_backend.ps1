# FIR Sahayak — Backend Startup Script
# Starts the FastAPI backend on http://localhost:8000

$pythonPath = "C:\Users\LENOVO\AppData\Local\Programs\Python\Python312"
$env:PATH = "$pythonPath;$pythonPath\Scripts;" + $env:PATH

$backendDir = "$PSScriptRoot\backend"
Set-Location $backendDir

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  FIR Sahayak — Backend (FastAPI)       " -ForegroundColor Cyan
Write-Host "  http://localhost:8000                  " -ForegroundColor Cyan
Write-Host "  API Docs: http://localhost:8000/docs   " -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check if database exists; if not, seed demo data
$dbPath = "$PSScriptRoot\data\fir_sahayak.db"
if (-Not (Test-Path $dbPath)) {
    Write-Host "[INFO] Database not found. Seeding demo data..." -ForegroundColor Yellow
    & python.exe scripts/seed_demo_data.py
}

Write-Host "[INFO] Starting backend server..." -ForegroundColor Green
& python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
