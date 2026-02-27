@echo off
REM NSE FO Data Aggregator - Windows Batch Runner
REM Ensures dependencies are installed and runs the aggregator script

setlocal enabledelayedexpansion

cls
echo ============================================================
echo NSE Futures ^& Options Data Aggregator
echo ============================================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.8+ from https://www.python.org
    pause
    exit /b 1
)

echo ✓ Python found
echo.

REM Check and install requirements
echo Checking dependencies...
pip show requests >nul 2>&1
if %errorlevel% neq 0 (
    echo Installing required packages...
    pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo ERROR: Failed to install dependencies
        pause
        exit /b 1
    )
)

echo ✓ All dependencies installed
echo.

REM Run the aggregator
echo Starting NSE FO Data Aggregator...
echo ============================================================
echo.

python nse_fo_aggregator.py

echo.
echo ============================================================
echo Aggregator completed. Check nse_fo_aggregated.csv for results.
echo ============================================================
pause
