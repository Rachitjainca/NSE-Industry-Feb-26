import pandas as pd
from datetime import datetime, timedelta

df = pd.read_csv('nse_fo_aggregated_data.csv')
df['Date'] = pd.to_datetime(df['Date'], format='mixed', dayfirst=True)
df = df.sort_values('Date')

# Check for specific dates
dates_to_check = ['2026-01-15', '2026-02-01', '2026-02-17']
print('Checking specific dates:')
for date_str in dates_to_check:
    count = len(df[df['Date'] == pd.to_datetime(date_str)])
    status = 'Present' if count > 0 else 'MISSING'
    
    # Check if it's a weekend
    dt = pd.to_datetime(date_str)
    day_name = dt.strftime('%A')
    
    print(f'{date_str} ({day_name}): {status}')

print('\n\nAll unique dates in CSV (sorted):')
dates = sorted(df['Date'].unique())
print(f'Total trading days: {len(dates)}')
print(f'Date range: {dates[0].date()} to {dates[-1].date()}')

print('\n\nFirst 5 dates:')
for d in dates[:5]:
    print(pd.Timestamp(d).strftime('%Y-%m-%d %A'))

print('\n\nLast 5 dates:')
for d in dates[-5:]:
    print(pd.Timestamp(d).strftime('%Y-%m-%d %A'))
