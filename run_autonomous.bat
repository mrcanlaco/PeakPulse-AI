@echo off
setlocal enabledelayedexpansion
title DAO VANG - RUN AUTONOMOUS ENGINE (Scanner + Trading + Web)
cls

echo ================================================================
echo      DAO VANG (PEAKPULSE AI) - 1-CLICK AUTONOMOUS LAUNCHER
echo ================================================================
echo  * Che do        : TU DONG HOAN TOAN (Autonomous Trading & Scanning)
echo  * Cau hinh      : configs/trading_auto.yaml
echo  * Web Dashboard : http://localhost:8000
echo  * Quan tri rui ro: Stop Loss 5 USDT, Trailing TP 1.5 ATR, Time Exit 72h
echo ================================================================
echo.

cd /d "%~dp0"
set PYTHONPATH=src

if exist .venv\Scripts\python.exe (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else if exist .venv_dev\Scripts\python.exe (
    set "PYTHON_EXE=.venv_dev\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo [INFO] Dang su dung Python: %PYTHON_EXE%
echo [INFO] Khoi chay Autonomous Orchestrator...
echo.

%PYTHON_EXE% scripts/run_autonomous.py %*

echo.
echo [INFO] He thong da dung lai.
pause
