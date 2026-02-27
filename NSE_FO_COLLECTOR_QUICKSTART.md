# NSE FO Data Collector - Quick Start Guide

## What This Does

Automatically downloads NSE Futures & Options market data, extracts daily totals for 4 key metrics, and updates a CSV file. Subsequent runs only fetch new data (smart caching).

## 3 Ways to Run It

### Option 1: Click & Run (Easiest) ⭐
**Windows Users:**
1. Double-click `run_nse_collector.bat` 
2. Wait for completion
3. Find results in `nse_fo_aggregated_data.csv`

### Option 2: PowerShell
```powershell
.\run_nse_collector.ps1
```

### Option 3: Python Command
```bash
python run_nse_collector.py
```

## What You Get

| File | Contents |
|------|----------|
| `nse_fo_aggregated_data.csv` | **Results** - Daily sums of 4 metrics (Date, NO_OF_CONT, NO_OF_TRADE, NOTION_VAL, PR_VAL) |
| `nse_fo_cache.json` | Cache file - Prevents re-downloading known dates |
| `nse_fo_collector.log` | Logs - Shows what was downloaded and any errors |

## Output Format

```
Date,NO_OF_CONT,NO_OF_TRADE,NOTION_VAL,PR_VAL
01-02-2025,1234567.89,5678901.23,12345678901.23,98765432.10
02-02-2025,2345678.90,6789012.34,23456789012.34,87654321.09
...
```

## Data Collection Timeline

- **Start Date**: February 1, 2025
- **End Date**: Today (February 27, 2026)
- **Dataset**: ~250 trading days (weekends & NSE holidays skipped)
- **Time**: First run ~2-3 minutes, subsequent runs <30 seconds

## First Run Details

On first run:
- Downloads ~250 files (1 per trading day)
- Extracts metric sums from each
- Caches results locally
- Creates output CSV

## Subsequent Runs

Just run the script again:
- Checks cache (finds previously fetched dates)
- Only downloads NEW dates since last run
- Appends new rows to output CSV
- Updates cache file

## Troubleshooting

### "Python not found"
Install Python from https://www.python.org/ (version 3.7+)

### "Connection timeout"
- Try running again (has automatic retry)
- Check internet connection
- Edit script to increase `REQUEST_TIMEOUT` value

### Want to restart from scratch
```bash
# Delete these files:
# - nse_fo_cache.json
# - nse_fo_aggregated_data.csv

# Then run the script again to re-download everything
```

## For Advanced Users

Edit `nse_fo_data_collector.py` to:
- Change start date: `START_DATE = datetime(2025, 2, 1)`
- Add holidays: Update `NSE_HOLIDAYS` set
- Adjust timeouts: `REQUEST_TIMEOUT = 15`
- Change retry attempts: `RETRY_ATTEMPTS = 3`

See `NSE_FO_COLLECTOR_README.md` for full documentation.

---

**Status**: Ready to use
**Date Created**: February 27, 2026
**Start Date**: February 1, 2025
