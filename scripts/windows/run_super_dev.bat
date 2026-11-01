@echo off
setlocal enabledelayedexpansion
title DAO VANG - SUPER DEV (Hot-Reload Frontend + Auto-Reload Backend)
cls

echo ================================================================
echo           DAO VANG - ONE-CLICK SUPER HOT-RELOAD DEV
echo ================================================================
echo  * Frontend Dev  : http://localhost:8088 (Vite Hot-Reload TUC THI)
echo  * Backend API   : http://localhost:8000 (Python Auto-Reload)
echo  * Dac diem      : Sua code React/CSS -^> An ngay lap tuc
echo                    Sua code Python    -^> Backend tu dong restart
echo ================================================================
echo.

cd /d "%~dp0..\.."

echo [1/3] Dang khoi chay Backend Auto-Reload Server (Port 8000)...
start "DAO VANG - BACKEND [AUTO-RELOAD]" cmd /c "%~dp0run_dev.bat"

echo [2/3] Dang khoi chay Frontend Vite Dev Server (Port 8088)...
start "DAO VANG - FRONTEND [HOT-RELOAD]" cmd /k "cd /d frontend && npm run dev"

timeout /t 3 /nobreak >nul

echo [3/3] Dang mo trinh duyet tai http://localhost:8088 ...
start http://localhost:8088

echo.
echo ================================================================
echo  [OK] He thong phat trien Hot-Reload da san sang!
echo  Ban co the sua code va thay doi se cap nhat ngay lap tuc.
echo ================================================================
timeout /t 5
exit
