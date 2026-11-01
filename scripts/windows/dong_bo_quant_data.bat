@echo off
title Dong Bo Du Lieu Quant Data
echo =========================================================
echo    DANG DONG BO DU LIEU TU DAO VANG SANG QUANT DATA
echo =========================================================
cd /d "%~dp0..\.."
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\sync_quant_data.ps1"
echo =========================================================
pause