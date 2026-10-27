@echo off
title FIR VisionAI Diagnostics
powershell -ExecutionPolicy Bypass -File "%~dp0diagnose.ps1"
pause
