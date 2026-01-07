@echo off
echo Stopping existing backend processes...
taskkill /F /FI "WINDOWTITLE eq python*" 2>nul
taskkill /F /IM python.exe /FI "WINDOWTITLE eq *backend*" 2>nul

timeout /t 2 /nobreak >nul

echo Starting backend...
cd /d "%~dp0"
call venv\Scripts\activate.bat
python run.py
pause
