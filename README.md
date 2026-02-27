# NSE + BSE FO Market Data Collector

Automated daily pipeline that collects Futures & Options market data from NSE and BSE, caches it locally, and pushes the combined output to a Google Sheet.

## Output

`nse_fo_aggregated_data.csv` — 19 columns, one row per trading day from 1 Feb 2025 onwards.

| Column | Source | Description |
|---|---|---|
| `Date` | — | DD-MM-YYYY |
| `NSE_NO_OF_CONT` | NSE FO | Total contracts |
| `NSE_NO_OF_TRADE` | NSE FO | Total trades |
| `NSE_NOTION_VAL` | NSE FO | Notional value |
| `NSE_PR_VAL` | NSE FO | Premium value |
| `BSE_TTL_TRADED_QTY` | BSE Derivatives (IO+IF) | Total traded quantity |
| `BSE_TTL_TRADED_VAL` | BSE Derivatives (IO+IF) | Total traded value |
| `BSE_AVG_TRADED_PRICE` | BSE Derivatives (IO+IF) | Average traded price |
| `BSE_NO_OF_TRADES` | BSE Derivatives (IO+IF) | Number of trades |
| `NSE_CAT_RETAIL_BUY_CR` | NSE FO Category | Retail buy turnover (Rs.Cr) |
| `NSE_CAT_RETAIL_SELL_CR` | NSE FO Category | Retail sell turnover (Rs.Cr) |
| `NSE_CAT_RETAIL_AVG_CR` | NSE FO Category | Retail avg turnover (Rs.Cr) |
| `NSE_EQ_RETAIL_BUY_CR` | NSE Equity Category | Retail buy turnover (Rs.Cr) |
| `NSE_EQ_RETAIL_SELL_CR` | NSE Equity Category | Retail sell turnover (Rs.Cr) |
| `NSE_EQ_RETAIL_AVG_CR` | NSE Equity Category | Retail avg turnover (Rs.Cr) |
| `MRG_OUTSTANDING_BOD_LAKHS` | NSE Margin | Outstanding at start of day (Rs.Lakh) |
| `MRG_FRESH_EXP_LAKHS` | NSE Margin | Fresh exposure during day (Rs.Lakh) |
| `MRG_EXP_LIQ_LAKHS` | NSE Margin | Exposure liquidated (Rs.Lakh) |
| `MRG_NET_EOD_LAKHS` | NSE Margin | Net outstanding end of day (Rs.Lakh) |

## Project Structure

```
collector.py              # Main data collector (5 sources, ~550 lines)
gsheet_upload.py          # Uploads CSV to Google Sheet
requirements.txt          # Python dependencies
.github/workflows/
  daily_collect.yml       # GitHub Actions — runs every day at 7 PM IST
nse_fo_cache.json         # NSE FO cache
bse_fo_cache.json         # BSE cache
nse_cat_cache.json        # NSE FO category cache
nse_eq_cat_cache.json     # NSE equity category cache
nse_mrg_cache.json        # NSE margin trading cache
nse_fo_aggregated_data.csv  # Final combined output
```

## Running locally

```bash
pip install -r requirements.txt
python collector.py         # fetch new data + write CSV
python gsheet_upload.py     # push CSV to Google Sheet
```

## Automation (GitHub Actions)

The workflow `.github/workflows/daily_collect.yml` runs every day at **7:00 PM IST** (13:30 UTC).

### One-time setup required

1. **Add GitHub Secret** — go to *Settings → Secrets → Actions*, create:
   - Name: `GSHEET_SERVICE_ACCOUNT`
   - Value: entire contents of the Google service-account JSON key file

2. **Share the Google Sheet** with the service account email:
   ```
   nse-industry-data@groww-data-488513.iam.gserviceaccount.com
   ```
   Grant **Editor** access.

Each automated run:
- Skips all already-cached dates (fully incremental)
- Fetches only new trading days from all 5 sources
- Uploads the full CSV to Google Sheet
- Commits updated caches + CSV back to the repo
