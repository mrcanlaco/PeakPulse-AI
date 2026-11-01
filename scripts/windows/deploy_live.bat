@echo off
setlocal
cd /d "%~dp0..\.."
echo Trien khai commit da luu len Google Cloud.
echo Script se dung neu server co thay doi chua commit.
if exist .venv\Scripts\python.exe (
  .venv\Scripts\python.exe scripts/deploy_google_server.py --apply
) else (
  python scripts/deploy_google_server.py --apply
)
if errorlevel 1 echo Trien khai that bai. Kiem tra thong bao o tren.
pause
