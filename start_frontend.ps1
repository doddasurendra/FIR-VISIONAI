# FIR Sahayak — Frontend Startup Script
# Starts the Vite dev server on http://localhost:5173

$nodePath = "C:\Users\LENOVO\AppData\Local\Programs\PortableTools\node"
$env:PATH = "$nodePath;" + $env:PATH

$frontendDir = "$PSScriptRoot\frontend"
Set-Location $frontendDir

Write-Host ""
Write-Host "========================================" -ForegroundColor Magenta
Write-Host "  FIR Sahayak — Frontend (React/Vite)  " -ForegroundColor Magenta
Write-Host "  http://localhost:5173                 " -ForegroundColor Magenta
Write-Host "========================================" -ForegroundColor Magenta
Write-Host ""
Write-Host "[INFO] Make sure the backend is running on port 8000 first!" -ForegroundColor Yellow
Write-Host ""

& npm.cmd run dev
