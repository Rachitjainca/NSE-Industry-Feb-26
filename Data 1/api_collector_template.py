"""
=============================================================================
DATA COLLECTION FRAMEWORK - REUSABLE TEMPLATE
=============================================================================

Purpose: Template for any new API data collection + transformation + cloud sync
Usage: Copy this file, customize CONFIG section, run once to test

Author: Data Engineering Team
Version: 1.0
Last Updated: February 28, 2026

Key Features:
  ✓ Session management with automatic retry
  ✓ Flexible API parameter handling
  ✓ Multi-source data consolidation
  ✓ Automatic Google Sheets upload
  ✓ Comprehensive error handling & logging
  ✓ Data quality validation
  ✓ Execution status tracking

USAGE:
  1. Edit CONFIG section below
  2. Implement fetch_api_data() and parse_api_response()
  3. Run: python api_collector.py
  4. Deploy to Windows Task Scheduler for daily runs

=============================================================================
"""

import json
import csv
import os
import sys
import time
import logging
import requests
import pandas as pd
import argparse
from datetime import datetime
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ═════════════════════════════════════════════════════════════════════════════
# CONFIGURATION - CUSTOMIZE THIS SECTION FOR YOUR API
# ═════════════════════════════════════════════════════════════════════════════

CONFIG = {
    # API Configuration - NSE TBG ENDPOINTS
    "API": {
        "BASE_URL": "https://www.nseindia.com/api/historicalOR/",
        "ENDPOINTS": {
            "cm": "https://www.nseindia.com/api/historicalOR/cm/tbg/daily",
            "fo": "https://www.nseindia.com/api/historicalOR/fo/tbg/daily",
            "comder": "https://www.nseindia.com/api/historicalOR/comder/tbg/daily",
        },
        "TIMEOUT": 15,
        "RETRIES": 5,
        "BACKOFF_FACTOR": 0.5,
        "HEADERS": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://www.nseindia.com/",
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
        }
    },
    
    # Data Sources - List of endpoints/months/segments to fetch
    "DATA_SOURCES": {
        # Example: "SEGMENT_NAME": {names: ["segment"], months: ["Jan", "Feb", ...], year: "2026"}
        "CM": {"names": ["CM"], "months": list("Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()), "year": "26"},
        "FO": {"names": ["FO"], "months": list("Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()), "year": "2026"},
    },
    
    # Execution Mode - Set via command-line: --mode daily or --mode historical
    "EXECUTION": {
        "MODE": "daily",  # Will be overridden by --mode flag
        "HISTORICAL": {
            "START_YEAR": 2025,
            "END_YEAR": 2026,
            "MONTHS": list("Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()),
        }
    },
    
    # Caching
    "CACHE": {
        "ENABLED": True,
        "DIR": ".cache",
        "MAX_AGE_HOURS": 24,
    },
    
    # Output Files
    "OUTPUT": {
        "CSV_FILE": "output_data.csv",
        "BACKUP_DIR": "backups",
        "INCLUDE_TIMESTAMP": True,
    },
    
    # Google Sheets
    "GOOGLE_SHEETS": {
        "ENABLED": True,
        "CREDENTIALS_FILE": "nse-industry-data-88d157be9048.json",
        "SHEET_ID": "1AeHIxoEgLgPiF0s9Sk4AwRZZAbDvqPsRt2NjryTxX-M",
        "WORKSHEET_NAME": "Sheet1",
    },
    
    # Logging
    "LOGGING": {
        "LEVEL": "INFO",
        "FORMAT": "%(asctime)s - %(levelname)s - [%(funcName)s] %(message)s",
        "FILE": "execution.log",
    },
    
    # Validation
    "VALIDATION": {
        "EXPECTED_TRADING_DAYS": 250,
        "MIN_ROWS_THRESHOLD": 220,  # 90% of expected
    }
}

# ═════════════════════════════════════════════════════════════════════════════
# LOGGING SETUP
# ═════════════════════════════════════════════════════════════════════════════

def setup_logging():
    """Configure logging to file and console"""
    log_format = CONFIG["LOGGING"]["FORMAT"]
    log_level = getattr(logging, CONFIG["LOGGING"]["LEVEL"])
    
    logging.basicConfig(
        level=log_level,
        format=log_format,
        handlers=[
            logging.FileHandler(CONFIG["LOGGING"]["FILE"]),
            logging.StreamHandler(sys.stdout)
        ]
    )
    return logging.getLogger(__name__)

logger = setup_logging()

# ═════════════════════════════════════════════════════════════════════════════
# SESSION & CACHE MANAGEMENT
# ═════════════════════════════════════════════════════════════════════════════

class SessionManager:
    """Manage HTTP session with retry strategy"""
    
    @staticmethod
    def create_session():
        """Create session with HTTPAdapter and Retry"""
        session = requests.Session()
        
        retry_strategy = Retry(
            total=CONFIG["API"]["RETRIES"],
            backoff_factor=CONFIG["API"]["BACKOFF_FACTOR"],
            status_forcelist=[500, 502, 503, 504]
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        return session


class APICache:
    """Simple JSON cache management"""
    
    def __init__(self):
        self.cache_dir = CONFIG["CACHE"]["DIR"]
        if CONFIG["CACHE"]["ENABLED"]:
            os.makedirs(self.cache_dir, exist_ok=True)
    
    def get(self, key):
        """Get cached data if fresh"""
        if not CONFIG["CACHE"]["ENABLED"]:
            return None
        
        cache_file = os.path.join(self.cache_dir, f"{key}.json")
        if not os.path.exists(cache_file):
            return None
        
        # Check if cache is still fresh
        age_hours = (time.time() - os.path.getmtime(cache_file)) / 3600
        if age_hours > CONFIG["CACHE"]["MAX_AGE_HOURS"]:
            logger.info(f"Cache expired for {key} ({age_hours:.1f}h old)")
            return None
        
        with open(cache_file) as f:
            return json.load(f).get("data")
    
    def set(self, key, data):
        """Save data to cache"""
        if not CONFIG["CACHE"]["ENABLED"]:
            return
        
        cache_file = os.path.join(self.cache_dir, f"{key}.json")
        with open(cache_file, 'w') as f:
            json.dump({
                "data": data,
                "cached_at": datetime.now().isoformat()
            }, f, indent=2)

# ═════════════════════════════════════════════════════════════════════════════
# API FETCHING - IMPLEMENT THESE FOR YOUR API
# ═════════════════════════════════════════════════════════════════════════════

class DataCollector:
    """Collect data from APIs"""
    
    def __init__(self):
        self.session = SessionManager.create_session()
        self.cache = APICache()
        self.headers = CONFIG["API"]["HEADERS"]
    
    def fetch_api_data(self, segment, month, year):
        """
        CUSTOMIZE THIS: Fetch data from your API
        
        Args:
            segment: Data segment (e.g., "CM", "FO", "COMDER")
            month: Month name (e.g., "Feb")
            year: Year as string (e.g., "2026" or "26")
        
        Returns:
            List of data records or empty list on failure
        """
        
        # Check cache first
        cache_key = f"{segment}_{month}_{year}"
        cached = self.cache.get(cache_key)
        if cached:
            logger.info(f"[CACHE HIT] {segment}/{month}/{year}")
            return cached
        
        try:
            # Get endpoint for segment
            segment_lower = segment.lower()
            if segment_lower in CONFIG["API"]["ENDPOINTS"]:
                url = CONFIG["API"]["ENDPOINTS"][segment_lower]
            else:
                url = CONFIG["API"]["BASE_URL"]
            
            # Handle year format variations
            if segment.lower() in ["fo", "comder"]:
                year_param = year if len(year) == 4 else ("20" + year)
            else:
                year_param = year if len(year) == 2 else year[-2:]
            
            # Build query parameters (NO section parameter needed)
            params = {
                "month": month,
                "year": year_param
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
            
            # CUSTOMIZE: Parse your API response
            records = self.parse_api_response(data, segment)
            
            # Cache if got data
            if records:
                self.cache.set(cache_key, records)
                logger.info(f"✓ {segment}/{month}/{year}: {len(records)} records")
            else:
                logger.warning(f"⚠ {segment}/{month}/{year}: No data returned")
            
            return records
            
        except requests.Timeout:
            logger.error(f"✗ Timeout: {segment}/{month}/{year}")
            return []
        except requests.HTTPError as e:
            logger.error(f"✗ HTTP {response.status_code}: {segment}/{month}/{year}")
            return []
        except Exception as e:
            logger.error(f"✗ Error fetching {segment}/{month}/{year}: {e}")
            return []
    
    def parse_api_response(self, data, segment):
        """
        CUSTOMIZE THIS: Parse your API response into list of records
        
        Args:
            data: JSON response from API
            segment: Data segment (for context-aware parsing)
        
        Returns:
            List of records like [{"field1": value, "field2": value}, ...]
        """
        
        # CUSTOMIZE: Extract records from your API response structure
        # Example for NSE (nested "data" key):
        if not isinstance(data, dict):
            return []
        
        records = data.get("data", [])
        
        if isinstance(records, dict):
            # If API returns single object, wrap in list
            records = [records]
        
        return records if isinstance(records, list) else []
    
    def collect_all_segments(self):
        """Collect all configured segments and months"""
        
        all_records = {}
        
        for segment_name, config in CONFIG["DATA_SOURCES"].items():
            segment_names = config["names"]
            months = config["months"]
            year = config["year"]
            
            segment_data = []
            
            for segment in segment_names:
                for month in months:
                    records = self.fetch_api_data(segment, month, year)
                    segment_data.extend(records)
            
            all_records[segment_name] = segment_data
            logger.info(f"[SUMMARY] {segment_name}: {len(segment_data)} total records")
        
        return all_records
    
    def collect_historical_data(self):
        """
        Collect historical data for all months in configured range
        
        Fetches data for all months from START_YEAR to END_YEAR
        """
        
        all_records = {}
        hist_config = CONFIG["EXECUTION"]["HISTORICAL"]
        
        logger.info(f"[BACKFILLING] Data from {hist_config['START_YEAR']} to {hist_config['END_YEAR']}...")
        
        for segment_name, config in CONFIG["DATA_SOURCES"].items():
            segment_names = config["names"]
            months = hist_config["MONTHS"]
            
            segment_data = []
            
            for year in range(hist_config["START_YEAR"], hist_config["END_YEAR"] + 1):
                # Convert year to appropriate format per segment
                if segment_name.upper() in ["FO", "COMDER"]:
                    year_param = str(year)  # 4-digit: 2025, 2026
                else:
                    year_param = str(year)[-2:]  # 2-digit: 25, 26
                
                logger.info(f"[FETCH] {segment_name}/{year}...")
                
                for segment in segment_names:
                    for month in months:
                        records = self.fetch_api_data(segment, month, year_param)
                        segment_data.extend(records)
                        time.sleep(0.3)  # Rate limiting - 300ms between requests
            
            all_records[segment_name] = segment_data
            logger.info(f"[COMPLETE] {segment_name}: {len(segment_data)} total records collected")
        
        return all_records

# ═════════════════════════════════════════════════════════════════════════════
# DATA PARSING & CONSOLIDATION - CUSTOMIZE IF NEEDED
# ═════════════════════════════════════════════════════════════════════════════

def get_field_value(record, field_names, default=None):
    """Try multiple field names in priority order"""
    for field in field_names:
        if field in record and record[field] is not None:
            return record[field]
    return default


def consolidate_data(all_records):
    """
    CUSTOMIZE THIS: Consolidate multi-segment data into single output
    
    Args:
        all_records: Dict of {segment_name: [records]}
    
    Returns:
        pandas DataFrame with consolidated columns
    """
    
    consolidated = []
    
    # CUSTOMIZE: Build output rows with consolidated data
    # Example: Merge CM, FO, COMDER data by date
    
    # For this template, we'll just flatten all records
    for segment_name, records in all_records.items():
        for record in records:
            row = {"Segment": segment_name}
            # CUSTOMIZE: Extract columns you need
            row.update(record)
            consolidated.append(row)
    
    if not consolidated:
        logger.warning("No data to consolidate")
        return pd.DataFrame()
    
    df = pd.DataFrame(consolidated)
    
    # Parse dates if Date column exists
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"], format="mixed", dayfirst=True, errors="coerce")
        df = df.sort_values("Date")
    
    return df

# ═════════════════════════════════════════════════════════════════════════════
# DATA VALIDATION
# ═════════════════════════════════════════════════════════════════════════════

def validate_data(df):
    """Validate data quality"""
    
    logger.info("\n[VALIDATION] Running data quality checks...")
    
    if df.empty:
        logger.error("❌ DataFrame is empty!")
        return False
    
    # Check row count
    expected = CONFIG["VALIDATION"]["EXPECTED_TRADING_DAYS"]
    min_threshold = CONFIG["VALIDATION"]["MIN_ROWS_THRESHOLD"]
    
    if len(df) < min_threshold:
        logger.warning(f"⚠ Low row count: {len(df)} (expected ~{expected}, min {min_threshold})")
    else:
        logger.info(f"✓ Row count: {len(df)}")
    
    # Check for duplicates
    if df.duplicated().any():
        logger.warning(f"⚠ Found {df.duplicated().sum()} duplicate rows")
    else:
        logger.info("✓ No duplicates")
    
    # Check for nulls
    null_counts = df.isnull().sum()
    if null_counts.any():
        logger.info(f"ℹ Nulls per column:\n{null_counts[null_counts > 0]}")
    
    return True

# ═════════════════════════════════════════════════════════════════════════════
# CSV OUTPUT
# ═════════════════════════════════════════════════════════════════════════════

def export_to_csv(df, output_file):
    """Export DataFrame to CSV"""
    
    if df.empty:
        logger.error("Cannot export empty DataFrame")
        return False
    
    try:
        df.to_csv(
            output_file,
            index=False,
            quotechar='"',
            quoting=csv.QUOTE_ALL,
            encoding='utf-8'
        )
        
        logger.info(f"✓ Exported {len(df)} rows to {output_file}")
        
        # Create backup if timestamp enabled
        if CONFIG["OUTPUT"]["INCLUDE_TIMESTAMP"]:
            backup_dir = CONFIG["OUTPUT"]["BACKUP_DIR"]
            os.makedirs(backup_dir, exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = os.path.join(
                backup_dir,
                f"{os.path.splitext(output_file)[0]}_{timestamp}.csv"
            )
            df.to_csv(backup_file, index=False, quoting=csv.QUOTE_ALL, encoding='utf-8')
            logger.info(f"✓ Backup saved to {backup_file}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to export CSV: {e}")
        return False

# ═════════════════════════════════════════════════════════════════════════════
# GOOGLE SHEETS UPLOAD
# ═════════════════════════════════════════════════════════════════════════════

def upload_to_google_sheets(csv_file):
    """Upload CSV to Google Sheets"""
    
    if not CONFIG["GOOGLE_SHEETS"]["ENABLED"]:
        logger.info("ℹ Google Sheets upload disabled in config")
        return False
    
    try:
        from google.oauth2.service_account import Credentials
        import gspread
        
        creds_file = CONFIG["GOOGLE_SHEETS"]["CREDENTIALS_FILE"]
        
        if not os.path.exists(creds_file):
            logger.error(f"❌ Credentials not found: {creds_file}")
            logger.info("To enable upload:")
            logger.info("  1. Download credentials from Google Cloud Console")
            logger.info("  2. Place in: " + os.path.abspath(creds_file))
            return False
        
        # Read CSV
        with open(csv_file) as f:
            data = list(csv.reader(f))
        
        if not data:
            logger.error("CSV is empty")
            return False
        
        # Authenticate
        SCOPES = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        creds = Credentials.from_service_account_file(creds_file, scopes=SCOPES)
        gc = gspread.authorize(creds)
        
        # Open sheet
        sheet_id = CONFIG["GOOGLE_SHEETS"]["SHEET_ID"]
        sh = gc.open_by_key(sheet_id)
        
        try:
            ws = sh.worksheet(CONFIG["GOOGLE_SHEETS"]["WORKSHEET_NAME"])
        except gspread.exceptions.WorksheetNotFound:
            ws = sh.sheet1
        
        # Upload
        ws.clear()
        ws.update(range_name="A1", values=data)
        
        logger.info(f"✓ Uploaded {len(data)-1} rows to Google Sheet '{sh.title}/'{ws.title}'")
        return True
        
    except ImportError:
        logger.error("❌ gspread not installed. Install: pip install gspread google-auth-oauthlib")
        return False
    except Exception as e:
        logger.error(f"❌ Google Sheets upload failed: {e}")
        return False

# ═════════════════════════════════════════════════════════════════════════════
# STATUS TRACKING
# ═════════════════════════════════════════════════════════════════════════════

def log_execution_status(status, duration_seconds, row_count=0):
    """Log execution status for monitoring"""
    
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "status": status,  # "success" or "failed"
        "duration_seconds": duration_seconds,
        "rows_processed": row_count
    }
    
    log_file = "execution_log.jsonl"
    with open(log_file, "a") as f:
        f.write(json.dumps(log_entry) + "\n")
    
    return 0 if status == "success" else 1

# ═════════════════════════════════════════════════════════════════════════════
# MAIN EXECUTION
# ═════════════════════════════════════════════════════════════════════════════

def main():
    """
    Main execution flow
    
    Usage:
        python api_collector.py              # Daily mode (current day only)
        python api_collector.py --mode daily # Same as above
        python api_collector.py --mode historical  # Backfill all 2025-2026 data
    """
    
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Data Collection Pipeline")
    parser.add_argument(
        "--mode",
        choices=["daily", "historical"],
        default="daily",
        help="Execution mode: 'daily' (current day only) or 'historical' (backfill all months)"
    )
    args = parser.parse_args()
    CONFIG["EXECUTION"]["MODE"] = args.mode
    
    start_time = time.time()
    
    try:
        logger.info("=" * 80)
        logger.info(f"DATA COLLECTION STARTED [MODE: {args.mode.upper()}]")
        logger.info("=" * 80)
        
        # Step 1: Collect data
        logger.info("\n[STEP 1] Collecting data from APIs...")
        collector = DataCollector()
        
        if CONFIG["EXECUTION"]["MODE"] == "historical":
            logger.info("[HISTORICAL MODE] Collecting all months from 2025-2026...")
            all_records = collector.collect_historical_data()
        else:
            logger.info("[DAILY MODE] Collecting current day's data...")
            all_records = collector.collect_all_segments()
        
        # Step 2: Consolidate
        logger.info("\n[STEP 2] Consolidating data...")
        df = consolidate_data(all_records)
        
        if df.empty:
            logger.error("No data collected. Exiting.")
            duration = time.time() - start_time
            log_execution_status("failed", duration, 0)
            return 1
        
        # Step 3: Validate
        logger.info("\n[STEP 3] Validating data...")
        validate_data(df)
        
        # Step 4: Export to CSV
        logger.info("\n[STEP 4] Exporting to CSV...")
        output_file = CONFIG["OUTPUT"]["CSV_FILE"]
        if not export_to_csv(df, output_file):
            duration = time.time() - start_time
            log_execution_status("failed", duration, len(df))
            return 1
        
        # Step 5: Upload to Google Sheets
        logger.info("\n[STEP 5] Uploading to Google Sheets...")
        upload_to_google_sheets(output_file)
        
        # Success
        duration = time.time() - start_time
        logger.info("\n" + "=" * 80)
        logger.info(f"✓ COLLECTION COMPLETE ({duration:.1f}s)")
        logger.info(f"  Rows: {len(df)}")
        logger.info(f"  File: {output_file}")
        logger.info("=" * 80 + "\n")
        
        log_execution_status("success", duration, len(df))
        return 0
        
    except Exception as e:
        logger.error(f"\n❌ FATAL ERROR: {e}", exc_info=True)
        duration = time.time() - start_time
        log_execution_status("failed", duration, 0)
        return 1


if __name__ == "__main__":
    exit_code = main()
    exit(exit_code)
