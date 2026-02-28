#!/usr/bin/env python3
"""
Task Scheduler for Daily NSE + BSE Market Data Collection at 7PM
==================================================================
Runs the complete collector.py script every day at 7:00 PM
Collects: NSE FO, BSE Derivatives, Categories, Margin Trading, TBG, & Registered Investors
"""

import schedule
import time
import subprocess
import logging
from datetime import datetime
import sys

# ── Logging ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    handlers=[
        logging.FileHandler("scheduler.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def run_collector():
    """Run the complete market data collector."""
    logger.info("=" * 70)
    logger.info("🕖 Scheduled Task: Running full market data collection at 7PM")
    logger.info("=" * 70)
    
    try:
        result = subprocess.run(
            [sys.executable, "Data 1/collector.py"],
            capture_output=True,
            text=True,
            timeout=1800  # 30 minutes timeout for full collection
        )
        
        if result.returncode == 0:
            logger.info("✅ Collector executed successfully")
            logger.info("Uploading to Google Sheets...")
            
            # Run gsheet upload
            try:
                upload_result = subprocess.run(
                    [sys.executable, "Data 1/gsheet_upload.py"],
                    capture_output=True,
                    text=True,
                    timeout=300  # 5 minutes timeout for upload
                )
                
                if upload_result.returncode == 0:
                    logger.info("✅ Google Sheets upload completed successfully")
                    if upload_result.stdout:
                        logger.info(f"{upload_result.stdout}")
                else:
                    logger.error(f"❌ Google Sheets upload failed with return code {upload_result.returncode}")
                    if upload_result.stderr:
                        logger.error(f"Error:\n{upload_result.stderr}")
            except subprocess.TimeoutExpired:
                logger.error("❌ Google Sheets upload timed out")
            except Exception as exc:
                logger.error(f"❌ Failed to execute gsheet upload: {exc}")
        else:
            logger.error(f"❌ Collector failed with return code {result.returncode}")
            if result.stderr:
                logger.error(f"Error:\n{result.stderr}")
    
    except subprocess.TimeoutExpired:
        logger.error("❌ Collector execution timed out")
    except Exception as exc:
        logger.error(f"❌ Failed to execute collector: {exc}")


def schedule_tasks():
    """Schedule the daily collection task."""
    # Schedule collector to run at 7:00 PM daily
    schedule.every().day.at("19:00").do(run_collector)
    logger.info("✅ Scheduled: Full market data collection (collector.py) at 19:00 (7:00 PM) daily")


def main():
    """Main scheduler loop."""
    logger.info("=" * 70)
    logger.info("NSE + BSE Market Data Daily Scheduler (7PM)")
    logger.info("=" * 70)
    
    schedule_tasks()
    
    logger.info("Scheduler started. Waiting for scheduled tasks...")
    logger.info("Press Ctrl+C to exit")
    
    try:
        while True:
            schedule.run_pending()
            time.sleep(60)  # Check every minute
    
    except KeyboardInterrupt:
        logger.info("\nScheduler stopped by user")
    except Exception as exc:
        logger.error(f"Scheduler error: {exc}", exc_info=True)
        raise


if __name__ == "__main__":
    main()
