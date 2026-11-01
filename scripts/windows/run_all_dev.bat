@echo off
setlocal enabledelayedexpansion
title DAO VANG - RUN ALL LOCAL DEV (Web + Scanner)
cls

echo ================================================================
echo           DAO VANG - ONE CLICK LOCAL DEV LAUNCHER
echo ================================================================
echo  Dang mo 2 cua so Local Development doc lap:
echo    [1] Web UI Server  -^> http://localhost:8000
echo    [2] Scanner Daemon -^> Quet thi truong Shadow Mode
echo ================================================================
echo.

cd /d "%~dp0..\.."

start "DAO VANG - WEB UI [DEV]" cmd /c "%~dp0run_dev.bat"
timeout /t 2 /nobreak >nul
start "DAO VANG - SCANNER [DEV]" cmd /c "%~dp0run_scanner_dev.bat"

echo [OK] Ca 2 tien trinh da duoc khoi chay trong 2 cua so rieng biet.
echo Ban co the dong cua so nay.
timeout /t 3
exit
