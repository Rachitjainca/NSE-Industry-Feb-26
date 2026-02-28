import pandas as pd

df = pd.read_csv('nse_fo_aggregated_data.csv')
df['Date'] = pd.to_datetime(df['Date'], format='mixed', dayfirst=True)
df = df.sort_values('Date')

dates_to_check = ['2026-01-15', '2026-02-01', '2026-02-17']

for date_str in dates_to_check:
    target_date = pd.to_datetime(date_str)
    rows = df[df['Date'] == target_date]
    
    print(f"\n{date_str} ({target_date.strftime('%A')}): {len(rows)} rows")
    if len(rows) > 0:
        row = rows.iloc[0]
        print(f"  CM_NO_OF_TRADES: {row.get('NSE_TBG_CM_NOS_OF_TRADES', 'N/A')}")
        print(f"  CM_TRADES_VALUES: {row.get('NSE_TBG_CM_TRADES_VALUES', 'N/A')}")
        print(f"  FO_INDEX_FUT_QTY: {row.get('NSE_TBG_FO_INDEX_FUT_QTY', 'N/A')}")
        print(f"  COM_TOTAL_QTY: {row.get('NSE_TBG_COM_TOTAL_QTY', 'N/A')}")
    else:
        print("  ❌ NO DATA FOUND")
