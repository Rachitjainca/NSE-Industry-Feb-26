@echo off
REM ============================================================================
REM Windows Task Scheduler Runner - NSE + BSE Market Data Collector
REM ============================================================================
REM This batch file can be scheduled via Windows Task Scheduler to run at 7PM
REM 
REM Setup Instructions:
REM 1. Open Task Scheduler (taskschd.msc)
REM 2. Create Basic Task
REM 3. Name: "NSE BSE Daily Market Data Collection 7PM"
REM 4. Trigger: Daily at 19:00 (7:00 PM)
REM 5. Action: Start a program
REM 6. Program: cmd.exe
REM 7. Arguments: /c "run_daily_7pm.bat"
REM 8. Start in: <NSE BSE Latest folder path>
REM ============================================================================

setlocal enabledelayedexpansion

REM Get current directory
set SCRIPT_DIR=%~dp0

REM Timestamp for logging
for /f "tokens=2-4 delims=/ " %%a in ('date /t') do (set mydate=%%c-%%a-%%b)
for /f "tokens=1-2 delims=/:" %%a in ('time /t') do (set mytime=%%a:%%b)

echo.
echo ============================================================================
echo %mydate% %mytime% - Starting Market Data Collection Task
echo ============================================================================
echo.

REM Change to script directory
cd /d "%SCRIPT_DIR%"

REM Run the full Python collector from Data 1 folder
python Data 1\collector.py

REM Check exit code
if errorlevel 1 (
    echo.
    echo ERROR: Market data collection failed!
    echo.
    exit /b 1
)

echo.
echo ============================================================================
echo Uploading data to Google Sheets...
echo ============================================================================
echo.

REM Run Google Sheets upload
python Data 1\gsheet_upload.py

REM Check exit code
if errorlevel 1 (
    echo.
    echo ERROR: Google Sheets upload failed!
    echo.
    exit /b 1
) else (
    echo.
    echo SUCCESS: Market data collection and Google Sheets upload completed successfully
    echo.
    exit /b 0
)
