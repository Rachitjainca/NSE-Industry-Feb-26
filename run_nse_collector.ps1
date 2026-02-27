# NSE FO Data Collector Runner - Windows PowerShell Script

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "NSE FO Market Data Collector" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# Check if Python is installed
try {
    $pythonVersion = python --version 2>&1
    Write-Host "✓ Python found: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "✗ Python is not installed or not in PATH" -ForegroundColor Red
    Write-Host "Please install Python 3.7+ from https://www.python.org/" -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}

# Check and install dependencies
Write-Host ""
Write-Host "Checking and installing dependencies..." -ForegroundColor Yellow
$deps = pip install -q -r requirements.txt 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "✗ Failed to install dependencies" -ForegroundColor Red
    Write-Host $deps
    Read-Host "Press Enter to exit"
    exit 1
}
Write-Host "✓ Dependencies ready" -ForegroundColor Green

# Run the collector
Write-Host ""
Write-Host "Starting NSE FO Data Collector..." -ForegroundColor Cyan
Write-Host "This may take a few minutes. Please wait..." -ForegroundColor Yellow
Write-Host ""

python nse_fo_data_collector.py
$exitCode = $LASTEXITCODE

Write-Host ""
if ($exitCode -eq 0) {
    Write-Host "============================================================" -ForegroundColor Green
    Write-Host "Collection completed successfully!" -ForegroundColor Green
    Write-Host "============================================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "Output files:" -ForegroundColor Green
    Write-Host "  ✓ nse_fo_aggregated_data.csv (main results)" -ForegroundColor Green
    Write-Host "  ✓ nse_fo_cache.json (cached data)" -ForegroundColor Green
    Write-Host "  ✓ nse_fo_collector.log (execution log)" -ForegroundColor Green
} else {
    Write-Host "============================================================" -ForegroundColor Red
    Write-Host "Error: Script execution failed" -ForegroundColor Red
    Write-Host "============================================================" -ForegroundColor Red
    Write-Host "Check nse_fo_collector.log for details" -ForegroundColor Yellow
}

Write-Host ""
Read-Host "Press Enter to exit"
exit $exitCode
