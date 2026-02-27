#!/usr/bin/env python3
"""
NSE Futures & Options Data Aggregator

This script fetches daily FO market data from NSE archives, caches results,
and aggregates sums of NO_OF_CONT, NO_OF_TRADE, NOTION_VAL, and PR_VAL metrics.

Start date: 1st Feb 2025
Handles weekends and NSE holidays gracefully.
"""

import os
import sys
import csv
import zipfile
import requests
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Tuple, Dict
import logging
import json
from io import StringIO, BytesIO

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
BASE_URL = "https://nsearchives.nseindia.com/archives/fo/mkt/"
START_DATE = datetime(2025, 2, 1)
SCRIPT_DIR = Path(__file__).parent
CACHE_DIR = SCRIPT_DIR / "nse_cache"
OUTPUT_FILE = SCRIPT_DIR / "nse_fo_aggregated.csv"
METADATA_FILE = SCRIPT_DIR / "nse_fo_metadata.json"
TIMEOUT_RETRIES = 3
TIMEOUT_SECONDS = 30

# Required columns to sum
REQUIRED_COLUMNS = ["NO_OF_CONT", "NO_OF_TRADE", "NOTION_VAL", "PR_VAL"]

# NSE holidays in 2025-2026 (DDMMYYYY format for reference)
NSE_HOLIDAYS = {
    datetime(2025, 1, 26),   # Republic Day
    datetime(2025, 3, 10),   # Holi
    datetime(2025, 4, 11),   # Good Friday
    datetime(2025, 4, 14),   # Ambedkar Jayanti
    datetime(2025, 4, 17),   # Ram Navami
    datetime(2025, 5, 1),    # May Day
    datetime(2025, 6, 7),    # Eid-ul-Adha
    datetime(2025, 7, 17),   # Muharram
    datetime(2025, 8, 15),   # Independence Day
    datetime(2025, 8, 27),   # Janmashtami
    datetime(2025, 9, 16),   # Milad-un-Nabi
    datetime(2025, 10, 2),   # Gandhi Jayanti
    datetime(2025, 10, 12),  # Dussehra
    datetime(2025, 10, 31),  # Diwali
    datetime(2025, 11, 1),   # Day after Diwali
    datetime(2025, 11, 25),  # Guru Nanak Jayanti
    datetime(2025, 12, 25),  # Christmas
    datetime(2026, 1, 26),   # Republic Day
    datetime(2026, 3, 10),   # Holi
    datetime(2026, 3, 29),   # Good Friday
}

def is_trading_day(date: datetime) -> bool:
    """Check if date is a trading day (not weekend or NSE holiday)"""
    if date.weekday() >= 5:  # Weekend (5=Saturday, 6=Sunday)
        return False
    if date in NSE_HOLIDAYS:
        return False
    return True

def format_date_for_url(date: datetime) -> str:
    """Format date as DDMMYYYY for URL"""
    return date.strftime("%d%m%Y")

def load_metadata() -> Dict:
    """Load metadata about processed files"""
    if METADATA_FILE.exists():
        with open(METADATA_FILE, 'r') as f:
            return json.load(f)
    return {"processed_dates": [], "last_run": None}

def save_metadata(metadata: Dict) -> None:
    """Save metadata about processed files"""
    with open(METADATA_FILE, 'w') as f:
        json.dump(metadata, f, indent=2)

def download_file(date: datetime, retries: int = TIMEOUT_RETRIES) -> Tuple[bool, bytes | None]:
    """
    Download ZIP file from NSE with retry logic and timeout handling
    
    Args:
        date: Date to download file for
        retries: Number of retry attempts
        
    Returns:
        Tuple of (success, file_content)
    """
    date_str = format_date_for_url(date)
    url = f"{BASE_URL}fo{date_str}.zip"
    
    for attempt in range(1, retries + 1):
        try:
            logger.info(f"Downloading {url} (Attempt {attempt}/{retries})")
            response = requests.get(url, timeout=TIMEOUT_SECONDS, allow_redirects=True)
            
            if response.status_code == 200:
                logger.info(f"✓ Successfully downloaded fo{date_str}.zip")
                return True, response.content
            elif response.status_code == 404:
                logger.debug(f"File not found (404): fo{date_str}.zip - likely weekend or holiday")
                return False, None
            else:
                logger.warning(f"HTTP {response.status_code} for fo{date_str}.zip")
                
        except requests.exceptions.Timeout:
            logger.warning(f"Timeout on attempt {attempt}/{retries} for fo{date_str}.zip")
            if attempt == retries:
                logger.error(f"Failed to download fo{date_str}.zip after {retries} retries")
                return False, None
                
        except requests.exceptions.RequestException as e:
            logger.warning(f"Request error on attempt {attempt}/{retries}: {e}")
            if attempt == retries:
                logger.error(f"Failed to download fo{date_str}.zip: {e}")
                return False, None
    
    return False, None

def extract_csv_from_zip(zip_content: bytes, date_str: str) -> Tuple[bool, List[Dict] | None]:
    """
    Extract and parse CSV from ZIP content
    
    Args:
        zip_content: Content of ZIP file
        date_str: Date string for logging
        
    Returns:
        Tuple of (success, parsed_data)
    """
    try:
        with zipfile.ZipFile(BytesIO(zip_content)) as zip_file:
            csv_files = [f for f in zip_file.namelist() if f.endswith('.csv')]
            
            if not csv_files:
                logger.warning(f"No CSV file found in archive for {date_str}")
                return False, None
            
            csv_filename = csv_files[0]
            logger.debug(f"Extracting {csv_filename} from archive")
            
            with zip_file.open(csv_filename) as csv_file:
                content = csv_file.read().decode('latin-1')
                reader = csv.DictReader(StringIO(content))
                rows = list(reader)
                
                logger.info(f"✓ Extracted {len(rows)} rows from {csv_filename}")
                return True, rows
                
    except zipfile.BadZipFile:
        logger.error(f"Invalid ZIP format for {date_str}")
    except Exception as e:
        logger.error(f"Error extracting CSV from {date_str}: {e}")
    
    return False, None

def calculate_sums(data: List[Dict]) -> Dict[str, float]:
    """
    Calculate sums of required columns
    
    Args:
        data: List of CSV rows
        
    Returns:
        Dictionary with column names as keys and sums as values
    """
    sums = {col: 0.0 for col in REQUIRED_COLUMNS}
    
    for row in data:
        for col in REQUIRED_COLUMNS:
            if col in row and row[col]:
                try:
                    sums[col] += float(row[col])
                except (ValueError, TypeError):
                    logger.debug(f"Could not convert {col}={row[col]} to float")
    
    return sums

def load_existing_data() -> Dict[str, Dict]:
    """Load existing aggregated data from output file"""
    data = {}
    if OUTPUT_FILE.exists():
        with open(OUTPUT_FILE, 'r', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                data[row['Date']] = {
                    'NO_OF_CONT': float(row['NO_OF_CONT']),
                    'NO_OF_TRADE': float(row['NO_OF_TRADE']),
                    'NOTION_VAL': float(row['NOTION_VAL']),
                    'PR_VAL': float(row['PR_VAL']),
                }
    return data

def save_aggregated_data(aggregated: Dict[str, Dict]) -> None:
    """Save aggregated data to CSV file"""
    sorted_dates = sorted(aggregated.keys(), key=lambda x: datetime.strptime(x, "%d-%b-%Y"))
    
    with open(OUTPUT_FILE, 'w', newline='') as f:
        fieldnames = ['Date', 'NO_OF_CONT', 'NO_OF_TRADE', 'NOTION_VAL', 'PR_VAL']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        
        writer.writeheader()
        for date_str in sorted_dates:
            sums = aggregated[date_str]
            writer.writerow({
                'Date': date_str,
                'NO_OF_CONT': int(sums['NO_OF_CONT']),
                'NO_OF_TRADE': int(sums['NO_OF_TRADE']),
                'NOTION_VAL': int(sums['NOTION_VAL']),
                'PR_VAL': int(sums['PR_VAL']),
            })
    
    logger.info(f"✓ Saved aggregated data to {OUTPUT_FILE}")

def main():
    """Main execution function"""
    logger.info("=" * 60)
    logger.info("NSE Futures & Options Data Aggregator")
    logger.info("=" * 60)
    
    # Create cache directory
    CACHE_DIR.mkdir(exist_ok=True)
    
    # Load metadata and existing data
    metadata = load_metadata()
    aggregated = load_existing_data()
    
    # Determine last processed date
    if metadata['processed_dates']:
        last_date = datetime.strptime(metadata['processed_dates'][-1], "%d%m%Y")
        current_date = last_date + timedelta(days=1)
    else:
        current_date = START_DATE
    
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    logger.info(f"Start date: {START_DATE.strftime('%d-%b-%Y')}")
    logger.info(f"Last processed: {current_date.strftime('%d-%b-%Y') if metadata['processed_dates'] else 'Never'}")
    logger.info(f"Today: {today.strftime('%d-%b-%Y')}")
    logger.info(f"Processing from: {current_date.strftime('%d-%b-%Y')}")
    
    error_count = 0
    success_count = 0
    
    while current_date <= today:
        date_str_display = current_date.strftime("%d-%b-%Y")
        date_str_url = format_date_for_url(current_date)
        date_str_metadata = current_date.strftime("%d%m%Y")
        
        if not is_trading_day(current_date):
            logger.debug(f"⊘ {date_str_display} - Weekend or holiday, skipping")
            current_date += timedelta(days=1)
            continue
        
        # Download file
        success, file_content = download_file(current_date)
        
        if not success or file_content is None:
            logger.warning(f"✗ Could not obtain data for {date_str_display}")
            error_count += 1
            current_date += timedelta(days=1)
            continue
        
        # Extract and parse CSV
        success, csv_data = extract_csv_from_zip(file_content, date_str_url)
        
        if not success or csv_data is None:
            logger.error(f"✗ Failed to process data for {date_str_display}")
            error_count += 1
            current_date += timedelta(days=1)
            continue
        
        # Calculate sums
        sums = calculate_sums(csv_data)
        aggregated[date_str_display] = sums
        metadata['processed_dates'].append(date_str_metadata)
        success_count += 1
        
        logger.info(f"✓ {date_str_display}: NO_OF_CONT={int(sums['NO_OF_CONT']):,} "
                   f"NO_OF_TRADE={int(sums['NO_OF_TRADE']):,} "
                   f"NOTION_VAL={int(sums['NOTION_VAL']):,} "
                   f"PR_VAL={int(sums['PR_VAL']):,}")
        
        current_date += timedelta(days=1)
    
    # Save results
    if success_count > 0:
        metadata['last_run'] = datetime.now().isoformat()
        save_aggregated_data(aggregated)
        save_metadata(metadata)
        logger.info(f"\n✓ Processed {success_count} trading days successfully")
    
    if error_count > 0:
        logger.warning(f"⚠ {error_count} days failed to process")
    
    logger.info("=" * 60)
    logger.info(f"Output saved to: {OUTPUT_FILE}")
    logger.info("=" * 60)

if __name__ == "__main__":
    main()
