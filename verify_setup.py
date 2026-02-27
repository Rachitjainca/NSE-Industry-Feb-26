#!/usr/bin/env python3
"""
NSE FO Data Aggregator - Setup Verification

Checks if the environment is correctly configured and ready to run.
"""

import sys
import subprocess
from pathlib import Path

def check_python_version():
    """Verify Python version is 3.8+"""
    print("\n✓ Checking Python version...")
    version = sys.version_info
    version_str = f"Python {version.major}.{version.minor}.{version.micro}"
    
    if version >= (3, 8):
        print(f"  {version_str} ✓ (Required: 3.8+)")
        return True
    else:
        print(f"  {version_str} ✗ (Required: 3.8+)")
        return False

def check_requests_library():
    """Verify requests library is installed"""
    print("\n✓ Checking requests library...")
    try:
        import requests
        print(f"  requests {requests.__version__} ✓ installed")
        return True
    except ImportError:
        print(f"  requests library ✗ NOT installed")
        print("  Run: pip install -r requirements.txt")
        return False

def check_required_files():
    """Verify all required files are present"""
    print("\n✓ Checking required files...")
    
    required_files = [
        "nse_fo_aggregator.py",
        "requirements.txt",
        "README.md",
        "QUICKSTART.md",
    ]
    
    all_present = True
    for filename in required_files:
        filepath = Path(filename)
        if filepath.exists():
            size = filepath.stat().st_size
            print(f"  {filename} ✓ ({size:,} bytes)")
        else:
            print(f"  {filename} ✗ MISSING!")
            all_present = False
    
    return all_present

def check_write_permission():
    """Verify write permission in current directory"""
    print("\n✓ Checking write permission...")
    try:
        test_file = Path(".setup_test_file_")
        test_file.write_text("test")
        test_file.unlink()
        print(f"  Write permission ✓")
        return True
    except Exception as e:
        print(f"  Write permission ✗: {e}")
        return False

def check_internet():
    """Quick internet connectivity check"""
    print("\n✓ Checking internet connectivity...")
    try:
        import requests
        response = requests.head("https://nsearchives.nseindia.com", timeout=5)
        if response.status_code < 500:
            print(f"  NSE Archives ✓ reachable")
            return True
    except Exception as e:
        print(f"  NSE Archives ✗ unreachable: {e}")
        return False

def main():
    """Run all checks"""
    print("\n" + "=" * 60)
    print("NSE FO Data Aggregator - Setup Verification".center(60))
    print("=" * 60)
    
    checks = [
        ("Python Version", check_python_version),
        ("Requests Library", check_requests_library),
        ("Required Files", check_required_files),
        ("Write Permission", check_write_permission),
        ("Internet Connection", check_internet),
    ]
    
    results = []
    for check_name, check_func in checks:
        try:
            result = check_func()
            results.append((check_name, result))
        except Exception as e:
            print(f"\n✗ {check_name} check failed: {e}")
            results.append((check_name, False))
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY".center(60))
    print("=" * 60)
    
    all_passed = all(result for _, result in results)
    
    for check_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"  {check_name:<25} {status}")
    
    print("=" * 60)
    
    if all_passed:
        print("\n✓ All checks passed! You're ready to run:\n")
        print("  python nse_fo_aggregator.py\n")
        print("Or double-click:\n")
        print("  run_aggregator.bat (Windows)")
        print("  run_aggregator.ps1 (PowerShell)\n")
        return 0
    else:
        failed = [name for name, result in results if not result]
        print(f"\n✗ {len(failed)} check(s) failed:")
        for name in failed:
            print(f"  - {name}")
        
        print("\nPlease fix the issues above and try again.")
        print("\nFor help, see QUICKSTART.md or README.md\n")
        return 1

if __name__ == "__main__":
    sys.exit(main())
