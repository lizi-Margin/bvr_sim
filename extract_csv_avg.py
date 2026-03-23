#!/usr/bin/env python3
"""
Extract last N rows from a CSV column and calculate average.
Usage: python extract_csv_avg.py <csv_path> [column_name] [n_rows]
"""
import pandas as pd
import sys

def main():
    if len(sys.argv) < 2:
        print("Usage: python extract_csv_avg.py <csv_path> [column_name] [n_rows]")
        print("Default column_name: 'train top-rank ratio of=team-0'")
        print("Default n_rows: 30")
        sys.exit(1)

    csv_path = sys.argv[1]
    column_name = sys.argv[2] if len(sys.argv) > 2 else 'train top-rank ratio of=team-0'
    n_rows = int(sys.argv[3]) if len(sys.argv) > 3 else 30

    # Read CSV
    df = pd.read_csv(csv_path)

    # Get last N values
    last_n_values = df[column_name].tail(n_rows)

    # Calculate average
    average = last_n_values.mean()

    print(f"Last {n_rows} values of '{column_name}':")
    print(last_n_values.values)
    print(f"\nAverage: {average}")

if __name__ == '__main__':
    main()
