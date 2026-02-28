# TBG Endpoint Investigation Results

## Test Summary

**Status:** ❌ **All TBG endpoints TIMEOUT (unreachable/non-existent)**

### Tested URLs
```
✗ https://www.nseindia.com/api/historicalOR/cm/tbg/daily?month=Feb&year=26
✗ https://www.nseindia.com/api/historicalOR/cm/tbg/daily?month=Feb&year=2026
✗ https://www.nseindia.com/api/historicalOR/fo/tbg/daily?month=Feb&year=26
✗ https://www.nseindia.com/api/historicalOR/fo/tbg/daily?month=Feb&year=2026
✗ https://www.nseindia.com/api/historicalOR/comder/tbg/daily?month=Feb&year=26
✗ https://www.nseindia.com/api/historicalOR/comder/tbg/daily?month=Feb&year=2026
```

**Result:** 5+ second timeout on **every variant** (parameters, URL structure, year format)

---

## Probable Causes

### 1. **Endpoints Don't Exist** 🔴
- `/historicalOR/` path may be incorrect
- These endpoints might not be public NSE APIs
- NSE might require different routing

### 2. **Network/Firewall Block**
- NSE might be blocking/rate-limiting requests
- VPN/Proxy required to access
- Geographic restrictions

### 3. **Authentication Required** 🔐
- Endpoints might need API key or headers
- Session validation required
- CORS restrictions

### 4. **Endpoint Moved/Deprecated** 📦
- These endpoints might be retired
- Replaced with different naming convention
- Data available through different API

---

## Current System Status

### ✅ What's Working (9/10 sources)
- NSE FO (249 cached records)
- BSE Derivatives (255 cached)
- NSE CAT (253 cached)
- NSE Equity CAT (253 cached)
- NSE Margin (254 cached)
- NSE Participants (255 cached)
- MFSS Mutual Funds (140 cached)
- Market Turnover Orders ✅
- Registered Investors ✅

### ❌ What's Not Working
- **TBG Daily Data** (0 cached records)
  - 28 columns remain empty
  - No functionality impact (graceful handling)
  - 7 PM runs succeed anyway

---

## Solutions (Choose One)

### Solution A: DISABLE TBG (Recommended) ✅
**Best for:** Getting 7 PM automation working smoothly NOW

**What to do:**
1. Remove TBG collector from main()
2. Remove 28 TBG columns from CSV
3. Remove fetch_segment_data() logic

**Benefits:**
- Eliminates 15-20 second timeout delays ⚡
- Cleaner CSV (34 columns instead of 61)
- Faster 7 PM runs (3-4 minutes instead of 5+)
- No errors in logs
- Better performance

**Downside:**
- Lose TBG data (but you're not getting it anyway)
- Can add back later if endpoint found

---

### Solution B: KEEP TBG AS-IS
**Best for:** Placeholder in case TBG endpoints come online later

**What happens:**
- Every 7 PM run: 3 timeout delays (~5 sec each = ~15 sec total)
- CSV always generated with empty TBG columns
- System continues gracefully ✅
- If TBG comes online: data auto-populates

**Downside:**
- Slower 7 PM runs (+15-20 seconds per run)
- Timeout messages in logs (not errors, but noise)
- Wasted network calls

---

### Solution C: MANUAL DATA ENTRY
**Best for:** If you have TBG data from another source

**Process:**
1. Download TBG data manually from NSE
2. Convert to JSON cache format
3. Store in `nse_tbg_cache.json`
4. Collector will use cached data

---

### Solution D: FIND CORRECT ENDPOINT
**Best for:** If you have NSE API documentation

**What I need:**
- Correct NSE API endpoint for TBG data
- Required parameters (month/year format, etc.)
- Example response JSON

**Where to find:**
- NSE Knowledge Base / API Documentation
- NSE Developer Portal
- Direct NSE support contact

---

## Recommended Action Plan

### ✅ **IMMEDIATE (Do NOW)**
Choose between A or B above

### A) IF DISABLING TBG:
I can make these changes immediately:
- Remove TBGDailyCollector from main() (1 line)
- Remove TBG fetch calls (2 lines)
- Remove 28 TBG columns from CSV header
- Clean up empty column logic
- **Result:** Faster, cleaner, production-ready

### B) IF KEEPING TBG:
No changes needed - system works as-is
- 7 PM runs will include timeout periods
- TBG columns remain empty
- Everything else works perfectly

---

## Implementation Decision Required

**Please choose:**

```
Option A: DISABLE TBG NOW
  ✓ Fast 7 PM runs (3-4 min)
  ✓ Clean logs
  ✓ 34-column CSV
  → Say: "DISABLE"

Option B: KEEP TBG AS-IS
  ✓ Keep structure in case TBG works later
  ✓ 28 columns preserved
  ✗ Slower runs (5+ min)
  → Say: "KEEP"

Option C: YOU'LL FIND CORRECT ENDPOINT
  → Say: "I'LL FIND IT" + provide endpoint URL
```

---

## Impact Comparison

| Aspect | Disable TBG | Keep TBG | Manual Data |
|--------|-------------|----------|------------|
| 7 PM Run Time | 3-4 min | 5+ min | 3-4 min |
| CSV Columns | 34 | 61 | 61 |
| Empty Columns | 0 | 28 | 0 |
| Error Likelihood | 0 | 0 | Depends |
| Setup Effort | 5 min | 0 min | High |
| Working Status | ✅ | ✅ | Depends |
| Production Ready | ✅ Yes | ✅ Yes | Pending |

---

**What would you like me to do?**
