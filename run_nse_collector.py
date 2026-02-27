#!/usr/bin/env python3
"""
Runner script for NSE FO Data Collector
Use this script to run the data collector with a single command
"""

import subprocess
import sys
import os

def check_requirements():
    """Check if required packages are installed"""
    try:
        import requests
        print("✓ requests module found")
        return True
    except ImportError:
        print("✗ requests module not found")
        print("Installing requirements...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
            return True
        except Exception as e:
            print(f"Failed to install requirements: {e}")
            return False

def main():
    print("=" * 60)
    print("NSE FO Market Data Collector Runner")
    print("=" * 60)
    print()
    
    if not check_requirements():
        print("\nFailed to install dependencies. Exiting.")
        sys.exit(1)
    
    print("\nStarting data collection...")
    print("This may take some time depending on the date range and network speed.\n")
    
    try:
        import nse_fo_data_collector
        nse_fo_data_collector.main()
    except Exception as e:
        print(f"Error running collector: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
