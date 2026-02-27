"""
NSE + BSE FO Market Data Collector  (Combined)
==================================================
Fetches and aggregates daily Futures & Options metrics from NSE and BSE.
Results are written to a single output CSV with 9 columns.

NSE source:  https://nsearchives.nseindia.com/archives/fo/mkt/fo<DDMMYYYY>.zip
             File inside zip: op<DDMMYYYY>.csv
             Columns: NO_OF_CONT, NO_OF_TRADE, NOTION_VAL, PR_VAL

BSE source:  https://www.bseindia.com/download/Bhavcopy/Derivative/MS_<YYYYMMDD>-01.csv
             Columns (by index): 15=Total Traded Quantity,
                                 16=Total Traded Value (in Thousands)(absolute),
                                 17=Average Traded Price,
                                 18=No. of Trades

Output file: nse_fo_aggregated_data.csv
Columns:
  Date | NSE_NO_OF_CONT | NSE_NO_OF_TRADE | NSE_NOTION_VAL | NSE_PR_VAL |
  BSE_TTL_TRADED_QTY | BSE_TTL_TRADED_VAL | BSE_AVG_TRADED_PRICE | BSE_NO_OF_TRADES
"""

import os
import sys
import io
import json
import csv
import zipfile
import requests
import xlrd
from datetime import datetime, timedelta
from pathlib import Path
import time
import logging
from typing import Dict, Optional

# ---------------------------------------------------------------------------
# Logging — UTF-8 safe on Windows cp1252 terminals
# ---------------------------------------------------------------------------
_file_handler = logging.FileHandler('nse_bse_combined.log', encoding='utf-8')
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
# Common configuration
# ---------------------------------------------------------------------------
START_DATE   = datetime(2025, 2, 1)
CURRENT_DATE = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
OUTPUT_FILE  = "nse_fo_aggregated_data.csv"

REQUEST_TIMEOUT = 30
RETRY_ATTEMPTS  = 4
RETRY_DELAY     = 5    # base seconds; multiplied per attempt (5, 10, 15 s)
SESSION_REFRESH = 20   # re-seed cookies every N downloads

# ---------------------------------------------------------------------------
# NSE configuration
# ---------------------------------------------------------------------------
NSE_BASE_URL   = "https://nsearchives.nseindia.com/archives/fo/mkt/"
NSE_HOME       = "https://www.nseindia.com"
NSE_CACHE_FILE = "nse_fo_cache.json"
NSE_TEMP_DIR   = "temp_nse_downloads"

NSE_HEADERS = {
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

# ---------------------------------------------------------------------------
# BSE configuration
# ---------------------------------------------------------------------------
BSE_BASE_URL   = "https://www.bseindia.com/download/Bhavcopy/Derivative/"
BSE_HOME       = "https://www.bseindia.com"
BSE_CACHE_FILE = "bse_fo_cache.json"

BSE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection":      "keep-alive",
    "Referer":         "https://www.bseindia.com/markets/Derivatives/DerivativesHome.aspx",
}

# BSE Target column indices in MS_<date>-01.csv (0-based)
BSE_COL_TTL_QTY   = 15   # Total Traded Quantity
BSE_COL_TTL_VAL   = 16   # Total Traded Value (in Thousands)(absolute)
BSE_COL_AVG_PRICE = 17   # Average Traded Price
BSE_COL_NO_TRADES = 18   # No. of Trades

# ---------------------------------------------------------------------------
# NSE Category Turnover — FO configuration
# ---------------------------------------------------------------------------
NSE_CAT_BASE_URL   = "https://nsearchives.nseindia.com/archives/fo/cat/"
NSE_CAT_CACHE_FILE = "nse_cat_cache.json"
NSE_CAT_TEMP_DIR   = "temp_nse_downloads"  # reuse same temp dir

# ---------------------------------------------------------------------------
# NSE Category Turnover — Equity configuration
# ---------------------------------------------------------------------------
NSE_EQ_CAT_BASE_URL   = "https://nsearchives.nseindia.com/archives/equities/cat/"
NSE_EQ_CAT_CACHE_FILE = "nse_eq_cat_cache.json"

# ---------------------------------------------------------------------------
# NSE Margin Trading configuration
# ---------------------------------------------------------------------------
NSE_MRG_BASE_URL   = "https://nsearchives.nseindia.com/content/equities/"
NSE_MRG_CACHE_FILE = "nse_mrg_cache.json"

# ---------------------------------------------------------------------------
# BSE Holidays 2025-2026 (DDMMYYYY) — largely mirrors NSE; add/remove as needed
BSE_HOLIDAYS = {
    "26012025",  # Republic Day
    "24022025",  # Mahashivratri
    "10032025",  # Holi
    "21032025",  # Good Friday
    "08042025",  # Mahavir Jayanti
    "10042025",  # Dr Ambedkar Jayanti
    "14042025",  # Ram Navami (observed)
    "21042025",  # Ramzan Id
    "01052025",  # Maharashtra Day (BSE extra holiday)
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


# ===========================================================================
# NSE Margin Trading Collector
# ===========================================================================
class NSEMrgCollector:
    """
    Downloads mrg_trading_DDMMYY.zip from NSE archives.
    Parses the CSV inside and extracts the 4 aggregate metrics (Rs. Lakhs):
      1. Scripwise Total Outstanding on the beginning of the day
      2. Fresh Exposure taken during the day
      3. Exposure liquidated during the day
      4. Net scripwise outstanding at the end of the day
    Cache key = DDMMYYYY (8-digit).
    """

    def __init__(self):
        self.cache                     = self._load_cache()
        self._downloads_since_refresh  = 0
        self.session                   = self._new_session()
        Path(NSE_TEMP_DIR).mkdir(exist_ok=True)

    def _new_session(self) -> requests.Session:
        s = requests.Session()
        s.headers.update(NSE_HEADERS)
        try:
            logger.info("[MRG] Seeding session cookies from NSE homepage ...")
            r = s.get(NSE_HOME, timeout=20)
            logger.info(f"[MRG] Homepage: HTTP {r.status_code} | Cookies: {list(s.cookies.keys())}")
            time.sleep(1)
        except Exception as exc:
            logger.warning(f"[MRG] Could not seed cookies: {exc}")
        return s

    def _maybe_refresh_session(self):
        self._downloads_since_refresh += 1
        if self._downloads_since_refresh >= SESSION_REFRESH:
            logger.info("[MRG] Periodic session refresh ...")
            self.session = self._new_session()
            self._downloads_since_refresh = 0

    def _load_cache(self) -> Dict:
        if os.path.exists(NSE_MRG_CACHE_FILE):
            try:
                with open(NSE_MRG_CACHE_FILE, 'r') as f:
                    data = json.load(f)
                    logger.info(f"[MRG] Loaded {len(data)} cached entries from {NSE_MRG_CACHE_FILE}")
                    return data
            except Exception as e:
                logger.warning(f"[MRG] Failed to load cache: {e}")
        return {}

    def _save_cache(self):
        try:
            with open(NSE_MRG_CACHE_FILE, 'w') as f:
                json.dump(self.cache, f, indent=2)
            logger.info(f"[MRG] Cache saved: {len(self.cache)} entries")
        except Exception as e:
            logger.error(f"[MRG] Failed to save cache: {e}")

    def _is_trading_day(self, date: datetime) -> bool:
        if date.weekday() >= 5:
            return False
        return date.strftime("%d%m%Y") not in NSE_HOLIDAYS

    @staticmethod
    def _zip_filename(date: datetime) -> str:
        """URL uses 6-digit DDMMYY, e.g. mrg_trading_250226.zip"""
        return "mrg_trading_" + date.strftime("%d%m%y") + ".zip"

    def _download_and_parse(self, date: datetime) -> Optional[Dict]:
        filename = self._zip_filename(date)
        url      = NSE_MRG_BASE_URL + filename

        self._maybe_refresh_session()

        for attempt in range(1, RETRY_ATTEMPTS + 1):
            try:
                logger.info(f"[MRG]   GET {filename} (attempt {attempt}/{RETRY_ATTEMPTS}) ...")
                resp = self.session.get(url, timeout=REQUEST_TIMEOUT)

                if resp.status_code == 200:
                    if resp.content[:2] != b'PK':
                        logger.warning(f"[MRG]   {filename} did not return ZIP binary")
                        return None
                    logger.info(f"[MRG]   Downloaded {filename} -- OK ({len(resp.content)} bytes)")
                    return self._parse_zip(resp.content)

                elif resp.status_code == 403:
                    logger.warning(f"[MRG]   HTTP 403 -- refreshing session")
                    if attempt < RETRY_ATTEMPTS:
                        self.session = self._new_session()
                    else:
                        return None

                elif resp.status_code == 404:
                    logger.debug(f"[MRG]   HTTP 404 -- file not on server for {filename}")
                    return None

                else:
                    logger.warning(f"[MRG]   HTTP {resp.status_code}")

            except requests.exceptions.Timeout:
                logger.warning(f"[MRG]   Timeout (attempt {attempt})")
            except requests.exceptions.ConnectionError as exc:
                logger.warning(f"[MRG]   Connection error: {exc} (attempt {attempt})")
                if attempt < RETRY_ATTEMPTS:
                    self.session = self._new_session()
            except Exception as exc:
                logger.error(f"[MRG]   Unexpected error: {exc}")
                break

            if attempt < RETRY_ATTEMPTS:
                wait = RETRY_DELAY * attempt
                logger.info(f"[MRG]   Retrying in {wait}s ...")
                time.sleep(wait)

        return None

    @staticmethod
    def _parse_zip(raw_bytes: bytes) -> Optional[Dict]:
        """
        Parse the mrg_trading zip — CSV inside has rows like:
          1,Scripwise Total Outstanding on the beginning of the day,<value>,
          2,Fresh Exposure taken during the day,<value>,
          3,Exposure liquidated during the day,<value>,
          4,Net scripwise outstanding at the end of the day,<value>,
        Values are in Rs. Lakhs.
        Older files have an extra leading blank column (Sr.No. at col[1], value at col[3]).
        """
        try:
            with zipfile.ZipFile(io.BytesIO(raw_bytes)) as zf:
                csv_name = next(n for n in zf.namelist() if n.lower().endswith('.csv'))
                content  = zf.read(csv_name).decode('utf-8', errors='replace')

            metrics = {
                'MRG_OUTSTANDING_BOD_LAKHS': None,
                'MRG_FRESH_EXP_LAKHS':       None,
                'MRG_EXP_LIQ_LAKHS':         None,
                'MRG_NET_EOD_LAKHS':         None,
            }
            sr_to_key = {
                '1': 'MRG_OUTSTANDING_BOD_LAKHS',
                '2': 'MRG_FRESH_EXP_LAKHS',
                '3': 'MRG_EXP_LIQ_LAKHS',
                '4': 'MRG_NET_EOD_LAKHS',
            }

            reader = csv.reader(content.splitlines())
            for row in reader:
                if not row:
                    continue
                # Check col[0] (new format) or col[1] (old format with leading blank)
                for sr_col, val_col in ((0, 2), (1, 3)):
                    sr = row[sr_col].strip() if sr_col < len(row) else ''
                    if sr in sr_to_key and val_col < len(row):
                        key = sr_to_key[sr]
                        if metrics[key] is None:   # take first occurrence (reporting date)
                            try:
                                metrics[key] = float(str(row[val_col]).strip().replace(',', ''))
                            except (ValueError, IndexError):
                                pass
                        break

            found = {k: v for k, v in metrics.items() if v is not None}
            if len(found) < 4:
                logger.warning(f"[MRG]   Only {len(found)}/4 metrics found")
                return None if not found else found

            logger.info(
                f"[MRG]   BOD={found['MRG_OUTSTANDING_BOD_LAKHS']:.2f}  "
                f"Fresh={found['MRG_FRESH_EXP_LAKHS']:.2f}  "
                f"Liq={found['MRG_EXP_LIQ_LAKHS']:.2f}  "
                f"EOD={found['MRG_NET_EOD_LAKHS']:.2f}  (Rs.Lakhs)"
            )
            return found

        except Exception as exc:
            logger.error(f"[MRG] Parse error: {exc}")
            return None

    def collect(self):
        processed = skipped = failed = 0
        current   = START_DATE

        logger.info(f"[MRG] Collecting from {START_DATE.date()} to {CURRENT_DATE.date()}")

        while current <= CURRENT_DATE:
            date_str = current.strftime("%d%m%Y")

            if date_str in self.cache:
                current += timedelta(days=1)
                continue

            if not self._is_trading_day(current):
                logger.info(f"[MRG] Skipping {date_str} (weekend/holiday)")
                skipped += 1
                current += timedelta(days=1)
                continue

            logger.info(f"[MRG] Processing {date_str} ...")
            data = self._download_and_parse(current)

            if data:
                self.cache[date_str] = data
                processed += 1
                logger.info(f"[MRG]   [OK]  {date_str}")
            else:
                failed += 1
                logger.error(f"[MRG]   [FAIL] {date_str}")

            current += timedelta(days=1)

        self._save_cache()
        logger.info(
            f"[MRG] Done — fetched={processed}, skipped={skipped}, "
            f"failed={failed}, total_cached={len(self.cache)}"
        )


# ===========================================================================
# NSE Category Turnover Collector
# ===========================================================================
class NSECatCollector:
    """
    Downloads fo_cat_turnover_DDMMYY.xls from NSE archives.
    Extracts Buy Value and Sell Value (Rs.Crores) for the 'Retail' category,
    and computes their average. Cache key = DDMMYYYY (8-digit, consistent with others).
    """

    def __init__(self):
        self.cache                     = self._load_cache()
        self._downloads_since_refresh  = 0
        self.session                   = self._new_session()
        Path(NSE_CAT_TEMP_DIR).mkdir(exist_ok=True)

    def _new_session(self) -> requests.Session:
        s = requests.Session()
        s.headers.update(NSE_HEADERS)
        try:
            logger.info("[CAT] Seeding session cookies from NSE homepage ...")
            r = s.get(NSE_HOME, timeout=20)
            logger.info(f"[CAT] Homepage: HTTP {r.status_code} | Cookies: {list(s.cookies.keys())}")
            time.sleep(1)
        except Exception as exc:
            logger.warning(f"[CAT] Could not seed cookies: {exc}")
        return s

    def _maybe_refresh_session(self):
        self._downloads_since_refresh += 1
        if self._downloads_since_refresh >= SESSION_REFRESH:
            logger.info("[CAT] Periodic session refresh ...")
            self.session = self._new_session()
            self._downloads_since_refresh = 0

    def _load_cache(self) -> Dict:
        if os.path.exists(NSE_CAT_CACHE_FILE):
            try:
                with open(NSE_CAT_CACHE_FILE, 'r') as f:
                    data = json.load(f)
                    logger.info(f"[CAT] Loaded {len(data)} cached entries from {NSE_CAT_CACHE_FILE}")
                    return data
            except Exception as e:
                logger.warning(f"[CAT] Failed to load cache: {e}")
        return {}

    def _save_cache(self):
        try:
            with open(NSE_CAT_CACHE_FILE, 'w') as f:
                json.dump(self.cache, f, indent=2)
            logger.info(f"[CAT] Cache saved: {len(self.cache)} entries")
        except Exception as e:
            logger.error(f"[CAT] Failed to save cache: {e}")

    def _is_trading_day(self, date: datetime) -> bool:
        if date.weekday() >= 5:
            return False
        return date.strftime("%d%m%Y") not in NSE_HOLIDAYS

    @staticmethod
    def _xls_filename(date: datetime) -> str:
        """URL uses 6-digit DDMMYY, e.g. fo_cat_turnover_270226.xls"""
        return "fo_cat_turnover_" + date.strftime("%d%m%y") + ".xls"

    def _download_and_parse(self, date: datetime) -> Optional[Dict]:
        filename = self._xls_filename(date)
        url      = NSE_CAT_BASE_URL + filename

        self._maybe_refresh_session()

        for attempt in range(1, RETRY_ATTEMPTS + 1):
            try:
                logger.info(f"[CAT]   GET {filename} (attempt {attempt}/{RETRY_ATTEMPTS}) ...")
                resp = self.session.get(url, timeout=REQUEST_TIMEOUT)

                if resp.status_code == 200:
                    # Verify it is actually an XLS binary
                    if resp.content[:2] != b'\xd0\xcf':
                        logger.warning(f"[CAT]   {filename} did not return XLS binary")
                        return None
                    logger.info(f"[CAT]   Downloaded {filename} -- OK ({len(resp.content)} bytes)")
                    return self._parse_xls(resp.content)

                elif resp.status_code == 403:
                    logger.warning(f"[CAT]   HTTP 403 -- refreshing session")
                    if attempt < RETRY_ATTEMPTS:
                        self.session = self._new_session()
                    else:
                        return None

                elif resp.status_code == 404:
                    logger.debug(f"[CAT]   HTTP 404 -- file not on server for {filename}")
                    return None

                else:
                    logger.warning(f"[CAT]   HTTP {resp.status_code}")

            except requests.exceptions.Timeout:
                logger.warning(f"[CAT]   Timeout (attempt {attempt})")
            except requests.exceptions.ConnectionError as exc:
                logger.warning(f"[CAT]   Connection error: {exc} (attempt {attempt})")
                if attempt < RETRY_ATTEMPTS:
                    self.session = self._new_session()
            except Exception as exc:
                logger.error(f"[CAT]   Unexpected error: {exc}")
                break

            if attempt < RETRY_ATTEMPTS:
                wait = RETRY_DELAY * attempt
                logger.info(f"[CAT]   Retrying in {wait}s ...")
                time.sleep(wait)

        return None

    @staticmethod
    def _parse_xls(raw_bytes: bytes) -> Optional[Dict]:
        """
        Parse the XLS file and find the 'Retail' row.
        Returns dict with keys: RETAIL_BUY_CR, RETAIL_SELL_CR, RETAIL_AVG_CR
        """
        try:
            wb = xlrd.open_workbook(file_contents=raw_bytes)
            sh = wb.sheets()[0]  # always first sheet

            buy_val  = None
            sell_val = None

            for row_idx in range(sh.nrows):
                category = str(sh.cell_value(row_idx, 1)).strip()
                if category.lower() == 'retail':
                    try:
                        buy_val  = float(sh.cell_value(row_idx, 2))
                        sell_val = float(sh.cell_value(row_idx, 3))
                    except (ValueError, TypeError):
                        pass
                    break

            if buy_val is None or sell_val is None:
                logger.warning("[CAT]   'Retail' row not found in XLS")
                return None

            avg_val = (buy_val + sell_val) / 2.0
            logger.info(f"[CAT]   Retail — Buy={buy_val:.2f}  Sell={sell_val:.2f}  Avg={avg_val:.2f} (Rs.Cr)")
            return {
                'RETAIL_BUY_CR':  buy_val,
                'RETAIL_SELL_CR': sell_val,
                'RETAIL_AVG_CR':  avg_val,
            }
        except Exception as exc:
            logger.error(f"[CAT] XLS parse error: {exc}")
            return None

    def collect(self):
        processed = skipped = failed = 0
        current   = START_DATE

        logger.info(f"[CAT] Collecting from {START_DATE.date()} to {CURRENT_DATE.date()}")

        while current <= CURRENT_DATE:
            date_str = current.strftime("%d%m%Y")

            if date_str in self.cache:
                current += timedelta(days=1)
                continue

            if not self._is_trading_day(current):
                logger.info(f"[CAT] Skipping {date_str} (weekend/holiday)")
                skipped += 1
                current += timedelta(days=1)
                continue

            logger.info(f"[CAT] Processing {date_str} ...")
            data = self._download_and_parse(current)

            if data:
                self.cache[date_str] = data
                processed += 1
                logger.info(
                    f"[CAT]   [OK]  {date_str}: "
                    f"Buy={data['RETAIL_BUY_CR']:.2f}  "
                    f"Sell={data['RETAIL_SELL_CR']:.2f}  "
                    f"Avg={data['RETAIL_AVG_CR']:.2f} (Rs.Cr)"
                )
            else:
                failed += 1
                logger.error(f"[CAT]   [FAIL] {date_str}")

            current += timedelta(days=1)

        self._save_cache()
        logger.info(
            f"[CAT] Done — fetched={processed}, skipped={skipped}, "
            f"failed={failed}, total_cached={len(self.cache)}"
        )


# ===========================================================================
# NSE Equity Category Turnover Collector
# ===========================================================================
class NSEEqCatCollector:
    """
    Downloads cat_turnover_DDMMYY.xls from NSE equities/cat archives.
    Extracts Buy Value and Sell Value (Rs.Crores) for the 'RETAIL' category
    from the 'Daily' sheet, and computes their average.
    Cache key = DDMMYYYY (8-digit, consistent with other collectors).
    """

    def __init__(self):
        self.cache                     = self._load_cache()
        self._downloads_since_refresh  = 0
        self.session                   = self._new_session()
        Path(NSE_CAT_TEMP_DIR).mkdir(exist_ok=True)

    def _new_session(self) -> requests.Session:
        s = requests.Session()
        s.headers.update(NSE_HEADERS)
        try:
            logger.info("[EQCAT] Seeding session cookies from NSE homepage ...")
            r = s.get(NSE_HOME, timeout=20)
            logger.info(f"[EQCAT] Homepage: HTTP {r.status_code} | Cookies: {list(s.cookies.keys())}")
            time.sleep(1)
        except Exception as exc:
            logger.warning(f"[EQCAT] Could not seed cookies: {exc}")
        return s

    def _maybe_refresh_session(self):
        self._downloads_since_refresh += 1
        if self._downloads_since_refresh >= SESSION_REFRESH:
            logger.info("[EQCAT] Periodic session refresh ...")
            self.session = self._new_session()
            self._downloads_since_refresh = 0

    def _load_cache(self) -> Dict:
        if os.path.exists(NSE_EQ_CAT_CACHE_FILE):
            try:
                with open(NSE_EQ_CAT_CACHE_FILE, 'r') as f:
                    data = json.load(f)
                    logger.info(f"[EQCAT] Loaded {len(data)} cached entries from {NSE_EQ_CAT_CACHE_FILE}")
                    return data
            except Exception as e:
                logger.warning(f"[EQCAT] Failed to load cache: {e}")
        return {}

    def _save_cache(self):
        try:
            with open(NSE_EQ_CAT_CACHE_FILE, 'w') as f:
                json.dump(self.cache, f, indent=2)
            logger.info(f"[EQCAT] Cache saved: {len(self.cache)} entries")
        except Exception as e:
            logger.error(f"[EQCAT] Failed to save cache: {e}")

    def _is_trading_day(self, date: datetime) -> bool:
        if date.weekday() >= 5:
            return False
        return date.strftime("%d%m%Y") not in NSE_HOLIDAYS

    @staticmethod
    def _xls_filename(date: datetime) -> str:
        """URL uses 6-digit DDMMYY, e.g. cat_turnover_260226.xls"""
        return "cat_turnover_" + date.strftime("%d%m%y") + ".xls"

    def _download_and_parse(self, date: datetime) -> Optional[Dict]:
        filename = self._xls_filename(date)
        url      = NSE_EQ_CAT_BASE_URL + filename

        self._maybe_refresh_session()

        for attempt in range(1, RETRY_ATTEMPTS + 1):
            try:
                logger.info(f"[EQCAT]   GET {filename} (attempt {attempt}/{RETRY_ATTEMPTS}) ...")
                resp = self.session.get(url, timeout=REQUEST_TIMEOUT)

                if resp.status_code == 200:
                    if resp.content[:2] != b'\xd0\xcf':
                        logger.warning(f"[EQCAT]   {filename} did not return XLS binary")
                        return None
                    logger.info(f"[EQCAT]   Downloaded {filename} -- OK ({len(resp.content)} bytes)")
                    return self._parse_xls(resp.content)

                elif resp.status_code == 403:
                    logger.warning(f"[EQCAT]   HTTP 403 -- refreshing session")
                    if attempt < RETRY_ATTEMPTS:
                        self.session = self._new_session()
                    else:
                        return None

                elif resp.status_code == 404:
                    logger.debug(f"[EQCAT]   HTTP 404 -- file not on server for {filename}")
                    return None

                else:
                    logger.warning(f"[EQCAT]   HTTP {resp.status_code}")

            except requests.exceptions.Timeout:
                logger.warning(f"[EQCAT]   Timeout (attempt {attempt})")
            except requests.exceptions.ConnectionError as exc:
                logger.warning(f"[EQCAT]   Connection error: {exc} (attempt {attempt})")
                if attempt < RETRY_ATTEMPTS:
                    self.session = self._new_session()
            except Exception as exc:
                logger.error(f"[EQCAT]   Unexpected error: {exc}")
                break

            if attempt < RETRY_ATTEMPTS:
                wait = RETRY_DELAY * attempt
                logger.info(f"[EQCAT]   Retrying in {wait}s ...")
                time.sleep(wait)

        return None

    @staticmethod
    def _parse_xls(raw_bytes: bytes) -> Optional[Dict]:
        """
        Parse equity cat_turnover XLS — 'Daily' sheet.
        Find the row where col[1].strip().lower() == 'retail'.
        Returns dict: EQ_RETAIL_BUY_CR, EQ_RETAIL_SELL_CR, EQ_RETAIL_AVG_CR
        """
        try:
            wb = xlrd.open_workbook(file_contents=raw_bytes)
            sh = wb.sheets()[0]  # 'Daily' sheet is always first

            buy_val  = None
            sell_val = None

            for row_idx in range(sh.nrows):
                category = str(sh.cell_value(row_idx, 1)).strip().lower()
                if category == 'retail':
                    try:
                        buy_val  = float(sh.cell_value(row_idx, 2))
                        sell_val = float(sh.cell_value(row_idx, 3))
                    except (ValueError, TypeError):
                        pass
                    break

            if buy_val is None or sell_val is None:
                logger.warning("[EQCAT]   'RETAIL' row not found in XLS")
                return None

            avg_val = (buy_val + sell_val) / 2.0
            logger.info(f"[EQCAT]   Retail — Buy={buy_val:.2f}  Sell={sell_val:.2f}  Avg={avg_val:.2f} (Rs.Cr)")
            return {
                'EQ_RETAIL_BUY_CR':  buy_val,
                'EQ_RETAIL_SELL_CR': sell_val,
                'EQ_RETAIL_AVG_CR':  avg_val,
            }
        except Exception as exc:
            logger.error(f"[EQCAT] XLS parse error: {exc}")
            return None

    def collect(self):
        processed = skipped = failed = 0
        current   = START_DATE

        logger.info(f"[EQCAT] Collecting from {START_DATE.date()} to {CURRENT_DATE.date()}")

        while current <= CURRENT_DATE:
            date_str = current.strftime("%d%m%Y")

            if date_str in self.cache:
                current += timedelta(days=1)
                continue

            if not self._is_trading_day(current):
                logger.info(f"[EQCAT] Skipping {date_str} (weekend/holiday)")
                skipped += 1
                current += timedelta(days=1)
                continue

            logger.info(f"[EQCAT] Processing {date_str} ...")
            data = self._download_and_parse(current)

            if data:
                self.cache[date_str] = data
                processed += 1
                logger.info(
                    f"[EQCAT]   [OK]  {date_str}: "
                    f"Buy={data['EQ_RETAIL_BUY_CR']:.2f}  "
                    f"Sell={data['EQ_RETAIL_SELL_CR']:.2f}  "
                    f"Avg={data['EQ_RETAIL_AVG_CR']:.2f} (Rs.Cr)"
                )
            else:
                failed += 1
                logger.error(f"[EQCAT]   [FAIL] {date_str}")

            current += timedelta(days=1)

        self._save_cache()
        logger.info(
            f"[EQCAT] Done — fetched={processed}, skipped={skipped}, "
            f"failed={failed}, total_cached={len(self.cache)}"
        )


# ===========================================================================
# NSE Data Collector
# ===========================================================================
class NSEDataCollector:
    """Collects and caches NSE FO daily aggregate metrics."""

    def __init__(self):
        self.cache                     = self._load_cache()
        self._downloads_since_refresh  = 0
        self.session                   = self._new_session()
        Path(NSE_TEMP_DIR).mkdir(exist_ok=True)

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------
    def _new_session(self) -> requests.Session:
        s = requests.Session()
        s.headers.update(NSE_HEADERS)
        try:
            logger.info("[NSE] Seeding session cookies from NSE homepage ...")
            r = s.get(NSE_HOME, timeout=20)
            logger.info(f"[NSE] Homepage: HTTP {r.status_code} | Cookies: {list(s.cookies.keys())}")
            time.sleep(1)
        except Exception as exc:
            logger.warning(f"[NSE] Could not seed cookies: {exc}")
        return s

    def _maybe_refresh_session(self):
        self._downloads_since_refresh += 1
        if self._downloads_since_refresh >= SESSION_REFRESH:
            logger.info("[NSE] Periodic session refresh ...")
            self.session = self._new_session()
            self._downloads_since_refresh = 0

    # ------------------------------------------------------------------
    # Cache
    # ------------------------------------------------------------------
    def _load_cache(self) -> Dict:
        if os.path.exists(NSE_CACHE_FILE):
            try:
                with open(NSE_CACHE_FILE, 'r') as f:
                    data = json.load(f)
                    logger.info(f"[NSE] Loaded {len(data)} cached entries from {NSE_CACHE_FILE}")
                    return data
            except Exception as e:
                logger.warning(f"[NSE] Failed to load cache: {e}")
        return {}

    def _save_cache(self):
        try:
            with open(NSE_CACHE_FILE, 'w') as f:
                json.dump(self.cache, f, indent=2)
            logger.info(f"[NSE] Cache saved: {len(self.cache)} entries")
        except Exception as e:
            logger.error(f"[NSE] Failed to save cache: {e}")

    # ------------------------------------------------------------------
    # Trading day check
    # ------------------------------------------------------------------
    def _is_trading_day(self, date: datetime) -> bool:
        if date.weekday() >= 5:
            return False
        return date.strftime("%d%m%Y") not in NSE_HOLIDAYS

    # ------------------------------------------------------------------
    # File helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _zip_name(date: datetime) -> str:
        return "fo" + date.strftime("%d%m%Y") + ".zip"

    @staticmethod
    def _op_csv_name(date: datetime) -> str:
        return "op" + date.strftime("%d%m%Y") + ".csv"

    # ------------------------------------------------------------------
    # Download
    # ------------------------------------------------------------------
    def _download_file(self, date: datetime) -> Optional[str]:
        filename = self._zip_name(date)
        url      = NSE_BASE_URL + filename
        filepath = os.path.join(NSE_TEMP_DIR, filename)

        self._maybe_refresh_session()

        for attempt in range(1, RETRY_ATTEMPTS + 1):
            try:
                logger.info(f"[NSE]   GET {filename} (attempt {attempt}/{RETRY_ATTEMPTS}) ...")
                resp = self.session.get(url, timeout=REQUEST_TIMEOUT, stream=True)

                if resp.status_code == 200:
                    with open(filepath, 'wb') as fh:
                        for chunk in resp.iter_content(chunk_size=65536):
                            if chunk:
                                fh.write(chunk)
                    logger.info(f"[NSE]   Downloaded {filename} -- OK")
                    return filepath

                elif resp.status_code == 403:
                    logger.warning(f"[NSE]   HTTP 403 -- refreshing session")
                    if attempt < RETRY_ATTEMPTS:
                        self.session = self._new_session()
                    else:
                        return None

                elif resp.status_code == 404:
                    logger.debug(f"[NSE]   HTTP 404 -- file not on server")
                    return None

                else:
                    logger.warning(f"[NSE]   HTTP {resp.status_code}")

            except requests.exceptions.Timeout:
                logger.warning(f"[NSE]   Timeout (attempt {attempt})")
            except requests.exceptions.ConnectionError as exc:
                logger.warning(f"[NSE]   Connection error: {exc} (attempt {attempt})")
                if attempt < RETRY_ATTEMPTS:
                    self.session = self._new_session()
            except Exception as exc:
                logger.error(f"[NSE]   Unexpected error: {exc}")
                break

            if attempt < RETRY_ATTEMPTS:
                wait = RETRY_DELAY * attempt
                logger.info(f"[NSE]   Retrying in {wait}s ...")
                time.sleep(wait)

        return None

    # ------------------------------------------------------------------
    # Parse
    # ------------------------------------------------------------------
    def _extract_and_parse(self, filepath: str, date: datetime) -> Optional[Dict]:
        op_target = self._op_csv_name(date)
        try:
            with zipfile.ZipFile(filepath, 'r') as zf:
                names = zf.namelist()
                if op_target in names:
                    chosen = op_target
                else:
                    ops = [n for n in names if n.lower().startswith('op') and n.endswith('.csv')]
                    if not ops:
                        logger.warning(f"[NSE] No op*.csv in zip: {filepath}")
                        return None
                    chosen = ops[0]

                with zf.open(chosen) as fh:
                    return self._parse_csv(fh)
        except zipfile.BadZipFile:
            logger.error(f"[NSE] Bad zip: {filepath}")
        except Exception as exc:
            logger.error(f"[NSE] Extraction error: {exc}")
        return None

    @staticmethod
    def _parse_csv(csv_file) -> Optional[Dict]:
        TARGET = {'NO_OF_CONT', 'NO_OF_TRADE', 'NOTION_VAL', 'PR_VAL'}
        try:
            text  = csv_file.read().decode('utf-8', errors='ignore')
            lines = [l for l in text.splitlines() if l.strip()]
            if not lines:
                return None

            stripped_headers = [h.strip() for h in next(csv.reader([lines[0]]))]
            col_index = {h: i for i, h in enumerate(stripped_headers) if h in TARGET}

            if not col_index:
                logger.warning(f"[NSE] Target columns not found. Headers: {stripped_headers[:10]}")
                return None

            sums = {k: 0.0 for k in TARGET}
            row_count = 0
            for row in csv.reader(lines[1:]):
                if not row:
                    continue
                for col, idx in col_index.items():
                    if idx < len(row):
                        raw = (row[idx] or '').strip().replace(',', '')
                        if raw:
                            try:
                                sums[col] += float(raw)
                            except ValueError:
                                pass
                row_count += 1

            if row_count:
                logger.info(f"[NSE]   Parsed {row_count} rows")
                return sums
            return None
        except Exception as exc:
            logger.error(f"[NSE] CSV parse error: {exc}")
            return None

    @staticmethod
    def _cleanup(filepath: str):
        try:
            if filepath and os.path.exists(filepath):
                os.remove(filepath)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Main collection loop
    # ------------------------------------------------------------------
    def collect(self):
        processed = skipped = failed = 0
        current   = START_DATE

        logger.info(f"[NSE] Collecting from {START_DATE.date()} to {CURRENT_DATE.date()}")

        while current <= CURRENT_DATE:
            date_str = current.strftime("%d%m%Y")

            if date_str in self.cache:
                current += timedelta(days=1)
                continue

            if not self._is_trading_day(current):
                logger.info(f"[NSE] Skipping {date_str} (weekend/holiday)")
                skipped += 1
                current += timedelta(days=1)
                continue

            logger.info(f"[NSE] Processing {date_str} ...")
            fp   = self._download_file(current)
            data = None
            if fp:
                data = self._extract_and_parse(fp, current)
                self._cleanup(fp)

            if data:
                self.cache[date_str] = data
                processed += 1
                logger.info(
                    f"[NSE]   [OK]  {date_str}: "
                    f"CONT={data['NO_OF_CONT']:.0f}  "
                    f"TRADE={data['NO_OF_TRADE']:.0f}  "
                    f"NOTION={data['NOTION_VAL']:.2f}  "
                    f"PR={data['PR_VAL']:.2f}"
                )
            else:
                failed += 1
                logger.error(f"[NSE]   [FAIL] {date_str}")

            current += timedelta(days=1)

        self._save_cache()
        logger.info(
            f"[NSE] Done — fetched={processed}, skipped={skipped}, "
            f"failed={failed}, total_cached={len(self.cache)}"
        )


# ===========================================================================
# BSE Data Collector
# ===========================================================================
class BSEDataCollector:
    """Collects and caches BSE Derivatives daily aggregate metrics."""

    def __init__(self):
        self.cache                     = self._load_cache()
        self._downloads_since_refresh  = 0
        self.session                   = self._new_session()

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------
    def _new_session(self) -> requests.Session:
        s = requests.Session()
        s.headers.update(BSE_HEADERS)
        try:
            logger.info("[BSE] Seeding session from BSE homepage ...")
            r = s.get(BSE_HOME, timeout=20)
            logger.info(f"[BSE] Homepage: HTTP {r.status_code} | Cookies: {list(s.cookies.keys())}")
            time.sleep(1)
        except Exception as exc:
            logger.warning(f"[BSE] Could not seed cookies: {exc}")
        return s

    def _maybe_refresh_session(self):
        self._downloads_since_refresh += 1
        if self._downloads_since_refresh >= SESSION_REFRESH:
            logger.info("[BSE] Periodic session refresh ...")
            self.session = self._new_session()
            self._downloads_since_refresh = 0

    # ------------------------------------------------------------------
    # Cache
    # ------------------------------------------------------------------
    def _load_cache(self) -> Dict:
        if os.path.exists(BSE_CACHE_FILE):
            try:
                with open(BSE_CACHE_FILE, 'r') as f:
                    data = json.load(f)
                    logger.info(f"[BSE] Loaded {len(data)} cached entries from {BSE_CACHE_FILE}")
                    return data
            except Exception as e:
                logger.warning(f"[BSE] Failed to load cache: {e}")
        return {}

    def _save_cache(self):
        try:
            with open(BSE_CACHE_FILE, 'w') as f:
                json.dump(self.cache, f, indent=2)
            logger.info(f"[BSE] Cache saved: {len(self.cache)} entries")
        except Exception as e:
            logger.error(f"[BSE] Failed to save cache: {e}")

    # ------------------------------------------------------------------
    # Trading day check
    # ------------------------------------------------------------------
    def _is_trading_day(self, date: datetime) -> bool:
        if date.weekday() >= 5:
            return False
        return date.strftime("%d%m%Y") not in BSE_HOLIDAYS

    # ------------------------------------------------------------------
    # File name helper
    # ------------------------------------------------------------------
    @staticmethod
    def _csv_filename(date: datetime) -> str:
        """BSE filename uses YYYYMMDD, e.g. MS_20250203-01.csv"""
        return "MS_" + date.strftime("%Y%m%d") + "-01.csv"

    # ------------------------------------------------------------------
    # Download + parse (no zip — direct CSV)
    # ------------------------------------------------------------------
    def _download_and_parse(self, date: datetime) -> Optional[Dict]:
        filename = self._csv_filename(date)
        url      = BSE_BASE_URL + filename

        self._maybe_refresh_session()

        for attempt in range(1, RETRY_ATTEMPTS + 1):
            try:
                logger.info(f"[BSE]   GET {filename} (attempt {attempt}/{RETRY_ATTEMPTS}) ...")
                resp = self.session.get(url, timeout=REQUEST_TIMEOUT)

                if resp.status_code == 200:
                    # Verify it is actually CSV and not an HTML error page
                    if b'Market Summary' not in resp.content[:100]:
                        logger.warning(f"[BSE]   {filename} returned non-CSV content")
                        return None
                    logger.info(f"[BSE]   Downloaded {filename} -- OK ({len(resp.content)} bytes)")
                    return self._parse_csv(resp.content)

                elif resp.status_code == 403:
                    logger.warning(f"[BSE]   HTTP 403 -- refreshing session")
                    if attempt < RETRY_ATTEMPTS:
                        self.session = self._new_session()
                    else:
                        return None

                elif resp.status_code == 404:
                    logger.debug(f"[BSE]   HTTP 404 -- file not on server for {filename}")
                    return None

                else:
                    logger.warning(f"[BSE]   HTTP {resp.status_code}")

            except requests.exceptions.Timeout:
                logger.warning(f"[BSE]   Timeout (attempt {attempt})")
            except requests.exceptions.ConnectionError as exc:
                logger.warning(f"[BSE]   Connection error: {exc} (attempt {attempt})")
                if attempt < RETRY_ATTEMPTS:
                    self.session = self._new_session()
            except Exception as exc:
                logger.error(f"[BSE]   Unexpected error: {exc}")
                break

            if attempt < RETRY_ATTEMPTS:
                wait = RETRY_DELAY * attempt
                logger.info(f"[BSE]   Retrying in {wait}s ...")
                time.sleep(wait)

        return None

    @staticmethod
    def _parse_csv(raw_bytes: bytes) -> Optional[Dict]:
        """Sum the 4 target columns for rows where Product Type is IO or IF only."""
        try:
            text  = raw_bytes.decode('utf-8', errors='ignore')
            lines = [l for l in text.splitlines() if l.strip()]
            if len(lines) < 2:
                return None

            header_cols = [h.strip() for h in next(csv.reader([lines[0]]))]

            # Name-based lookup (fallback to fixed index if name not found)
            name_to_idx = {h: i for i, h in enumerate(header_cols)}
            col_map = {
                'BSE_TTL_TRADED_QTY':   name_to_idx.get("Total Traded Quantity",                      BSE_COL_TTL_QTY),
                'BSE_TTL_TRADED_VAL':   name_to_idx.get("Total Traded Value (in Thousands)(absolute)", BSE_COL_TTL_VAL),
                'BSE_AVG_TRADED_PRICE': name_to_idx.get("Average Traded Price",                       BSE_COL_AVG_PRICE),
                'BSE_NO_OF_TRADES':     name_to_idx.get("No. of Trades",                             BSE_COL_NO_TRADES),
            }
            prod_type_idx = name_to_idx.get("Product Type", 4)

            sums      = {k: 0.0 for k in col_map}
            row_count = 0

            for row in csv.reader(lines[1:]):
                if not row:
                    continue
                # Only include Index Options (IO) and Index Futures (IF)
                prod_type = row[prod_type_idx].strip() if prod_type_idx < len(row) else ''
                if prod_type not in ('IO', 'IF'):
                    continue
                for col, idx in col_map.items():
                    if idx < len(row):
                        raw = (row[idx] or '').strip().replace(',', '')
                        if raw:
                            try:
                                sums[col] += float(raw)
                            except ValueError:
                                pass
                row_count += 1

            if row_count:
                logger.info(f"[BSE]   Parsed {row_count} IO/IF rows")
                return sums
            return None
        except Exception as exc:
            logger.error(f"[BSE] CSV parse error: {exc}")
            return None

    # ------------------------------------------------------------------
    # Main collection loop
    # ------------------------------------------------------------------
    def collect(self):
        processed = skipped = failed = 0
        current   = START_DATE

        logger.info(f"[BSE] Collecting from {START_DATE.date()} to {CURRENT_DATE.date()}")

        while current <= CURRENT_DATE:
            date_str = current.strftime("%d%m%Y")

            if date_str in self.cache:
                current += timedelta(days=1)
                continue

            if not self._is_trading_day(current):
                logger.info(f"[BSE] Skipping {date_str} (weekend/holiday)")
                skipped += 1
                current += timedelta(days=1)
                continue

            logger.info(f"[BSE] Processing {date_str} ...")
            data = self._download_and_parse(current)

            if data:
                self.cache[date_str] = data
                processed += 1
                logger.info(
                    f"[BSE]   [OK]  {date_str}: "
                    f"QTY={data['BSE_TTL_TRADED_QTY']:.0f}  "
                    f"VAL={data['BSE_TTL_TRADED_VAL']:.2f}  "
                    f"AVG={data['BSE_AVG_TRADED_PRICE']:.4f}  "
                    f"TRADES={data['BSE_NO_OF_TRADES']:.0f}"
                )
            else:
                failed += 1
                logger.error(f"[BSE]   [FAIL] {date_str}")

            current += timedelta(days=1)

        self._save_cache()
        logger.info(
            f"[BSE] Done — fetched={processed}, skipped={skipped}, "
            f"failed={failed}, total_cached={len(self.cache)}"
        )


# ===========================================================================
# Combined output writer
# ===========================================================================
def write_combined_output(
    nse_cache: Dict, bse_cache: Dict,
    cat_cache: Dict, eq_cat_cache: Dict,
    mrg_cache: Dict,
):
    """
    Merge all caches by DDMMYYYY date key and write the combined CSV.
    Rows present in at least one cache are included.
    Missing values are written as empty strings.
    """
    all_dates = sorted(
        set(nse_cache.keys()) | set(bse_cache.keys())
        | set(cat_cache.keys()) | set(eq_cat_cache.keys())
        | set(mrg_cache.keys()),
        key=lambda s: datetime.strptime(s, "%d%m%Y")
    )

    try:
        with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                'Date',
                'NSE_NO_OF_CONT', 'NSE_NO_OF_TRADE', 'NSE_NOTION_VAL', 'NSE_PR_VAL',
                'BSE_TTL_TRADED_QTY', 'BSE_TTL_TRADED_VAL',
                'BSE_AVG_TRADED_PRICE', 'BSE_NO_OF_TRADES',
                'NSE_CAT_RETAIL_BUY_CR', 'NSE_CAT_RETAIL_SELL_CR', 'NSE_CAT_RETAIL_AVG_CR',
                'NSE_EQ_RETAIL_BUY_CR', 'NSE_EQ_RETAIL_SELL_CR', 'NSE_EQ_RETAIL_AVG_CR',
                'MRG_OUTSTANDING_BOD_LAKHS', 'MRG_FRESH_EXP_LAKHS',
                'MRG_EXP_LIQ_LAKHS', 'MRG_NET_EOD_LAKHS',
            ])

            for date_str in all_dates:
                display = datetime.strptime(date_str, "%d%m%Y").strftime("%d-%m-%Y")
                nse    = nse_cache.get(date_str)
                bse    = bse_cache.get(date_str)
                cat    = cat_cache.get(date_str)
                eq_cat = eq_cat_cache.get(date_str)
                mrg    = mrg_cache.get(date_str)

                writer.writerow([
                    display,
                    # NSE FO columns
                    f"{nse['NO_OF_CONT']:.2f}"  if nse else '',
                    f"{nse['NO_OF_TRADE']:.2f}" if nse else '',
                    f"{nse['NOTION_VAL']:.2f}"  if nse else '',
                    f"{nse['PR_VAL']:.2f}"      if nse else '',
                    # BSE columns
                    f"{bse['BSE_TTL_TRADED_QTY']:.2f}"   if bse else '',
                    f"{bse['BSE_TTL_TRADED_VAL']:.2f}"   if bse else '',
                    f"{bse['BSE_AVG_TRADED_PRICE']:.4f}" if bse else '',
                    f"{bse['BSE_NO_OF_TRADES']:.2f}"     if bse else '',
                    # NSE FO Category Turnover — Retail
                    f"{cat['RETAIL_BUY_CR']:.2f}"  if cat else '',
                    f"{cat['RETAIL_SELL_CR']:.2f}" if cat else '',
                    f"{cat['RETAIL_AVG_CR']:.2f}"  if cat else '',
                    # NSE Equity Category Turnover — Retail
                    f"{eq_cat['EQ_RETAIL_BUY_CR']:.2f}"  if eq_cat else '',
                    f"{eq_cat['EQ_RETAIL_SELL_CR']:.2f}" if eq_cat else '',
                    f"{eq_cat['EQ_RETAIL_AVG_CR']:.2f}"  if eq_cat else '',
                    # NSE Margin Trading
                    f"{mrg['MRG_OUTSTANDING_BOD_LAKHS']:.2f}" if mrg else '',
                    f"{mrg['MRG_FRESH_EXP_LAKHS']:.2f}"       if mrg else '',
                    f"{mrg['MRG_EXP_LIQ_LAKHS']:.2f}"         if mrg else '',
                    f"{mrg['MRG_NET_EOD_LAKHS']:.2f}"          if mrg else '',
                ])

        logger.info(f"Combined output written to {OUTPUT_FILE} ({len(all_dates)} rows)")
    except Exception as e:
        logger.error(f"Failed to write output: {e}")


# ===========================================================================
# Entry point
# ===========================================================================
def main():
    logger.info("=" * 70)
    logger.info("NSE + BSE FO Market Data Collector  (Combined)")
    logger.info("=" * 70)

    nse    = None
    bse    = None
    cat    = None
    eq_cat = None
    mrg    = None

    try:
        # --- NSE FO ---
        logger.info("\n--- NSE FO Collection ---")
        nse = NSEDataCollector()
        nse.collect()

        # --- BSE ---
        logger.info("\n--- BSE Collection ---")
        bse = BSEDataCollector()
        bse.collect()

        # --- NSE FO Category Turnover ---
        logger.info("\n--- NSE FO Category Turnover Collection ---")
        cat = NSECatCollector()
        cat.collect()

        # --- NSE Equity Category Turnover ---
        logger.info("\n--- NSE Equity Category Turnover Collection ---")
        eq_cat = NSEEqCatCollector()
        eq_cat.collect()

        # --- NSE Margin Trading ---
        logger.info("\n--- NSE Margin Trading Collection ---")
        mrg = NSEMrgCollector()
        mrg.collect()

        # --- Merge & write ---
        logger.info("\n--- Writing combined output ---")
        write_combined_output(nse.cache, bse.cache, cat.cache, eq_cat.cache, mrg.cache)

        logger.info("\nAll done.")

    except KeyboardInterrupt:
        logger.info("Interrupted by user — saving partial results ...")
        write_combined_output(
            nse.cache    if nse    else {},
            bse.cache    if bse    else {},
            cat.cache    if cat    else {},
            eq_cat.cache if eq_cat else {},
            mrg.cache    if mrg    else {},
        )

    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)


if __name__ == "__main__":
    main()
