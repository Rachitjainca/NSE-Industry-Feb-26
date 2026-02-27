# Parse a locally downloaded BSE CSV file and inject its aggregated data
# into bse_fo_cache.json for a specific date, then regenerate the output CSV.
#
# Usage: python inject_bse_local.py <path_to_bse_csv> <DDMMYYYY>
# Example: python inject_bse_local.py "C:/Users/rachit.jain/Desktop/MS_20260227-01.csv" 27022026
import sys, json, csv, os
from datetime import datetime

# -- BSE column indices (0-based) --
BSE_COL_TTL_QTY   = 15
BSE_COL_TTL_VAL   = 16
BSE_COL_AVG_PRICE = 17
BSE_COL_NO_TRADES = 18

BSE_CACHE_FILE = "bse_fo_cache.json"
NSE_CACHE_FILE = "nse_fo_cache.json"
OUTPUT_FILE    = "nse_fo_aggregated_data.csv"

def parse_bse_csv(filepath, expected_date_key=None):
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        raw = f.read()
    lines = [l for l in raw.splitlines() if l.strip()]
    if len(lines) < 2:
        print("ERROR: file seems empty")
        return None

    header_cols = [h.strip() for h in next(csv.reader([lines[0]]))]
    print(f"Columns ({len(header_cols)}): {header_cols[:5]} ...")

    # Validate the date in the first data row (column 0 = "Market Summary Date")
    if expected_date_key:
        first_row = next(csv.reader([lines[1]]))
        file_date_raw = first_row[0].strip()  # e.g. "27 Feb 2026"
        try:
            file_date = datetime.strptime(file_date_raw, "%d %b %Y")
            expected_date = datetime.strptime(expected_date_key, "%d%m%Y")
            if file_date != expected_date:
                print(f"\nWARNING: File internal date is '{file_date_raw}' ({file_date.strftime('%d-%m-%Y')})")
                print(f"         but you specified target date {expected_date.strftime('%d-%m-%Y')}.")
                answer = input("Proceed anyway? (yes/no): ").strip().lower()
                if answer != 'yes':
                    print("Aborted.")
                    sys.exit(1)
            else:
                print(f"Date check passed: file is for {file_date.strftime('%d-%m-%Y')}")
        except Exception:
            print(f"(Could not parse file date from first row: {file_date_raw!r})")

    name_to_idx = {h: i for i, h in enumerate(header_cols)}
    col_map = {
        'BSE_TTL_TRADED_QTY':   name_to_idx.get("Total Traded Quantity",                       BSE_COL_TTL_QTY),
        'BSE_TTL_TRADED_VAL':   name_to_idx.get("Total Traded Value (in Thousands)(absolute)",  BSE_COL_TTL_VAL),
        'BSE_AVG_TRADED_PRICE': name_to_idx.get("Average Traded Price",                        BSE_COL_AVG_PRICE),
        'BSE_NO_OF_TRADES':     name_to_idx.get("No. of Trades",                               BSE_COL_NO_TRADES),
    }

    sums = {k: 0.0 for k in col_map}
    row_count = 0
    for row in csv.reader(lines[1:]):
        if not row:
            continue
        for col, idx in col_map.items():
            if idx < len(row):
                raw_val = (row[idx] or '').strip().replace(',', '')
                if raw_val:
                    try:
                        sums[col] += float(raw_val)
                    except ValueError:
                        pass
        row_count += 1

    print(f"Parsed {row_count} rows")
    print(f"Sums: {sums}")
    return sums

def write_combined_output(nse_cache, bse_cache):
    all_dates = sorted(
        set(nse_cache.keys()) | set(bse_cache.keys()),
        key=lambda s: datetime.strptime(s, "%d%m%Y")
    )
    with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([
            'Date',
            'NSE_NO_OF_CONT', 'NSE_NO_OF_TRADE', 'NSE_NOTION_VAL', 'NSE_PR_VAL',
            'BSE_TTL_TRADED_QTY', 'BSE_TTL_TRADED_VAL',
            'BSE_AVG_TRADED_PRICE', 'BSE_NO_OF_TRADES',
        ])
        for date_str in all_dates:
            display = datetime.strptime(date_str, "%d%m%Y").strftime("%d-%m-%Y")
            nse = nse_cache.get(date_str)
            bse = bse_cache.get(date_str)
            writer.writerow([
                display,
                f"{nse['NO_OF_CONT']:.2f}"  if nse else '',
                f"{nse['NO_OF_TRADE']:.2f}" if nse else '',
                f"{nse['NOTION_VAL']:.2f}"  if nse else '',
                f"{nse['PR_VAL']:.2f}"      if nse else '',
                f"{bse['BSE_TTL_TRADED_QTY']:.2f}"   if bse else '',
                f"{bse['BSE_TTL_TRADED_VAL']:.2f}"   if bse else '',
                f"{bse['BSE_AVG_TRADED_PRICE']:.4f}" if bse else '',
                f"{bse['BSE_NO_OF_TRADES']:.2f}"     if bse else '',
            ])
    print(f"Output written: {OUTPUT_FILE} ({len(all_dates)} rows)")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python inject_bse_local.py <csv_path> <DDMMYYYY>")
        sys.exit(1)

    csv_path = sys.argv[1]
    date_key = sys.argv[2]

    # Validate date
    try:
        datetime.strptime(date_key, "%d%m%Y")
    except ValueError:
        print(f"ERROR: date must be in DDMMYYYY format, got: {date_key}")
        sys.exit(1)

    if not os.path.exists(csv_path):
        print(f"ERROR: file not found: {csv_path}")
        sys.exit(1)

    print(f"\nParsing: {csv_path}")
    data = parse_bse_csv(csv_path, expected_date_key=date_key)
    if not data:
        sys.exit(1)

    # Load BSE cache
    bse_cache = {}
    if os.path.exists(BSE_CACHE_FILE):
        with open(BSE_CACHE_FILE) as f:
            bse_cache = json.load(f)

    # Inject
    bse_cache[date_key] = data
    with open(BSE_CACHE_FILE, 'w') as f:
        json.dump(bse_cache, f, indent=2)
    print(f"\nInjected {date_key} into {BSE_CACHE_FILE} ({len(bse_cache)} total entries)")

    # Regenerate output
    nse_cache = {}
    if os.path.exists(NSE_CACHE_FILE):
        with open(NSE_CACHE_FILE) as f:
            nse_cache = json.load(f)

    write_combined_output(nse_cache, bse_cache)
