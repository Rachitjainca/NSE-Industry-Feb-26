# New API Integration Workflow Template

**Version:** 1.0  
**Updated:** February 28, 2026  
**Purpose:** Step-by-step guide to add any new API using the reusable framework

---

## Quick Start (5 Steps)

### Step 1: Copy Template Files
```bash
cp api_collector_template.py my_api_collector.py
cp run_daily_collection_template.bat run_daily_my_api.bat
```

### Step 2: Customize CONFIG Section
Edit `my_api_collector.py` - modify the CONFIG dict (lines 35-95)

### Step 3: Implement API Methods
Update two functions in `my_api_collector.py`:
1. `fetch_api_data()` - How to call the API
2. `parse_api_response()` - How to extract data

### Step 4: Test Locally
```bash
python my_api_collector.py
```
Check `output_data.csv` and `execution.log`

### Step 5: Schedule Daily
Open Windows Task Scheduler and import the `.bat` file

---

## Detailed Implementation Guide

### Phase 1: API Analysis & Documentation

**Time Required:** 30-60 minutes

#### 1.1 Document API Details
Create a file: `API_DOCUMENTATION.md`

```markdown
# API Name: [Your API]

## Endpoint Details
- Base URL: https://api.example.com/v1/data
- Authentication: API Key / Bearer Token / OAuth2
- Rate Limits: X requests/minute
- Response Format: JSON / XML / CSV

## Parameters
| Parameter | Type | Required | Format | Notes |
|-----------|------|----------|--------|-------|
| month | string | yes | "Jan", "Feb" | ... |
| year | string | yes | "2026" or "26" | Check API docs |
| segment | string | yes | "CM", "FO" | Valid values |

## Response Structure
```json
{
  "status": "success",
  "data": [
    {
      "date": "27-Feb-2026",
      "trades": 34269344,
      "value": 144962.74
    }
  ]
}
```

## Key Discoveries
- ⚠️ Timeout: 15 seconds needed (API is slow)
- ⚠️ Year format: 4-digit for FO, 2-digit for CM
- ⚠️ Browser headers required (blocks bots)
- ⚠️ Empty "data" array on holidays (expected)

## Testing Results
- All endpoints: ✅ Working
- Authentication: ✅ Success
- Edge cases: Day off returns empty array (expected)
```

#### 1.2 Identify Field Mappings
Create: `FIELD_MAPPING.json`

```json
{
  "API_Response_Fields": {
    "date": "Date in DD-Mon-YYYY format",
    "no_of_trades": "Number of trades for the period",
    "traded_value": "Total traded value in currency"
  },
  
  "Output_CSV_Columns": {
    "Date": "Parsed as datetime",
    "NSE_NO_OF_TRADES": "Mapped from API field 'no_of_trades'",
    "NSE_TRADED_VALUE": "Mapped from API field 'traded_value'"
  },
  
  "Fallback_Fields": {
    "NSE_NO_OF_TRADES": ["no_of_trades", "numberOfTrades", "count"],
    "NSE_TRADED_VALUE": ["traded_value", "tradedValue", "totalValue"]
  }
}
```

---

### Phase 2: Template Customization

**Time Required:** 15-30 minutes

#### 2.1 Customize CONFIG

Open `api_collector_template.py` and edit CONFIG section:

```python
CONFIG = {
    "API": {
        "BASE_URL": "https://api.nseindia.com/api/historicalOR/",  # ← Your API URL
        "TIMEOUT": 15,      # ← Adjust based on API speed
        "RETRIES": 5,       # ← Keep at 5 for resilience
        "BACKOFF_FACTOR": 0.5,
        "HEADERS": {
            "User-Agent": "Mozilla/5.0...",  # ← Update if needed
            # Add API key or auth headers if needed
            # "Authorization": "Bearer YOUR_API_KEY"
        }
    },
    
    "DATA_SOURCES": {
        "CM": {
            "names": ["CM"],
            "months": list("Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()),
            "year": "26"  # ← Year format: "26" or "2026"
        },
        "FO": {
            "names": ["FO"],
            "months": list("Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()),
            "year": "2026"  # ← Different format if API requires
        },
    },
    
    "OUTPUT": {
        "CSV_FILE": "my_api_output_data.csv",  # ← Your output filename
    },
    
    "GOOGLE_SHEETS": {
        "SHEET_ID": "YOUR_SHEET_ID_HERE",  # ← Your Google Sheet ID
    },
}
```

#### 2.2 Implement fetch_api_data()

Replace the `fetch_api_data()` method:

```python
def fetch_api_data(self, segment, month, year):
    """Fetch data from [Your API]"""
    
    cache_key = f"{segment}_{month}_{year}"
    cached = self.cache.get(cache_key)
    if cached:
        logger.info(f"[CACHE] {segment}/{month}/{year}")
        return cached
    
    try:
        # Build your specific URL and parameters
        url = CONFIG["API"]["BASE_URL"]
        
        # Handle year format variations (if needed)
        if segment.lower() in ["fo"]:
            year_param = year if len(year) == 4 else ("20" + year)
        else:
            year_param = year if len(year) == 2 else year[-2:]
        
        params = {
            "month": month,
            "year": year_param,
            "section": segment
        }
        
        logger.info(f"Fetching {segment}/{month}/{year}...")
        
        response = self.session.get(
            url,
            params=params,
            headers=self.headers,
            timeout=CONFIG["API"]["TIMEOUT"]
        )
        
        response.raise_for_status()
        data = response.json()
        
        # Parse the response
        records = self.parse_api_response(data, segment)
        
        if records:
            self.cache.set(cache_key, records)
            logger.info(f"✓ {segment}/{month}/{year}: {len(records)} records")
        else:
            logger.warning(f"⚠ {segment}/{month}/{year}: No data")
        
        return records
        
    except requests.Timeout:
        logger.error(f"✗ Timeout: {segment}/{month}/{year}")
        return []
    except Exception as e:
        logger.error(f"✗ Error: {segment}/{month}/{year}: {e}")
        return []
```

#### 2.3 Implement parse_api_response()

Replace the `parse_api_response()` method:

```python
def parse_api_response(self, data, segment):
    """Parse [Your API] response"""
    
    # Adjust based on your API response structure
    # Examples:
    
    # Structure 1: {"data": [{...}, {...}]}
    if isinstance(data, dict) and "data" in data:
        records = data["data"]
        if isinstance(records, dict):
            records = [records]
        return records if isinstance(records, list) else []
    
    # Structure 2: [{...}, {...}] (direct array)
    if isinstance(data, list):
        return data
    
    # Structure 3: {"results": [{...}]}
    if isinstance(data, dict) and "results" in data:
        return data["results"]
    
    return []
```

#### 2.4 Customize consolidate_data()

Update `consolidate_data()` function if you need special merging logic:

```python
def consolidate_data(all_records):
    """Consolidate [Your API] data"""
    
    consolidated = []
    
    for segment_name, records in all_records.items():
        for record in records:
            row = {
                "Segment": segment_name,
                # Add your field mappings here
                "Date": record.get("date"),
                "NO_OF_TRADES": record.get("no_of_trades"),
                "TRADED_VALUE": record.get("traded_value"),
            }
            consolidated.append(row)
    
    df = pd.DataFrame(consolidated)
    
    # Parse dates
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"], format="mixed", dayfirst=True)
        df = df.sort_values("Date")
    
    return df
```

---

### Phase 3: Testing

**Time Required:** 30-45 minutes

#### 3.1 Unit Test - API Connection

Create: `test_api_connection.py`

```python
import requests
import json

BASE_URL = "https://api.example.com/endpoint"
HEADERS = {"User-Agent": "Mozilla/5.0..."}

def test_connectivity():
    """Test basic API connectivity"""
    print("Testing API connectivity...")
    
    response = requests.get(BASE_URL, headers=HEADERS, timeout=15)
    print(f"Status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"Response type: {type(data)}")
        print(f"Keys: {list(data.keys()) if isinstance(data, dict) else 'Array'}")
        print("✓ Connectivity OK")
        return True
    else:
        print(f"✗ Error {response.status_code}")
        return False

if __name__ == "__main__":
    test_connectivity()
```

Run: `python test_api_connection.py`

#### 3.2 Full Integration Test

```bash
python my_api_collector.py
```

**Check outputs:**
- ✅ `output_data.csv` created
- ✅ `execution.log` shows all steps completed
- ✅ Data contains expected columns
- ✅ Dates are parsed correctly

#### 3.3 Validate Data

```python
import pandas as pd

df = pd.read_csv("output_data.csv")
print(f"Rows: {len(df)}")
print(f"Columns: {list(df.columns)}")
print(f"\nFirst 5 rows:\n{df.head()}")
print(f"\nData types:\n{df.dtypes}")
print(f"\nNull counts:\n{df.isnull().sum()}")
```

---

### Phase 4: Cloud Integration

**Time Required:** 10-15 minutes

#### 4.1 Google Sheets Setup

1. Go to: https://console.cloud.google.com
2. Create new project or select existing
3. Enable APIs:
   - Google Sheets API
   - Google Drive API
4. Create Service Account:
   - IAM & Admin → Service Accounts
   - Create new service account
   - Grant Editor role
   - Create JSON key
5. Share your target Google Sheet with service account email:
   - Email format: `your-account@your-project.iam.gserviceaccount.com`

#### 4.2 Update Credentials

```python
CONFIG = {
    ...
    "GOOGLE_SHEETS": {
        "ENABLED": True,
        "CREDENTIALS_FILE": "service-account-key.json",  # Downloaded from above
        "SHEET_ID": "1AeHIxoEgLgPiF0s9Sk4AwRZZAbDvqPsRt2NjryTxX-M",  # Your sheet ID
        "WORKSHEET_NAME": "Sheet1",  # Tab name
    },
}
```

#### 4.3 Test Upload

```bash
python my_api_collector.py
```

Check:
- ✅ Log shows "Uploaded X rows to Google Sheet"
- ✅ Data appears in Google Sheet
- ✅ All columns are present

---

### Phase 5: Automation Setup

**Time Required:** 5-10 minutes

#### 5.1 Create Batch File

Copy `run_daily_collection_template.bat` and customize:

```batch
@echo off
cd /d "C:\Path\To\Your\Project"
python my_api_collector.py
```

#### 5.2 Schedule in Windows Task Scheduler

1. Open: `taskschd.msc`
2. Right-click Task Scheduler Library → Create Basic Task
3. Configure:

| Field | Value |
|-------|-------|
| Name | "Market Data Collection - [Your API]" |
| Trigger | Daily at 19:00 (7 PM) |
| Action | Start program: `cmd.exe` |
| Arguments | `/c "run_daily_my_api.bat"` |
| Run with highest privileges | ✓ Checked |

#### 5.3 Test Schedule

Right-click task → Run

Check:
- ✅ Script executes
- ✅ CSV updates with latest data
- ✅ Google Sheet updates
- ✅ Logs show success

---

## Common API Integration Patterns

### Pattern 1: Basic GET Request

```python
response = session.get(url, params={...}, headers=headers, timeout=15)
data = response.json()
records = data.get("data", [])
```

### Pattern 2: Authentication Required

```python
headers = {
    "Authorization": f"Bearer {API_KEY}",
    "User-Agent": "Mozilla/5.0..."
}
response = session.get(url, headers=headers, timeout=15)
```

### Pattern 3: Date Parameter Variations

```python
# Some APIs expect: "2026"
# Some APIs expect: "26"
# Test both:

for year_format in ["26", "2026"]:
    params = {"year": year_format, ...}
    response = session.get(url, params=params)
    if len(response.json().get("data", [])) > 0:
        print(f"✓ Year format {year_format} works")
        break
```

### Pattern 4: Nested Data Extraction

```python
# API response: {"status": "ok", "data": [{"field": value}]}
data = response.json()
records = data.get("data", [])

# API response: {"results": [{"field": value}]}
data = response.json()
records = data.get("results", [])
```

### Pattern 5: Date Parsing

```python
# Multiple formats
df["Date"] = pd.to_datetime(df["Date"], format="mixed", dayfirst=True)

# Or specific format
df["Date"] = pd.to_datetime(df["Date"], format="%d-%b-%Y")
```

---

## Troubleshooting Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| 403 Forbidden | Missing headers | Add browser headers (User-Agent, Referer) |
| Timeout errors | Slow API | Increase timeout to 20-30 seconds |
| Empty data arrays | Wrong parameter format | Test variations (year: "26" vs "2026") |
| Rate limiting | Too many requests | Add delays between requests or use caching |
| CSV upload fails | Credentials missing | Download service account JSON from Google |
| Schedule doesn't run | Bad path | Test script manually first with full paths |
| Data gaps | Partial failures | System returns partial data (expected) |

---

## Monitoring & Maintenance

### Daily Checks

1. ✅ Google Sheet updated with latest data
2. ✅ CSV file has new rows
3. ✅ No error entries in execution log

### Weekly Checks

1. ✅ Data quality metrics stable
2. ✅ No timeout warnings
3. ✅ All segments collecting data

### Monthly Review

1. ✅ Document any API changes
2. ✅ Update field mappings if needed
3. ✅ Review performance metrics

---

## File Structure After Setup

```
your-project/
├── my_api_collector.py           # Main script
├── run_daily_my_api.bat          # Scheduler batch file
├── config.json                   # Configuration (optional)
├── service-account-key.json      # Google credentials
├── API_DOCUMENTATION.md          # API reference
├── FIELD_MAPPING.json            # Column mappings
├── output_data.csv               # Latest data (generated)
├── execution.log                 # Detailed logs
├── execution_log.jsonl           # Execution status
├── .cache/                       # API cache directory
│   ├── CM_Jan_26.json
│   ├── FO_Jan_2026.json
│   └── ...
├── backups/                      # CSV backups
│   ├── output_data_20260228_190012.csv
│   └── ...
└── logs/                         # Scheduler logs
    └── collection_*.log
```

---

## Next Steps

1. **Customize Template** - Edit CONFIG section (15 min)
2. **Implement Methods** - Add fetch and parse functions (20 min)
3. **Test Locally** - Run script and verify output (20 min)
4. **Setup Google Sheets** - Download credentials and share sheet (15 min)
5. **Schedule** - Create Windows Task Scheduler entry (5 min)
6. **Monitor** - Watch first 3 days of execution

**Total Time: ~1.5 hours from zero to production**

---

## Support & Debugging

If collection fails:

1. Run manually: `python my_api_collector.py`
2. Check `execution.log` for error details
3. Review common issues table above
4. Create test script to isolate issue
5. Reference [BEST_PRACTICES_SCHEMA.md](BEST_PRACTICES_SCHEMA.md) for patterns

---

**Template Version:** 1.0  
**Last Updated:** February 28, 2026  
**Reusable for:** Any HTTP-based API data collection
