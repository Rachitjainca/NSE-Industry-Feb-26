# Quick Start Guide

## 🚀 Get Started in 2 Minutes

### Step 1: Install Dependencies
Open PowerShell or Command Prompt and run:
```bash
pip install -r requirements.txt
```

### Step 2: Run the Aggregator
Choose one method:

**Option A: Double-click batch file (Windows)**
- Find `run_aggregator.bat`
- Double-click to run

**Option B: PowerShell**
```powershell
.\run_aggregator.ps1
```

**Option C: Command Line**
```bash
python nse_fo_aggregator.py
```

## ✅ What to Expect

### First Run (Feb 1, 2025 to Today)
- Takes 5-10 minutes (depends on internet)
- Downloads ~250+ days of data
- Creates `nse_fo_aggregated.csv` with results

### Subsequent Runs
- Runs in <1 second
- Only fetches new days since last run
- Appends to existing `nse_fo_aggregated.csv`

## 📊 Output File Format

**File**: `nse_fo_aggregated.csv`

```
Date,NO_OF_CONT,NO_OF_TRADE,NOTION_VAL,PR_VAL
01-Feb-2025,1234567,2345678,987654321,123456789
04-Feb-2025,1345678,2456789,1098765432,234567890
...
```

Open in Excel or any spreadsheet application.

## 🔍 Verify Installation

Test single date download:
```bash
python test_aggregator.py 01022025
```

This will:
- Download one file
- Extract and parse it
- Show sums for that day
- Help verify everything works

## ⚠️ Common Issues

### Python not found?
- Install Python 3.8+ from https://www.python.org
- Make sure "Add Python to PATH" is checked during install
- Restart computer after installation

### Still not working?
- Delete `nse_fo_metadata.json` and `nse_cache/` folder
- Run again to restart from Feb 1, 2025

### Slow download?
- Increase `TIMEOUT_SECONDS` in `nse_fo_aggregator.py`
- Check internet connection
- Try running late night (less traffic)

## 🛠️ Advanced Usage

### Test single date (DDMMYYYY format):
```bash
python test_aggregator.py 01022025 04022025 05022025
```

### View logs in detail:
Edit `nse_fo_aggregator.py`, change:
```python
logging.basicConfig(level=logging.DEBUG)  # More detailed output
```

### Add NSE holidays:
Edit `NSE_HOLIDAYS` set in `nse_fo_aggregator.py`

### Change start date:
Edit `START_DATE` in `nse_fo_aggregator.py`

## 📁 Files Created

- `nse_fo_aggregated.csv` - Main output with sums
- `nse_fo_metadata.json` - Tracking info (don't edit!)
- `nse_cache/` - Downloaded ZIP files (cache)

## 🆘 Need Help?

1. Check README.md for detailed documentation
2. Review CONFIG_REFERENCE.txt for customization
3. Run test_aggregator.py to test specific dates
4. Check logs in console output

---

**That's it!** Your NSE data aggregator is ready to use. 🎉
