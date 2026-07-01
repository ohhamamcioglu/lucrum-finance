# LUCRUM Portfolio Platform - Start Script
$root = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host ""
Write-Host "LUCRUM Portfolio Platform baslatiliyor..." -ForegroundColor Cyan
Write-Host ""

# Backend
Write-Host "Backend baslatiliyor (port 8000)..." -ForegroundColor Yellow
$backendCmd = "cd `"$root\backend`"; `$env:PYTHONIOENCODING='utf-8'; python -m uvicorn app:app --reload --host 127.0.0.1 --port 8000"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $backendCmd -WindowStyle Normal

Start-Sleep -Seconds 3

# Frontend
Write-Host "Frontend baslatiliyor (port 3000)..." -ForegroundColor Yellow
$frontendCmd = "cd `"$root\frontend`"; npm run dev"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $frontendCmd -WindowStyle Normal

Start-Sleep -Seconds 4

Write-Host ""
Write-Host "Sistem hazir!" -ForegroundColor Green
Write-Host "  Uygulama : http://localhost:3000" -ForegroundColor Cyan
Write-Host "  API Docs : http://localhost:8000/docs" -ForegroundColor Cyan
Write-Host ""

Start-Process "http://localhost:3000"
