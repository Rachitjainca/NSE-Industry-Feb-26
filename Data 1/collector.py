"""
NSE + BSE FO Market Data Collector
====================================
Collects daily Futures & Options metrics from NSE/BSE sources,
caches each source to its own JSON file, and writes a combined CSV.

Output: nse_fo_aggregated_data.csv  (57 columns)

Sources
-------
1. NSE FO daily zip          – NO_OF_CONT, NO_OF_TRADE, NOTION_VAL, PR_VAL
2. BSE Derivatives CSV       – TTL_TRADED_QTY/VAL, AVG_TRADED_PRICE, NO_OF_TRADES (IO+IF only)
3. NSE FO Category XLS       – Retail buy/sell/avg (Rs.Cr)
4. NSE Equity Category XLS   – Retail buy/sell/avg (Rs.Cr)
5. NSE Margin Trading ZIP    – 4 aggregate metrics (Rs.Lakh)
6. NSE MFSS API              – Mutual Fund subscription/redemption order stats (5 columns)
7. NSE TBG Daily APIs        – CM/FO/Commodity metrics + premium/put-call ratios (28 columns)
8. NSE & BSE Registered Investors – Investor counts (2 columns)
"""

import csv
import io
import json
import logging
import os
import sys
import time
import zipfile
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional, Tuple

import requests
import xlrd

# ── Logging (UTF-8 safe on Windows cp1252 terminals) ───────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    handlers=[
        logging.FileHandler("collector.log", encoding="utf-8"),
        logging.StreamHandler(
            open(sys.stdout.fileno(), mode="w", encoding="utf-8",
                 buffering=1, closefd=False)
        ),
    ],
)
logger = logging.getLogger(__name__)

# ── Global config ───────────────────────────────────────────────────────────
START_DATE      = datetime(2025, 2, 1)
CURRENT_DATE    = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
OUTPUT_FILE     = "nse_fo_aggregated_data.csv"
REQUEST_TIMEOUT = 30
RETRY_ATTEMPTS  = 4
RETRY_DELAY     = 5   # seconds × attempt number
SESSION_REFRESH = 20  # re-seed cookies every N downloads

# ── Shared HTTP headers ─────────────────────────────────────────────────────
_BASE_HEADERS = {
    "User-Agent":      ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/122.0.0.0 Safari/537.36"),
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection":      "keep-alive",
}
NSE_HEADERS = {**_BASE_HEADERS, "Referer": "https://www.nseindia.com"}
BSE_HEADERS = {**_BASE_HEADERS,
               "Referer": "https://www.bseindia.com/markets/Derivatives/DerivativesHome.aspx"}

# ── Exchange homepages (for cookie seeding) ──────────────────────────────────
NSE_HOME = "https://www.nseindia.com"
BSE_HOME = "https://www.bseindia.com"

# ── Source base URLs ─────────────────────────────────────────────────────────
NSE_FO_BASE    = "https://nsearchives.nseindia.com/archives/fo/mkt/"
NSE_CAT_BASE   = "https://nsearchives.nseindia.com/archives/fo/cat/"
NSE_EQCAT_BASE = "https://nsearchives.nseindia.com/archives/equities/cat/"
NSE_MRG_BASE   = "https://nsearchives.nseindia.com/content/equities/"
NSE_PART_BASE  = "https://nsearchives.nseindia.com/content/nsccl/"
BSE_FO_BASE    = "https://www.bseindia.com/download/Bhavcopy/Derivative/"
NSE_TBG_CM_BASE = "https://www.nseindia.com/api/trendingEquityIndicesChart"
NSE_TBG_FO_BASE = "https://www.nseindia.com/api/trendingFOIndicesChart"
NSE_TBG_COM_BASE = "https://www.nseindia.com/api/trendingCommodityIndicesChart"

# ── Cache file paths ─────────────────────────────────────────────────────────
NSE_FO_CACHE    = "nse_fo_cache.json"
BSE_CACHE       = "bse_fo_cache.json"
NSE_CAT_CACHE   = "nse_cat_cache.json"
NSE_EQCAT_CACHE = "nse_eq_cat_cache.json"
NSE_MRG_CACHE   = "nse_mrg_cache.json"
NSE_PART_CACHE  = "nse_part_cache.json"
NSE_TBG_CM_CACHE = "nse_tbg_cm_cache.json"
NSE_TBG_FO_CACHE = "nse_tbg_fo_cache.json"
NSE_TBG_COM_CACHE = "nse_tbg_commodity_cache.json"

# ── NSE MFSS (Mutual Fund) API ──────────────────────────────────────────────
NSE_MFSS_API = "https://www.nseindia.com/api/historicalOR/mfssTradeStatisticsData"
NSE_MFSS_CACHE = "nse_mfss_cache.json"

# ── NSE Market Turnover Summary (Orders) API ────────────────────────────────
NSE_MARKET_TURNOVER_API = "https://www.nseindia.com/api/NextApi/apiClient?functionName=getMarketTurnover"
NSE_MARKET_TURNOVER_CACHE = "nse_market_turnover_cache.json"

# ── BSE column indices (0-based) in MS_<date>-01.csv ────────────────────────
BSE_COL_TTL_QTY   = 15
BSE_COL_TTL_VAL   = 16
BSE_COL_AVG_PRICE = 17
BSE_COL_NO_TRADES = 18

# ── Market holidays DDMMYYYY ────────────────────────────────────────────────
NSE_HOLIDAYS: set = {
    "26012025", "24022025", "10032025", "21032025", "08042025",
    "10042025", "14042025", "21042025", "08052025", "15082025",
    "29082025", "02102025", "24102025", "31102025", "01112025",
    "05112025", "25122025",
    "26012026", "17022026",
}
BSE_HOLIDAYS: set = {
    "26012025", "24022025", "10032025", "21032025", "08042025",
    "10042025", "14042025", "21042025", "01052025", "08052025",
    "15082025", "29082025", "02102025", "24102025", "31102025",
    "01112025", "05112025", "25122025",
    "26012026", "17022026",
}

# ── Registered Investors API endpoints ──────────────────────────────────────
REG_INV_CACHE_DIR = "reg_investors_cache"
NSE_REG_INV_URL = "https://www.nseindia.com/api/NextApi/apiClient?functionName=getMarketStatistics"
BSE_REG_INV_URL = "https://api.bseindia.com/BseIndiaAPI/api/MarketStat2/w"
BSE_HOME_URL = "https://www.bseindia.com"

REG_INV_NSE_CACHE_FILE = f"{REG_INV_CACHE_DIR}/nse_reg_investors_cache.json"
REG_INV_BSE_CACHE_FILE = f"{REG_INV_CACHE_DIR}/bse_reg_investors_cache.json"


# ============================================================================
# Cache management for Registered Investors
# ============================================================================
def load_reg_inv_cache(cache_file: str) -> Dict:
    """Load cache from JSON file."""
    if os.path.exists(cache_file):
        try:
            with open(cache_file, encoding="utf-8") as f:
                data = json.load(f)
            logger.info(f"[REG_INV] Cache loaded from {cache_file}: {len(data)} entries")
            return data
        except Exception as exc:
            logger.warning(f"[REG_INV] Cache read error ({cache_file}): {exc}")
    return {}


def save_reg_inv_cache(cache_file: str, data: Dict) -> None:
    """Save cache to JSON file."""
    try:
        os.makedirs(REG_INV_CACHE_DIR, exist_ok=True)
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        logger.info(f"[REG_INV] Cache saved to {cache_file}: {len(data)} entries")
    except Exception as exc:
        logger.error(f"[REG_INV] Cache write error ({cache_file}): {exc}")


# ============================================================================
# NSE Registered Investors Collector
# ============================================================================
def fetch_nse_reg_investors() -> Optional[int]:
    """Fetch registered investors count from NSE API."""
    logger.info("[REG_INV][NSE] Fetching registered investors...")
    
    try:
        # Create a session for NSE requests with JSON-specific headers
        session = requests.Session()
        # Use minimal headers for JSON API (avoid gzip compression issues)
        api_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": NSE_HOME,
            "Accept": "application/json, text/plain, */*",
        }
        session.headers.update(api_headers)
        
        # Step 1: Warm up session with homepage to get cookies
        logger.info("[REG_INV][NSE] Warming up session...")
        try:
            home_resp = session.get(NSE_HOME, timeout=REQUEST_TIMEOUT)
            logger.info(f"[REG_INV][NSE] Session warm-up: HTTP {home_resp.status_code}")
        except Exception as exc:
            logger.warning(f"[REG_INV][NSE] Session warm-up failed: {exc}")
        
        # Step 2: Fetch API endpoint
        for attempt in range(1, RETRY_ATTEMPTS + 1):
            try:
                logger.info(f"[REG_INV][NSE] API request (attempt {attempt}/{RETRY_ATTEMPTS})...")
                resp = session.get(NSE_REG_INV_URL, timeout=REQUEST_TIMEOUT)
                
                if resp.status_code == 200:
                    data = resp.json()
                    
                    # Extract regInvestors from nested "data" structure
                    reg_inv_str = None
                    
                    # Try nested structure first: data.data.regInvestors
                    if isinstance(data, dict) and "data" in data:
                        nested_data = data["data"]
                        if isinstance(nested_data, dict) and "regInvestors" in nested_data:
                            reg_inv_str = nested_data["regInvestors"]
                    
                    # Fallback to top-level: data.regInvestors
                    if not reg_inv_str and isinstance(data, dict) and "regInvestors" in data:
                        reg_inv_str = data["regInvestors"]
                    
                    if reg_inv_str:
                        # Remove commas from formatted string (e.g., "25,20,07,360" → 2520073604)
                        reg_investors = int(str(reg_inv_str).replace(",", ""))
                        logger.info(f"[REG_INV][NSE] ✅ Registered investors: {reg_investors:,}")
                        return reg_investors
                    else:
                        logger.warning(f"[REG_INV][NSE] 'regInvestors' field not found in response")
                        return None
                else:
                    logger.warning(f"[REG_INV][NSE] HTTP {resp.status_code} (attempt {attempt}/{RETRY_ATTEMPTS})")
            
            except Exception as exc:
                logger.warning(f"[REG_INV][NSE] Fetch error (attempt {attempt}/{RETRY_ATTEMPTS}): {exc}")
        
        logger.error("[REG_INV][NSE] Failed after retries")
        return None
    
    except Exception as exc:
        logger.error(f"[REG_INV][NSE] Fatal error: {exc}")
        return None


# ============================================================================
# BSE Registered Investors Collector
# ============================================================================
def fetch_bse_reg_investors() -> Optional[int]:
    """Fetch registered investors count from BSE API."""
    logger.info("[REG_INV][BSE] Fetching registered investors...")
    
    try:
        # Create a session for the BSE requests
        session = requests.Session()
        session.headers.update(BSE_HEADERS)
        
        # Step 1: Warm up session with homepage
        logger.info("[REG_INV][BSE] Warming up session...")
        try:
            home_resp = session.get(BSE_HOME_URL, timeout=REQUEST_TIMEOUT)
            logger.info(f"[REG_INV][BSE] Session warm-up: HTTP {home_resp.status_code}")
        except Exception as exc:
            logger.warning(f"[REG_INV][BSE] Session warm-up failed: {exc}")
        
        # Step 2: Fetch API endpoint
        for attempt in range(1, RETRY_ATTEMPTS + 1):
            try:
                logger.info(f"[REG_INV][BSE] API request (attempt {attempt}/{RETRY_ATTEMPTS})...")
                resp = session.get(BSE_REG_INV_URL, timeout=REQUEST_TIMEOUT)
                
                if resp.status_code == 200:
                    data = resp.json()
                    
                    # Extract Inv_count from nested Table structure
                    # Response format: {"Table": [{"Inv_count": 244653920, ...}]}
                    if isinstance(data, dict) and "Table" in data:
                        table = data["Table"]
                        if isinstance(table, list) and len(table) > 0:
                            first_item = table[0]
                            if isinstance(first_item, dict) and "Inv_count" in first_item:
                                inv_count = int(first_item["Inv_count"])
                                logger.info(f"[REG_INV][BSE] ✅ Registered investors: {inv_count:,}")
                                return inv_count
                    
                    # If we got here, structure was wrong
                    logger.warning(f"[REG_INV][BSE] Unexpected response structure")
                    return None
                
                else:
                    logger.warning(f"[REG_INV][BSE] HTTP {resp.status_code} (attempt {attempt}/{RETRY_ATTEMPTS})")
            
            except ValueError as exc:
                # JSON parse error
                logger.warning(f"[REG_INV][BSE] Invalid JSON (attempt {attempt}/{RETRY_ATTEMPTS}): {exc}")
            
            except Exception as exc:
                logger.warning(f"[REG_INV][BSE] Fetch error (attempt {attempt}/{RETRY_ATTEMPTS}): {exc}")
        
        logger.error("[REG_INV][BSE] Failed after retries")
        return None
    
    except Exception as exc:
        logger.error(f"[REG_INV][BSE] Fatal error: {exc}")
        return None


def collect_registered_investors() -> Tuple[Dict, Dict]:
    """Fetch daily registered investors and return updated caches."""
    logger.info("=" * 70)
    logger.info("Collecting Registered Investors Data")
    logger.info("=" * 70)
    
    date_key = datetime.now().strftime("%d%m%Y")
    
    # Load caches
    nse_cache = load_reg_inv_cache(REG_INV_NSE_CACHE_FILE)
    bse_cache = load_reg_inv_cache(REG_INV_BSE_CACHE_FILE)
    
    # Fetch data
    nse_investors = fetch_nse_reg_investors()
    bse_investors = fetch_bse_reg_investors()
    
    # Update caches
    if nse_investors is not None:
        nse_cache[date_key] = nse_investors
        save_reg_inv_cache(REG_INV_NSE_CACHE_FILE, nse_cache)
    
    if bse_investors is not None:
        bse_cache[date_key] = bse_investors
        save_reg_inv_cache(REG_INV_BSE_CACHE_FILE, bse_cache)
    
    logger.info("=" * 70)
    
    return nse_cache, bse_cache


# ============================================================================
# BaseCollector  —  shared session, cache, retry, and collection loop
# ============================================================================
class BaseCollector(ABC):
    """
    Abstract base for all 5 data collectors.

    Subclasses must implement:
      _get_url_and_file(date)  → Tuple[str, str]   url, filename
      _parse(raw: bytes)       → Optional[Dict]
    And may override:
      _get_magic()  → Optional[bytes]   expected leading bytes (content check)
      _log_ok(date_str, data)           verbose success message
    """

    def __init__(
        self,
        tag: str,
        cache_file: str,
        home_url: str,
        headers: dict,
        holidays: set,
    ):
        self.tag      = tag
        self._cache_file  = cache_file
        self._home_url    = home_url
        self._headers     = headers
        self._holidays    = holidays
        self.cache        = self._load_cache()
        self._n_downloads = 0
        self.session      = self._new_session()

    # ── Session ──────────────────────────────────────────────────────────────
    def _new_session(self) -> requests.Session:
        s = requests.Session()
        s.headers.update(self._headers)
        try:
            logger.info(f"[{self.tag}] Seeding cookies from {self._home_url} ...")
            r = s.get(self._home_url, timeout=20)
            logger.info(f"[{self.tag}] Seed: HTTP {r.status_code}")
            time.sleep(1)
        except Exception as exc:
            logger.warning(f"[{self.tag}] Cookie seed failed: {exc}")
        return s

    def _maybe_refresh(self) -> None:
        self._n_downloads += 1
        if self._n_downloads >= SESSION_REFRESH:
            logger.info(f"[{self.tag}] Periodic session refresh ...")
            self.session      = self._new_session()
            self._n_downloads = 0

    # ── Cache ─────────────────────────────────────────────────────────────────
    def _load_cache(self) -> Dict:
        if os.path.exists(self._cache_file):
            try:
                with open(self._cache_file, encoding="utf-8") as f:
                    data = json.load(f)
                logger.info(f"[{self.tag}] Cache loaded: {len(data)} entries")
                return data
            except Exception as exc:
                logger.warning(f"[{self.tag}] Cache read error: {exc}")
        return {}

    def _save_cache(self) -> None:
        try:
            with open(self._cache_file, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, indent=2)
            logger.info(f"[{self.tag}] Cache saved: {len(self.cache)} entries")
        except Exception as exc:
            logger.error(f"[{self.tag}] Cache write error: {exc}")

    # ── Trading day ──────────────────────────────────────────────────────────
    def _is_trading_day(self, date: datetime) -> bool:
        return date.weekday() < 5 and date.strftime("%d%m%Y") not in self._holidays

    # ── HTTP fetch (with retry / 403-refresh logic) ──────────────────────────
    def _fetch(self, url: str, filename: str,
               magic: Optional[bytes] = None) -> Optional[bytes]:
        self._maybe_refresh()
        for attempt in range(1, RETRY_ATTEMPTS + 1):
            try:
                logger.info(f"[{self.tag}]  GET {filename} (attempt {attempt}/{RETRY_ATTEMPTS})")
                resp = self.session.get(url, timeout=REQUEST_TIMEOUT)

                if resp.status_code == 200:
                    if magic and not resp.content.startswith(magic):
                        logger.warning(f"[{self.tag}]  {filename}: unexpected content")
                        return None
                    logger.info(f"[{self.tag}]  {filename}: OK ({len(resp.content):,} bytes)")
                    return resp.content

                if resp.status_code == 403:
                    logger.warning(f"[{self.tag}]  HTTP 403 — refreshing session")
                    if attempt < RETRY_ATTEMPTS:
                        self.session = self._new_session()
                    else:
                        return None

                elif resp.status_code == 404:
                    logger.debug(f"[{self.tag}]  HTTP 404 — {filename} not published yet")
                    return None

                else:
                    logger.warning(f"[{self.tag}]  HTTP {resp.status_code}")

            except requests.exceptions.Timeout:
                logger.warning(f"[{self.tag}]  Timeout (attempt {attempt})")
            except requests.exceptions.ConnectionError as exc:
                logger.warning(f"[{self.tag}]  Connection error: {exc}")
                if attempt < RETRY_ATTEMPTS:
                    self.session = self._new_session()
            except Exception as exc:
                logger.error(f"[{self.tag}]  Unexpected: {exc}")
                break

            if attempt < RETRY_ATTEMPTS:
                wait = RETRY_DELAY * attempt
                logger.info(f"[{self.tag}]  Retry in {wait}s ...")
                time.sleep(wait)

        return None

    # ── Abstract interface ────────────────────────────────────────────────────
    @abstractmethod
    def _get_url_and_file(self, date: datetime) -> Tuple[str, str]:
        """Return (full_url, display_filename) for this date."""

    @abstractmethod
    def _parse(self, raw: bytes) -> Optional[Dict]:
        """Parse raw bytes and return a dict of metrics, or None on failure."""

    def _get_magic(self) -> Optional[bytes]:
        """Expected leading content bytes for quick validation (override if needed)."""
        return None

    def _log_ok(self, date_str: str, data: Dict) -> None:
        logger.info(f"[{self.tag}]  [OK] {date_str}")

    # ── Main collection loop ──────────────────────────────────────────────────
    def collect(self) -> None:
        processed = skipped = failed = 0
        current = START_DATE
        logger.info(f"[{self.tag}] Collecting {START_DATE.date()} → {CURRENT_DATE.date()}")

        while current <= CURRENT_DATE:
            date_str = current.strftime("%d%m%Y")

            if date_str in self.cache:
                current += timedelta(days=1)
                continue

            if not self._is_trading_day(current):
                skipped += 1
                current += timedelta(days=1)
                continue

            url, fname = self._get_url_and_file(current)
            raw  = self._fetch(url, fname, self._get_magic())
            data = self._parse(raw) if raw is not None else None

            if data:
                self.cache[date_str] = data
                processed += 1
                self._log_ok(date_str, data)
            else:
                failed += 1
                logger.error(f"[{self.tag}]  [FAIL] {date_str}")

            current += timedelta(days=1)

        self._save_cache()
        logger.info(
            f"[{self.tag}] Done — new={processed} skipped={skipped} "
            f"failed={failed} cached={len(self.cache)}"
        )


# ============================================================================
# 1. NSE FO daily collector
# ============================================================================
class NSEFOCollector(BaseCollector):
    """fo<DDMMYYYY>.zip → op<DDMMYYYY>.csv → sums NO_OF_CONT/TRADE/NOTION_VAL/PR_VAL"""

    def __init__(self):
        super().__init__("NSE", NSE_FO_CACHE, NSE_HOME, NSE_HEADERS, NSE_HOLIDAYS)

    def _get_url_and_file(self, date: datetime) -> Tuple[str, str]:
        name = "fo" + date.strftime("%d%m%Y") + ".zip"
        return NSE_FO_BASE + name, name

    def _get_magic(self) -> bytes:
        return b"PK"   # ZIP magic bytes

    def _parse(self, raw: bytes) -> Optional[Dict]:
        TARGET = {"NO_OF_CONT", "NO_OF_TRADE", "NOTION_VAL", "PR_VAL"}
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as zf:
                names = zf.namelist()
                ops   = [n for n in names if n.lower().startswith("op") and n.endswith(".csv")]
                if not ops:
                    logger.warning("[NSE]  No op*.csv found in archive")
                    return None
                content = zf.read(ops[0]).decode("utf-8", errors="ignore")

            lines = [l for l in content.splitlines() if l.strip()]
            if not lines:
                return None

            headers   = [h.strip() for h in next(csv.reader([lines[0]]))]
            col_index = {h: i for i, h in enumerate(headers) if h in TARGET}
            if not col_index:
                logger.warning(f"[NSE]  Target columns not found. Got: {headers[:10]}")
                return None

            sums = {k: 0.0 for k in TARGET}
            for row in csv.reader(lines[1:]):
                for col, idx in col_index.items():
                    if idx < len(row):
                        raw_val = row[idx].strip().replace(",", "")
                        if raw_val:
                            try:
                                sums[col] += float(raw_val)
                            except ValueError:
                                pass
            return sums
        except Exception as exc:
            logger.error(f"[NSE]  Parse error: {exc}")
            return None

    def _log_ok(self, date_str: str, d: Dict) -> None:
        logger.info(
            f"[NSE]  [OK] {date_str}  CONT={d['NO_OF_CONT']:.0f}  "
            f"TRADE={d['NO_OF_TRADE']:.0f}  NOTION={d['NOTION_VAL']:.2f}  PR={d['PR_VAL']:.2f}"
        )


# ============================================================================
# 2. BSE Derivatives collector  (IO + IF product types only)
# ============================================================================
class BSEFOCollector(BaseCollector):
    """MS_<YYYYMMDD>-01.csv → sums 4 columns, IO+IF rows only"""

    def __init__(self):
        super().__init__("BSE", BSE_CACHE, BSE_HOME, BSE_HEADERS, BSE_HOLIDAYS)

    def _get_url_and_file(self, date: datetime) -> Tuple[str, str]:
        name = "MS_" + date.strftime("%Y%m%d") + "-01.csv"
        return BSE_FO_BASE + name, name

    def _parse(self, raw: bytes) -> Optional[Dict]:
        try:
            text  = raw.decode("utf-8", errors="ignore")
            lines = [l for l in text.splitlines() if l.strip()]
            if len(lines) < 2:
                return None

            # Verify it really is the bhavcopy (guard against HTML error pages)
            if b"Market Summary" not in raw[:200]:
                logger.warning("[BSE]  Response doesn't look like bhavcopy CSV")
                return None

            header_cols = [h.strip() for h in next(csv.reader([lines[0]]))]
            idx_map     = {h: i for i, h in enumerate(header_cols)}

            col_map = {
                "BSE_TTL_TRADED_QTY":   idx_map.get("Total Traded Quantity",                       BSE_COL_TTL_QTY),
                "BSE_TTL_TRADED_VAL":   idx_map.get("Total Traded Value (in Thousands)(absolute)", BSE_COL_TTL_VAL),
                "BSE_AVG_TRADED_PRICE": idx_map.get("Average Traded Price",                        BSE_COL_AVG_PRICE),
                "BSE_NO_OF_TRADES":     idx_map.get("No. of Trades",                               BSE_COL_NO_TRADES),
            }
            prod_idx = idx_map.get("Product Type", 4)

            sums      = {k: 0.0 for k in col_map}
            row_count = 0
            for row in csv.reader(lines[1:]):
                if not row:
                    continue
                prod = row[prod_idx].strip() if prod_idx < len(row) else ""
                if prod not in ("IO", "IF"):
                    continue
                for col, idx in col_map.items():
                    if idx < len(row):
                        v = row[idx].strip().replace(",", "")
                        if v:
                            try:
                                sums[col] += float(v)
                            except ValueError:
                                pass
                row_count += 1

            if row_count:
                logger.info(f"[BSE]  Parsed {row_count} IO/IF rows")
                return sums
            return None
        except Exception as exc:
            logger.error(f"[BSE]  Parse error: {exc}")
            return None

    def _log_ok(self, date_str: str, d: Dict) -> None:
        logger.info(
            f"[BSE]  [OK] {date_str}  QTY={d['BSE_TTL_TRADED_QTY']:.0f}  "
            f"VAL={d['BSE_TTL_TRADED_VAL']:.2f}  AVG={d['BSE_AVG_TRADED_PRICE']:.4f}  "
            f"TRADES={d['BSE_NO_OF_TRADES']:.0f}"
        )


# ============================================================================
# 3. NSE FO Category Turnover collector
# ============================================================================
class NSECatCollector(BaseCollector):
    """fo_cat_turnover_<DDMMYY>.xls → Retail buy/sell/avg (Rs.Cr)"""

    def __init__(self):
        super().__init__("CAT", NSE_CAT_CACHE, NSE_HOME, NSE_HEADERS, NSE_HOLIDAYS)

    def _get_url_and_file(self, date: datetime) -> Tuple[str, str]:
        name = "fo_cat_turnover_" + date.strftime("%d%m%y") + ".xls"
        return NSE_CAT_BASE + name, name

    def _get_magic(self) -> bytes:
        return b"\xd0\xcf"   # OLE2 / XLS magic

    def _parse(self, raw: bytes) -> Optional[Dict]:
        return _parse_retail_xls(raw, "[CAT]", "RETAIL_BUY_CR", "RETAIL_SELL_CR", "RETAIL_AVG_CR")

    def _log_ok(self, date_str: str, d: Dict) -> None:
        logger.info(
            f"[CAT]  [OK] {date_str}  Buy={d['RETAIL_BUY_CR']:.2f}  "
            f"Sell={d['RETAIL_SELL_CR']:.2f}  Avg={d['RETAIL_AVG_CR']:.2f} (Rs.Cr)"
        )


# ============================================================================
# 4. NSE Equity Category Turnover collector
# ============================================================================
class NSEEqCatCollector(BaseCollector):
    """cat_turnover_<DDMMYY>.xls → Retail buy/sell/avg (Rs.Cr)"""

    def __init__(self):
        super().__init__("EQCAT", NSE_EQCAT_CACHE, NSE_HOME, NSE_HEADERS, NSE_HOLIDAYS)

    def _get_url_and_file(self, date: datetime) -> Tuple[str, str]:
        name = "cat_turnover_" + date.strftime("%d%m%y") + ".xls"
        return NSE_EQCAT_BASE + name, name

    def _get_magic(self) -> bytes:
        return b"\xd0\xcf"

    def _parse(self, raw: bytes) -> Optional[Dict]:
        return _parse_retail_xls(raw, "[EQCAT]", "EQ_RETAIL_BUY_CR", "EQ_RETAIL_SELL_CR", "EQ_RETAIL_AVG_CR")

    def _log_ok(self, date_str: str, d: Dict) -> None:
        logger.info(
            f"[EQCAT] [OK] {date_str}  Buy={d['EQ_RETAIL_BUY_CR']:.2f}  "
            f"Sell={d['EQ_RETAIL_SELL_CR']:.2f}  Avg={d['EQ_RETAIL_AVG_CR']:.2f} (Rs.Cr)"
        )


# ============================================================================
# 5. NSE Margin Trading collector
# ============================================================================
class NSEMrgCollector(BaseCollector):
    """mrg_trading_<DDMMYY>.zip → 4 aggregate metrics (Rs.Lakh)"""

    def __init__(self):
        super().__init__("MRG", NSE_MRG_CACHE, NSE_HOME, NSE_HEADERS, NSE_HOLIDAYS)

    def _get_url_and_file(self, date: datetime) -> Tuple[str, str]:
        name = "mrg_trading_" + date.strftime("%d%m%y") + ".zip"
        return NSE_MRG_BASE + name, name

    def _get_magic(self) -> bytes:
        return b"PK"

    def _parse(self, raw: bytes) -> Optional[Dict]:
        """
        CSV inside the zip has rows:
          1, Scripwise Total Outstanding on beginning of day, <value>
          2, Fresh Exposure taken during the day,             <value>
          3, Exposure liquidated during the day,              <value>
          4, Net scripwise outstanding at end of day,         <value>
        Values in Rs.Lakhs.
        Older files have an extra leading blank column (Sr.No. at col[1], value col[3]).
        """
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as zf:
                csv_name = next(n for n in zf.namelist() if n.lower().endswith(".csv"))
                content  = zf.read(csv_name).decode("utf-8", errors="replace")

            sr_to_key = {
                "1": "NSE_MRG_OUTSTANDING_BOD_LAKHS",
                "2": "NSE_MRG_FRESH_EXP_LAKHS",
                "3": "NSE_MRG_EXP_LIQ_LAKHS",
                "4": "NSE_MRG_NET_EOD_LAKHS",
            }
            metrics: Dict[str, Optional[float]] = {k: None for k in sr_to_key.values()}

            for row in csv.reader(content.splitlines()):
                if not row:
                    continue
                # Try new format (Sr.No.@col[0], value@col[2]) then old (col[1], col[3])
                for sr_col, val_col in ((0, 2), (1, 3)):
                    sr = row[sr_col].strip() if sr_col < len(row) else ""
                    if sr in sr_to_key and val_col < len(row):
                        key = sr_to_key[sr]
                        if metrics[key] is None:
                            try:
                                metrics[key] = float(row[val_col].strip().replace(",", ""))
                            except (ValueError, IndexError):
                                pass
                        break

            found = {k: v for k, v in metrics.items() if v is not None}
            if len(found) < 4:
                logger.warning(f"[MRG]  Only {len(found)}/4 metrics parsed")
                return found or None
            return found
        except Exception as exc:
            logger.error(f"[MRG]  Parse error: {exc}")
            return None

    def _log_ok(self, date_str: str, d: Dict) -> None:
        logger.info(
            f"[MRG]  [OK] {date_str}  BOD={d['NSE_MRG_OUTSTANDING_BOD_LAKHS']:.2f}  "
            f"Fresh={d['NSE_MRG_FRESH_EXP_LAKHS']:.2f}  "
            f"Liq={d['NSE_MRG_EXP_LIQ_LAKHS']:.2f}  EOD={d['NSE_MRG_NET_EOD_LAKHS']:.2f} (Rs.Lakh)"
        )


# ============================================================================
# 6. NSE Participant-wise FO Volume collector  (Client type only)
# ============================================================================
class NSEParticipantCollector(BaseCollector):
    """
    fao_participant_vol_<DDMMYYYY>.csv  (8-digit date in URL)
    Picks the row where Client Type == 'Client' and extracts:
      - Total Long Contracts  (col 13)
      - Future Index Long     (col  1)
      - Future Index Short    (col  2)
    """

    def __init__(self):
        super().__init__("PART", NSE_PART_CACHE, NSE_HOME, NSE_HEADERS, NSE_HOLIDAYS)

    def _get_url_and_file(self, date: datetime) -> Tuple[str, str]:
        name = "fao_participant_vol_" + date.strftime("%d%m%Y") + ".csv"
        return NSE_PART_BASE + name, name

    def _parse(self, raw: bytes) -> Optional[Dict]:
        try:
            lines = [l for l in raw.decode("utf-8", errors="ignore").splitlines() if l.strip()]
            if len(lines) < 2:
                return None

            # Row 0 is a title; row 1 is the header; data starts at row 2
            # Find the header row (contains 'Client Type')
            header_row = None
            data_start  = 0
            for i, line in enumerate(lines):
                if "Client Type" in line:
                    header_row = i
                    data_start = i + 1
                    break
            if header_row is None:
                logger.warning("[PART]  Header row not found")
                return None

            headers = [h.strip().strip('"') for h in next(csv.reader([lines[header_row]]))]
            idx     = {h: i for i, h in enumerate(headers)}

            col_total_long = idx.get("Total Long Contracts", 13)
            col_fi_long    = idx.get("Future Index Long",    1)
            col_fi_short   = idx.get("Future Index Short",   2)

            for line in lines[data_start:]:
                row = [c.strip().strip('"') for c in next(csv.reader([line]))]
                if not row:
                    continue
                if row[0].strip().lower() == "client":
                    total_long = float(row[col_total_long].replace(",", ""))
                    fi_long    = float(row[col_fi_long].replace(",", ""))
                    fi_short   = float(row[col_fi_short].replace(",", ""))
                    logger.info(
                        f"[PART]  Client — TotalLong={total_long:.0f}  "
                        f"FILong={fi_long:.0f}  FIShort={fi_short:.0f}"
                    )
                    return {
                        "NSE_CLT_TOTAL_LONG":  total_long,
                        "NSE_CLT_FUT_IDX_LONG":  fi_long,
                        "NSE_CLT_FUT_IDX_SHORT": fi_short,
                    }

            logger.warning("[PART]  'Client' row not found")
            return None
        except Exception as exc:
            logger.error(f"[PART]  Parse error: {exc}")
            return None

    def _log_ok(self, date_str: str, d: Dict) -> None:
        logger.info(
            f"[PART]  [OK] {date_str}  TotalLong={d['NSE_CLT_TOTAL_LONG']:.0f}  "
            f"FILong={d['NSE_CLT_FUT_IDX_LONG']:.0f}  FIShort={d['NSE_CLT_FUT_IDX_SHORT']:.0f}"
        )


# ============================================================================
# Shared XLS parser (NSE Cat + NSE Eq Cat share identical structure)
# ============================================================================
def _parse_retail_xls(
    raw: bytes,
    tag: str,
    buy_key: str,
    sell_key: str,
    avg_key: str,
) -> Optional[Dict]:
    try:
        wb = xlrd.open_workbook(file_contents=raw)
        sh = wb.sheets()[0]

        for row_idx in range(sh.nrows):
            category = str(sh.cell_value(row_idx, 1)).strip().lower()
            if category == "retail":
                buy  = float(sh.cell_value(row_idx, 2))
                sell = float(sh.cell_value(row_idx, 3))
                avg  = (buy + sell) / 2.0
                logger.info(f"{tag}  Retail — Buy={buy:.2f}  Sell={sell:.2f}  Avg={avg:.2f}")
                return {buy_key: buy, sell_key: sell, avg_key: avg}

        logger.warning(f"{tag}  'Retail' row not found in XLS")
        return None
    except Exception as exc:
        logger.error(f"{tag}  XLS parse error: {exc}")
        return None


# ============================================================================
# 7. NSE TBG Daily Collector (CM + FO + Commodity consolidation)
# ============================================================================
class TBGDailyCollector:
    """
    Collects daily TBG (Trading and Borrowing) data from three NSE API endpoints:
      - CM (Cash Market): https://www.nseindia.com/api/historicalOR/cm/tbg/daily
      - FO (Futures & Options): https://www.nseindia.com/api/historicalOR/fo/tbg/daily
      - COMDER (Commodity Derivatives): https://www.nseindia.com/api/historicalOR/comder/tbg/daily
    
    Returns consolidated data with 28 columns (CM, FO, and Commodity metrics).
    """

    def __init__(self):
        self.tag = "TBG"
        self.cache_file = "nse_tbg_cache.json"
        self.cache = {}
        self.session = None
        self._setup_session()
        self.load_cache()

    def _setup_session(self) -> None:
        """Setup requests session with retry strategy and headers."""
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
        
        self.session = requests.Session()
        retry = Retry(total=3, backoff_factor=0.5, status_forcelist=(500, 502, 504))
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)
        
        # Browser-like headers
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
            'Referer': 'https://www.nseindia.com',
        })

    def load_cache(self) -> None:
        """Load TBG cache from JSON file."""
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, encoding="utf-8") as f:
                    self.cache = json.load(f)
                logger.info(f"[{self.tag}] Cache loaded: {len(self.cache)} entries")
            except Exception as exc:
                logger.warning(f"[{self.tag}] Cache load error: {exc}")
                self.cache = {}

    def save_cache(self) -> None:
        """Save TBG cache to JSON file."""
        try:
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, indent=2)
            logger.info(f"[{self.tag}] Cache saved: {len(self.cache)} entries")
        except Exception as exc:
            logger.error(f"[{self.tag}] Cache save error: {exc}")

    def fetch_segment_data(self, segment: str, month: str, year: str) -> list:
        """Fetch TBG data for a specific segment and month with separate session."""
        url_map = {
            "cm": "https://www.nseindia.com/api/historicalOR/cm/tbg/daily",
            "fo": "https://www.nseindia.com/api/historicalOR/fo/tbg/daily",
            "comder": "https://www.nseindia.com/api/historicalOR/comder/tbg/daily",
        }
        
        if segment not in url_map:
            return []
        
        try:
            url = url_map[segment]
            # Use 4-digit year format (e.g., "2026") for FO and COMDER, 2-digit (e.g., "26") for CM
            if segment.lower() in ["fo", "comder"]:
                year_param = year if len(year) == 4 else ("20" + year)
            else:
                year_param = year if len(year) == 2 else year[-2:]
            
            params = {"month": month, "year": year_param}
            response = self.session.get(url, params=params, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                if "data" in data:
                    data_list = data["data"]
                    if isinstance(data_list, list):
                        logger.debug(f"[{self.tag}] {segment.upper()}: Fetched {len(data_list)} records for {month}/{year_param}")
                        return data_list
            else:
                logger.debug(f"[{self.tag}] {segment.upper()} HTTP {response.status_code} for {month}/{year_param}")
        except requests.Timeout:
            logger.debug(f"[{self.tag}] {segment.upper()} timeout for {month}/{year}")
        except Exception as exc:
            logger.debug(f"[{self.tag}] {segment.upper()} error: {exc}")
        
        return []

    def extract_record_data(self, record: dict) -> dict:
        """Extract actual data from record (handles nested 'data' key if present)."""
        if "data" in record and isinstance(record["data"], dict):
            return record["data"]
        return record

    def parse_date(self, date_str: str) -> str:
        """Parse date string to DDMMYYYY format."""
        if not date_str:
            return ""
        
        # Try various date formats
        formats = ["%d-%b-%Y", "%d %b %Y", "%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%d-Feb-%Y"]
        for fmt in formats:
            try:
                dt = datetime.strptime(date_str.strip(), fmt)
                return dt.strftime("%d%m%Y")
            except ValueError:
                continue
        
        return ""

    def consolidate_records(self, cm_records: list, fo_records: list, comder_records: list) -> dict:
        """Consolidate records from three segments by date."""
        consolidated = {}
        
        # Extract actual data and build dictionaries indexed by date
        cm_by_date = {}
        for r in cm_records:
            data = self.extract_record_data(r)
            # Try different date field names
            date_str = data.get("F_TIMESTAMP", "") or data.get("CDT_DATE_ORDER", "") or data.get("date", "")
            date_key = self.parse_date(date_str)
            if date_key:
                cm_by_date[date_key] = data
        
        fo_by_date = {}
        for r in fo_records:
            data = self.extract_record_data(r)
            # Try different date field names for FO data
            date_str = data.get("date", "") or data.get("DATE_ORDER", "")
            date_key = self.parse_date(date_str)
            if date_key:
                fo_by_date[date_key] = data
        
        comder_by_date = {}
        for r in comder_records:
            data = self.extract_record_data(r)
            # Try different date field names for COMDER data
            date_str = data.get("date", "") or data.get("DATE_ORDER", "")
            date_key = self.parse_date(date_str)
            if date_key:
                comder_by_date[date_key] = data
        
        # Merge all dates
        all_dates = set(cm_by_date.keys()) | set(fo_by_date.keys()) | set(comder_by_date.keys())
        
        for date_key in all_dates:
            if not date_key:
                continue
                
            merged = {}
            
            # Extract CM data (handles both CDT_ prefixed and raw field names)
            if date_key in cm_by_date:
                cm = cm_by_date[date_key]
                merged["CM_NOS_OF_SECURITY_TRADES"] = cm.get("CDT_NOS_OF_SECURITY_TRADES", cm.get("NOS_OF_SECURITY_TRADES", 0))
                merged["CM_NOS_OF_TRADES"] = cm.get("CDT_NOS_OF_TRADES", cm.get("NOS_OF_TRADES", 0))
                merged["CM_TRADES_QTY"] = cm.get("CDT_TRADES_QTY", cm.get("TRADES_QTY", 0))
                merged["CM_TRADES_VALUES"] = cm.get("CDT_TRADES_VALUES", cm.get("TRADES_VALUES", 0))
            
            # Extract FO data (with multiple field name variations)
            if date_key in fo_by_date:
                fo = fo_by_date[date_key]
                # Index Futures
                merged["FO_INDEX_FUT_QTY"] = fo.get("Index_Futures_QTY", fo.get("INDEX_FUT_QTY", 0))
                merged["FO_INDEX_FUT_VAL"] = fo.get("Index_Futures_VAL", fo.get("INDEX_FUT_VAL", 0))
                # Stock Futures
                merged["FO_STOCK_FUT_QTY"] = fo.get("Stock_Futures_QTY", fo.get("STOCK_FUT_QTY", 0))
                merged["FO_STOCK_FUT_VAL"] = fo.get("Stock_Futures_VAL", fo.get("STOCK_FUT_VAL", 0))
                # Index Options
                merged["FO_INDEX_OPT_QTY"] = fo.get("Index_Options_QTY", fo.get("INDEX_OPT_QTY", 0))
                merged["FO_INDEX_OPT_VAL"] = fo.get("Index_Options_VAL", fo.get("INDEX_OPT_VAL", 0))
                merged["FO_INDEX_OPT_PREM_VAL"] = fo.get("Index_Options_PREM_VAL", fo.get("INDEX_OPT_PREM_VAL", 0))
                merged["FO_INDEX_OPT_PUT_CALL_RATIO"] = fo.get("Index_Options_PUT_CALL_RATIO", fo.get("INDEX_OPT_PUT_CALL_RATIO", 0))
                # Stock Options
                merged["FO_STOCK_OPT_QTY"] = fo.get("Stock_Options_QTY", fo.get("STOCK_OPT_QTY", 0))
                merged["FO_STOCK_OPT_VAL"] = fo.get("Stock_Options_VAL", fo.get("STOCK_OPT_VAL", 0))
                merged["FO_STOCK_OPT_PREM_VAL"] = fo.get("Stock_Options_PREM_VAL", fo.get("STOCK_OPT_PREM_VAL", 0))
                merged["FO_STOCK_OPT_PUT_CALL_RATIO"] = fo.get("Stock_Options_PUT_CALL_RATIO", fo.get("STOCK_OPT_PUT_CALL_RATIO", 0))
                # FO Totals
                merged["FO_TOTAL_FO_QTY"] = fo.get("F&O_Total_QTY", fo.get("Total_FO_QTY", fo.get("TOTAL_FO_QTY", 0)))
                merged["FO_TOTAL_FO_VAL"] = fo.get("F&O_Total_VAL", fo.get("Total_FO_VAL", fo.get("TOTAL_FO_VAL", 0)))
                merged["FO_TOTAL_TRADED_PREM_VAL"] = fo.get("Total_Traded_PREM_VAL", fo.get("TOTAL_TRADED_PREM_VAL", 0))
                merged["FO_TOTAL_PUT_CALL_RATIO"] = fo.get("F&O_Total_PUT_CALL_RATIO", fo.get("Total_PUT_CALL_RATIO", fo.get("TOTAL_PUT_CALL_RATIO", 0)))
            
            # Extract Commodity data (handles FUT_COM, OPT_COM field names)
            if date_key in comder_by_date:
                com = comder_by_date[date_key]
                merged["COM_FUT_QTY"] = com.get("FUT_COM_TOT_TRADED_QTY", com.get("FUT_QTY", 0))
                merged["COM_FUT_VAL"] = com.get("FUT_COM_TOT_TRADED_VAL", com.get("FUT_VAL", 0))
                merged["COM_OPT_QTY"] = com.get("OPT_COM_TOT_TRADED_QTY", com.get("OPT_QTY", 0))
                merged["COM_OPT_VAL"] = com.get("OPT_COM_TOT_TRADED_VAL", com.get("OPT_VAL", 0))
                merged["COM_OPT_PREM"] = com.get("OPT_COM_PREM", com.get("OPT_PREM", 0))
                merged["COM_TOTAL_QTY"] = com.get("TOTAL_TRADED_QTY", com.get("TOTAL_QTY", 0))
                merged["COM_TOTAL_VAL"] = com.get("TOTAL_TRADED_VAL", com.get("TOTAL_VAL", 0))
            
            if merged:
                consolidated[date_key] = merged
        
        return consolidated

    def collect(self) -> None:
        """Fetch and consolidate TBG data from all three segments."""
        # Fetch for Feb 2025 to Feb 2026 (months with data)
        months = [
            ("Feb", "25"), ("Mar", "25"), ("Apr", "25"), ("May", "25"), 
            ("Jun", "25"), ("Jul", "25"), ("Aug", "25"), ("Sep", "25"),
            ("Oct", "25"), ("Nov", "25"), ("Dec", "25"), ("Jan", "26"), ("Feb", "26")
        ]
        
        all_cm = []
        all_fo = []
        all_comder = []
        
        for month, year in months:
            # Fetch from all three segments for this month
            cm_data = self.fetch_segment_data("cm", month, year)
            fo_data = self.fetch_segment_data("fo", month, year)
            comder_data = self.fetch_segment_data("comder", month, year)
            
            all_cm.extend(cm_data)
            all_fo.extend(fo_data)
            all_comder.extend(comder_data)
        
        # Consolidate by date
        new_records = self.consolidate_records(all_cm, all_fo, all_comder)
        
        # Update cache
        if new_records:
            self.cache.update(new_records)
            logger.info(f"[{self.tag}] Loaded {len(new_records)} trading days")
            self.save_cache()
        else:
            logger.info(f"[{self.tag}] Cache current: {len(self.cache)} entries")

# ============================================================================
# NSE MFSS (Mutual Fund Systematic Side-pocket) Collector
# ============================================================================
class MFSSCollector:
    """Fetches NSE MFSS trade statistics data (subscription/redemption orders)."""

    def __init__(self):
        self.tag = "MFSS"
        self.cache_file = NSE_MFSS_CACHE
        self.cache = {}
        self.load_cache()

    def load_cache(self) -> None:
        """Load MFSS cache from JSON file."""
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, encoding="utf-8") as f:
                    self.cache = json.load(f)
                logger.info(f"[{self.tag}] Cache loaded: {len(self.cache)} entries")
            except Exception as exc:
                logger.warning(f"[{self.tag}] Cache load error: {exc}")
                self.cache = {}

    def save_cache(self) -> None:
        """Save MFSS cache to JSON file."""
        try:
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, indent=2)
            logger.info(f"[{self.tag}] Cache saved: {len(self.cache)} entries")
        except Exception as exc:
            logger.error(f"[{self.tag}] Cache save error: {exc}")

    def collect(self) -> None:
        """Fetch MFSS data from API and cache it."""
        logger.info(f"[{self.tag}] Fetching MFSS trade statistics data...")
        
        try:
            # On first run, backfill Feb 1, 2025 to Sep 30, 2025
            # On subsequent runs, fetch incrementally from last cached date
            if self.cache:
                # Incremental: fetch from day after last cached date to today
                last_date_str = max(self.cache.keys())
                try:
                    last_date = datetime.strptime(last_date_str, "%d%m%Y")
                    start_date = last_date + timedelta(days=1)
                except ValueError:
                    start_date = CURRENT_DATE - timedelta(days=7)
                end_date = CURRENT_DATE
            else:
                # First run: backfill Feb 1, 2025 to Sep 30, 2025
                start_date = datetime(2025, 2, 1)
                end_date = datetime(2025, 9, 30)
            
            # Format dates for API (DD-MM-YYYY)
            from_date = start_date.strftime("%d-%m-%Y")
            to_date = end_date.strftime("%d-%m-%Y")
            
            logger.info(f"[{self.tag}] Fetching from {from_date} to {to_date}")
            
            # Fetch from API with JSON-specific headers (no gzip)
            session = requests.Session()
            api_headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": NSE_HOME,
                "Accept": "application/json, text/plain, */*",
            }
            session.headers.update(api_headers)
            
            # Warm up session
            try:
                home_resp = session.get(NSE_HOME, timeout=REQUEST_TIMEOUT)
                logger.info(f"[{self.tag}] Session warm-up: HTTP {home_resp.status_code}")
            except Exception as exc:
                logger.warning(f"[{self.tag}] Session warm-up failed: {exc}")
            
            # Fetch MFSS data
            params = {"from": from_date, "to": to_date}
            resp = session.get(NSE_MFSS_API, params=params, timeout=REQUEST_TIMEOUT)
            
            if resp.status_code == 200:
                data = resp.json()
                if "data" in data and isinstance(data["data"], list):
                    count = 0
                    for record in data["data"]:
                        if record.get("MF_DATE"):
                            try:
                                # Parse date and convert to cache key format (DDMMYYYY)
                                date_obj = datetime.strptime(record["MF_DATE"], "%d-%b-%Y")
                                date_key = date_obj.strftime("%d%m%Y")
                                
                                # Store only numeric values
                                self.cache[date_key] = {
                                    "MF_NOS_OF_SUB_ORDER": int(record.get("MF_NOS_OF_SUB_ORDER", 0)),
                                    "MF_TOT_SUB_AMT": float(record.get("MF_TOT_SUB_AMT", 0)),
                                    "MF_NOS_OF_RED_ORDER": int(record.get("MF_NOS_OF_RED_ORDER", 0)),
                                    "MF_TOT_RED_AMT": float(record.get("MF_TOT_RED_AMT", 0)),
                                    "MF_TOT_ORDER": int(record.get("MF_TOT_ORDER", 0)),
                                }
                                count += 1
                            except (ValueError, TypeError) as e:
                                logger.warning(f"[{self.tag}] Error parsing record: {e}")
                    
                    logger.info(f"[{self.tag}] Fetched {count} new records")
                    self.save_cache()
                else:
                    logger.warning(f"[{self.tag}] Unexpected response format")
            else:
                logger.error(f"[{self.tag}] API returned {resp.status_code}")
        
        except Exception as exc:
            logger.error(f"[{self.tag}] Fetch error: {exc}")

# ============================================================================
# NSE Market Turnover Summary (Orders) Collector
# ============================================================================
class MarketTurnoverCollector:
    """Fetches NSE Market Turnover Summary data (daily noOfOrders by segment)."""

    def __init__(self):
        self.tag = "TURNOVER"
        self.cache_file = NSE_MARKET_TURNOVER_CACHE
        self.cache = {}
        self.load_cache()

    def load_cache(self) -> None:
        """Load Market Turnover cache from JSON file."""
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, encoding="utf-8") as f:
                    self.cache = json.load(f)
                logger.info(f"[{self.tag}] Cache loaded: {len(self.cache)} entries")
            except Exception as exc:
                logger.warning(f"[{self.tag}] Cache load error: {exc}")
                self.cache = {}

    def save_cache(self) -> None:
        """Save Market Turnover cache to JSON file."""
        try:
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, indent=2)
            logger.info(f"[{self.tag}] Cache saved: {len(self.cache)} entries")
        except Exception as exc:
            logger.error(f"[{self.tag}] Cache save error: {exc}")

    def collect(self) -> None:
        """Fetch Market Turnover from getMarketTurnover API — flat list with segment-based items."""
        logger.info(f"[{self.tag}] Fetching Market Turnover (getMarketTurnover API)...")
        
        try:
            session = requests.Session()
            api_headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": NSE_HOME,
                "Accept": "application/json, text/plain, */*",
            }
            session.headers.update(api_headers)
            
            # Warm up session
            try:
                home_resp = session.get(NSE_HOME, timeout=REQUEST_TIMEOUT)
                logger.info(f"[{self.tag}] Session warm-up: HTTP {home_resp.status_code}")
            except Exception as exc:
                logger.warning(f"[{self.tag}] Session warm-up failed: {exc}")
            
            # Fetch Market Turnover data
            resp = session.get(NSE_MARKET_TURNOVER_API, timeout=REQUEST_TIMEOUT)
            
            if resp.status_code == 200:
                raw = resp.json()
                # API returns {"data": {"data": [...], "timeStamp": "..."}}
                # Navigate to the inner list: raw["data"]["data"]
                items = []
                if isinstance(raw, list):
                    items = raw
                elif isinstance(raw, dict):
                    inner = raw.get("data", raw)
                    if isinstance(inner, dict):
                        items = inner.get("data", [])
                    elif isinstance(inner, list):
                        items = inner
                logger.info(f"[{self.tag}] Parsed {len(items)} segments from API response")
                
                if items:
                    # Extract date from updatedOn field of first item
                    date_key = None
                    for item in items:
                        ts = item.get("updatedOn", "")
                        if ts:
                            try:
                                date_obj = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
                                date_key = date_obj.strftime("%d%m%Y")
                                break
                            except ValueError:
                                pass
                    
                    if date_key:
                        orders_data = {}
                        
                        # Segment name mapping
                        for item in items:
                            seg = (item.get("segment") or "").strip()
                            seg_lower = seg.lower()
                            
                            if "equit" in seg_lower and "deriv" not in seg_lower:
                                # Equities / Cash Market
                                orders_data["EQUITY_TOTAL_NO_OF_ORDERS"] = item.get("noOfOrders", 0)
                            elif "equity" in seg_lower and "deriv" in seg_lower:
                                # Equity Derivatives / F&O
                                orders_data["FO_TOTAL_NO_OF_ORDERS"] = item.get("noOfOrders", 0)
                            elif "commodity" in seg_lower:
                                # Commodity Derivatives
                                orders_data["COMMODITY_TOTAL_NO_OF_ORDERS"] = item.get("noOfOrders", 0)
                            elif "mutual" in seg_lower or "mf" in seg_lower:
                                # Mutual Fund
                                orders_data["MF_NO_OF_ORDERS"] = item.get("noOfOrders", 0)
                                orders_data["MF_NOTIONAL_TURNOVER"] = item.get("totalValue", 0)
                            
                            logger.info(f"[{self.tag}]   segment='{seg}' orders={item.get('noOfOrders',0)} value={item.get('totalValue',0)}")
                        
                        # Store in cache (overwrite today's data if it exists)
                        self.cache[date_key] = orders_data
                        logger.info(f"[{self.tag}] Fetched {len(orders_data)} metrics for {date_key}")
                        self.save_cache()
                    else:
                        logger.warning(f"[{self.tag}] Could not extract date from response")
                else:
                    logger.warning(f"[{self.tag}] Empty or unexpected response format")
            else:
                logger.error(f"[{self.tag}] API returned {resp.status_code}")
        
        except Exception as exc:
            logger.error(f"[{self.tag}] Fetch error: {exc}")

# ============================================================================
# Combined CSV writer
# ============================================================================
def write_output(
    nse: Dict, bse: Dict, cat: Dict, eq_cat: Dict, mrg: Dict, part: Dict, tbg: Dict = None,
    nse_reg_inv: Dict = None, bse_reg_inv: Dict = None, mfss: Dict = None, turnover: Dict = None
) -> None:
    if tbg is None:
        tbg = {}
    if nse_reg_inv is None:
        nse_reg_inv = {}
    if bse_reg_inv is None:
        bse_reg_inv = {}
    if mfss is None:
        mfss = {}
    if turnover is None:
        turnover = {}
    
    # Extract the single/latest investor count values (not date-keyed)
    # The caches contain a single entry with the date key of when it was fetched
    nse_reg_inv_count = None
    bse_reg_inv_count = None
    
    if nse_reg_inv:
        # Get the most recent (or only) investor count from the cache
        nse_reg_inv_count = next(iter(nse_reg_inv.values()), None) if nse_reg_inv else None
    if bse_reg_inv:
        # Get the most recent (or only) investor count from the cache
        bse_reg_inv_count = next(iter(bse_reg_inv.values()), None) if bse_reg_inv else None
    
    all_dates = sorted(
        set(nse) | set(bse) | set(cat) | set(eq_cat) | set(mrg) | set(part) | set(tbg) | set(mfss) | set(turnover),
        key=lambda s: datetime.strptime(s, "%d%m%Y"),
    )

    HEADER = [
        "Date",
        "NSE_NO_OF_CONT", "NSE_NO_OF_TRADE", "NSE_NOTION_VAL", "NSE_PR_VAL",
        "BSE_TTL_TRADED_QTY", "BSE_TTL_TRADED_VAL", "BSE_AVG_TRADED_PRICE", "BSE_NO_OF_TRADES",
        "NSE_CAT_RETAIL_BUY_CR", "NSE_CAT_RETAIL_SELL_CR", "NSE_CAT_RETAIL_AVG_CR",
        "NSE_EQ_RETAIL_BUY_CR",  "NSE_EQ_RETAIL_SELL_CR",  "NSE_EQ_RETAIL_AVG_CR",
        "NSE_MRG_OUTSTANDING_BOD_LAKHS", "NSE_MRG_FRESH_EXP_LAKHS",
        "NSE_MRG_EXP_LIQ_LAKHS",        "NSE_MRG_NET_EOD_LAKHS",
        "NSE_CLT_TOTAL_LONG_CONT", "NSE_CLT_FUT_IDX_LONG", "NSE_CLT_FUT_IDX_SHORT",
        "NSE_REG_INVESTORS", "BSE_REG_INVESTORS",
        # NSE MFSS (Mutual Fund) data (5 columns)
        "NSE_MFSS_NOS_OF_SUB_ORDER", "NSE_MFSS_TOT_SUB_AMT", "NSE_MFSS_NOS_OF_RED_ORDER", "NSE_MFSS_TOT_RED_AMT", "NSE_MFSS_TOT_ORDER",
        # NSE Market Turnover - Daily Orders: Totals for Equities, EqDerivatives, CommodityDerivatives + MF (5 columns)
        "NSE_EQUITY_TOTAL_NO_OF_ORDERS", "NSE_FO_TOTAL_NO_OF_ORDERS", "NSE_COMMODITY_TOTAL_NO_OF_ORDERS",
        "NSE_MF_NO_OF_ORDERS", "NSE_MF_NOTIONAL_TURNOVER",
        # NSE TBG (Trading and Borrowing) Daily data (28 columns)
        "NSE_TBG_CM_NOS_OF_SECURITY_TRADES", "NSE_TBG_CM_NOS_OF_TRADES", "NSE_TBG_CM_TRADES_QTY", "NSE_TBG_CM_TRADES_VALUES",
        "NSE_TBG_FO_INDEX_FUT_QTY", "NSE_TBG_FO_INDEX_FUT_VAL", "NSE_TBG_FO_STOCK_FUT_QTY", "NSE_TBG_FO_STOCK_FUT_VAL",
        "NSE_TBG_FO_INDEX_OPT_QTY", "NSE_TBG_FO_INDEX_OPT_VAL", "NSE_TBG_FO_INDEX_OPT_PREM_VAL", "NSE_TBG_FO_INDEX_OPT_PUT_CALL_RATIO",
        "NSE_TBG_FO_STOCK_OPT_QTY", "NSE_TBG_FO_STOCK_OPT_VAL", "NSE_TBG_FO_STOCK_OPT_PREM_VAL", "NSE_TBG_FO_STOCK_OPT_PUT_CALL_RATIO",
        "NSE_TBG_FO_TOTAL_FO_QTY", "NSE_TBG_FO_TOTAL_FO_VAL", "NSE_TBG_FO_TOTAL_TRADED_PREM_VAL", "NSE_TBG_FO_TOTAL_PUT_CALL_RATIO",
        "NSE_TBG_COM_FUT_QTY", "NSE_TBG_COM_FUT_VAL", "NSE_TBG_COM_OPT_QTY", "NSE_TBG_COM_OPT_VAL",
        "NSE_TBG_COM_OPT_PREM", "NSE_TBG_COM_TOTAL_QTY", "NSE_TBG_COM_TOTAL_VAL",
    ]

    def f2(v):  return f"{v:.2f}" if v is not None else ""
    def f4(v):  return f"{v:.4f}" if v is not None else ""
    def fi(v):  return f"{v:.0f}" if v is not None else ""
    def fn(v):  return str(v) if v else ""

    try:
        with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(HEADER)
            for ds in all_dates:
                display = datetime.strptime(ds, "%d%m%Y").strftime("%d-%m-%Y")
                n = nse.get(ds);  b = bse.get(ds)
                c = cat.get(ds);  e = eq_cat.get(ds)
                m = mrg.get(ds);  p = part.get(ds)
                t = tbg.get(ds)
                
                row_data = [
                    display,
                    f2(n and n["NO_OF_CONT"]),    f2(n and n["NO_OF_TRADE"]),
                    f2(n and n["NOTION_VAL"]),    f2(n and n["PR_VAL"]),
                    f2(b and b["BSE_TTL_TRADED_QTY"]),
                    f2(b and b["BSE_TTL_TRADED_VAL"]),
                    f4(b and b["BSE_AVG_TRADED_PRICE"]),
                    f2(b and b["BSE_NO_OF_TRADES"]),
                    f2(c and c["RETAIL_BUY_CR"]),   f2(c and c["RETAIL_SELL_CR"]),
                    f2(c and c["RETAIL_AVG_CR"]),
                    f2(e and e["EQ_RETAIL_BUY_CR"]), f2(e and e["EQ_RETAIL_SELL_CR"]),
                    f2(e and e["EQ_RETAIL_AVG_CR"]),
                    f2(m and m["NSE_MRG_OUTSTANDING_BOD_LAKHS"]),
                    f2(m and m["NSE_MRG_FRESH_EXP_LAKHS"]),
                    f2(m and m["NSE_MRG_EXP_LIQ_LAKHS"]),
                    f2(m and m["NSE_MRG_NET_EOD_LAKHS"]),
                    fi(p and p["NSE_CLT_TOTAL_LONG"]),
                    fi(p and p["NSE_CLT_FUT_IDX_LONG"]),
                    fi(p and p["NSE_CLT_FUT_IDX_SHORT"]),
                    fi(nse_reg_inv_count),
                    fi(bse_reg_inv_count),
                ]
                
                # Add NSE MFSS data
                mf_data = mfss.get(ds)
                if mf_data:
                    row_data.extend([
                        fi(mf_data.get("MF_NOS_OF_SUB_ORDER", "")),
                        f2(mf_data.get("MF_TOT_SUB_AMT", "")),
                        fi(mf_data.get("MF_NOS_OF_RED_ORDER", "")),
                        f2(mf_data.get("MF_TOT_RED_AMT", "")),
                        fi(mf_data.get("MF_TOT_ORDER", "")),
                    ])
                else:
                    # Fill with empty strings if no NSE MFSS data
                    row_data.extend([""] * 5)
                
                # Add NSE Market Turnover (Orders) data
                to_data = turnover.get(ds)
                if to_data:
                    row_data.extend([
                        fi(to_data.get("EQUITY_TOTAL_NO_OF_ORDERS", 0)),
                        fi(to_data.get("FO_TOTAL_NO_OF_ORDERS", 0)),
                        fi(to_data.get("COMMODITY_TOTAL_NO_OF_ORDERS", 0)),
                        fi(to_data.get("MF_NO_OF_ORDERS", 0)),
                        fi(to_data.get("MF_NOTIONAL_TURNOVER", 0)),
                    ])
                else:
                    # Fill with empty strings if no Market Turnover data
                    row_data.extend([""] * 5)
                
                # Add NSE TBG daily data
                if t:
                    row_data.extend([
                        fn(t.get("CM_NOS_OF_SECURITY_TRADES", "")),
                        fn(t.get("CM_NOS_OF_TRADES", "")),
                        fn(t.get("CM_TRADES_QTY", "")),
                        fn(t.get("CM_TRADES_VALUES", "")),
                        fn(t.get("FO_INDEX_FUT_QTY", "")),
                        fn(t.get("FO_INDEX_FUT_VAL", "")),
                        fn(t.get("FO_STOCK_FUT_QTY", "")),
                        fn(t.get("FO_STOCK_FUT_VAL", "")),
                        fn(t.get("FO_INDEX_OPT_QTY", "")),
                        fn(t.get("FO_INDEX_OPT_VAL", "")),
                        fn(t.get("FO_INDEX_OPT_PREM_VAL", "")),
                        fn(t.get("FO_INDEX_OPT_PUT_CALL_RATIO", "")),
                        fn(t.get("FO_STOCK_OPT_QTY", "")),
                        fn(t.get("FO_STOCK_OPT_VAL", "")),
                        fn(t.get("FO_STOCK_OPT_PREM_VAL", "")),
                        fn(t.get("FO_STOCK_OPT_PUT_CALL_RATIO", "")),
                        fn(t.get("FO_TOTAL_FO_QTY", "")),
                        fn(t.get("FO_TOTAL_FO_VAL", "")),
                        fn(t.get("FO_TOTAL_TRADED_PREM_VAL", "")),
                        fn(t.get("FO_TOTAL_PUT_CALL_RATIO", "")),
                        fn(t.get("COM_FUT_QTY", "")),
                        fn(t.get("COM_FUT_VAL", "")),
                        fn(t.get("COM_OPT_QTY", "")),
                        fn(t.get("COM_OPT_VAL", "")),
                        fn(t.get("COM_OPT_PREM", "")),
                        fn(t.get("COM_TOTAL_QTY", "")),
                        fn(t.get("COM_TOTAL_VAL", "")),
                    ])
                else:
                    # Fill with empty strings if no TBG data
                    row_data.extend([""] * 28)
                
                w.writerow(row_data)
        
        logger.info(f"Output written → {OUTPUT_FILE}  ({len(all_dates)} rows, {len(HEADER)} columns)")
    except Exception as exc:
        logger.error(f"Failed to write output: {exc}")


# ============================================================================
# Entry point
# ============================================================================
def main() -> None:
    logger.info("=" * 70)
    logger.info("NSE + BSE FO Market Data Collector (with MFSS + TBG + Reg Investors)")
    logger.info("=" * 70)

    collectors = []
    try:
        steps = [
            ("NSE FO",                  NSEFOCollector),
            ("BSE Derivatives",         BSEFOCollector),
            ("NSE FO Cat",              NSECatCollector),
            ("NSE Equity Cat",          NSEEqCatCollector),
            ("NSE Margin Trading",      NSEMrgCollector),
            ("NSE Participant Vol",     NSEParticipantCollector),
        ]
        for label, Cls in steps:
            logger.info(f"\n--- {label} ---")
            c = Cls()
            collectors.append(c)
            c.collect()

        # Load TBG daily data
        logger.info(f"\n--- TBG Daily Data ---")
        tbg_collector = TBGDailyCollector()
        tbg_collector.collect()

        # Collect MFSS data
        logger.info(f"\n--- NSE MFSS (Mutual Fund) Data ---")
        mfss_collector = MFSSCollector()
        mfss_collector.collect()

        # Collect Market Turnover (Orders) data
        logger.info(f"\n--- NSE Market Turnover (Daily Orders) ---")
        turnover_collector = MarketTurnoverCollector()
        turnover_collector.collect()

        # Collect registered investors data
        logger.info(f"\n--- Registered Investors ---")
        nse_reg_inv_cache, bse_reg_inv_cache = collect_registered_investors()

        logger.info("\n--- Writing combined output ---")
        nse, bse, cat, eq_cat, mrg, part = [c.cache for c in collectors]
        write_output(nse, bse, cat, eq_cat, mrg, part, tbg_collector.cache, nse_reg_inv_cache, bse_reg_inv_cache, mfss_collector.cache, turnover_collector.cache)
        logger.info("All done.")

    except KeyboardInterrupt:
        logger.info("Interrupted — saving partial results ...")
        caches = [c.cache for c in collectors]
        while len(caches) < 6:
            caches.append({})
        tbg_cache = {}
        mfss_cache = {}
        nse_reg_inv_cache = {}
        bse_reg_inv_cache = {}
        if len(collectors) >= 6:
            tbg_cache = getattr(collectors[6] if len(collectors) > 6 else collectors[0], 'cache', {})
        write_output(*caches, tbg_cache, nse_reg_inv_cache, bse_reg_inv_cache)

    except Exception as exc:
        logger.error(f"Fatal error: {exc}", exc_info=True)
        raise


if __name__ == "__main__":
    main()
