#!/usr/bin/env python3

"""
preprocess_beijing_pm25.py
==========================
Standalone preprocessing script for the Beijing Multi-Site Air Quality dataset
(UCI ML Repository #501, Zhang et al. 2017) prior to ingestion by the DCF
publication pipeline.

Source
------
Raw archive : PRSA2017_Data_20130301-20170228.zip
Download    : https://archive.ics.uci.edu/dataset/501
Station file: PRSA_Data_Dongsi_20130301-20170228.csv  (~3 MB)
Format      : CSV, columns include year, month, day, hour, PM2.5, ...

Station selection (approved before any forecasting results were examined)
------------------------------------------------------------------------
Dongsi: central urban Beijing, most commonly cited station in the published
literature, most complete data record. Selected on scientific grounds before
examining forecasting results.

Target definition
-----------------
Daily PM2.5 mean with 75% hourly completeness threshold:
  - A daily mean is computed only when >= 18 of the 24 hourly observations
    are valid (non-NaN)
  - Days with fewer than 18 valid hourly readings are set to NaN
  - This is a conservative quality-control choice for constructing valid
    daily means, NOT a compulsory regulatory requirement for the source data
After constructing the daily series, the DCF pipeline applies the frozen
missing-value handler (linear interpolation, max_gap=5 days).

Output
------
Beijing_PM25_daily.csv  (~50 KB, ~1,461 rows)
  DATE   : ISO date string (YYYY-MM-DD)
  VALUE  : daily mean PM2.5 concentration (μg/m³) or NaN

Usage
-----
  python scripts/preprocess_beijing_pm25.py \\
      --raw PRSA_Data_Dongsi_20130301-20170228.csv \\
      --out Beijing_PM25_daily.csv

Run this script ONCE on the local machine before starting the pipeline.
Place Beijing_PM25_daily.csv in the DCF working directory and register its
path in data/raw/Beijing_PM25/provenance.json.
"""



import argparse

import hashlib

import sys

from pathlib import Path



import numpy as np

import pandas as pd



COMPLETENESS_THRESHOLD = 18  





def parse_args():

    p = argparse.ArgumentParser(

        description="Pre-aggregate Beijing PM2.5 Dongsi for DCF pipeline"

    )

    p.add_argument("--raw", required=True,

                   help="Path to PRSA_Data_Dongsi_20130301-20170228.csv")

    p.add_argument("--out", default="Beijing_PM25_daily.csv",

                   help="Output CSV path (default: Beijing_PM25_daily.csv)")

    p.add_argument("--threshold", type=int, default=COMPLETENESS_THRESHOLD,

                   help=f"Min valid hourly readings per day (default: {COMPLETENESS_THRESHOLD})")

    return p.parse_args()





def main():

    args = parse_args()

    raw_path = Path(args.raw)

    out_path = Path(args.out)

    threshold = args.threshold



    if not raw_path.exists():

        print(f"ERROR: raw file not found: {raw_path}", file=sys.stderr)

        sys.exit(1)



    print(f"Reading {raw_path} …")

    df = pd.read_csv(raw_path)

    print(f"  Raw shape: {df.shape[0]} rows × {df.shape[1]} columns")

    print(f"  Columns  : {list(df.columns)}")



    

    df["datetime"] = pd.to_datetime(df[["year", "month", "day", "hour"]])

    df = df.set_index("datetime").sort_index()



    if "PM2.5" not in df.columns:

        print("ERROR: column 'PM2.5' not found. Available columns:",

              list(df.columns), file=sys.stderr)

        sys.exit(1)



    pm25_hourly = df["PM2.5"].astype(float)

    n_total_hourly = len(pm25_hourly)

    n_missing_hourly = int(pm25_hourly.isna().sum())

    print(f"\nHourly PM2.5 series:")

    print(f"  Total readings   : {n_total_hourly}")

    print(f"  Missing (NaN)    : {n_missing_hourly}  ({100*n_missing_hourly/n_total_hourly:.2f}%)")

    print(f"  Date range       : {pm25_hourly.index[0]}  to  {pm25_hourly.index[-1]}")



    

    def daily_mean_with_threshold(x):

        valid = x.dropna()

        if len(valid) >= threshold:

            return valid.mean()

        return np.nan



    print(f"\nApplying {threshold}/24 hourly completeness threshold …")

    daily = pm25_hourly.resample("D").apply(daily_mean_with_threshold)

    daily.name = "VALUE"

    daily.index.name = "DATE"

    

    daily.index = daily.index.normalize()



    n_days_total = len(daily)

    n_days_nan = int(daily.isna().sum())

    n_days_valid = n_days_total - n_days_nan

    print(f"\nDaily series after threshold:")

    print(f"  Total days       : {n_days_total}")

    print(f"  Valid days       : {n_days_valid}")

    print(f"  NaN days         : {n_days_nan}  (below {threshold}/24 threshold)")

    print(f"  Date range       : {daily.index[0].date()}  to  {daily.index[-1].date()}")

    if n_days_valid > 0:

        valid = daily.dropna()

        print(f"  Min PM2.5 (daily): {valid.min():.2f} μg/m³")

        print(f"  Max PM2.5 (daily): {valid.max():.2f} μg/m³")

        print(f"  Mean PM2.5 (daily): {valid.mean():.2f} μg/m³")



    

    n_dups = int(daily.index.duplicated().sum())

    if n_dups > 0:

        print(f"  WARNING: {n_dups} duplicate date(s) in daily index")



    

    out = daily.reset_index()

    out["DATE"] = out["DATE"].astype(str)

    out.to_csv(out_path, index=False)



    sha256 = hashlib.sha256(out_path.read_bytes()).hexdigest()



    print(f"\nOutput written: {out_path}  ({out_path.stat().st_size / 1024:.1f} KB)")

    print(f"SHA-256        : {sha256}")

    print("\nTarget construction summary")

    print(f"  Station           : Dongsi (central urban Beijing)")

    print(f"  Raw frequency     : hourly")

    print(f"  Completeness rule : >= {threshold}/24 valid hourly readings required")

    print(f"  Aggregation       : daily mean of valid hourly PM2.5 readings")

    print(f"  Modelling freq    : daily")

    print(f"  Seasonal period   : 7")

    print(f"  Forecast horizon  : 7")

    print(f"  Unit              : μg/m³")

    print(f"  NaN treatment     : days below threshold set to NaN; the DCF")

    print(f"                      pipeline applies linear interpolation (max_gap=5)")

    print("\nNext step: copy Beijing_PM25_daily.csv and write data/raw/Beijing_PM25/provenance.json")





if __name__ == "__main__":

    main()

