# GitHub Actions Setup Guide - Daily 7 PM Data Collection

This guide explains how to set up automated daily data collection via GitHub Actions.

## ✅ What's Ready

- ✅ Workflow file created: `.github/workflows/daily-data-collection.yml`
- ✅ Scheduled for: **Daily at 7:00 PM IST** (1:30 PM UTC)
- ✅ Runs: collector.py → gsheet_upload.py → Git commit

---

## 📋 Setup Steps (5 minutes)

### Step 1: Add Google Sheets Credentials as GitHub Secret

1. Go to GitHub repo: https://github.com/Rachitjainca/NSE-Industry-Feb-26
2. Click **Settings** (top right)
3. Click **Secrets and variables** → **Actions** (left sidebar)
4. Click **New repository secret**
5. **Name:** `GOOGLE_SHEETS_CREDENTIALS`
6. **Value:** Copy-paste the entire contents of `nse-industry-data-88d157be9048.json`
   ```json
   {
     "type": "service_account",
     "project_id": "nse-industry-data",
     ...entire JSON file...
   }
   ```
7. Click **Add secret**

### Step 2: Push Workflow File to GitHub

The workflow file is already created locally at:
```
.github/workflows/daily-data-collection.yml
```

Push it to your repo:
```powershell
cd "C:\Users\rachit.jain\Desktop\NSE BSE Latest\Data 1"
git add .github/
git commit -m "Add daily data collection workflow"
git push origin main
```

### Step 3: Verify Workflow in GitHub

1. Go to repo: https://github.com/Rachitjainca/NSE-Industry-Feb-26
2. Click **Actions** tab
3. You should see: **"Daily NSE-BSE Data Collection"**
4. Status should show: **"Active"**

### Step 4: Test the Workflow (Optional)

1. Click the workflow: **"Daily NSE-BSE Data Collection"**
2. Click **Run workflow** → **Run workflow** button
3. Wait ~1 minute for execution to complete
4. Check:
   - ✅ Job logs show successful collection
   - ✅ `nse_fo_aggregated_data.csv` updated
   - ✅ New commit pushed to repo

---

## 📅 Automatic Execution

Once set up, the workflow **automatically runs every day at 7:00 PM IST**:

```
19:00 IST (1:30 PM UTC) Daily Trigger
    ↓
[1] Checkout repo
[2] Setup Python
[3] Install packages
[4] Create Google credentials file
[5] Run collector.py
    → Fetches NSE/BSE data
    → Saves to nse_fo_aggregated_data.csv
[6] Run gsheet_upload.py
    → Uploads CSV to Google Sheets
[7] Commit & push updated CSV
[8] Report status
    ↓
Workflow Complete ✓
```

---

## 🔍 Monitoring

### View Workflow Runs

1. Go to: **Actions** tab → **"Daily NSE-BSE Data Collection"**
2. See all past execution times and status
3. Click any run to view detailed logs

### Check Data File

The CSV is automatically committed to repo after each run:
- **File:** `Data 1/nse_fo_aggregated_data.csv`
- **Updated:** Every day at ~7:00 PM IST
- **Format:** 277+ rows × 61 columns

### Check Google Sheets

Data is automatically synced to your Google Sheet:
- **Sheet ID:** From `nse-industry-data-88d157be9048.json` (SHEET_ID in config)
- **Updated:** Every day at ~7:05 PM IST
- **Format:** Full data sync (overwrites previous)

---

## ⚙️ Workflow Details

### Cron Schedule
```
30 13 * * *  # Daily at 1:30 PM UTC = 7:00 PM IST
```

### Environment
- **OS:** Ubuntu (Linux)
- **Python:** 3.11
- **Packages:** requests, pandas, gspread, google-auth-oauthlib, openpyxl, xlrd

### Error Handling
- Both collector.py and gsheet_upload.py use `continue-on-error: true`
- If one fails, the other still executes
- Always commits what was successfully collected

### Credentials
- **Service Account:** `nse-industry-data@nse-industry-data.iam.gserviceaccount.com`
- **Storage:** GitHub Secrets (encrypted, never exposed)
- **File Created:** Dynamically at runtime in workflow

---

## 🚀 Manual Triggers

You can also run the workflow manually **anytime**:

1. Go to **Actions** tab
2. Click **"Daily NSE-BSE Data Collection"**
3. Click **"Run workflow"** dropdown
4. Click **"Run workflow"** button
5. Workflow starts immediately

---

## 📊 Sample Output

When you view the workflow run logs, you'll see:

```
[collector.py output]
2026-02-28 19:00:05  INFO   Fetching CM/Feb/26...
2026-02-28 19:00:10  INFO   ✓ 267 records collected
2026-02-28 19:00:15  INFO   Exporting to CSV...
2026-02-28 19:00:20  INFO   ✓ Exported 820 rows

[gsheet_upload.py output]
2026-02-28 19:00:25  INFO   Reading nse_fo_aggregated_data.csv...
2026-02-28 19:00:30  INFO   ✓ Uploaded 820 rows to Google Sheet

[Git commit]
2026-02-28 19:00:35  INFO   Committing changes...
2026-02-28 19:00:40  INFO   ✓ Pushed to main branch

=== Daily Data Collection Workflow ===
Time: 2026-02-28 19:00:45
Status: Completed
Data rows: 821
```

---

## 🔧 Troubleshooting

### Workflow Not Running at 7 PM

✅ Check 1: Verify secret is set correctly
```powershell
# In GitHub > Settings > Secrets
# GOOGLE_SHEETS_CREDENTIALS should show "Updated X minutes ago"
```

✅ Check 2: Verify workflow file syntax
```powershell
# Validate YAML: https://www.yamllint.com/
# Paste contents of .github/workflows/daily-data-collection.yml
```

✅ Check 3: Check GitHub Actions is enabled
- Go to **Settings** → **Actions** → **General**
- Ensure "Actions permissions" is set to **Allow all actions**

### Workflow Fails

1. Click **Actions** → Failed workflow
2. Click **collect-and-sync** job
3. Review logs to find error
4. Common issues:
   - **Secret not found:** Verify `GOOGLE_SHEETS_CREDENTIALS` in Settings
   - **Python error:** Check `requirements.txt` has all packages
   - **API error:** Check NSE/BSE APIs are working

### Data Not Syncing to Google Sheets

1. Verify credentials file is correct
2. Check Google Sheet ID in `gsheet_upload.py`
3. Ensure service account has edit access to sheet
4. Check workflow logs for upload errors

---

## 📝 Next Steps

1. **Add secret:**
   - Go to GitHub Repo Settings → Secrets
   - Add `GOOGLE_SHEETS_CREDENTIALS`

2. **Push workflow:**
   ```powershell
   git add .github/workflows/
   git commit -m "Add daily data collection"
   git push origin main
   ```

3. **Verify:**
   - Check Actions tab shows workflow
   - Test manually (Run workflow button)

4. **Monitor:**
   - Check Actions tab daily for status
   - Verify CSV updates in repo
   - Verify Google Sheets updates

---

**Status:** ✅ Ready for deployment!

**Questions?** Review the workflow file at `.github/workflows/daily-data-collection.yml`
