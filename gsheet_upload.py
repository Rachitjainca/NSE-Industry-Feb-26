"""
Upload nse_fo_aggregated_data.csv → Google Sheet
Sheet ID : 1AeHIxoEgLgPiF0s9Sk4AwRZZAbDvqPsRt2NjryTxX-M
Auth     : Service-account JSON (path set by KEY_FILE below)
"""

import csv
import os
import sys
import gspread
from google.oauth2.service_account import Credentials

# ── Config ────────────────────────────────────────────────────────────────────
SHEET_ID       = "1AeHIxoEgLgPiF0s9Sk4AwRZZAbDvqPsRt2NjryTxX-M"
CSV_FILE       = "nse_fo_aggregated_data.csv"
KEY_FILE       = "groww-data-488513-384d7e65fa4f.json"
WORKSHEET_NAME = "Sheet1"          # change if your tab has a different name

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
# ─────────────────────────────────────────────────────────────────────────────


def upload() -> None:
    # Locate key file
    key_path = KEY_FILE
    if not os.path.exists(key_path):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        key_path = os.path.join(script_dir, KEY_FILE)
    if not os.path.exists(key_path):
        print(f"ERROR: Service-account key not found at '{KEY_FILE}'")
        sys.exit(1)

    # Authenticate
    creds = Credentials.from_service_account_file(key_path, scopes=SCOPES)
    gc    = gspread.authorize(creds)

    # Open sheet
    sh = gc.open_by_key(SHEET_ID)
    try:
        ws = sh.worksheet(WORKSHEET_NAME)
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.sheet1          # fall back to first tab

    # Read CSV
    csv_path = CSV_FILE
    if not os.path.exists(csv_path):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        csv_path = os.path.join(script_dir, CSV_FILE)
    if not os.path.exists(csv_path):
        print(f"ERROR: CSV file not found: '{CSV_FILE}'")
        sys.exit(1)

    with open(csv_path, newline="", encoding="utf-8") as f:
        data = list(csv.reader(f))

    if not data:
        print("CSV is empty — nothing to upload.")
        return

    # Write to sheet (clear first, then batch-update)
    ws.clear()
    ws.update(range_name="A1", values=data)

    print(f"✓ Uploaded {len(data) - 1} data rows + header to Google Sheet '{sh.title}' → '{ws.title}'")


if __name__ == "__main__":
    upload()
