#!/usr/bin/env python3
"""
NSE FO Data Summary Analyzer

Provides statistics and summary of aggregated data in nse_fo_aggregated.csv
"""

import csv
from pathlib import Path
from datetime import datetime

def analyze_aggregated_data():
    """Analyze and display summary of aggregated data"""
    
    output_file = Path("nse_fo_aggregated.csv")
    
    if not output_file.exists():
        print("❌ No aggregated data file found.")
        print("   Run nse_fo_aggregator.py first to generate nse_fo_aggregated.csv")
        return
    
    # Read data
    data = []
    with open(output_file, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            data.append({
                'date': row['Date'],
                'no_of_cont': int(float(row['NO_OF_CONT'])),
                'no_of_trade': int(float(row['NO_OF_TRADE'])),
                'notion_val': int(float(row['NOTION_VAL'])),
                'pr_val': int(float(row['PR_VAL'])),
            })
    
    if not data:
        print("❌ No data in aggregated file")
        return
    
    # Calculate statistics
    print("\n" + "=" * 70)
    print("NSE FO Data Summary".center(70))
    print("=" * 70)
    
    print(f"\n📊 COVERAGE:")
    print(f"   Total Trading Days: {len(data):,}")
    print(f"   Date Range: {data[0]['date']} to {data[-1]['date']}")
    
    # Per-column statistics
    metrics = {
        'NO_OF_CONT': [d['no_of_cont'] for d in data],
        'NO_OF_TRADE': [d['no_of_trade'] for d in data],
        'NOTION_VAL': [d['notion_val'] for d in data],
        'PR_VAL': [d['pr_val'] for d in data],
    }
    
    print(f"\n📈 STATISTICS BY METRIC:\n")
    print(f"{'Metric':<15} {'Total':>15} {'Average':>15} {'Min':>15} {'Max':>15}")
    print("-" * 65)
    
    for metric_name, values in metrics.items():
        total = sum(values)
        avg = total / len(values)
        min_val = min(values)
        max_val = max(values)
        
        print(f"{metric_name:<15} {total:>15,d} {avg:>15,.0f} {min_val:>15,d} {max_val:>15,d}")
    
    # Find extreme dates
    print(f"\n🔍 EXTREMES:\n")
    
    # Highest contracts
    max_cont_idx = data.index(max(data, key=lambda x: x['no_of_cont']))
    print(f"   Highest NO_OF_CONT: {data[max_cont_idx]['no_of_cont']:,} on {data[max_cont_idx]['date']}")
    
    # Highest trades
    max_trade_idx = data.index(max(data, key=lambda x: x['no_of_trade']))
    print(f"   Highest NO_OF_TRADE: {data[max_trade_idx]['no_of_trade']:,} on {data[max_trade_idx]['date']}")
    
    # Highest notional value
    max_notion_idx = data.index(max(data, key=lambda x: x['notion_val']))
    print(f"   Highest NOTION_VAL: {data[max_notion_idx]['notion_val']:,} on {data[max_notion_idx]['date']}")
    
    # Highest premium value
    max_pr_idx = data.index(max(data, key=lambda x: x['pr_val']))
    print(f"   Highest PR_VAL: {data[max_pr_idx]['pr_val']:,} on {data[max_pr_idx]['date']}")
    
    # Lowest values
    print(f"\n")
    min_cont_idx = data.index(min(data, key=lambda x: x['no_of_cont']))
    print(f"   Lowest NO_OF_CONT: {data[min_cont_idx]['no_of_cont']:,} on {data[min_cont_idx]['date']}")
    
    min_trade_idx = data.index(min(data, key=lambda x: x['no_of_trade']))
    print(f"   Lowest NO_OF_TRADE: {data[min_trade_idx]['no_of_trade']:,} on {data[min_trade_idx]['date']}")
    
    # Aggregate totals
    print(f"\n📊 GRAND TOTALS (Sum of all days):\n")
    for metric_name, values in metrics.items():
        total = sum(values)
        print(f"   {metric_name}: {total:,}")
    
    print("\n" + "=" * 70)
    print("To view detailed data, open: nse_fo_aggregated.csv")
    print("=" * 70 + "\n")

if __name__ == "__main__":
    analyze_aggregated_data()
