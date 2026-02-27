# NSE FO Market Data Collector

A Python script that automatically fetches, aggregates, and caches NSE Futures & Options market data from the NSE archives.

## Features

✅ **Automatic Data Fetching**: Downloads daily FO market data from https://nsearchives.nseindia.com/archives/fo/mkt/
✅ **Smart Caching**: Saves downloaded data to avoid re-fetching existing dates
✅ **Catchup Updates**: On subsequent runs, only fetches new dates since last run
✅ **Holiday/Weekend Handling**: Automatically skips NSE trading holidays and weekends
✅ **Robust Error Handling**: Retries failed downloads with configurable timeout and retry logic
✅ **Performance Optimized**: Efficient CSV parsing and data aggregation
✅ **Comprehensive Logging**: Detailed logs for monitoring and debugging

## What the Script Does

1. **Fetches Data**: Downloads NSE FO market data from official archives starting from Feb 1, 2025
2. **Extracts Metrics**: Extracts 4 key metrics from each day's data:
   - `NO_OF_CONT`: Number of Contracts
   - `NO_OF_TRADE`: Number of Trades
   - `NOTION_VAL`: Notional Value
   - `PR_VAL`: Premium Value
3. **Aggregates**: Sums these metrics for each trading day
4. **Caches**: Stores results in `nse_fo_cache.json` for fast subsequent runs
5. **Outputs**: Writes formatted results to `nse_fo_aggregated_data.csv`

## Installation

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

Or let the runner script handle it automatically.

## Usage

### Method 1: Using the Runner Script (Recommended)
```bash
python run_nse_collector.py
```

### Method 2: Direct Execution
```bash
python nse_fo_data_collector.py
```

### Method 3: Using Batch/PowerShell Scripts
On Windows:
```bash
# PowerShell
.\run_nse_collector_windows.ps1

# Or CMD
run_nse_collector.bat
```

## Output Files

After execution, you'll get:

### 1. `nse_fo_aggregated_data.csv`
Main output file with aggregated daily metrics:
```
Date,NO_OF_CONT,NO_OF_TRADE,NOTION_VAL,PR_VAL
01-02-2025,1234.56,5678.90,12345678.90,98765.43
02-02-2025,2345.67,6789.01,23456789.01,87654.32
...
```

### 2. `nse_fo_cache.json`
Cache file storing fetched data (auto-generated):
```json
{
  "01022025": {
    "NO_OF_CONT": 1234.56,
    "NO_OF_TRADE": 5678.90,
    "NOTION_VAL": 12345678.90,
    "PR_VAL": 98765.43
  },
  ...
}
```

### 3. `nse_fo_collector.log`
Detailed execution logs for debugging and monitoring.

## Configuration

Edit `nse_fo_data_collector.py` to customize:

```python
START_DATE = datetime(2025, 2, 1)        # Start date for data collection
CURRENT_DATE = datetime.now()             # End date (default: today)
REQUEST_TIMEOUT = 15                      # Timeout for file downloads (seconds)
RETRY_ATTEMPTS = 3                        # Number of retry attempts
RETRY_DELAY = 2                          # Delay between retries (seconds)
```

### Add NSE Trading Holidays

Edit the `NSE_HOLIDAYS` set to include additional or updated holidays:
```python
NSE_HOLIDAYS = {
    "26012025",  # DD-MM-YYYY format
    "10032025",
    # Add more as needed
}
```

## How Caching Works

1. **First Run**: Fetches all available data from Feb 1, 2025 to today
   - Downloads: ~40-50 files (depending on weekends/holidays)
   - Time: 2-5 minutes (depends on network speed)

2. **Subsequent Runs**: Only fetches new dates since last run
   - If run daily: Fetches 1 file (or 0 if today is weekend/holiday)
   - Time: <30 seconds (just checks new dates)

3. **Cache File**: Stored in `nse_fo_cache.json`
   - Delete this file to force a complete re-download
   - Automatically backed up in execution logs

## Error Handling

The script handles:
- **Timeout Errors**: Retries up to 3 times with 2-second delays
- **Missing Files**: Gracefully skips unavailable dates (weekends/holidays)
- **Bad Zip Files**: Logs error and continues to next date
- **CSV Parsing Errors**: Handles missing/malformed columns
- **Network Errors**: Retries failed downloads automatically

Check `nse_fo_collector.log` for detailed error messages.

## Performance Notes

- **Initial Run**: ~1-2 minutes for 1 year of data (~250 trading days)
- **Daily Updates**: <30 seconds (just checking new dates)
- **Downloads**: Optimized with stream processing and chunk handling
- **Memory**: Efficient - doesn't load entire files into memory

## Troubleshooting

### Issue: "No CSV file found in zip"
- The NSE archive format may have changed
- Check the actual zip file contents manually
- Update the CSV detection logic if needed

### Issue: Column names not matching
- NSE may have changed column headers
- Check `nse_fo_collector.log` for column name details
- Update the column matching logic in `_parse_csv()` method

### Issue: Timeout errors
- Increase `REQUEST_TIMEOUT` value
- Improve network connection
- Run during off-peak hours

### Issue: Want to reset and re-download
```bash
# Delete cache file
rm nse_fo_cache.json

# Run script again
python run_nse_collector.py
```

## Data Format

The script supports dates in NSE format: **DDMMYYYY**
- Example: `01022025` = February 1, 2025
- Example: `25122025` = December 25, 2025

URLs are automatically constructed:
- `https://nsearchives.nseindia.com/archives/fo/mkt/fo01022025.zip`
- `https://nsearchives.nseindia.com/archives/fo/mkt/fo25122025.zip`

## Requirements

- Python 3.7+
- requests library (for HTTP downloads)
- Standard library: os, json, csv, zipfile, datetime, logging, pathlib, typing, time

## Notes

- The script automatically detects and skips weekends
- NSE trading holidays are pre-configured but can be updated
- All dates and calculations are logged for verification
- Output CSV is in DD-MM-YYYY format for easy readability
- Cache is automatically maintained and updated

## Support

If you encounter issues:
1. Check `nse_fo_collector.log` for error details
2. Verify NSE website is accessible
3. Check if the date falls on a holiday (you can check NSE holiday calendar)
4. Try deleting `nse_fo_cache.json` and running again

---

**Last Updated**: February 27, 2026
**Start Date**: February 1, 2025
