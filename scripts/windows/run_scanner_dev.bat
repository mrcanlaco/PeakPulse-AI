@echo off
setlocal enabledelayedexpansion
title DAO VANG - LOCAL DEV (Scanner Daemon)
cls

echo ================================================================
echo           DAO VANG RADAR SCANNER - LOCAL DEV (SHADOW)
echo ================================================================
echo  * Environment : LOCAL DEVELOPMENT (Shadow Mode)
echo  * Data Path   : data/
echo  * Config File : configs/dev.yaml
echo ================================================================
echo.

cd /d "%~dp0..\.."
set PYTHONPATH=src
set DAO_VANG_PATHS__DATA_DIR=data
set DAO_VANG_PATHS__RAW_DIR=data/raw
set DAO_VANG_PATHS__NORMALIZED_DIR=data/normalized
set DAO_VANG_SCANNER__DB_PATH=data/dev.duckdb
set DAO_VANG_SCANNER__OPERATING_MODE=shadow

if exist .venv_dev\Scripts\python.exe (
    set "PYTHON_EXE=.venv_dev\Scripts\python.exe"
) else if exist .venv\Scripts\python.exe (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo [INFO] Su dung Python: %PYTHON_EXE%
echo [INFO] Dang khoi chay Scanner voi file cau hinh configs/dev.yaml ...
echo [INFO] Nhan Ctrl+C de dung.
echo.

%PYTHON_EXE% -m dao_vang scanner start --config configs/dev.yaml
pause
