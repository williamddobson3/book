# PowerShell script to start backend with proper setup
Write-Host "Starting Backend Server..." -ForegroundColor Green
Write-Host ""

# Check if venv exists
if (-not (Test-Path "venv")) {
    Write-Host "[ERROR] Virtual environment not found!" -ForegroundColor Red
    Write-Host "Please run: python -m venv venv" -ForegroundColor Yellow
    exit 1
}

# Activate virtual environment
Write-Host "Activating virtual environment..." -ForegroundColor Cyan
& ".\venv\Scripts\Activate.ps1"

if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Failed to activate virtual environment!" -ForegroundColor Red
    Write-Host "You may need to run: Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser" -ForegroundColor Yellow
    exit 1
}

Write-Host "[OK] Virtual environment activated" -ForegroundColor Green
Write-Host ""

# Check dependencies
Write-Host "Checking dependencies..." -ForegroundColor Cyan
python check_setup.py

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "[ERROR] Setup check failed!" -ForegroundColor Red
    Write-Host "Installing dependencies..." -ForegroundColor Yellow
    pip install -r requirements.txt
    playwright install chromium
}

Write-Host ""
Write-Host "Starting backend server on http://0.0.0.0:8001" -ForegroundColor Green
Write-Host "Press Ctrl+C to stop" -ForegroundColor Yellow
Write-Host ""

# Start the backend
python run.py
