@echo off
REM NSE FO Data Collector Runner - Windows Batch Script

echo.
echo ============================================================
echo NSE FO Market Data Collector
echo ============================================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo Error: Python is not installed or not in PATH
    echo Please install Python 3.7+ from https://www.python.org/
    pause
    exit /b 1
)

echo Checking and installing dependencies...
pip install -q -r requirements.txt
if errorlevel 1 (
    echo Error: Failed to install dependencies
    pause
    exit /b 1
)

echo.
echo Starting NSE FO Data Collector...
echo This may take a few minutes. Please wait...
echo.

python nse_fo_data_collector.py

if errorlevel 1 (
    echo.
    echo Error: Script execution failed
    pause
    exit /b 1
)

echo.
echo ============================================================
echo Collection completed successfully!
echo ============================================================
echo.
echo Output files:
echo  - nse_fo_aggregated_data.csv (main results)
echo  - nse_fo_cache.json (cached data)
echo  - nse_fo_collector.log (execution log)
echo.
pause
