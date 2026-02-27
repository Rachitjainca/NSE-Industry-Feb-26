# NSE FO Data Aggregator - PowerShell Runner
# Ensures dependencies are installed and runs the aggregator script

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "NSE Futures & Options Data Aggregator" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# Check if Python is installed
try {
    $pythonVersion = python --version 2>&1
    Write-Host "✓ Python found: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "✗ ERROR: Python is not installed or not in PATH" -ForegroundColor Red
    Write-Host "  Please install Python 3.8+ from https://www.python.org" -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host ""

# Check and install requirements
Write-Host "Checking dependencies..." -ForegroundColor Yellow
$requirementsInstalled = pip show requests 2>&1 | Select-String "Name"

if (-not $requirementsInstalled) {
    Write-Host "Installing required packages..." -ForegroundColor Yellow
    pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) {
        Write-Host "✗ ERROR: Failed to install dependencies" -ForegroundColor Red
        Read-Host "Press Enter to exit"
        exit 1
    }
}

Write-Host "✓ All dependencies installed" -ForegroundColor Green
Write-Host ""

# Run the aggregator
Write-Host "Starting NSE FO Data Aggregator..." -ForegroundColor Yellow
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

& python nse_fo_aggregator.py

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Aggregator completed. Check nse_fo_aggregated.csv for results." -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Cyan

Read-Host "Press Enter to exit"
