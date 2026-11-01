@echo off
setlocal enabledelayedexpansion
title DAO VANG - LOCAL DEV (Auto-Reload Web Server)
cls

echo ================================================================
echo      DAO VANG SIGNAL COMMAND CENTER - AUTO-RELOAD DEV SERVER
echo ================================================================
echo  * Environment : LOCAL DEVELOPMENT (Auto-Reload Mode)
echo  * Web API Port: 8000 (http://localhost:8000)
echo  * Auto-Reload : BAT (Sua code Python xong la tu dong reload)
echo  * Data Path   : data/
echo  * Config File : configs/dev.yaml
echo ================================================================
echo.

cd /d "%~dp0..\.."
set PYTHONPATH=src
set DAO_VANG_WEB__PORT=8000
set DAO_VANG_PATHS__DATA_DIR=data
set DAO_VANG_PATHS__RAW_DIR=data/raw
set DAO_VANG_PATHS__NORMALIZED_DIR=data/normalized
set DAO_VANG_SCANNER__DB_PATH=data/dev.duckdb

if exist .venv_dev\Scripts\python.exe (
    set "PYTHON_EXE=.venv_dev\Scripts\python.exe"
) else if exist .venv\Scripts\python.exe (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo [INFO] Su dung Python: %PYTHON_EXE%
echo [INFO] Dang khoi dong Auto-Reload Server tai http://localhost:8000 ...
echo [INFO] Nhan Ctrl+C de dung.
echo.

%PYTHON_EXE% -m dao_vang.web.dev_server 8000
pause
