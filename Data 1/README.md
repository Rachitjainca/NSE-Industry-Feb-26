# NSE + BSE FO Market Data Collector

Automated daily pipeline (7 PM) that collects comprehensive Futures & Options and market data from 10 NSE/BSE sources:

## Data Sources (10 Total)

1. **NSE FO Daily** - Contracts, trades, notional value
2. **BSE Derivatives** - IO+IF segments turnover
3. **NSE FO Category** - Retail participation participation
4. **NSE Equity Category** - Equity market retail data
5. **NSE Margin Trading** - Margin outstanding/expiry
6. **NSE Participants** - CLT (Clearing Member) volume
7. **NSE MFSS** - Mutual fund subscription/redemption orders
8. **Market Turnover Orders** - Equities/FO/Commodity/MF metrics
9. **TBG Daily Data** - CM/FO/Commodity trading & borrowing
10. **Registered Investors** - NSE & BSE investor count

## Output

**`nse_fo_aggregated_data.csv`** — 61 columns, 257+ trading days (Feb 2025 onwards)

**Column Breakdown:**
- Date (1)
- NSE FO (4) + BSE (4) + Categories (6) + Margin (4) + Participants (3)
- Registered Investors (2)
- MFSS (5)
- **Market Turnover Orders (5):** — [NEW]
  - NSE_EQUITY_TOTAL_NO_OF_ORDERS
  - NSE_FO_TOTAL_NO_OF_ORDERS
  - NSE_COMMODITY_TOTAL_NO_OF_ORDERS
  - NSE_MF_NO_OF_ORDERS
  - NSE_MF_NOTIONAL_TURNOVER
- **TBG Daily Data (28):** — [NEW - CM/FO/Commodity metrics]
  - CM: 4 cols | FO: 16 cols | Commodity: 7 cols

## Project Structure

```
collector.py              # Main data collector (all 10 sources)
scheduler_7pm.py          # Daily scheduler (7 PM trigger)
run_daily_7pm.bat         # Windows Task Scheduler batch file
gsheet_upload.py          # Google Sheets uploader
test_workflow.py          # Validates complete workflow
requirements.txt          # All dependencies

(Generated at runtime, gitignored:)
├── *_cache.json           # Source data caches
├── nse_fo_aggregated_data.csv  # Output CSV
└── reg_investors_cache/   # Investor caches
```

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run collector once
python collector.py

# 3. (Optional) Push to Google Sheets
python gsheet_upload.py
```

## Daily Automation (7 PM)

### Windows Task Scheduler (Recommended)
```
Program:   cmd.exe
Arguments: /c "run_daily_7pm.bat"
Start in:  <your folder path>
Schedule:  Daily at 19:00 (7:00 PM)
```

run_daily_7pm.bat will:
1. Run `collector.py` → fetches all data
2. Run `gsheet_upload.py` → uploads CSV to Google Sheet

### Python Scheduler (Alternative)
```bash
python scheduler_7pm.py  # Runs continuously, triggers daily at 19:00
```

## Google Sheets Integration (Optional)

### To Enable:
1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create Service Account with Editor role
3. Download JSON credentials file
4. Rename to: `groww-data-488513-384d7e65fa4f.json`
5. Place in this folder
6. Share your Google Sheet with the service account email
7. Add Sheet ID to `gsheet_upload.py` (line ~14)

**Without credentials:** CSV is still generated locally; upload is skipped gracefully

## Verification

```bash
# Test complete workflow
python test_workflow.py

# Check CSV output
python check_output.py
```

## Features

✅ **Multi-source consolidation** — All 10 sources merged by date  
✅ **Smart caching** — Incremental updates, preserves historical data  
✅ **Fault tolerance** — Works offline, gracefully handles API timeouts  
✅ **Automation ready** — 7 PM scheduler + Windows Task Scheduler support  
✅ **Google Sheets integration** — Auto-upload if credentials configured  
✅ **Zero dependencies for CSV** — Google auth is optional  
