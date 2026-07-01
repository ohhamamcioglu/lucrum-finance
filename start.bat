@echo off
title LUCRUM Platform Starter
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File .\start.ps1
exit
