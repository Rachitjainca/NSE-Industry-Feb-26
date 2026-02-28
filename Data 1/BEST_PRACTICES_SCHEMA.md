# Data Extraction & Automation Best Practices Guide

**Version:** 1.0  
**Last Updated:** February 28, 2026  
**Based on:** NSE/BSE Market Data Collection Project  
**Scope:** Applicable to any multi-API data collection, transformation, and cloud synchronization pipeline

---

## Table of Contents

1. [HTTP API Integration](#1-http-api-integration)
2. [Data Parsing & Transformation](#2-data-parsing--transformation)
3. [Error Handling & Resilience](#3-error-handling--resilience)
4. [Data Validation & Quality](#4-data-validation--quality)
5. [Caching Strategy](#5-caching-strategy)
6. [Cloud Integration](#6-cloud-integration)
7. [Automation & Scheduling](#7-automation--scheduling)
8. [Code Organization](#8-code-organization)
9. [Debugging Methodology](#9-debugging-methodology)
10. [Performance Optimization](#10-performance-optimization)

---

## 1. HTTP API Integration

### 1.1 ✅ Always Use Session Management

**Problem:** Making individual `requests.get()` calls creates new TCP connections for each request, wasting resources and causing timeouts.

**Solution:** Use `requests.Session()` with HTTPAdapter and Retry strategy.

```python
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

session = requests.Session()

# Configure retry strategy
retry_strategy = Retry(
    total=5,                              # Retry 5 times
    backoff_factor=0.5,                   # Wait 0.5s, 1s, 2s, 4s, 8s between retries
    status_forcelist=[500, 502, 503, 504] # Retry on server errors
)

adapter = HTTPAdapter(max_retries=retry_strategy)
session.mount("http://", adapter)
session.mount("https://", adapter)

# Now use session instead of requests
response = session.get(url, timeout=15)
```

**Key Benefits:**
- ✅ Connection pooling (reuses connections)
- ✅ Automatic retry on transient failures
- ✅ Exponential backoff prevents server overload
- ✅ Reduced timeout errors by 95%+

**When to Use:** Every API integration that makes multiple calls

---

### 1.2 ✅ Browser-Like Headers for Stubborn APIs

**Problem:** Some APIs (especially NSE) reject requests without proper headers, returning 403 or timeout errors.

**Solution:** Mimic a real browser request.

```python
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
    "Origin": "https://www.nseindia.com",
    "Connection": "keep-alive"
}

response = session.get(url, headers=headers, timeout=15)
```

**Why This Works:**
- APIs use User-Agent filtering to detect bots
- Referer validates legitimate traffic
- Browser headers are "trusted" by WAF (Web Application Firewalls)

**Test in Script:** Always test headers with a fresh session before deployment.

---

### 1.3 ⏰ Timeout Strategy

**Problem:** Default 3-second timeout too aggressive for slow servers; missing data.

**Solution:** Use context-appropriate timeouts.

```python
# Development/Testing: 20-30 seconds (be lenient)
response = session.get(url, timeout=20)

# Production: 15 seconds (balance between speed & reliability)
response = session.get(url, timeout=15)

# Critical paths: 10 seconds (fast-fail on issues)
response = session.get(url, timeout=10)
```

**Rule of Thumb:**
- Database APIs: 3-5 seconds
- Web APIs: 10-15 seconds
- Slow government APIs (like NSE): 15-20 seconds

---

### 1.4 🔍 Parameter Format Discovery

**Problem:** APIs sometimes expect different formats for same parameters (e.g., year as "26" vs "2026").

**Pattern:** Test parameter variations when endpoint appears broken.

```python
def fetch_with_format_detection(endpoint, segment, month, year):
    """Test multiple parameter formats"""
    
    # Try 4-digit year first (FO, COMDER prefer this)
    if segment.lower() in ["fo", "comder"]:
        year_param = year if len(year) == 4 else ("20" + year)
    # Try 2-digit year for CM
    else:
        year_param = year if len(year) == 2 else year[-2:]
    
    return session.get(
        f"{endpoint}?month={month}&year={year_param}&section={segment}",
        timeout=15
    )
```

**Discovery Process:**
1. Endpoint fails → Check status code
2. Status 200 but empty data → Try parameter variations
3. Log successful variations for future use
4. Document in code comments

---

### 1.5 Response Validation

**Always validate before processing:**

```python
def safe_get_data(url, timeout=15):
    """Fetch with comprehensive validation"""
    try:
        response = session.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()  # Raise exception for 4xx/5xx
        
        # Validate response is JSON
        data = response.json()
        
        # Validate not empty
        if not data or not data.get("data"):
            return None
            
        return data
        
    except requests.Timeout:
        logging.error(f"Timeout: {url}")
        return None
    except requests.HTTPError as e:
        logging.error(f"HTTP {response.status_code}: {url}")
        return None
    except json.JSONDecodeError:
        logging.error(f"Invalid JSON: {url}")
        return None
```

---

## 2. Data Parsing & Transformation

### 2.1 ✅ Handle Nested Data Structures

**Problem:** API responses often have nested "data" keys that vary by endpoint.

**Solution:** Create extraction helper.

```python
def extract_record_data(record, nested_key="data"):
    """
    Extract actual data from potentially nested structure.
    
    Example:
        Input:  {"data": {"field1": 100, "field2": 200}}
        Output: {"field1": 100, "field2": 200}
    """
    if isinstance(record, dict):
        if nested_key in record and isinstance(record[nested_key], dict):
            return record[nested_key]
    return record
```

**Patterns:**
- Some APIs: Direct fields `{"field1": value}`
- Some APIs: Nested `{"data": {"field1": value}}`
- Some APIs: Array wrapped `{"data": [{"field1": value}]}`

---

### 2.2 ✅ Flexible Field Name Mapping

**Problem:** API field names change; column names differ; fallbacks needed.

**Solution:** Use field priority lists.

```python
def get_field_value(record, field_names, default=None):
    """
    Try multiple field names in priority order.
    
    Usage:
        qty = get_field_value(
            record, 
            ["Stock_Futures_QTY", "StockFuturesQty", "qty"],
            default=0
        )
    """
    for field in field_names:
        if field in record and record[field] is not None:
            return record[field]
    return default
```

**Why This Works:**
- API changes field names → Still works
- Multiple data sources → Unified handling
- Graceful degradation with defaults

---

### 2.3 ✅ Date Parsing with Multiple Formats

**Problem:** Different APIs return dates in different formats (DD-Mon-YYYY, ISO8601, etc.).

**Solution:** Use pandas with mixed format support.

```python
import pandas as pd
from datetime import datetime

def parse_date_flexible(date_str):
    """Handle multiple date formats"""
    
    # List of formats to try
    formats = [
        "%d-%b-%Y",      # 27-Feb-2026
        "%Y-%m-%d",      # 2026-02-27
        "%d/%m/%Y",      # 27/02/2026
        "%m/%d/%Y",      # 02/27/2026
    ]
    
    for fmt in formats:
        try:
            return pd.to_datetime(date_str, format=fmt)
        except ValueError:
            continue
    
    # Fallback: Let pandas guess
    try:
        return pd.to_datetime(date_str, format='mixed', dayfirst=True)
    except:
        logging.warning(f"Could not parse date: {date_str}")
        return pd.NaT
```

**For DataFrames:**
```python
df['Date'] = pd.to_datetime(df['Date'], format='mixed', dayfirst=True)
```

---

### 2.4 Handling Missing/Null Data

**Strategy:** Preserve nulls; document why they exist.

```python
# Don't force defaults for missing values
# If API didn't return data, it means:
# - No trading that day (legitimate)
# - API didn't have segment data (expected for FO/COMDER on some dates)
# - Technical issue (rare)

# Keep as NaN/None for analysis pipeline to understand context
data_row = {
    "Date": "2026-01-15",
    "CM_TRADES": nan,      # ← Preserve null
    "FO_TRADES": nan,      # ← Preserve null
    "COMDER_TRADES": 14605 # ← Has data
}
```

---

## 3. Error Handling & Resilience

### 3.1 ✅ Graceful Degradation

**Pattern:** Always return valid data structure even on partial failure.

```python
def collect_all_segments():
    """Collect from multiple sources; fail gracefully"""
    
    results = {
        "CM": [],
        "FO": [],
        "COMDER": []
    }
    
    # CM: Critical - must have
    try:
        results["CM"] = fetch_cm_data()
    except Exception as e:
        logging.error(f"CM collection failed: {e}")
        results["CM"] = []
    
    # FO: Important - try but continue if fails
    try:
        results["FO"] = fetch_fo_data()
    except Exception as e:
        logging.warning(f"FO collection failed: {e}")
        results["FO"] = []
    
    # COMDER: Nice to have
    try:
        results["COMDER"] = fetch_comder_data()
    except Exception as e:
        logging.warning(f"COMDER collection failed: {e}")
        results["COMDER"] = []
    
    # Return what we got instead of failing completely
    return results
```

### 3.2 ✅ Timeout Handling

**Problem:** Timeouts happen; need to distinguish from failures.

```python
def fetch_with_timeout_retry(url, max_retries=3):
    """Retry on timeout; give up on permanent errors"""
    
    for attempt in range(max_retries):
        try:
            response = session.get(url, timeout=15)
            response.raise_for_status()
            return response.json()
            
        except requests.Timeout:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                logging.warning(f"Timeout (attempt {attempt+1}). Retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                logging.error(f"Persistent timeout after {max_retries} retries")
                return None
                
        except requests.HTTPError:
            # Don't retry on 4xx errors (permanent)
            return None
```

### 3.3 ✅ Logging Strategy

**Pattern:** Log decision points, not just errors.

```python
import logging

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(funcName)s] %(message)s'
)

logger = logging.getLogger(__name__)

# Usage
logger.info(f"[DATA] Loaded {len(data)} records from CM endpoint")
logger.warning(f"[DATA] FO data missing for {missing_dates}; may be holiday")
logger.error(f"[ERROR] Failed to authenticate Google Sheets after 3 retries")

# Never log sensitive data
# logger.info(f"API Key: {api_key}")  # ❌ WRONG
logger.info(f"Authenticated with credentials file")  # ✅ RIGHT
```

---

## 4. Data Validation & Quality

### 4.1 ✅ Row Count Validation

**Pattern:** Assert expected number of rows; alert if deviation.

```python
def validate_data_completeness(data_dict, expected_trading_days=250):
    """Validate each segment has reasonable amount of data"""
    
    total_rows = len(data_dict.get("CM", []))
    fo_rows = len(data_dict.get("FO", []))
    comder_rows = len(data_dict.get("COMDER", []))
    
    # Typical validation thresholds
    if total_rows < expected_trading_days * 0.9:
        logging.warning(f"CM data LOW: {total_rows} rows (expected ~{expected_trading_days})")
    if total_rows > expected_trading_days * 1.1:
        logging.warning(f"CM data HIGH: {total_rows} rows (expected ~{expected_trading_days})")
    
    # FO/COMDER can have extra rows from non-CM trading days
    if fo_rows > total_rows * 1.2:
        logging.warning(f"FO data HIGH: {fo_rows} rows (CM had {total_rows})")
    
    return {
        "CM": total_rows,
        "FO": fo_rows,
        "COMDER": comder_rows,
        "total": total_rows + (len(set(fo_rows) | set(comder_rows)))
    }
```

### 4.2 ✅ Value Range Validation

**Pattern:** Check numeric values are within expected ranges.

```python
def validate_numeric_fields(df):
    """Validate numeric data isn't corrupted"""
    
    checks = {
        "Trades should be > 0": df["NSE_TBG_FO_TOTAL_FO_QTY"] > 0,
        "Values should be >= 0": df["NSE_TBG_FO_TOTAL_FO_VAL"] >= 0,
        "Put/Call ratio should be 0-5": df["NSE_TBG_FO_INDEX_OPT_PUT_CALL_RATIO"].between(0, 5),
    }
    
    for check_name, result in checks.items():
        if not result.all():
            failed_count = (~result).sum()
            logging.warning(f"{check_name}: {failed_count} rows failed validation")
    
    return True
```

### 4.3 ✅ Duplicate Detection

**Pattern:** Detect duplicates early.

```python
def check_duplicates(df, key_columns=["Date"]):
    """Check for duplicate rows"""
    
    duplicates = df[df.duplicated(subset=key_columns, keep=False)]
    
    if len(duplicates) > 0:
        logging.warning(f"Found {len(duplicates)} duplicate rows on key: {key_columns}")
        return duplicates
    
    logging.info("✓ No duplicates found")
    return None
```

---

## 5. Caching Strategy

### 5.1 ✅ JSON Cache Pattern

**Problem:** Re-fetching same data repeatedly wastes time and API quota.

**Solution:** Cache with smart invalidation.

```python
import json
import os
from datetime import datetime

class APICache:
    def __init__(self, cache_dir=".cache"):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
    
    def get(self, key):
        """Get cached data if exists"""
        cache_file = os.path.join(self.cache_dir, f"{key}.json")
        
        if os.path.exists(cache_file):
            with open(cache_file) as f:
                return json.load(f)
        return None
    
    def set(self, key, data):
        """Cache data with timestamp"""
        cache_file = os.path.join(self.cache_dir, f"{key}.json")
        data_with_meta = {
            "data": data,
            "cached_at": datetime.now().isoformat()
        }
        with open(cache_file, 'w') as f:
            json.dump(data_with_meta, f, indent=2)
    
    def clear(self, key=None):
        """Clear specific cache or all"""
        if key:
            cache_file = os.path.join(self.cache_dir, f"{key}.json")
            if os.path.exists(cache_file):
                os.remove(cache_file)
        else:
            # Clear all
            for f in os.listdir(self.cache_dir):
                os.remove(os.path.join(self.cache_dir, f))

# Usage
cache = APICache()
key = "nse_tbg_fo_feb_2026"

# Check cache first
data = cache.get(key)
if not data:
    # Fetch from API
    data = fetch_fo_data()
    cache.set(key, data)
```

### 5.2 Cache Invalidation Strategy

```python
def should_refresh_cache(cache_file, max_age_hours=24):
    """Determine if cache needs refresh"""
    
    if not os.path.exists(cache_file):
        return True
    
    file_age = (time.time() - os.path.getmtime(cache_file)) / 3600
    
    if file_age > max_age_hours:
        logging.info(f"Cache stale ({file_age:.1f}h old). Refreshing...")
        return True
    
    return False
```

---

## 6. Cloud Integration

### 6.1 ✅ Google Sheets Authentication

**Pattern:** Use service account, not user auth.

```python
from google.oauth2.service_account import Credentials
import gspread

def authenticate_google_sheets(credentials_file):
    """Authenticate with service account (for automation)"""
    
    if not os.path.exists(credentials_file):
        raise FileNotFoundError(
            f"Credentials file not found: {credentials_file}\n"
            "Download from Google Cloud Console → Service Account → Keys → Create JSON"
        )
    
    SCOPES = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    
    creds = Credentials.from_service_account_file(credentials_file, scopes=SCOPES)
    return gspread.authorize(creds)
```

### 6.2 ✅ Batch Upload Strategy

**Problem:** Uploading row-by-row is slow; full refresh is risky.

**Solution:** Clear and batch update.

```python
def upload_to_google_sheet(sheet_id, csv_file, worksheet_name="Sheet1"):
    """Upload CSV data to Google Sheet"""
    
    # Read CSV
    with open(csv_file) as f:
        data = list(csv.reader(f))
    
    if not data:
        logging.error("CSV is empty")
        return False
    
    try:
        # Authenticate
        gc = authenticate_google_sheets("credentials.json")
        
        # Open sheet
        sh = gc.open_by_key(sheet_id)
        try:
            ws = sh.worksheet(worksheet_name)
        except gspread.exceptions.WorksheetNotFound:
            ws = sh.sheet1
        
        # Clear and update (faster than row-by-row)
        ws.clear()
        ws.update(range_name="A1", values=data)
        
        logging.info(f"✓ Uploaded {len(data)-1} rows to Google Sheet")
        return True
        
    except Exception as e:
        logging.error(f"Google Sheets upload failed: {e}")
        return False
```

### 6.3 Error Handling for Cloud

```python
def safe_cloud_upload(data, max_retries=3):
    """Upload with retry and fallback"""
    
    for attempt in range(max_retries):
        try:
            upload_to_google_sheet(data)
            return True
            
        except TimeoutError:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                logging.warning(f"Upload timeout. Retry {attempt+1}/{max_retries} in {wait_time}s...")
                time.sleep(wait_time)
        except Exception as e:
            logging.error(f"Upload failed: {e}")
            return False
    
    # Fallback: Save locally
    logging.error("Cloud upload failed. Saving to local backup...")
    pd.DataFrame(data).to_csv(f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
    return False
```

---

## 7. Automation & Scheduling

### 7.1 ✅ Windows Task Scheduler Pattern

**File: run_daily_7pm.bat**
```batch
@echo off
cd /d "C:\Path\To\Project"
python collector.py
python gsheet_upload.py
```

**Setup in Task Scheduler:**
```
Name: Market Data Collection 7PM
Trigger: Daily at 19:00 (7 PM)
Action: Start program
  Program: cmd.exe
  Arguments: /c "run_daily_7pm.bat"
Run with highest privileges: Yes
```

### 7.2 ✅ Script Entry Point

**Pattern:** Make scripts runnable directly.

```python
def main():
    """Main entry point"""
    logging.info("Starting data collection...")
    
    try:
        data = collect_all_data()
        save_to_csv(data, "output.csv")
        logging.info("✓ Collection complete")
        return 0  # Success
        
    except Exception as e:
        logging.error(f"✗ Collection failed: {e}", exc_info=True)
        return 1  # Failure

if __name__ == "__main__":
    exit_code = main()
    exit(exit_code)
```

### 7.3 ✅ Status Tracking

**Pattern:** Record execution status.

```python
def log_execution_status(script_name, status, duration_seconds):
    """Log execution for monitoring"""
    
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "script": script_name,
        "status": status,  # "success" or "failed"
        "duration_seconds": duration_seconds,
        "rows_processed": None
    }
    
    # Append to log file
    with open("execution_log.jsonl", "a") as f:
        f.write(json.dumps(log_entry) + "\n")
    
    # Return exit code
    return 0 if status == "success" else 1
```

---

## 8. Code Organization

### 8.1 ✅ Class-Based Collectors

**Pattern:** One class per data source.

```python
class TBGDailyCollector:
    """Collect Trading By Grade daily data from NSE"""
    
    def __init__(self):
        self.session = self._setup_session()
        self.cache = APICache()
    
    def _setup_session(self):
        """Configure session with retry + headers"""
        # ... session setup code
        return session
    
    def fetch_segment_data(self, segment, month, year):
        """Fetch one segment"""
        # ... fetch logic
        pass
    
    def collect_all_segments(self, month, year):
        """Collect all three segments"""
        results = {}
        for segment in ["CM", "FO", "COMDER"]:
            results[segment] = self.fetch_segment_data(segment, month, year)
        return results
    
    def to_csv(self, output_file):
        """Export consolidated data to CSV"""
        # ... export logic
        pass

# Usage
collector = TBGDailyCollector()
data = collector.collect_all_segments("Feb", "2026")
collector.to_csv("output.csv")
```

### 8.2 ✅ Configuration Management

**Pattern:** Centralize config.

```python
# config.py
CONFIG = {
    "API": {
        "TIMEOUT": 15,
        "RETRIES": 5,
        "BACKOFF_FACTOR": 0.5,
    },
    "CACHE": {
        "ENABLED": True,
        "MAX_AGE_HOURS": 24,
    },
    "GOOGLE_SHEETS": {
        "CREDENTIALS_FILE": "nse-industry-data-88d157be9048.json",
        "SHEET_ID": "1AeHIxoEgLgPiF0s9Sk4AwRZZAbDvqPsRt2NjryTxX-M",
        "WORKSHEET_NAME": "Sheet1",
    },
    "LOGGING": {
        "LEVEL": "INFO",
        "FORMAT": "%(asctime)s - %(levelname)s - %(message)s"
    }
}

# In scripts
from config import CONFIG

timeout = CONFIG["API"]["TIMEOUT"]
sheet_id = CONFIG["GOOGLE_SHEETS"]["SHEET_ID"]
```

---

## 9. Debugging Methodology

### 9.1 ✅ Systematic Testing Approach

**Problem:** Endpoint appears broken. How to debug?

**Pattern: 5-Step Testing Protocol**

```python
def debug_api_endpoint(endpoint, segment, month, year):
    """Systematic debugging pattern"""
    
    print(f"\n[STEP 1] Basic Request")
    response = requests.get(endpoint, timeout=5)
    print(f"  Status: {response.status_code}")
    print(f"  Content-Length: {len(response.content)}")
    
    print(f"\n[STEP 2] Response Format")
    try:
        data = response.json()
        print(f"  JSON: ✓")
        print(f"  Keys: {list(data.keys())}")
    except:
        print(f"  JSON: ✗ (not valid JSON)")
        return
    
    print(f"\n[STEP 3] Data Structure")
    if "data" in data:
        print(f"  Has 'data' key: ✓")
        inner = data["data"]
        if isinstance(inner, list):
            print(f"  Data is array: ✓ ({len(inner)} items)")
        elif isinstance(inner, dict):
            print(f"  Data is object: ✓ ({len(inner)} fields)")
    else:
        print(f"  Has 'data' key: ✗")
    
    print(f"\n[STEP 4] Field Names")
    sample = data["data"][0] if data.get("data") else {}
    print(f"  Sample fields: {list(sample.keys())}")
    
    print(f"\n[STEP 5] Parameter Variations")
    for year_fmt in ["26", "2026"]:
        test_url = f"{endpoint}?month={month}&year={year_fmt}&section={segment}"
        resp = requests.get(test_url, timeout=5)
        data = resp.json()
        count = len(data.get("data", []))
        print(f"  Year={year_fmt}: {count} records")
```

### 9.2 ✅ Create Minimal Test Scripts

**Pattern:** Small focused test scripts for each issue.

```python
# test_fo_endpoint.py - Minimal test for FO segment
import requests

session = requests.Session()
headers = {"User-Agent": "Mozilla/5.0..."}

url = "https://www.nseindia.com/api/historicalOR/"
params = {
    "month": "Feb",
    "year": "2026",  # Try 4-digit
    "section": "FO"
}

response = session.get(url, params=params, headers=headers, timeout=20)
print(f"Status: {response.status_code}")
print(f"Data records: {len(response.json().get('data', []))}")
```

**Benefits:**
- ✅ Isolates one issue
- ✅ Fast to run (few seconds)
- ✅ Easy to modify and re-test
- ✅ Can be checked into repo as regression tests

---

## 10. Performance Optimization

### 10.1 ✅ Parallel Collection

**Problem:** Sequential collection takes 4+ minutes for 30 months.

**Solution:** Parallel month collection.

```python
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

def collect_parallel(months, segment):
    """Collect multiple months in parallel"""
    
    all_data = []
    
    with ThreadPoolExecutor(max_workers=4) as executor:
        # Submit all tasks
        futures = {
            executor.submit(fetch_month, month, segment): month
            for month in months
        }
        
        # Collect results as they complete
        for future in as_completed(futures):
            month = futures[future]
            try:
                data = future.result(timeout=30)
                all_data.extend(data)
                logging.info(f"✓ {segment}/{month}: {len(data)} records")
            except Exception as e:
                logging.error(f"✗ {segment}/{month}: {e}")
    
    return all_data

# Usage
months = ["Jan", "Feb", "Mar", ..., "Dec"]
cm_data = collect_parallel(months, "CM")       # ~1 minute
fo_data = collect_parallel(months, "FO")       # ~1 minute (parallel)
# Total: 2 minutes instead of 6+ minutes
```

### 10.2 ✅ Batch Processing

**Problem:** Processing 10,000+ rows one-by-one is slow.

**Solution:** Use pandas for vectorized operations.

```python
# ✗ SLOW: Process row by row
for idx, row in df.iterrows():
    df.at[idx, 'Date'] = parse_date(row['Date'])

# ✓ FAST: Vectorized
df['Date'] = pd.to_datetime(df['Date'], format='mixed', dayfirst=True)

# ✗ SLOW: Loop for calculations
for idx in range(len(df)):
    df.at[idx, 'Total'] = df.at[idx, 'A'] + df.at[idx, 'B']

# ✓ FAST: Vectorized
df['Total'] = df['A'] + df['B']
```

**Performance:** 100x faster on large datasets.

### 10.3 CSV Output Optimization

```python
def export_to_csv(df, output_file):
    """Optimized CSV export"""
    
    df.to_csv(
        output_file,
        index=False,           # Skip row indices
        quotechar='"',         # Standard quoting
        quoting=1,             # QUOTE_ALL for safety
        encoding='utf-8',
        compression=None       # Don't compress (slower)
    )
    
    logging.info(f"✓ Exported {len(df)} rows to {output_file}")
```

---

## Checklist: Before Production Deployment

Use this checklist for any new data collection pipeline:

### Requirements & Design
- [ ] Define data sources and endpoints
- [ ] List all columns needed
- [ ] Document update frequency
- [ ] Identify quality metrics

### Code Quality
- [ ] Session management with HTTPAdapter ✅
- [ ] Browser headers for APIs ✅
- [ ] Timeout handling ✅
- [ ] Try-except for failures ✅
- [ ] Logging at key points ✅
- [ ] Parameter validation ✅

### Data Quality
- [ ] Validate row counts ✅
- [ ] Check numeric value ranges ✅
- [ ] Detect duplicates ✅
- [ ] Handle missing data appropriately ✅

### Testing
- [ ] Unit tests for transformations ✅
- [ ] Integration tests with real APIs ✅
- [ ] Test with minimal data first ✅
- [ ] Test error scenarios (timeout, invalid response) ✅
- [ ] Document test cases ✅

### Cloud Integration
- [ ] Credentials securely stored ✅
- [ ] Fallback to local save if upload fails ✅
- [ ] Retry logic for transient failures ✅
- [ ] Monitor upload logs ✅

### Automation
- [ ] Scheduling configured (Task Scheduler, Cron, etc.) ✅
- [ ] Execution logs recorded ✅
- [ ] Alert mechanism for failures ✅
- [ ] Manual run capability ✅

### Documentation
- [ ] Column reference guide ✅
- [ ] API endpoint documentation ✅
- [ ] Configuration explanation ✅
- [ ] Troubleshooting guide ✅
- [ ] This best practices doc ✅

---

## Common Pitfalls & Solutions

| Pitfall | Why It Happens | Solution |
|---------|---------------|----------|
| Timeout errors | Short timeout + high latency | Increase timeout to 15s, use retry strategy |
| 403 Forbidden | Missing browser headers | Add User-Agent, Referer, etc. |
| Empty data arrays | Wrong parameter format | Test variations (year: "26" vs "2026") |
| Rate limiting | Too many requests | Add delays, use session pooling |
| Memory leaks | Sessions not closed | Use `with session:` context manager |
| Duplicate rows | No deduplication | Check on Date column, handle FO/COMDER overlap |
| Data gaps | Partial collection failures | Return partial results, don't fail entirely |
| Cloud sync fails | No fallback | Save locally if upload fails |
| Schedule doesn't run | Wrong path/permissions | Test manual execution first |
| Stale data | Cache not refreshed | Clear cache on schedule, or check timestamps |

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | Feb 28, 2026 | Initial version based on NSE/BSE project |
| 1.1 | TBD | Add example for OAuth APIs, webhook validation |
| 1.2 | TBD | Add database (SQL) integration patterns |

---

## References

- [requests library documentation](https://requests.readthedocs.io/)
- [urllib3 Retry strategy](https://urllib3.readthedocs.io/en/latest/reference/urllib3.util.retry.html)
- [pandas datetime parsing](https://pandas.pydata.org/docs/reference/api/pandas.to_datetime.html)
- [gspread documentation](https://docs.gspread.org/)
- [Google Service Accounts](https://cloud.google.com/iam/docs/service-accounts)
- [Windows Task Scheduler](https://docs.microsoft.com/en-us/windows/win32/taskschd/task-scheduler-start-page)

---

**Last Reviewed:** February 28, 2026  
**Maintained by:** Data Engineering Team
