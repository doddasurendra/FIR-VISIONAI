# FIR Sahayak — Run All Tests Script
# Runs the full pytest suite and reports results

$pythonPath = "C:\Users\LENOVO\AppData\Local\Programs\Python\Python312"
$env:PATH = "$pythonPath;$pythonPath\Scripts;" + $env:PATH

$backendDir = "$PSScriptRoot\backend"
Set-Location $backendDir

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  FIR Sahayak — Test Suite              " -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

& python.exe -m pytest tests/ -v --tb=short

Write-Host ""
Write-Host "Tests complete." -ForegroundColor Green
