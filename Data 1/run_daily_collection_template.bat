@echo off
REM ═══════════════════════════════════════════════════════════════════════════════
REM WINDOWS TASK SCHEDULER - DATA COLLECTION EXECUTION
REM ═══════════════════════════════════════════════════════════════════════════════
REM
REM Purpose: Daily automated data collection (7:00 PM IST / 1:30 PM UTC)
REM Schedule: Daily at 19:00 (7:00 PM)
REM Execution Mode: DAILY (use --mode historical for backfill)
REM
REM SETUP INSTRUCTIONS FOR WINDOWS TASK SCHEDULER:
REM ──────────────────────────────────────────────────────────────
REM 1. Save this file in your project directory
REM 2. Open Windows Task Scheduler (taskschd.msc)
REM 3. Click "Create Basic Task..." on right panel
REM 4. Configure:
REM    - Name: "NSE/BSE Market Data Collection"
REM    - Description: "Daily data collection from NSE APIs at 7 PM"
REM    - Trigger: Daily at 19:00 (7:00 PM)
REM    - Repeat: Every day
REM    - Action: Start program
REM      * Program: cmd.exe
REM      * Arguments: /c "%~dp0run_daily_collection_template.bat"
REM    - Check: "Run with highest privileges"
REM    - Check: "Run whether user is logged in or not"
REM
REM HISTORICAL BACKFILL (RUN ONCE):
REM ──────────────────────────────────────────────────────────────
REM To populate all historical data (all months 2025-2026):
REM   1. Open Command Prompt as Administrator
REM   2. Navigate to project directory: cd C:\Users\rachit.jain\Desktop\NSE BSE Latest\Data 1
REM   3. Run: python api_collector_template.py --mode historical
REM   4. Wait for completion (may take 5-10 minutes)
REM   5. Data will be saved to output_data.csv
REM   6. Then set up Task Scheduler for daily 7 PM runs (daily mode)
REM
REM ═══════════════════════════════════════════════════════════════════════════════

REM Set working directory to script location
cd /d "%~dp0"

REM Create logs directory if it doesn't exist
if not exist logs mkdir logs

REM Log file with timestamp
set LOGFILE=logs\daily_collection_%date:~-4%-%date:~-10,2%-%date:~-7,2%_%time:~0,2%_00.log

REM Add timestamp header
echo. >> %LOGFILE%
echo ═══════════════════════════════════════════════════════════════════════════════ >> %LOGFILE%
echo Daily Collection Run - %date% %time% >> %LOGFILE%
echo Mode: DAILY (current day only) >> %LOGFILE%
echo ═══════════════════════════════════════════════════════════════════════════════ >> %LOGFILE%

REM Step 1: Run data collection in DAILY mode
echo [%time%] [STEP 1] Running data collection (DAILY mode)... >> %LOGFILE%
python api_collector_template.py --mode daily >> %LOGFILE% 2>&1

if %ERRORLEVEL% NEQ 0 (
    echo [%time%] [ERROR] Data collection failed with exit code %ERRORLEVEL% >> %LOGFILE%
    echo Status: FAILED >> %LOGFILE%
    exit /b 1
)

echo [%time%] [SUCCESS] Data collection completed >> %LOGFILE%

REM Step 2: Run Google Sheets upload (if script exists)
if exist gsheet_upload.py (
    echo [%time%] [STEP 2] Uploading to Google Sheets... >> %LOGFILE%
    python gsheet_upload.py >> %LOGFILE% 2>&1
    
    if %ERRORLEVEL% EQU 0 (
        echo [%time%] [SUCCESS] Google Sheets upload completed >> %LOGFILE%
    ) else (
        echo [%time%] [WARNING] Google Sheets upload skipped or failed >> %LOGFILE%
    )
) else (
    echo [%time%] [NOTE] gsheet_upload.py not found, skipping Google Sheets sync >> %LOGFILE%
)

REM Final status
echo. >> %LOGFILE%
echo ═══════════════════════════════════════════════════════════════════════════════ >> %LOGFILE%
echo Execution completed successfully at %date% %time% >> %LOGFILE%
echo Status: SUCCESS >> %LOGFILE%
echo ═══════════════════════════════════════════════════════════════════════════════ >> %LOGFILE%
echo. >> %LOGFILE%

REM Display log location
echo.
echo Execution log saved to: %CD%\%LOGFILE%
echo.

exit /b 0
REM python post_processing.py >> %LOGFILE% 2>&1
REM if %ERRORLEVEL% NEQ 0 (
REM     echo [WARNING] Post-processing failed >> %LOGFILE%
REM )

:end
echo. >> %LOGFILE%
echo Execution completed at %date% %time% >> %LOGFILE%
echo ═══════════════════════════════════════════════════════════════════════════════ >> %LOGFILE%
echo. >> %LOGFILE%

REM Exit with success
exit /b 0
