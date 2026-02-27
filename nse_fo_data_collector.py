"""
NSE FO Market Data Collector
Fetches and aggregates daily FO market metrics with caching and error handling
"""

import os
import sys
import json
import csv
import zipfile
import requests
from datetime import datetime, timedelta
from pathlib import Path
import time
import logging
from typing import Dict, Optional

# ---------------------------------------------------------------------------
# Logging -- UTF-8 safe on Windows cp1252 terminals
# ---------------------------------------------------------------------------
_file_handler   = logging.FileHandler('nse_fo_collector.log', encoding='utf-8')
_stream_handler = logging.StreamHandler(
    stream=open(sys.stdout.fileno(), mode='w', encoding='utf-8',
                buffering=1, closefd=False)
)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[_file_handler, _stream_handler],
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
START_DATE   = datetime(2025, 2, 1)
CURRENT_DATE = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

BASE_URL     = "https://nsearchives.nseindia.com/archives/fo/mkt/"
NSE_HOME     = "https://www.nseindia.com"
CACHE_FILE   = "nse_fo_cache.json"
OUTPUT_FILE  = "nse_fo_aggregated_data.csv"
TEMP_DIR     = "temp_nse_downloads"

REQUEST_TIMEOUT = 30   # seconds per attempt
RETRY_ATTEMPTS  = 4
RETRY_DELAY     = 5    # base seconds (exponential back-off applied)
SESSION_REFRESH = 20   # refresh cookies every N downloads

# Browser-like headers -- NSE blocks plain requests without these
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection":      "keep-alive",
    "Referer":         "https://www.nseindia.com",
}

# NSE Trading Holidays 2025-2026  (DDMMYYYY)
NSE_HOLIDAYS = {
    "26012025",  # Republic Day
    "24022025",  # Mahashivratri
    "10032025",  # Holi
    "21032025",  # Good Friday
    "08042025",  # Mahavir Jayanti
    "10042025",  # Dr Ambedkar Jayanti
    "14042025",  # Ram Navami (observed)
    "21042025",  # Ramzan Id
    "08052025",  # Buddha Pournima
    "15082025",  # Independence Day
    "29082025",  # Janmashtami
    "02102025",  # Gandhi Jayanti
    "24102025",  # Dussehra
    "31102025",  # Diwali Laxmi Puja
    "01112025",  # Diwali Balipratipada
    "05112025",  # Guru Nanak Jayanti
    "25122025",  # Christmas
    "26012026",  # Republic Day
    "17022026",  # Mahashivratri
}


class NSEDataCollector:
    def __init__(self):
        self.cache                    = self._load_cache()
        self._downloads_since_refresh = 0
        self.session                  = self._new_session()
        Path(TEMP_DIR).mkdir(exist_ok=True)

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------
    def _new_session(self) -> requests.Session:
        """Create a session pre-seeded with NSE homepage cookies."""
        s = requests.Session()
        s.headers.update(HEADERS)
        try:
            logger.info("Seeding session cookies from NSE homepage ...")
            r = s.get(NSE_HOME, timeout=20)
            logger.info(
                f"Homepage: HTTP {r.status_code} | "
                f"Cookies: {list(s.cookies.keys())}"
            )
            time.sleep(1)
        except Exception as exc:
            logger.warning(f"Could not seed cookies: {exc}")
        return s

    def _maybe_refresh_session(self):
        self._downloads_since_refresh += 1
        if self._downloads_since_refresh >= SESSION_REFRESH:
            logger.info("Periodic session refresh ...")
            self.session = self._new_session()
            self._downloads_since_refresh = 0
        
    def _load_cache(self) -> Dict:
        """Load cached data if it exists"""
        if os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE, 'r') as f:
                    logger.info(f"Loaded cache from {CACHE_FILE}")
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load cache: {e}")
                return {}
        return {}
    
    def _save_cache(self):
        """Save cache to file"""
        try:
            with open(CACHE_FILE, 'w') as f:
                json.dump(self.cache, f, indent=2)
                logger.info(f"Cache saved with {len(self.cache)} entries")
        except Exception as e:
            logger.error(f"Failed to save cache: {e}")
    
    def _is_trading_day(self, date: datetime) -> bool:
        """Check if date is a trading day (not weekend or holiday)"""
        # Check if weekend (5=Saturday, 6=Sunday)
        if date.weekday() >= 5:
            return False
        
        # Check if holiday
        date_str = date.strftime("%d%m%Y")
        if date_str in NSE_HOLIDAYS:
            return False
        
        return True
    
    @staticmethod
    def _zip_name(date: datetime) -> str:
        return f"fo{date.strftime('%d%m%Y')}.zip"

    @staticmethod
    def _op_csv_name(date: datetime) -> str:
        """Name of the options CSV file inside the zip."""
        return f"op{date.strftime('%d%m%Y')}.csv"

    def _download_file(self, date: datetime) -> Optional[str]:
        """Download NSE FO zip file using browser-like session with retry/back-off."""
        filename = self._zip_name(date)
        url      = BASE_URL + filename
        filepath = os.path.join(TEMP_DIR, filename)

        self._maybe_refresh_session()

        for attempt in range(1, RETRY_ATTEMPTS + 1):
            try:
                logger.info(f"  GET {filename} (attempt {attempt}/{RETRY_ATTEMPTS}) ...")
                resp = self.session.get(url, timeout=REQUEST_TIMEOUT, stream=True)

                if resp.status_code == 200:
                    with open(filepath, 'wb') as fh:
                        for chunk in resp.iter_content(chunk_size=65536):
                            if chunk:
                                fh.write(chunk)
                    logger.info(f"  Downloaded {filename} -- OK")
                    return filepath

                elif resp.status_code == 403:
                    logger.warning(f"  HTTP 403 for {filename} -- refreshing session")
                    if attempt < RETRY_ATTEMPTS:
                        self.session = self._new_session()
                    else:
                        return None

                elif resp.status_code == 404:
                    logger.debug(f"  HTTP 404 for {filename} -- file not on server")
                    return None

                else:
                    logger.warning(f"  HTTP {resp.status_code} for {filename}")

            except requests.exceptions.Timeout:
                logger.warning(f"  Timeout on {filename} (attempt {attempt})")

            except requests.exceptions.ConnectionError as exc:
                logger.warning(f"  Connection error on {filename}: {exc} (attempt {attempt})")
                if attempt < RETRY_ATTEMPTS:
                    logger.info("  Refreshing session after connection error ...")
                    self.session = self._new_session()

            except Exception as exc:
                logger.error(f"  Unexpected error {filename}: {exc}")
                break

            if attempt < RETRY_ATTEMPTS:
                wait = RETRY_DELAY * attempt   # 5 s, 10 s, 15 s back-off
                logger.info(f"  Retrying in {wait}s ...")
                time.sleep(wait)

        return None
    
    def _extract_and_parse(self, filepath: str, date: datetime) -> Optional[Dict]:
        """Extract zip, find op<date>.csv, and parse it."""
        op_target = self._op_csv_name(date)
        try:
            with zipfile.ZipFile(filepath, 'r') as zf:
                names = zf.namelist()
                logger.debug(f"Files in zip: {names}")

                # Prefer exact op<date>.csv; fall back to any file starting with 'op'
                if op_target in names:
                    chosen = op_target
                else:
                    op_candidates = [n for n in names
                                     if n.lower().startswith('op') and n.endswith('.csv')]
                    if not op_candidates:
                        logger.warning(f"No op*.csv found in {filepath}")
                        return None
                    chosen = op_candidates[0]

                logger.debug(f"Parsing {chosen}")
                with zf.open(chosen) as fh:
                    return self._parse_csv(fh)
        except zipfile.BadZipFile:
            logger.error(f"Bad zip: {filepath}")
        except Exception as exc:
            logger.error(f"Extraction error {filepath}: {exc}")
        return None

    def _parse_csv(self, csv_file) -> Optional[Dict]:
        """
        Parse op<date>.csv and sum the four target columns.

        The file header (line 0) looks like:
        INSTRUMENT,SYMBOL    ,EXP_DATE  ,...,NO_OF_CONT       ,NO_OF_TRADE      ,NOTION_VAL        ,PR_VAL
        Column names have trailing whitespace -- we strip them.
        """
        TARGET_COLS = {
            'NO_OF_CONT':  'NO_OF_CONT',
            'NO_OF_TRADE': 'NO_OF_TRADE',
            'NOTION_VAL':  'NOTION_VAL',
            'PR_VAL':      'PR_VAL',
        }
        try:
            raw   = csv_file.read()
            text  = raw.decode('utf-8', errors='ignore')
            lines = [l for l in text.splitlines() if l.strip()]
            if not lines:
                logger.warning("  Empty CSV")
                return None

            # Build normalised header -> original header mapping
            first_line_cols = next(csv.reader([lines[0]]))
            # Strip whitespace from all column names
            stripped_headers = [h.strip() for h in first_line_cols]

            # Check which target columns are present
            col_index: Dict[str, int] = {}   # canonical -> index in row
            for i, hdr in enumerate(stripped_headers):
                if hdr in TARGET_COLS:
                    col_index[hdr] = i
            logger.debug(f"  Found target columns at indices: {col_index}")

            if not col_index:
                logger.warning(f"  None of the 4 target columns found. Headers: {stripped_headers}")
                return None

            sums      = {k: 0.0 for k in TARGET_COLS}
            row_count = 0

            # Skip header row (index 0), iterate data rows
            data_reader = csv.reader(lines[1:])
            for row in data_reader:
                if not row:
                    continue
                for canon, idx in col_index.items():
                    if idx < len(row):
                        raw_val = (row[idx] or '').strip().replace(',', '')
                        if raw_val:
                            try:
                                sums[canon] += float(raw_val)
                            except ValueError:
                                pass
                row_count += 1

            if row_count:
                logger.info(f"  Parsed {row_count} rows")
                return sums
            logger.warning("  No data rows found in CSV")
            return None
        except Exception as exc:
            logger.error(f"CSV parse error: {exc}")
            return None
    
    def _cleanup(self, filepath: str):
        """Remove temporary download file."""
        try:
            if filepath and os.path.exists(filepath):
                os.remove(filepath)
        except Exception:
            pass
    
    def fetch_and_aggregate(self):
        """Main method to fetch data and aggregate"""
        current_date = START_DATE
        dates_processed = 0
        dates_skipped = 0
        dates_failed = 0
        
        logger.info(f"Starting data collection from {START_DATE.date()} to {CURRENT_DATE.date()}")
        
        while current_date <= CURRENT_DATE:
            date_str = current_date.strftime("%d%m%Y")
            
            # Skip if already cached
            if date_str in self.cache:
                logger.info(f"Skipping {date_str} (already cached)")
                current_date += timedelta(days=1)
                continue
            
            # Skip non-trading days
            if not self._is_trading_day(current_date):
                logger.info(f"Skipping {date_str} (weekend/holiday)")
                dates_skipped += 1
                current_date += timedelta(days=1)
                continue
            
            # Download and process
            logger.info(f"[{date_str}] Processing ...")
            filepath = self._download_file(current_date)
            data = None

            if filepath:
                data = self._extract_and_parse(filepath, current_date)
                self._cleanup(filepath)

            if data:
                self.cache[date_str] = data
                dates_processed += 1
                logger.info(
                    f"  [OK]   {date_str}: "
                    f"CONT={data['NO_OF_CONT']:.0f}  "
                    f"TRADE={data['NO_OF_TRADE']:.0f}  "
                    f"NOTION_VAL={data['NOTION_VAL']:.2f}  "
                    f"PR_VAL={data['PR_VAL']:.2f}"
                )
            else:
                dates_failed += 1
                logger.error(f"  [FAIL] {date_str}: could not fetch/parse")

            current_date += timedelta(days=1)

        self._save_cache()
        self._write_output()

        logger.info(
            "\n--- Run Summary ---\n"
            f"  Newly fetched       : {dates_processed}\n"
            f"  Skipped (wknd/hol) : {dates_skipped}\n"
            f"  Failed              : {dates_failed}\n"
            f"  Total in cache      : {len(self.cache)}"
        )
    
    def _write_output(self):
        """Write aggregated data to CSV output file"""
        try:
            with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                
                # Write header
                writer.writerow(['Date', 'NO_OF_CONT', 'NO_OF_TRADE', 'NOTION_VAL', 'PR_VAL'])
                
                # Write data sorted chronologically (parse DDMMYYYY for correct order)
                for date_str in sorted(self.cache.keys(),
                                       key=lambda s: datetime.strptime(s, "%d%m%Y")):
                    data = self.cache[date_str]
                    writer.writerow([
                        datetime.strptime(date_str, "%d%m%Y").strftime("%d-%m-%Y"),
                        f"{data['NO_OF_CONT']:.2f}",
                        f"{data['NO_OF_TRADE']:.2f}",
                        f"{data['NOTION_VAL']:.2f}",
                        f"{data['PR_VAL']:.2f}"
                    ])
            
            logger.info(f"Output written to {OUTPUT_FILE}")
        except Exception as e:
            logger.error(f"Failed to write output: {e}")


def main():
    """Main entry point"""
    logger.info("="*60)
    logger.info("NSE FO Market Data Collector")
    logger.info("="*60)
    
    try:
        collector = NSEDataCollector()
        collector.fetch_and_aggregate()
        logger.info("Collection completed successfully")
    except KeyboardInterrupt:
        logger.info("Collection interrupted by user")
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)


if __name__ == "__main__":
    main()
