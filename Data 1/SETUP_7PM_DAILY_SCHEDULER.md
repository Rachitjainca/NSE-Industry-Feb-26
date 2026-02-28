# 🕖 Setting Up Daily 7 PM Automated Data Collection

This guide explains how to:
1. Populate historical data (one-time backfill)
2. Set up daily 7 PM automated collection in Windows Task Scheduler

---

## 📋 Step 1: Populate Historical Data (ONE-TIME ONLY)

Historical backfill collects all data from Jan 2025 to Feb 2026 to populate your output_data.csv.

### Command

```powershell
cd "C:\Users\rachit.jain\Desktop\NSE BSE Latest\Data 1"
python api_collector_template.py --mode historical
```

### Expected Output

```
================================================================================
DATA COLLECTION STARTED [MODE: HISTORICAL]
================================================================================

[STEP 1] Collecting data from APIs...
⏱ HISTORICAL MODE: Collecting all months from 2025-2026 (this may take a few minutes)...
📚 Backfilling data from 2025 to 2026...
  📆 Fetching CM/2025...
  📆 Fetching FO/2025...
  📆 Fetching COMDER/2025...
  📆 Fetching CM/2026...
  📆 Fetching FO/2026...
  📆 Fetching COMDER/2026...

[BACKFILL COMPLETE] CM: 267 total records collected
[BACKFILL COMPLETE] FO: 277 total records collected
[BACKFILL COMPLETE] COMDER: 276 total records collected

[STEP 2] Consolidating data...
✓ Row count: 820
✓ No duplicates
[STEP 3] Exporting to CSV...
✓ Exported 820 rows to output_data.csv
[STEP 4] Uploading to Google Sheets...
✓ Uploaded 820 rows to Google Sheet
```

### Estimated Time
- **First Run:** 5-10 minutes (rate limited to 300ms between requests)
- **Output:** `output_data.csv` with all historical data
- **Google Sheets:** Automatically synced to your configured sheet

### Verification
After backfill completes, verify:
```powershell
# Check file size (should be >100KB)
Get-Item output_data.csv | Select-Object Length

# Check row count
(Import-Csv output_data.csv).Count
```

---

## 🕖 Step 2: Configure Windows Task Scheduler (Daily 7 PM)

This sets up automatic daily execution at 19:00 (7:00 PM IST).

### Method A: Using Task Scheduler GUI (Easiest)

1. **Open Task Scheduler:**
   - Press `Win + R`
   - Type: `taskschd.msc`
   - Press Enter

2. **Create Basic Task:**
   - Right-click "Task Scheduler Library" → "Create Basic Task..."
   - Name: `NSE Market Data Collection`
   - Description: `Daily data collection at 7 PM`
   - Click "Next >"

3. **Set Trigger:**
   - Select: "Daily"
   - Start: Today at 19:00 (7:00 PM)
   - Repeat: Every 1 day
   - Click "Next >"

4. **Set Action:**
   - Select: "Start a program"
   - Program: `cmd.exe`
   - Arguments: `/c "C:\Users\rachit.jain\Desktop\NSE BSE Latest\Data 1\run_daily_collection_template.bat"`
   - Click "Next >"

5. **Finish:**
   - ✓ Check "Open the Properties dialog for this task when I click Finish"
   - Click "Finish"

6. **Additional Settings (Important):**
   - Go to "General" tab
   - ✓ Check "Run with highest privileges"
   - ✓ Check "Run whether user is logged in or not"
   - Click "OK"

### Method B: Using PowerShell (Advanced)

```powershell
# Run as Administrator
$taskName = "NSE Market Data Collection"
$scriptPath = "C:\Users\rachit.jain\Desktop\NSE BSE Latest\Data 1\run_daily_collection_template.bat"

# Create trigger (Daily at 7 PM)
$trigger = New-ScheduledTaskTrigger -Daily -At 19:00

# Create action (Run script)
$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$scriptPath`""

# Create principal (Run with highest privileges)
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

# Register task
Register-ScheduledTask -TaskName $taskName -Trigger $trigger -Action $action -Principal $principal -Force
```

---

## ✅ Step 3: Verify Setup

### Check Task Status

1. Open Task Scheduler
2. Navigate to: Task Scheduler Library
3. Look for "NSE Market Data Collection"
4. Verify:
   - Status: `Ready`
   - Trigger: `Daily at 19:00`
   - Last Run: Shows recent run timestamp
   - Last Run Result: `The task completed with an exit code (0)`

### Test Run

To test immediately without waiting until 7 PM:

```powershell
# Right-click task in Task Scheduler → "Run"
# Or use PowerShell:
Start-ScheduledTask -TaskName "NSE Market Data Collection"
```

### Monitor Logs

Execution logs are saved in: `logs/daily_collection_YYYY-MM-DD_HH_00.log`

```powershell
# View latest log
Get-ChildItem logs/daily_collection_*.log | Sort-Object LastWriteTime -Descending | Select-Object -First 1 | Get-Content

# Or with timestamps
Get-Content logs/daily_collection_*.log -Tail 50
```

---

## 📊 Daily Execution Flow

Every day at 7:00 PM:

1. **[19:00] Task Scheduler triggers** `run_daily_collection_template.bat`
2. **[19:00:05] STEP 1** - Data Collection
   - Fetches today's data from NSE APIs
   - Updates `output_data.csv`
   - Takes ~5-7 seconds
3. **[19:00:12] STEP 2** - Google Sheets Sync
   - Uploads new data to configured Google Sheet
   - Takes ~2-3 seconds
4. **[19:00:15] Execution Complete**
   - Logs saved to: `logs/daily_collection_2026-02-28_19_00.log`
   - Email alert: (Optional - can be added in Task Scheduler properties)

---

## 🔧 Configuration Reference

### api_collector_template.py Modes

```bash
# Daily mode (7 PM task runs this)
python api_collector_template.py               # Defaults to daily
python api_collector_template.py --mode daily  # Explicit

# Historical mode (one-time backfill)
python api_collector_template.py --mode historical
```

### Batch File Location

```
C:\Users\rachit.jain\Desktop\NSE BSE Latest\Data 1\run_daily_collection_template.bat
```

### Output Files

| File | Location | Purpose |
|------|----------|---------|
| CSV Data | `output_data.csv` | Main data export |
| Log Files | `logs/daily_collection_*.log` | Execution history |
| Cache | `.cache/` | API response cache (24h) |
| Backups | `backups/` | CSV backups with timestamps |

---

## 🐛 Troubleshooting

### Task Not Running at 7 PM

1. Verify Task Scheduler is enabled:
   ```powershell
   Get-ScheduledTask -TaskName "NSE Market Data Collection" | Select-Object State
   ```
   Should show: `Ready`

2. Check if trigger is set correctly:
   ```powershell
   Get-ScheduledTask -TaskName "NSE Market Data Collection" | Get-ScheduledTaskInfo
   ```

3. Verify script path is correct in task properties

4. Run manually to test:
   ```powershell
   Start-ScheduledTask -TaskName "NSE Market Data Collection"
   ```

### Script Execution Fails

Check the log file:
```powershell
Get-Content logs/daily_collection_*.log -Tail 20
```

Common issues:
- **"ModuleNotFoundError"** → Install missing packages: `pip install -r requirements.txt`
- **"Connection timeout"** → API might be down, check NSE website
- **"Google Sheets error"** → Verify credentials file exists: `nse-industry-data-88d157be9048.json`

### Python Not Found Error

Task Scheduler needs full path to Python:

1. Find Python location:
   ```powershell
   where python
   # Example: C:\Users\rachit.jain\AppData\Local\Programs\Python\Python311\python.exe
   ```

2. Update batch file to use full path:
   ```batch
   "C:\Users\rachit.jain\AppData\Local\Programs\Python\Python311\python.exe" api_collector_template.py --mode daily
   ```

---

## 📈 Monitoring Checklist

Daily checklist (verify each morning):

- [ ] Check last execution in Task Scheduler (should be ~7 PM previous day)
- [ ] Verify `output_data.csv` was updated (timestamp check)
- [ ] Check Google Sheet for latest data
- [ ] Review execution log for errors
- [ ] Verify row count increased (one day's worth of data added)

---

## 🎯 Next Steps

1. **Run backfill NOW**
   ```powershell
   cd "C:\Users\rachit.jain\Desktop\NSE BSE Latest\Data 1"
   python api_collector_template.py --mode historical
   ```

2. **Set up Task Scheduler** (after backfill completes)
   - Open `taskschd.msc`
   - Create basic task for daily 7 PM execution

3. **Test execution** (same day)
   - Right-click task → "Run"
   - Check logs immediately

4. **Verify next morning**
   - Check if data was collected at 7 PM
   - Review execution logs and Google Sheet

---

## 📞 Support

**Regular Issues:**
- Check execution logs: `logs/daily_collection_*.log`
- Verify API endpoints: See COLUMNS_AND_APIS.md
- Test API manually: `python api_collector_template.py --mode daily`

**API Down:**
- Check NSE website: https://www.nseindia.com
- Logs will show "Connection timeout" or HTTP error codes
- Task will automatically retry next day at 7 PM

**Need Help:**
- Review BEST_PRACTICES_SCHEMA.md for debugging steps
- Check NEW_API_INTEGRATION_WORKFLOW.md for common patterns

---

**Last Updated:** Feb 28, 2026  
**Status:** ✅ Ready for Production
