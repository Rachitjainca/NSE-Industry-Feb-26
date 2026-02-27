#!/usr/bin/env python3
"""
Test utility for NSE FO Data Aggregator

Tests single date downloads and parsing without running full aggregation.
Useful for debugging and verifying setup.
"""

import sys
from datetime import datetime
from pathlib import Path

# Import main script functions
sys.path.insert(0, str(Path(__file__).parent))
from nse_fo_aggregator import (
    download_file, extract_csv_from_zip, calculate_sums,
    format_date_for_url, is_trading_day, logger
)

def test_date(date_str: str):
    """Test download and parsing for a specific date"""
    try:
        date = datetime.strptime(date_str, "%d%m%Y")
    except ValueError:
        logger.error(f"Invalid date format. Use DDMMYYYY (e.g., 01022025)")
        return False
    
    logger.info(f"Testing date: {date.strftime('%d-%b-%Y')}")
    logger.info(f"URL format: fo{format_date_for_url(date)}.zip")
    
    # Check if trading day
    if not is_trading_day(date):
        logger.warning(f"Not a trading day (weekend or holiday)")
        return False
    
    # Download
    success, content = download_file(date)
    if not success or content is None:
        logger.error(f"Download failed")
        return False
    
    logger.info(f"Downloaded {len(content):,} bytes")
    
    # Extract and parse
    success, data = extract_csv_from_zip(content, format_date_for_url(date))
    if not success or data is None:
        logger.error(f"Extraction failed")
        return False
    
    # Calculate sums
    sums = calculate_sums(data)
    logger.info(f"Calculated sums:")
    logger.info(f"  NO_OF_CONT:  {int(sums['NO_OF_CONT']):,}")
    logger.info(f"  NO_OF_TRADE: {int(sums['NO_OF_TRADE']):,}")
    logger.info(f"  NOTION_VAL:  {int(sums['NOTION_VAL']):,}")
    logger.info(f"  PR_VAL:      {int(sums['PR_VAL']):,}")
    
    return True

def main():
    """Main test function"""
    logger.info("=" * 60)
    logger.info("NSE FO Data Aggregator - Test Utility")
    logger.info("=" * 60)
    
    if len(sys.argv) < 2:
        logger.error("Usage: python test_aggregator.py DDMMYYYY [DDMMYYYY ...]")
        logger.error("Example: python test_aggregator.py 01022025 04022025")
        return
    
    for date_str in sys.argv[1:]:
        logger.info("")
        logger.info("-" * 60)
        test_date(date_str)
    
    logger.info("")
    logger.info("=" * 60)
    logger.info("Test completed")
    logger.info("=" * 60)

if __name__ == "__main__":
    main()
