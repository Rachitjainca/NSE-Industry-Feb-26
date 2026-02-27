# NSE Futures & Options Data Aggregator

A Python script that automatically fetches, caches, and aggregates daily NSE FO market data starting from February 1, 2025.

## Features

- **Automatic Data Fetching**: Downloads daily NSE FO market data from official NSE archives
- **Smart Caching**: Caches downloaded files and only fetches new data on subsequent runs (catch-up updates)
- **Holiday Handling**: Automatically skips weekends and NSE trading holidays
- **Error Resilience**: Implements retry logic with configurable timeouts for network issues
- **Data Aggregation**: Sums key metrics (NO_OF_CONT, NO_OF_TRADE, NOTION_VAL, PR_VAL) per trading day
- **Append-Only Output**: Maintains a CSV file with historical aggregated data

## Installation

1. Ensure Python 3.8+ is installed
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

Run the script:
```bash
python nse_fo_aggregator.py
```

### First Run
- Fetches data from Feb 1, 2025 to current date
- Creates output file `nse_fo_aggregated.csv`
- Creates metadata file `nse_fo_metadata.json` for tracking

### Subsequent Runs
- Only processes new dates since last run
- Appends new data to `nse_fo_aggregated.csv`
- Fast execution (only downloads missing data)

## Output

### Main Output: `nse_fo_aggregated.csv`
CSV file with columns:
- **Date**: Trading date (DD-MMM-YYYY format)
- **NO_OF_CONT**: Sum of number of contracts
- **NO_OF_TRADE**: Sum of number of trades
- **NOTION_VAL**: Sum of notional value
- **PR_VAL**: Sum of premium value

Example:
```
Date,NO_OF_CONT,NO_OF_TRADE,NOTION_VAL,PR_VAL
01-Feb-2025,1234567,2345678,987654321,123456789
04-Feb-2025,1345678,2456789,1098765432,234567890
...
```

### Metadata: `nse_fo_metadata.json`
Tracks:
- List of processed dates
- Last run timestamp
- Used for incremental updates

### Cache Directory: `nse_cache/`
Stores downloaded ZIP files for potential offline processing

## Configuration

Edit the constants in the script to customize:

```python
START_DATE = datetime(2025, 2, 1)      # Start date for data collection
TIMEOUT_SECONDS = 30                    # Download timeout (seconds)
TIMEOUT_RETRIES = 3                    # Retry attempts on timeout
NSE_HOLIDAYS = {...}                   # Add/modify NSE holidays
```

## Error Handling

- **404 Errors**: Files not found are silently skipped (likely weekends/holidays)
- **Timeout Errors**: Script retries 3 times before moving to next date
- **Parsing Errors**: Logged as warnings, process continues with next file
- **Network Issues**: Retry logic with exponential backoff

## Logging

Console output shows:
- ✓ Successfully processed dates
- ✗ Failed dates
- ⚠ Warnings and errors
- ⊘ Skipped days (weekends/holidays)

## Date Format

- **Internal**: DDMMYYYY (stored in metadata)
- **Output CSV**: DD-MMM-YYYY (e.g., 01-Feb-2025)
- **URL**: DDMMYYYY (e.g., http://.../fo01022025.zip)

## Performance Notes

- First run: ~5-10 minutes (depending on data availability and network)
- Subsequent runs: <1 second (only new dates)
- Downloads are optimized with timeout handling
- No repeated downloads due to caching

## Troubleshooting

### "File not found" for a specific date
- Check if it's a weekend or NSE holiday
- Add date to `NSE_HOLIDAYS` if needed
- Verify date format in URL

### Timeout errors
- Increase `TIMEOUT_SECONDS` in script
- Check internet connection
- Verify NSE site is accessible

### Missing columns in CSV
- NSE may have changed CSV format
- Update `REQUIRED_COLUMNS` constant
- Check actual column names in downloaded CSV

## NSE Holidays (2025-2026)

Predefined holidays include major Indian national holidays and market closures. Update `NSE_HOLIDAYS` set if holidays change.

## Contact & Support

For issues with NSE data format changes or missing holidays, update the `NSE_HOLIDAYS` set in the script.
