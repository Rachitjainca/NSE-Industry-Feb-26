"""
NSE + BSE FO Market Data Collector
====================================
Collects daily Futures & Options metrics from five NSE/BSE sources,
caches each source to its own JSON file, and writes a combined CSV.

Output: nse_fo_aggregated_data.csv  (19 columns)

Sources
-------
1. NSE FO daily zip        – NO_OF_CONT, NO_OF_TRADE, NOTION_VAL, PR_VAL
2. BSE Derivatives CSV     – TTL_TRADED_QTY/VAL, AVG_TRADED_PRICE, NO_OF_TRADES (IO+IF only)
3. NSE FO Category XLS     – Retail buy/sell/avg (Rs.Cr)
4. NSE Equity Category XLS – Retail buy/sell/avg (Rs.Cr)
5. NSE Margin Trading ZIP  – 4 aggregate metrics (Rs.Lakh)
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
BSE_FO_BASE    = "https://www.bseindia.com/download/Bhavcopy/Derivative/"

# ── Cache file paths ─────────────────────────────────────────────────────────
NSE_FO_CACHE    = "nse_fo_cache.json"
BSE_CACHE       = "bse_fo_cache.json"
NSE_CAT_CACHE   = "nse_cat_cache.json"
NSE_EQCAT_CACHE = "nse_eq_cat_cache.json"
NSE_MRG_CACHE   = "nse_mrg_cache.json"

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
                "1": "MRG_OUTSTANDING_BOD_LAKHS",
                "2": "MRG_FRESH_EXP_LAKHS",
                "3": "MRG_EXP_LIQ_LAKHS",
                "4": "MRG_NET_EOD_LAKHS",
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
            f"[MRG]  [OK] {date_str}  BOD={d['MRG_OUTSTANDING_BOD_LAKHS']:.2f}  "
            f"Fresh={d['MRG_FRESH_EXP_LAKHS']:.2f}  "
            f"Liq={d['MRG_EXP_LIQ_LAKHS']:.2f}  EOD={d['MRG_NET_EOD_LAKHS']:.2f} (Rs.Lakh)"
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
# Combined CSV writer
# ============================================================================
def write_output(
    nse: Dict, bse: Dict, cat: Dict, eq_cat: Dict, mrg: Dict
) -> None:
    all_dates = sorted(
        set(nse) | set(bse) | set(cat) | set(eq_cat) | set(mrg),
        key=lambda s: datetime.strptime(s, "%d%m%Y"),
    )

    HEADER = [
        "Date",
        "NSE_NO_OF_CONT", "NSE_NO_OF_TRADE", "NSE_NOTION_VAL", "NSE_PR_VAL",
        "BSE_TTL_TRADED_QTY", "BSE_TTL_TRADED_VAL", "BSE_AVG_TRADED_PRICE", "BSE_NO_OF_TRADES",
        "NSE_CAT_RETAIL_BUY_CR", "NSE_CAT_RETAIL_SELL_CR", "NSE_CAT_RETAIL_AVG_CR",
        "NSE_EQ_RETAIL_BUY_CR",  "NSE_EQ_RETAIL_SELL_CR",  "NSE_EQ_RETAIL_AVG_CR",
        "MRG_OUTSTANDING_BOD_LAKHS", "MRG_FRESH_EXP_LAKHS",
        "MRG_EXP_LIQ_LAKHS",        "MRG_NET_EOD_LAKHS",
    ]

    def f2(v):  return f"{v:.2f}" if v is not None else ""
    def f4(v):  return f"{v:.4f}" if v is not None else ""

    try:
        with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(HEADER)
            for ds in all_dates:
                display = datetime.strptime(ds, "%d%m%Y").strftime("%d-%m-%Y")
                n = nse.get(ds);  b = bse.get(ds)
                c = cat.get(ds);  e = eq_cat.get(ds); m = mrg.get(ds)
                w.writerow([
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
                    f2(m and m["MRG_OUTSTANDING_BOD_LAKHS"]),
                    f2(m and m["MRG_FRESH_EXP_LAKHS"]),
                    f2(m and m["MRG_EXP_LIQ_LAKHS"]),
                    f2(m and m["MRG_NET_EOD_LAKHS"]),
                ])
        logger.info(f"Output written → {OUTPUT_FILE}  ({len(all_dates)} rows)")
    except Exception as exc:
        logger.error(f"Failed to write output: {exc}")


# ============================================================================
# Entry point
# ============================================================================
def main() -> None:
    logger.info("=" * 60)
    logger.info("NSE + BSE FO Market Data Collector")
    logger.info("=" * 60)

    collectors = []
    try:
        steps = [
            ("NSE FO",             NSEFOCollector),
            ("BSE Derivatives",    BSEFOCollector),
            ("NSE FO Cat",         NSECatCollector),
            ("NSE Equity Cat",     NSEEqCatCollector),
            ("NSE Margin Trading", NSEMrgCollector),
        ]
        for label, Cls in steps:
            logger.info(f"\n--- {label} ---")
            c = Cls()
            collectors.append(c)
            c.collect()

        logger.info("\n--- Writing combined output ---")
        nse, bse, cat, eq_cat, mrg = [c.cache for c in collectors]
        write_output(nse, bse, cat, eq_cat, mrg)
        logger.info("All done.")

    except KeyboardInterrupt:
        logger.info("Interrupted — saving partial results ...")
        caches = [c.cache for c in collectors]
        while len(caches) < 5:
            caches.append({})
        write_output(*caches)

    except Exception as exc:
        logger.error(f"Fatal error: {exc}", exc_info=True)
        raise


if __name__ == "__main__":
    main()
