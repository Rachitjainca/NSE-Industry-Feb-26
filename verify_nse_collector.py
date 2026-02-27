#!/usr/bin/env python3
"""
Verification script for NSE FO Data Collector setup
Tests connectivity, dependencies, and basic functionality
"""

import sys
import os
from datetime import datetime

def check_python_version():
    """Check Python version"""
    print("Checking Python version...", end=" ")
    version = sys.version_info
    if version.major >= 3 and version.minor >= 7:
        print(f"✓ Python {version.major}.{version.minor}.{version.micro}")
        return True
    else:
        print(f"✗ Python {version.major}.{version.minor} (need 3.7+)")
        return False

def check_dependencies():
    """Check if required packages are installed"""
    print("Checking dependencies...", end=" ")
    try:
        import requests
        print(f"✓ requests {requests.__version__}")
        return True
    except ImportError:
        print("✗ requests not installed")
        return False

def check_nse_connectivity():
    """Check if NSE website is reachable"""
    print("Checking NSE connectivity...", end=" ")
    try:
        import requests
        base_url = "https://nsearchives.nseindia.com/archives/fo/mkt/"
        
        # Test with a small timeout
        response = requests.head(base_url, timeout=5)
        if response.status_code < 400:
            print(f"✓ Connected (HTTP {response.status_code})")
            return True
        else:
            print(f"✗ Server returned {response.status_code}")
            return False
    except requests.exceptions.Timeout:
        print("✗ Connection timeout")
        return False
    except requests.exceptions.ConnectionError:
        print("✗ Cannot connect to NSE servers")
        return False
    except Exception as e:
        print(f"✗ Connection error: {e}")
        return False

def check_file_structure():
    """Check if required files exist"""
    print("Checking file structure...")
    required_files = [
        "nse_fo_data_collector.py",
        "run_nse_collector.py",
        "requirements.txt"
    ]
    
    all_ok = True
    for fname in required_files:
        if os.path.exists(fname):
            print(f"  ✓ {fname}")
        else:
            print(f"  ✗ {fname} (missing)")
            all_ok = False
    
    return all_ok

def check_write_permissions():
    """Check if we can write to the directory"""
    print("Checking write permissions...", end=" ")
    try:
        test_file = ".write_test_file"
        with open(test_file, 'w') as f:
            f.write("test")
        os.remove(test_file)
        print("✓ Can write files")
        return True
    except Exception as e:
        print(f"✗ {e}")
        return False

def check_cache_file():
    """Check if cache file exists"""
    print("Checking cache file...", end=" ")
    if os.path.exists("nse_fo_cache.json"):
        try:
            import json
            with open("nse_fo_cache.json", 'r') as f:
                data = json.load(f)
            count = len(data)
            print(f"✓ Found with {count} cached dates")
            return True
        except Exception as e:
            print(f"✗ Exists but corrupted: {e}")
            return False
    else:
        print("✓ Not present (will be created on first run)")
        return True

def check_output_file():
    """Check if output file exists"""
    print("Checking output file...", end=" ")
    if os.path.exists("nse_fo_aggregated_data.csv"):
        try:
            with open("nse_fo_aggregated_data.csv", 'r') as f:
                lines = f.readlines()
            rows = len(lines) - 1  # subtract header
            print(f"✓ Found with {rows} data rows")
            return True
        except Exception as e:
            print(f"✗ Exists but corrupted: {e}")
            return False
    else:
        print("✓ Not present (will be created on first run)")
        return True

def check_logs():
    """Check if log file exists"""
    print("Checking logs...", end=" ")
    if os.path.exists("nse_fo_collector.log"):
        try:
            with open("nse_fo_collector.log", 'r') as f:
                lines = f.readlines()
            print(f"✓ Found with {len(lines)} log entries")
            return True
        except Exception as e:
            print(f"✗ Exists but corrupted: {e}")
            return False
    else:
        print("✓ Not present (will be created on first run)")
        return True

def test_date_parsing():
    """Test date parsing functionality"""
    print("Testing date parsing...", end=" ")
    try:
        from datetime import datetime
        test_date = "01022025"
        parsed = datetime.strptime(test_date, "%d%m%Y")
        formatted = parsed.strftime("%d-%m-%Y")
        if formatted == "01-02-2025":
            print(f"✓ {test_date} → {formatted}")
            return True
        else:
            print(f"✗ Incorrect parsing: {formatted}")
            return False
    except Exception as e:
        print(f"✗ {e}")
        return False

def main():
    """Run all checks"""
    print("=" * 60)
    print("NSE FO Data Collector - Setup Verification")
    print("=" * 60)
    print()
    
    checks = [
        ("Environment", [
            check_python_version,
            check_dependencies,
        ]),
        ("Connectivity", [
            check_nse_connectivity,
        ]),
        ("File System", [
            check_file_structure,
            check_write_permissions,
        ]),
        ("Data Files", [
            check_cache_file,
            check_output_file,
            check_logs,
        ]),
        ("Functionality", [
            test_date_parsing,
        ])
    ]
    
    results = []
    for section, check_functions in checks:
        print(f"\n{section}:")
        for check_func in check_functions:
            result = check_func()
            results.append(result)
    
    # Summary
    print("\n" + "=" * 60)
    passed = sum(results)
    total = len(results)
    
    if all(results):
        print(f"✓ All checks passed ({passed}/{total})")
        print("=" * 60)
        print("\nYou're ready to run the NSE FO Data Collector!")
        print("\nExecute one of these commands:")
        print("  • python run_nse_collector.py")
        print("  • python nse_fo_data_collector.py")
        print("  • .\run_nse_collector.bat (Windows)")
        print("  • .\run_nse_collector.ps1 (Windows PowerShell)")
        return 0
    else:
        print(f"✗ Some checks failed ({passed}/{total})")
        print("=" * 60)
        print("\nPlease fix the issues above and try again.")
        print("See NSE_FO_COLLECTOR_README.md for troubleshooting.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
