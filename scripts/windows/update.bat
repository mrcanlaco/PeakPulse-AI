@echo off
setlocal enabledelayedexpansion
title DAO VANG - LOCAL SYSTEM UPDATER
cls

echo ================================================================
echo           DAO VANG - ONE CLICK LOCAL SYSTEM UPDATER
echo ================================================================
echo  Kiem tra va dong bo ma nguon moi nhat tu GitHub ve may Local...
echo ================================================================
echo.

cd /d "%~dp0..\.."

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "scripts\update.ps1"

echo.
echo ================================================================
echo [INFO] Hoan tat. Nhan phim bat ky de dong cua so nay.
echo ================================================================
pause >nul
