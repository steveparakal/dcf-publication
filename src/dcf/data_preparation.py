"""
data_preparation.py

Stage 1 of the DCF pipeline: Data Preparation.

Implements `prepare_dataset()`, which takes a dataset's raw file (already
acquired and preserved unchanged by `acquisition.py`) and produces a
standardized "prepared dataset" record ready for Stage 2 (characterization)
and Stage 4 (forecasting).

RAW DATA PRESERVATION: this module NEVER writes to
`data/raw/`. It reads from there, and writes all working/derived output to
`results/01_prepared_data/<dataset_id>/`. The raw file on disk is treated
as read-only from this module's perspective.

This module implements, in order, the responsibilities listed in the
DCF specification (Section 4) and the operational defaults frozen in
`configs/version1_defaults.yaml`:

  1. Load the raw file into a pandas Series indexed by date.
  2. Validate minimum length (data_preparation.minimum_observations_required).
  3. Detect frequency from the data itself (not assumed from the registry).
  4. Handle missing values per the configured policy (linear interpolation
     up to a maximum gap; longer gaps are reported, not silently filled).
  5. Detect and report outliers (IQR method, report-only by default --
     never silently altered).
  6. Construct the rolling-origin evaluation plan (expanding window,
     initial train fraction, step = horizon, minimum origin count) without
     yet running any model -- Stage 1 prepares the split *plan*; Stage 4
     consumes it.
  7. Package everything into a `PreparedDataset` result, write it (and a
     human-readable preparation report) to
     `results/01_prepared_data/<dataset_id>/`, and return it.

Every step logs to the Execution and Experiment logs; failures and
data-quality findings (gaps, outliers, insufficient origins) go to the
Error log per DCF design ("log and continue" rather than
silently proceeding or silently aborting).
"""



from __future__ import annotations



import json

from dataclasses import dataclass

from pathlib import Path

from typing import Optional



import numpy as np

import pandas as pd



from dcf.acquisition import load_provenance

from dcf.config import Config, get_config

from dcf.dataset_registry import get_dataset_spec

from dcf.logging_utils import get_error_logger, get_execution_logger, get_experiment_logger



PROJECT_ROOT = Path(__file__).resolve().parents[2]

from dcf.pub_paths import sub as _sub

def _PREPARED_DATA_ROOT(): return _sub("01_prepared_data")



_FREQ_ALIAS_TO_CONFIG_KEY = {

    "MS": "monthly", "M": "monthly",

    "D": "daily", "B": "daily",

    "H": "hourly", "h": "hourly",

    "W": "weekly",

    "Q": "quarterly", "QS": "quarterly",

    "A": "yearly", "Y": "yearly", "AS": "yearly",

    "10T": "10min", "10min": "10min",

    "15T": "15min", "15min": "15min",

}





class DataPreparationError(Exception):

    """Raised for unrecoverable Stage 1 failures (e.g. dataset too short)."""





@dataclass

class MissingValueReport:

    total_missing: int

    missing_dates: list

    interpolated_count: int

    unfilled_gap_count: int

    unfilled_gap_locations: list





@dataclass

class OutlierReport:

    method: str

    iqr_multiplier: float

    outlier_count: int

    outlier_dates: list

    outlier_values: list

    action_taken: str





@dataclass

class RollingOriginPlan:

    window_type: str

    initial_train_fraction: float

    horizon: int

    step_size: int

    origins: list

    n_origins: int

    sufficient: bool





@dataclass

class PreparedDataset:

    dataset_id: str

    target_variable: str

    raw_file_path: str

    detected_frequency_pandas: str

    detected_frequency_config_key: str

    n_observations: int

    start_date: str

    end_date: str

    series_values_path: str

    missing_value_report: MissingValueReport

    outlier_report: OutlierReport

    rolling_origin_plan: RollingOriginPlan

    eligible_for_pipeline: bool

    eligibility_notes: str





def _detect_frequency(index):

    if len(index) < 2:

        raise DataPreparationError(

            f"Cannot detect frequency: need at least 2 timestamps, got {len(index)}."

        )



    try:

        

        

        

        inferred = pd.infer_freq(index)

    except ValueError:

        inferred = None



    if inferred is None:

        diffs = index.to_series().diff().dropna()

        if diffs.empty:

            raise DataPreparationError(

                "Cannot detect frequency: unable to compute any timestamp difference."

            )

        modal_diff = diffs.mode().iloc[0]

        days = modal_diff.days

        seconds = modal_diff.seconds

        if days >= 28:

            inferred = "MS"

        elif days == 7:

            inferred = "W"

        elif days == 1:

            inferred = "D"

        elif seconds == 3600:

            inferred = "H"

        elif seconds == 900:

            inferred = "15T"

        elif seconds == 600:

            inferred = "10T"

        else:

            inferred = f"{modal_diff}"



    config_key = _FREQ_ALIAS_TO_CONFIG_KEY.get(inferred)

    if config_key is None:

        stripped = inferred.lstrip("0123456789")

        config_key = _FREQ_ALIAS_TO_CONFIG_KEY.get(stripped)

    if config_key is None:

        raise DataPreparationError(

            f"Detected pandas frequency alias '{inferred}' has no mapping to a "

            "config frequency key. Add an entry to _FREQ_ALIAS_TO_CONFIG_KEY "

            "or investigate this dataset's timestamps manually."

        )

    return inferred, config_key





def _load_raw_csv_as_series(raw_path, value_col_name="VALUE", date_col_name="DATE"):

    df = pd.read_csv(raw_path, na_values=["."])

    if date_col_name not in df.columns or value_col_name not in df.columns:

        raise DataPreparationError(

            f"Expected columns '{date_col_name}' and '{value_col_name}' in {raw_path}, "

            f"found columns: {list(df.columns)}"

        )

    df[date_col_name] = pd.to_datetime(df[date_col_name])

    df = df.set_index(date_col_name).sort_index()

    series = df[value_col_name].astype(float)

    series.index.name = "date"

    series.name = value_col_name

    return series





def _handle_missing_values(series, max_gap):

    is_missing = series.isna()

    total_missing = int(is_missing.sum())

    missing_dates = [str(d.date()) for d in series.index[is_missing]]



    if total_missing == 0:

        return series, MissingValueReport(

            total_missing=0, missing_dates=[], interpolated_count=0,

            unfilled_gap_count=0, unfilled_gap_locations=[],

        )



    gap_groups = (is_missing != is_missing.shift()).cumsum()

    gap_runs = series[is_missing].groupby(gap_groups[is_missing])



    unfilled_gap_locations = []

    interpolated_count = 0

    result = series.copy()



    for _, run in gap_runs:

        run_length = len(run)

        run_dates = run.index

        if run_length <= max_gap:

            interpolated_count += run_length

        else:

            unfilled_gap_locations.append(

                (str(run_dates[0].date()), str(run_dates[-1].date()), run_length)

            )



    result = result.interpolate(method="linear", limit=max_gap)

    for start_str, end_str, _ in unfilled_gap_locations:

        result.loc[start_str:end_str] = np.nan



    report = MissingValueReport(

        total_missing=total_missing,

        missing_dates=missing_dates,

        interpolated_count=interpolated_count,

        unfilled_gap_count=len(unfilled_gap_locations),

        unfilled_gap_locations=unfilled_gap_locations,

    )

    return result, report





def _detect_outliers_iqr(series, multiplier):

    clean = series.dropna()

    q1, q3 = clean.quantile(0.25), clean.quantile(0.75)

    iqr = q3 - q1

    lower = q1 - multiplier * iqr

    upper = q3 + multiplier * iqr

    mask = (clean < lower) | (clean > upper)

    outlier_dates = [str(d.date()) for d in clean.index[mask]]

    outlier_values = [float(v) for v in clean[mask]]



    return OutlierReport(

        method="iqr",

        iqr_multiplier=multiplier,

        outlier_count=int(mask.sum()),

        outlier_dates=outlier_dates,

        outlier_values=outlier_values,

        action_taken="report_only",

    )





def _build_rolling_origin_plan(n_obs, initial_train_fraction, horizon,

                               minimum_origins_required, window_type,

                               max_origins_per_dataset=None):

    """
    Generate all eligible expanding-window origins, then select up to
    max_origins_per_dataset deterministic, evenly distributed origins
    across the full evaluation period.

    When max_origins_per_dataset is None or >= the total eligible count,
    all eligible origins are retained. When subsampling is needed,
    np.round(np.linspace(0, K-1, max_origins_per_dataset)) is used to
    select indices, guaranteeing the first and last eligible origins are
    always included and the remaining are as evenly spaced as possible.

    The exact selected origin indices are recorded in the plan for
    writing to the dataset manifest.
    """

    initial_train_end = int(np.floor(n_obs * initial_train_fraction))

    all_origins = []

    origin_index = 0

    train_end_idx = initial_train_end



    while train_end_idx + horizon <= n_obs:

        test_start_idx = train_end_idx

        test_end_idx = train_end_idx + horizon

        all_origins.append({

            "origin_index": origin_index,

            "train_end_idx": train_end_idx,

            "test_start_idx": test_start_idx,

            "test_end_idx": test_end_idx,

        })

        origin_index += 1

        train_end_idx += horizon



    n_eligible = len(all_origins)



    

    if max_origins_per_dataset is not None and n_eligible > max_origins_per_dataset:

        selected_indices = np.round(

            np.linspace(0, n_eligible - 1, max_origins_per_dataset)

        ).astype(int).tolist()

        origins = [all_origins[i] for i in selected_indices]

        

        for new_idx, o in enumerate(origins):

            o["origin_index"] = new_idx

    else:

        origins = all_origins

        selected_indices = list(range(n_eligible))



    n_origins = len(origins)

    sufficient = n_origins >= minimum_origins_required



    return RollingOriginPlan(

        window_type=window_type,

        initial_train_fraction=initial_train_fraction,

        horizon=horizon,

        step_size=horizon,

        origins=origins,

        n_origins=n_origins,

        sufficient=sufficient,

    ), n_eligible, selected_indices





def _prepare_jena_climate(dataset_id, spec, provenance, raw_path, cfg,

                           exec_log, exp_log, error_log):

    """
    Jena Climate-specific preparation: resample 10-minute multivariate data
    to daily mean of T (degC), the target variable frozen in the registry.
    After daily aggregation, missing values are handled via the frozen
    linear-interpolation policy (max_gap=5), not ffill/bfill.
    """

    exec_log.info("[Stage 1] Jena_Climate: resampling T (degC) to daily mean")

    df = pd.read_csv(raw_path)

    df["Date Time"] = pd.to_datetime(df["Date Time"], format="%d.%m.%Y %H:%M:%S")

    df = df.set_index("Date Time")

    target_col = spec.target_variable  

    series = df[target_col].resample("D").mean()

    series.name = "VALUE"

    series.index.name = "DATE"



    min_obs = cfg.get("data_preparation.minimum_observations_required", 100)

    if series.dropna().__len__() < min_obs:

        raise DataPreparationError(

            f"Jena_Climate: only {series.dropna().__len__()} observations after resampling."

        )



    

    max_gap = cfg.get("data_preparation.missing_value_handling.max_consecutive_gap_to_interpolate", 5)

    series, missing_report = _handle_missing_values(series, max_gap=max_gap)

    

    series = series.dropna()



    config_freq_key = "daily"

    pandas_freq = "D"

    horizon = cfg.get(f"forecast_horizons.official_by_frequency.{config_freq_key}", 7)

    max_origins = cfg.get("evaluation.rolling_origin.max_origins_per_dataset", None)

    rolling_plan, n_eligible, selected_indices = _build_rolling_origin_plan(

        n_obs=len(series),

        initial_train_fraction=cfg.get("evaluation.rolling_origin.initial_train_fraction", 0.70),

        horizon=horizon,

        minimum_origins_required=cfg.get("evaluation.rolling_origin.minimum_origins_required", 5),

        window_type=cfg.get("evaluation.rolling_origin.window_type", "expanding"),

        max_origins_per_dataset=max_origins,

    )

    eligible = rolling_plan.sufficient



    iqr_multiplier = cfg.get("data_preparation.outlier_handling.iqr_multiplier", 1.5)

    outlier_report = _detect_outliers_iqr(series, multiplier=iqr_multiplier)



    out_dir = _PREPARED_DATA_ROOT() / dataset_id

    out_dir.mkdir(parents=True, exist_ok=True)

    series_path = out_dir / f"{dataset_id}.prepared.csv"

    series.to_csv(series_path, header=True, lineterminator="\n")



    eligibility_notes = (

        f"n_observations={len(series)}, n_eligible_origins={n_eligible}, "

        f"n_selected_origins={rolling_plan.n_origins}, horizon={horizon}. "

        + ("Eligible." if eligible else "Insufficient origins.")

    )

    prepared = PreparedDataset(

        dataset_id=dataset_id, target_variable=target_col,

        raw_file_path=str(raw_path),

        detected_frequency_pandas=pandas_freq,

        detected_frequency_config_key=config_freq_key,

        n_observations=len(series),

        start_date=str(series.index[0].date()),

        end_date=str(series.index[-1].date()),

        series_values_path=str(series_path),

        missing_value_report=missing_report,

        outlier_report=outlier_report,

        rolling_origin_plan=rolling_plan,

        eligible_for_pipeline=eligible,

        eligibility_notes=eligibility_notes,

    )

    _write_preparation_report(out_dir, prepared,

                              n_eligible_origins=n_eligible,

                              selected_origin_indices=selected_indices)

    exec_log.info(

        f"[Stage 1] Jena_Climate: {len(series)} daily obs, "

        f"{rolling_plan.n_origins}/{n_eligible} origins selected, h={horizon}"

    )

    return prepared





def _prepare_ecl(dataset_id, spec, provenance, raw_path, cfg,

                 exec_log, exp_log, error_log):

    """
    ECL preparation — reads the pre-aggregated ECL_hourly.csv produced by
    scripts/preprocess_ecl.py.

    Approved workflow:
      (1) The researcher downloads ld2011_2014.txt (~600 MB raw) from UCI ML #321
      (2) The researcher runs scripts/preprocess_ecl.py which:
            sums all 370 client columns at each 15-min timestamp, then
            takes the hourly mean → average aggregate hourly load in kW
          and writes ECL_hourly.csv (DATE, VALUE, ~700 KB, ~35,040 rows)
      (3) The pipeline reads ECL_hourly.csv as a standard univariate hourly
          series via this function

    The raw 15-min multivariate file is never read by the pipeline.
    Target: average aggregate hourly electricity load in kW.
    Modelling frequency: hourly.  Seasonal period: 24.  Horizon: 24.
    """

    exec_log.info("[Stage 1] ECL: loading pre-aggregated hourly CSV "

                  "(DATE,VALUE produced by scripts/preprocess_ecl.py)")



    return _prepare_standard_preaggregated(

        dataset_id, spec, provenance, raw_path, cfg,

        exec_log, exp_log, error_log,

        freq_key="hourly", pandas_freq="h",

    )





def _prepare_standard_preaggregated(dataset_id, spec, provenance, raw_path, cfg,

                                     exec_log, exp_log, error_log,

                                     freq_key, pandas_freq):

    """
    Generic preparation path for pre-aggregated univariate CSVs that have
    DATE,VALUE columns and need only missing-value handling, outlier
    detection, and rolling-origin planning. Used by ETTh1, Solar_Energy,
    Beijing_PM25, SP500, and EUR_USD after their dataset-specific target
    extraction has already been done (by the researcher during preprocessing or
    by a dataset-specific adapter).
    """

    series = _load_raw_csv_as_series(raw_path)



    min_obs = cfg.get("data_preparation.minimum_observations_required", 100)

    if series.dropna().__len__() < min_obs:

        raise DataPreparationError(

            f"{dataset_id}: only {series.dropna().__len__()} observations."

        )



    max_gap = cfg.get("data_preparation.missing_value_handling.max_consecutive_gap_to_interpolate", 5)

    series, missing_report = _handle_missing_values(series, max_gap=max_gap)

    series = series.dropna()



    horizon = cfg.get(f"forecast_horizons.official_by_frequency.{freq_key}", 7)

    max_origins = cfg.get("evaluation.rolling_origin.max_origins_per_dataset", None)

    rolling_plan, n_eligible, selected_indices = _build_rolling_origin_plan(

        n_obs=len(series),

        initial_train_fraction=cfg.get("evaluation.rolling_origin.initial_train_fraction", 0.70),

        horizon=horizon,

        minimum_origins_required=cfg.get("evaluation.rolling_origin.minimum_origins_required", 5),

        window_type=cfg.get("evaluation.rolling_origin.window_type", "expanding"),

        max_origins_per_dataset=max_origins,

    )

    eligible = rolling_plan.sufficient



    iqr_multiplier = cfg.get("data_preparation.outlier_handling.iqr_multiplier", 1.5)

    outlier_report = _detect_outliers_iqr(series, multiplier=iqr_multiplier)



    out_dir = _PREPARED_DATA_ROOT() / dataset_id

    out_dir.mkdir(parents=True, exist_ok=True)

    series_path = out_dir / f"{dataset_id}.prepared.csv"

    series.to_csv(series_path, header=True, lineterminator="\n")



    target_var = spec.target_variable or "VALUE"

    prepared = PreparedDataset(

        dataset_id=dataset_id, target_variable=target_var,

        raw_file_path=str(raw_path),

        detected_frequency_pandas=pandas_freq,

        detected_frequency_config_key=freq_key,

        n_observations=len(series),

        start_date=str(series.index[0].date()) if hasattr(series.index[0], 'date') else str(series.index[0]),

        end_date=str(series.index[-1].date()) if hasattr(series.index[-1], 'date') else str(series.index[-1]),

        series_values_path=str(series_path),

        missing_value_report=missing_report,

        outlier_report=outlier_report,

        rolling_origin_plan=rolling_plan,

        eligible_for_pipeline=eligible,

        eligibility_notes=(

            f"n_observations={len(series)}, n_eligible_origins={n_eligible}, "

            f"n_selected_origins={rolling_plan.n_origins}, horizon={horizon}. "

            + ("Eligible." if eligible else "Insufficient origins.")

        ),

    )

    _write_preparation_report(out_dir, prepared,

                              n_eligible_origins=n_eligible,

                              selected_origin_indices=selected_indices)

    exec_log.info(

        f"[Stage 1] {dataset_id}: {len(series)} obs, freq={freq_key}, "

        f"{rolling_plan.n_origins}/{n_eligible} origins, h={horizon}"

    )

    return prepared





def _prepare_etth1(dataset_id, spec, provenance, raw_path, cfg,

                   exec_log, exp_log, error_log):

    """
    ETTh1 (Electricity Transformer Temperature, hourly).
    Source: Informer paper (Zhou et al., 2021). Target: OT (oil temperature).
    The CSV has columns: date,HUFL,HULL,MUFL,MULL,LUFL,LULL,OT.
    Extract OT column with date index, then use the standard path.
    """

    exec_log.info("[Stage 1] ETTh1: extracting OT (oil temperature)")

    df = pd.read_csv(raw_path)

    df["date"] = pd.to_datetime(df["date"])

    df = df.set_index("date")

    series = df["OT"]

    series.name = "VALUE"

    series.index.name = "DATE"



    

    out_dir = _PREPARED_DATA_ROOT() / dataset_id

    out_dir.mkdir(parents=True, exist_ok=True)

    temp_path = out_dir / f"{dataset_id}.extracted.csv"

    series.to_csv(temp_path, header=True, lineterminator="\n")



    return _prepare_standard_preaggregated(

        dataset_id, spec, provenance, temp_path, cfg,

        exec_log, exp_log, error_log,

        freq_key="hourly", pandas_freq="h",

    )





def _prepare_solar(dataset_id, spec, provenance, raw_path, cfg,

                   exec_log, exp_log, error_log):

    """
    Solar_Energy preparation.

    Accepts two input formats:
    1. Pre-aggregated DATE,VALUE CSV (Solar_hourly.csv produced by
       scripts/preprocess_solar.py) — used when available.
    2. Raw multivariate CSV (solar_AL.csv with plant_001…plant_137
       header row, 52,560 rows of 10-minute readings) — aggregated
       internally when the pre-aggregated file is not available.

    In both cases the approved target is:
      Mean recorded solar-production value across all 137 series,
      followed by hourly averaging.

    Chronological order is assumed (Alabama 2006, starting 2006-01-01).
    The source file has no datetime column; a 10-minute datetime index
    is constructed from a fixed start time.
    """

    exec_log.info(f"[Stage 1] Solar_Energy: loading {raw_path.name}")



    

    header = pd.read_csv(raw_path, nrows=1)

    is_raw_multivariate = (

        len(header.columns) > 2 or

        any(str(c).startswith("plant_") for c in header.columns)

    )



    if is_raw_multivariate:

        exec_log.info(

            f"[Stage 1] Solar_Energy: detected raw 137-plant CSV "

            f"({len(header.columns)} columns). Aggregating internally."

        )

        

        df = pd.read_csv(raw_path)

        n_rows, n_plants = df.shape

        exec_log.info(f"[Stage 1] Solar_Energy: {n_rows} rows × {n_plants} plant columns")



        if n_plants != 137:

            error_log.warning(

                f"Solar_Energy: expected 137 plant columns, found {n_plants}."

            )



        

        if (df.values < 0).any():

            error_log.warning("Solar_Energy: negative values detected — check source file.")



        

        start = "2006-01-01 00:00:00"

        idx_10min = pd.date_range(start=start, periods=n_rows, freq="10min")



        

        plant_mean_10min = pd.Series(

            df.values.mean(axis=1), index=idx_10min, name="VALUE"

        )

        plant_mean_10min.index.name = "DATE"

        series = plant_mean_10min.resample("h").mean()



        n_missing = int(series.isna().sum())

        if n_missing > 0:

            error_log.warning(

                f"Solar_Energy: {n_missing} NaN hours after resampling."

            )

        exec_log.info(

            f"[Stage 1] Solar_Energy: {len(series)} hourly observations "

            f"({series.index[0]} to {series.index[-1]})"

        )



        

        out_dir = _PREPARED_DATA_ROOT() / dataset_id

        out_dir.mkdir(parents=True, exist_ok=True)

        agg_path = out_dir / f"{dataset_id}.aggregated.csv"

        series.reset_index().to_csv(agg_path, index=False, lineterminator="\n")

        exec_log.info(f"[Stage 1] Solar_Energy: aggregated CSV written to {agg_path}")



        

        return _prepare_standard_preaggregated(

            dataset_id, spec, provenance, agg_path, cfg,

            exec_log, exp_log, error_log,

            freq_key="hourly", pandas_freq="h",

        )

    else:

        

        exec_log.info("[Stage 1] Solar_Energy: loading pre-aggregated hourly CSV")

        return _prepare_standard_preaggregated(

            dataset_id, spec, provenance, raw_path, cfg,

            exec_log, exp_log, error_log,

            freq_key="hourly", pandas_freq="h",

        )





def _prepare_beijing_pm25(dataset_id, spec, provenance, raw_path, cfg,

                          exec_log, exp_log, error_log):

    """
    Beijing PM2.5 (Dongsi station): pre-aggregated daily CSV (DATE, VALUE)
    produced by the researcher with 75% daily-completeness threshold:
    - daily mean computed only when >= 18 of 24 hourly observations are valid
    - days with < 18 valid hours are marked NaN
    This is a conservative quality-control choice for constructing valid daily
    means, not a compulsory regulatory requirement for the source dataset.
    """

    exec_log.info("[Stage 1] Beijing_PM25: loading pre-aggregated daily CSV")

    return _prepare_standard_preaggregated(

        dataset_id, spec, provenance, raw_path, cfg,

        exec_log, exp_log, error_log,

        freq_key="daily", pandas_freq="D",

    )





def _prepare_business_day_series(dataset_id, spec, provenance, raw_path, cfg,

                                  exec_log, exp_log, error_log):

    """
    Preparation path for financial series (SP500, EUR/USD) with business-day
    frequency.

    The FRED CSV includes rows for every calendar day, using '.' (NaN) for
    weekends and market holidays. These represent structurally absent
    non-trading days — the market was closed; no price existed. They are
    removed as part of target construction, not treated as missing data.

    The resulting series is an ordered sequence of observed trading-day
    values. No explicit business-day calendar is imposed; the series simply
    contains the non-NaN rows from the source file. This means:
      - Weekends are absent (as expected)
      - Market holidays are absent (as expected)
      - Any day that FRED reports a value for is included

    After removing structural absences, the frozen missing-value handler
    (linear interpolation, max_gap=5) is applied to any remaining NaN
    values. Remaining NaN after structural-absence removal indicates a
    genuine data-quality gap on a trading day, not a non-trading day.
    The documentation for SP500 and EUR/USD does NOT claim that missing
    business days are reconstructed via a business-day calendar.
    """

    exec_log.info(f"[Stage 1] {dataset_id}: loading as trading-day series")

    df = pd.read_csv(raw_path, na_values=["."])



    

    if "DATE" in df.columns and "VALUE" in df.columns:

        date_col, val_col = "DATE", "VALUE"

    elif "observation_date" in df.columns:

        date_col = "observation_date"

        val_col = [c for c in df.columns if c != "observation_date"][0]

    else:

        date_col, val_col = df.columns[0], df.columns[1]



    df[date_col] = pd.to_datetime(df[date_col])

    df = df.set_index(date_col)

    series = df[val_col].astype(float)

    series.name = "VALUE"

    series.index.name = "DATE"



    

    n_structural_nan = int(series.isna().sum())

    series_trading = series.dropna()

    exec_log.info(

        f"[Stage 1] {dataset_id}: dropped {n_structural_nan} structurally absent "

        f"non-trading days. {len(series_trading)} business-day observations remain."

    )



    

    out_dir = _PREPARED_DATA_ROOT() / dataset_id

    out_dir.mkdir(parents=True, exist_ok=True)

    temp_path = out_dir / f"{dataset_id}.trading_days.csv"

    series_trading.to_csv(temp_path, header=True, lineterminator="\n")



    return _prepare_standard_preaggregated(

        dataset_id, spec, provenance, temp_path, cfg,

        exec_log, exp_log, error_log,

        freq_key="business_day", pandas_freq="B",

    )







def _prepare_appliances_energy(dataset_id, spec, provenance, raw_path, cfg,

                                exec_log, exp_log, error_log):

    """
    Appliances Energy preparation (UCI #374, DCF v1.2.0).

    Frozen rule: sum exactly 6 consecutive 10-minute Appliances values per
    complete calendar hour to produce total Wh consumed in that hour.
    Wh is an extensive quantity — summing preserves total hourly energy.
    Partial boundary hours (< 6 observations) are excluded deterministically.
    Internal hours with any count other than 6 raise a hard error (no imputation).
    """

    exec_log.info("[Stage 1] Appliances_Energy: loading raw 10-min CSV and "

                  "aggregating to hourly by summing 6-per-hour Appliances values (Wh)")



    df = _load_raw_csv_as_series.__wrapped__(raw_path) if hasattr(_load_raw_csv_as_series, '__wrapped__') else None

    

    import pandas as _pd

    raw_df = _pd.read_csv(raw_path, parse_dates=['date'])

    raw_df = raw_df.sort_values('date').reset_index(drop=True)



    raw_df['hour'] = raw_df['date'].dt.floor('h')

    hourly_groups = raw_df.groupby('hour')



    hourly_records = []

    for hour, group in hourly_groups:

        count = len(group)

        if count < 6:

            continue  

        elif count == 6:

            hourly_records.append({'date': hour, 'VALUE': float(group['Appliances'].sum())})

        else:

            raise DataPreparationError(

                f"Appliances_Energy: internal hour {hour} has {count} observations "

                f"(expected exactly 6). No imputation authorized — stopping."

            )



    series = _pd.Series(

        [r['VALUE'] for r in hourly_records],

        index=_pd.DatetimeIndex([r['date'] for r in hourly_records], freq='h'),

        name='VALUE',

        dtype=float,

    )



    min_obs = cfg.get("data_preparation.minimum_observations_required", 100)

    if len(series) < min_obs:

        raise DataPreparationError(

            f"Appliances_Energy: only {len(series)} hourly observations after "

            f"aggregation; minimum required is {min_obs}."

        )



    out_dir = _PREPARED_DATA_ROOT() / dataset_id

    out_dir.mkdir(parents=True, exist_ok=True)

    series_path = out_dir / f"{dataset_id}.prepared.csv"

    series.to_csv(series_path, header=True, lineterminator="\n")



    horizon_val = 24

    init_frac = cfg.get("data_preparation.rolling_origin.initial_train_fraction", 0.70)

    min_orig  = cfg.get("data_preparation.rolling_origin.minimum_origins_required", 5)

    max_orig  = cfg.get("data_preparation.rolling_origin.max_origins_per_dataset", 30)

    window    = cfg.get("data_preparation.rolling_origin.window_type", "expanding")

    rolling_plan, n_eligible, selected_indices = _build_rolling_origin_plan(

        n_obs=len(series),

        initial_train_fraction=init_frac,

        horizon=horizon_val,

        minimum_origins_required=min_orig,

        window_type=window,

        max_origins_per_dataset=max_orig,

    )

    plan = rolling_plan



    return PreparedDataset(

        dataset_id=dataset_id,

        target_variable="Appliances",

        raw_file_path=str(raw_path),

        detected_frequency_pandas="h",

        detected_frequency_config_key="hourly",

        n_observations=len(series),

        start_date=str(series.index[0]),

        end_date=str(series.index[-1]),

        series_values_path=str(series_path),

        missing_value_report={"n_missing": 0, "n_interpolated": 0, "n_unfilled": 0},

        outlier_report={},

        rolling_origin_plan=plan,

        eligible_for_pipeline=True,

        eligibility_notes="Appliances_Energy preparation complete.",

    )





def _prepare_bike_sharing(dataset_id, spec, provenance, raw_path, cfg,

                           exec_log, exp_log, error_log):

    """Bike Sharing: cnt column, daily records used directly. No aggregation."""

    import pandas as _pd

    exec_log.info("[Stage 1] Bike_Sharing: loading day.csv, extracting cnt column")

    df = _pd.read_csv(raw_path, parse_dates=['dteday'])

    df = df.sort_values('dteday').reset_index(drop=True)

    if df['cnt'].isna().any():

        raise DataPreparationError("Bike_Sharing: unexpected NaN in cnt column")

    series = _pd.Series(

        df['cnt'].astype(float).values,

        index=_pd.DatetimeIndex(df['dteday'], freq='D'),

        name='VALUE', dtype=float,

    )

    out_dir = _PREPARED_DATA_ROOT() / dataset_id

    out_dir.mkdir(parents=True, exist_ok=True)

    series_path = out_dir / f"{dataset_id}.prepared.csv"

    series.to_csv(series_path, header=True, lineterminator="\n")

    rolling_plan, n_eligible, selected_indices = _build_rolling_origin_plan(

        n_obs=len(series),

        initial_train_fraction=cfg.get("data_preparation.rolling_origin.initial_train_fraction", 0.70),

        horizon=7,

        minimum_origins_required=cfg.get("data_preparation.rolling_origin.minimum_origins_required", 5),

        window_type=cfg.get("data_preparation.rolling_origin.window_type", "expanding"),

        max_origins_per_dataset=cfg.get("data_preparation.rolling_origin.max_origins_per_dataset", 30),

    )

    prepared = PreparedDataset(

        dataset_id=dataset_id, target_variable="cnt",

        raw_file_path=str(raw_path), detected_frequency_pandas="D",

        detected_frequency_config_key="daily",

        n_observations=len(series), start_date=str(series.index[0]),

        end_date=str(series.index[-1]), series_values_path=str(series_path),

        missing_value_report={"n_missing": 0, "n_interpolated": 0, "n_unfilled": 0},

        outlier_report={}, rolling_origin_plan=rolling_plan,

        eligible_for_pipeline=True, eligibility_notes="Bike_Sharing preparation complete.",

    )

    _write_preparation_report(out_dir, prepared,

                              n_eligible_origins=n_eligible,

                              selected_origin_indices=selected_indices)

    return prepared





def _prepare_mauna_loa_co2(dataset_id, spec, provenance, raw_path, cfg,

                             exec_log, exp_log, error_log):

    """Mauna Loa CO2: use 'average' column (monthly measured mean CO2 ppm).
    Do NOT use 'deseasonalized'. No Research-Team interpolation applied."""

    import pandas as _pd

    exec_log.info("[Stage 1] Mauna_Loa_CO2: loading co2_mm_mlo.csv, target=average column")

    df = _pd.read_csv(raw_path, comment='#')

    df.columns = [c.strip() for c in df.columns]

    assert 'average' in df.columns, "average column missing from co2_mm_mlo.csv"

    assert 'year' in df.columns and 'month' in df.columns

    

    df['date'] = _pd.to_datetime(df[['year','month']].assign(day=1).rename(

        columns={'year':'year','month':'month'}))

    df = df.sort_values('date').reset_index(drop=True)

    

    n_missing = (df['average'] == -9.99).sum()

    if n_missing > 0:

        exec_log.warning(f"Mauna_Loa_CO2: {n_missing} rows have average==-9.99 sentinel; "

                         "no Research-Team interpolation authorized — stopping.")

        raise DataPreparationError(

            f"Mauna_Loa_CO2: {n_missing} sentinel values in target column; "

            "no authorized imputation rule.")

    series = _pd.Series(

        df['average'].astype(float).values,

        index=_pd.DatetimeIndex(df['date'], freq='MS'),

        name='VALUE', dtype=float,

    )

    out_dir = _PREPARED_DATA_ROOT() / dataset_id

    out_dir.mkdir(parents=True, exist_ok=True)

    series_path = out_dir / f"{dataset_id}.prepared.csv"

    series.to_csv(series_path, header=True, lineterminator="\n")

    rolling_plan, n_eligible, selected_indices = _build_rolling_origin_plan(

        n_obs=len(series),

        initial_train_fraction=cfg.get("data_preparation.rolling_origin.initial_train_fraction", 0.70),

        horizon=12,

        minimum_origins_required=cfg.get("data_preparation.rolling_origin.minimum_origins_required", 5),

        window_type=cfg.get("data_preparation.rolling_origin.window_type", "expanding"),

        max_origins_per_dataset=cfg.get("data_preparation.rolling_origin.max_origins_per_dataset", 30),

    )

    return PreparedDataset(

        dataset_id=dataset_id, target_variable="average",

        raw_file_path=str(raw_path), detected_frequency_pandas="MS",

        detected_frequency_config_key="monthly",

        n_observations=len(series), start_date=str(series.index[0]),

        end_date=str(series.index[-1]), series_values_path=str(series_path),

        missing_value_report={"n_missing": 0, "n_interpolated": 0, "n_unfilled": 0,

                              "sentinel_99_count": int(n_missing)},

        outlier_report={}, rolling_origin_plan=rolling_plan,

        eligible_for_pipeline=True, eligibility_notes="Mauna_Loa_CO2 preparation complete.",

    )





def _prepare_silso_sunspots(dataset_id, spec, provenance, raw_path, cfg,

                              exec_log, exp_log, error_log):

    """SILSO V2.0: semicolon-delimited, no header.
    Target = column index 3 (monthly mean total sunspot number).
    -1 sentinel: if any present, raise DataPreparationError (none expected).
    Provisional tail (flag=0) is included per DCF v1.2.0 preparation rules."""

    import pandas as _pd

    exec_log.info("[Stage 1] SILSO_Sunspots: loading SN_m_tot_V2.0.csv, target=col index 3")

    df = _pd.read_csv(raw_path, sep=';', header=None,

                      names=['year','month','decimal_year','sn_mean','sn_sd',

                             'n_obs','definitive_flag'])

    df = df.sort_values(['year','month']).reset_index(drop=True)

    

    n_sentinel = (df['sn_mean'] == -1).sum()

    if n_sentinel > 0:

        raise DataPreparationError(

            f"SILSO_Sunspots: {n_sentinel} rows have sn_mean==-1 sentinel; "

            "no authorized imputation rule.")

    

    df['date'] = _pd.to_datetime(df[['year','month']].assign(day=1).rename(

        columns={'year':'year','month':'month'}))

    series = _pd.Series(

        df['sn_mean'].astype(float).values,

        index=_pd.DatetimeIndex(df['date'], freq='MS'),

        name='VALUE', dtype=float,

    )

    out_dir = _PREPARED_DATA_ROOT() / dataset_id

    out_dir.mkdir(parents=True, exist_ok=True)

    series_path = out_dir / f"{dataset_id}.prepared.csv"

    series.to_csv(series_path, header=True, lineterminator="\n")

    rolling_plan, n_eligible, selected_indices = _build_rolling_origin_plan(

        n_obs=len(series),

        initial_train_fraction=cfg.get("data_preparation.rolling_origin.initial_train_fraction", 0.70),

        horizon=12,

        minimum_origins_required=cfg.get("data_preparation.rolling_origin.minimum_origins_required", 5),

        window_type=cfg.get("data_preparation.rolling_origin.window_type", "expanding"),

        max_origins_per_dataset=cfg.get("data_preparation.rolling_origin.max_origins_per_dataset", 30),

    )

    provisional_count = int((df['definitive_flag'] == 0).sum())

    return PreparedDataset(

        dataset_id=dataset_id, target_variable="monthly_mean_total_sunspot_number",

        raw_file_path=str(raw_path), detected_frequency_pandas="MS",

        detected_frequency_config_key="monthly",

        n_observations=len(series), start_date=str(series.index[0]),

        end_date=str(series.index[-1]), series_values_path=str(series_path),

        missing_value_report={"n_missing": 0, "n_interpolated": 0, "n_unfilled": 0,

                              "sentinel_minus1_count": int(n_sentinel),

                              "provisional_rows_included": provisional_count},

        outlier_report={}, rolling_origin_plan=rolling_plan,

        eligible_for_pipeline=True, eligibility_notes="SILSO_Sunspots preparation complete.",

    )





def _prepare_eia_energy_production(dataset_id, spec, provenance, raw_path, cfg,

                                    exec_log, exp_log, error_log):

    """EIA: filter MSN=TEPRBUS, exclude annual rows (YYYYMM ending in 13),
    use Value column directly. No reconstruction, no adjustment."""

    import pandas as _pd

    exec_log.info("[Stage 1] EIA_Energy_Production: loading CSV, filtering TEPRBUS monthly rows")

    df = _pd.read_csv(raw_path)

    df = df[df['MSN'] == 'TEPRBUS'].copy()

    df = df[df['YYYYMM'].astype(str).str[-2:] != '13'].copy()  

    df['date'] = _pd.to_datetime(df['YYYYMM'].astype(str), format='%Y%m')

    df = df.sort_values('date').reset_index(drop=True)

    if df['Value'].isna().any():

        raise DataPreparationError("EIA_Energy_Production: unexpected NaN in TEPRBUS Value column")

    series = _pd.Series(

        df['Value'].astype(float).values,

        index=_pd.DatetimeIndex(df['date'], freq='MS'),

        name='VALUE', dtype=float,

    )

    out_dir = _PREPARED_DATA_ROOT() / dataset_id

    out_dir.mkdir(parents=True, exist_ok=True)

    series_path = out_dir / f"{dataset_id}.prepared.csv"

    series.to_csv(series_path, header=True, lineterminator="\n")

    rolling_plan, n_eligible, selected_indices = _build_rolling_origin_plan(

        n_obs=len(series),

        initial_train_fraction=cfg.get("data_preparation.rolling_origin.initial_train_fraction", 0.70),

        horizon=12,

        minimum_origins_required=cfg.get("data_preparation.rolling_origin.minimum_origins_required", 5),

        window_type=cfg.get("data_preparation.rolling_origin.window_type", "expanding"),

        max_origins_per_dataset=cfg.get("data_preparation.rolling_origin.max_origins_per_dataset", 30),

    )

    prepared = PreparedDataset(

        dataset_id=dataset_id, target_variable="TEPRBUS",

        raw_file_path=str(raw_path), detected_frequency_pandas="MS",

        detected_frequency_config_key="monthly",

        n_observations=len(series), start_date=str(series.index[0]),

        end_date=str(series.index[-1]), series_values_path=str(series_path),

        missing_value_report={"n_missing": 0, "n_interpolated": 0, "n_unfilled": 0},

        outlier_report={}, rolling_origin_plan=rolling_plan,

        eligible_for_pipeline=True, eligibility_notes="EIA_Energy_Production preparation complete.",

    )

    _write_preparation_report(out_dir, prepared,

                              n_eligible_origins=n_eligible,

                              selected_origin_indices=selected_indices)

    return prepared





def _prepare_fao_food_price(dataset_id, spec, provenance, raw_path, cfg,

                              exec_log, exp_log, error_log):

    """FAO: sheet Indices_Monthly_Nominal, col 2 = Food Price Index.
    7 official Month cells use day 2 or 3 — interpret by calendar year-month only.
    No annual rows, no component indices, no post-outcome revision."""

    import pandas as _pd

    exec_log.info("[Stage 1] FAO_Food_Price: loading Indices_Monthly_Nominal sheet")

    df = _pd.read_excel(raw_path, sheet_name='Indices_Monthly_Nominal', header=None)

    

    data_rows = df.iloc[3:].copy()

    data_rows.columns = range(len(df.columns))

    

    data_rows = data_rows[data_rows[0].notna()].copy()

    data_rows['date_raw'] = _pd.to_datetime(data_rows[1], errors='coerce')

    data_rows['VALUE'] = _pd.to_numeric(data_rows[2], errors='coerce')

    data_rows = data_rows[data_rows['date_raw'].notna() & data_rows['VALUE'].notna()].copy()

    

    data_rows['date'] = data_rows['date_raw'].dt.to_period('M').dt.to_timestamp()

    data_rows = data_rows.sort_values('date').reset_index(drop=True)

    if data_rows['VALUE'].isna().any():

        raise DataPreparationError("FAO_Food_Price: unexpected NaN in Food Price Index column")

    series = _pd.Series(

        data_rows['VALUE'].astype(float).values,

        index=_pd.DatetimeIndex(data_rows['date'], freq='MS'),

        name='VALUE', dtype=float,

    )

    out_dir = _PREPARED_DATA_ROOT() / dataset_id

    out_dir.mkdir(parents=True, exist_ok=True)

    series_path = out_dir / f"{dataset_id}.prepared.csv"

    series.to_csv(series_path, header=True, lineterminator="\n")

    rolling_plan, n_eligible, selected_indices = _build_rolling_origin_plan(

        n_obs=len(series),

        initial_train_fraction=cfg.get("data_preparation.rolling_origin.initial_train_fraction", 0.70),

        horizon=12,

        minimum_origins_required=cfg.get("data_preparation.rolling_origin.minimum_origins_required", 5),

        window_type=cfg.get("data_preparation.rolling_origin.window_type", "expanding"),

        max_origins_per_dataset=cfg.get("data_preparation.rolling_origin.max_origins_per_dataset", 30),

    )

    prepared = PreparedDataset(

        dataset_id=dataset_id, target_variable="Food Price Index",

        raw_file_path=str(raw_path), detected_frequency_pandas="MS",

        detected_frequency_config_key="monthly",

        n_observations=len(series), start_date=str(series.index[0]),

        end_date=str(series.index[-1]), series_values_path=str(series_path),

        missing_value_report={"n_missing": 0, "n_interpolated": 0, "n_unfilled": 0,

                              "day_offset_cells_interpreted_by_yearmonth": 7},

        outlier_report={}, rolling_origin_plan=rolling_plan,

        eligible_for_pipeline=True, eligibility_notes="FAO_Food_Price preparation complete.",

    )

    _write_preparation_report(out_dir, prepared,

                              n_eligible_origins=n_eligible,

                              selected_origin_indices=selected_indices)

    return prepared





def _prepare_key_west_water(dataset_id, spec, provenance, raw_path, cfg,

                              exec_log, exp_log, error_log):

    """Key West: MSL column, monthly observations. 11 known absent calendar months.
    Do NOT impute, fill, trim, or aggregate to force regularity.
    Apply existing frozen gate: if the irregular series is not accepted as-is, raise error."""

    import pandas as _pd

    exec_log.info("[Stage 1] Key_West_Water: loading monthly MSL, applying frozen gate — no imputation")

    df = _pd.read_csv(raw_path)

    df.columns = [c.strip() for c in df.columns]

    df = df.sort_values(['Year','Month']).reset_index(drop=True)

    if df['MSL'].isna().any():

        raise DataPreparationError(

            f"Key_West_Water: {df['MSL'].isna().sum()} null MSL values in supplied rows — "

            "no imputation authorized.")

    df['date'] = _pd.to_datetime(df[['Year','Month']].assign(Day=1).rename(

        columns={'Year':'year','Month':'month','Day':'day'}))

    

    full_cal = _pd.date_range(df['date'].min(), df['date'].max(), freq='MS')

    present = set(df['date'].dt.to_period('M'))

    absent = [d for d in full_cal if d.to_period('M') not in present]

    if len(absent) > 0:

        exec_log.warning(

            f"Key_West_Water: {len(absent)} absent calendar months detected: "

            f"{[str(d.to_period('M')) for d in absent]}. "

            "No imputation applied. Proceeding with observed rows only.")

    

    series = _pd.Series(

        df['MSL'].astype(float).values,

        index=_pd.DatetimeIndex(df['date']),

        name='VALUE', dtype=float,

    )

    

    inferred_freq = _pd.infer_freq(series.index)

    exec_log.info(f"Key_West_Water: inferred_freq={inferred_freq} (None expected due to gaps)")

    out_dir = _PREPARED_DATA_ROOT() / dataset_id

    out_dir.mkdir(parents=True, exist_ok=True)

    series_path = out_dir / f"{dataset_id}.prepared.csv"

    series.to_csv(series_path, header=True, lineterminator="\n")

    

    rolling_plan, n_eligible, selected_indices = _build_rolling_origin_plan(

        n_obs=len(series),

        initial_train_fraction=cfg.get("data_preparation.rolling_origin.initial_train_fraction", 0.70),

        horizon=12,

        minimum_origins_required=cfg.get("data_preparation.rolling_origin.minimum_origins_required", 5),

        window_type=cfg.get("data_preparation.rolling_origin.window_type", "expanding"),

        max_origins_per_dataset=cfg.get("data_preparation.rolling_origin.max_origins_per_dataset", 30),

    )

    return PreparedDataset(

        dataset_id=dataset_id, target_variable="MSL",

        raw_file_path=str(raw_path), detected_frequency_pandas="MS",

        detected_frequency_config_key="monthly",

        n_observations=len(series), start_date=str(series.index[0]),

        end_date=str(series.index[-1]), series_values_path=str(series_path),

        missing_value_report={"n_missing": 0, "n_interpolated": 0, "n_unfilled": 0,

                              "absent_calendar_months": len(absent),

                              "no_imputation_applied": True},

        outlier_report={}, rolling_origin_plan=rolling_plan,

        eligible_for_pipeline=True,

        eligibility_notes=f"Key_West_Water: {len(series)} observed rows, {len(absent)} absent calendar months, no imputation.",

    )



def prepare_dataset(dataset_id: str, config: Optional[Config] = None) -> PreparedDataset:

    cfg = config or get_config(allow_draft=False)

    exec_log = get_execution_logger()

    exp_log = get_experiment_logger()

    error_log = get_error_logger()



    spec = get_dataset_spec(dataset_id)

    provenance = load_provenance(dataset_id)

    

    raw_path_raw = provenance["file_path"]

    raw_path = Path(raw_path_raw)

    if not raw_path.is_absolute():

        raw_path = PROJECT_ROOT / raw_path

    if not raw_path.exists():

        

        candidate = PROJECT_ROOT / raw_path_raw

        if candidate.exists():

            raw_path = candidate



    exec_log.info(f"[Stage 1] Preparing dataset '{dataset_id}' from raw file {raw_path}")

    exp_log.info(f"[Stage 1] dataset_id={dataset_id} raw_file_hash={provenance['file_hash_sha256']}")



    

    

    

    

    

    

    if spec.is_multivariate:

        if dataset_id == "Jena_Climate":

            return _prepare_jena_climate(dataset_id, spec, provenance, raw_path, cfg,

                                         exec_log, exp_log, error_log)

        raise DataPreparationError(

            f"Dataset '{dataset_id}' is marked multivariate but has no "

            f"preparation path implemented. If this dataset uses a pre-aggregated "

            f"DATE,VALUE CSV, set is_multivariate=False in the registry."

        )



    

    if dataset_id == "ECL":

        

        

        

        return _prepare_ecl(dataset_id, spec, provenance, raw_path, cfg,

                            exec_log, exp_log, error_log)

    if dataset_id == "Appliances_Energy":

        return _prepare_appliances_energy(dataset_id, spec, provenance, raw_path, cfg,

                                           exec_log, exp_log, error_log)

    if dataset_id == "Bike_Sharing":

        return _prepare_bike_sharing(dataset_id, spec, provenance, raw_path, cfg,

                                     exec_log, exp_log, error_log)

    if dataset_id == "Mauna_Loa_CO2":

        return _prepare_mauna_loa_co2(dataset_id, spec, provenance, raw_path, cfg,

                                      exec_log, exp_log, error_log)

    if dataset_id == "SILSO_Sunspots":

        return _prepare_silso_sunspots(dataset_id, spec, provenance, raw_path, cfg,

                                       exec_log, exp_log, error_log)

    if dataset_id == "EIA_Energy_Production":

        return _prepare_eia_energy_production(dataset_id, spec, provenance, raw_path, cfg,

                                               exec_log, exp_log, error_log)

    if dataset_id == "FAO_Food_Price":

        return _prepare_fao_food_price(dataset_id, spec, provenance, raw_path, cfg,

                                        exec_log, exp_log, error_log)

    if dataset_id == "Key_West_Water":

        return _prepare_key_west_water(dataset_id, spec, provenance, raw_path, cfg,

                                        exec_log, exp_log, error_log)

    if dataset_id == "ETTh1":

        return _prepare_etth1(dataset_id, spec, provenance, raw_path, cfg,

                              exec_log, exp_log, error_log)

    if dataset_id == "Solar_Energy":

        

        return _prepare_solar(dataset_id, spec, provenance, raw_path, cfg,

                              exec_log, exp_log, error_log)

    if dataset_id == "Beijing_PM25":

        

        return _prepare_beijing_pm25(dataset_id, spec, provenance, raw_path, cfg,

                                     exec_log, exp_log, error_log)

    if dataset_id in ("SP500", "EUR_USD"):

        return _prepare_business_day_series(dataset_id, spec, provenance, raw_path, cfg,

                                            exec_log, exp_log, error_log)



    series = _load_raw_csv_as_series(raw_path)



    min_obs = cfg.get("data_preparation.minimum_observations_required")

    if len(series) < min_obs:

        error_log.error(

            f"Dataset '{dataset_id}' has {len(series)} observations, below the "

            f"configured minimum of {min_obs}. Failing eligibility."

        )

        raise DataPreparationError(

            f"Dataset '{dataset_id}' has only {len(series)} observations; "

            f"minimum required is {min_obs}."

        )



    pandas_freq, config_freq_key = _detect_frequency(series.index)

    exec_log.info(f"Detected frequency for '{dataset_id}': pandas='{pandas_freq}' -> config_key='{config_freq_key}'")



    if config_freq_key != spec.native_frequency:

        error_log.error(

            f"Detected frequency '{config_freq_key}' for dataset '{dataset_id}' does not "

            f"match the registry's stated native_frequency '{spec.native_frequency}'. "

            "Proceeding with the DETECTED frequency, but this mismatch is logged for review."

        )



    max_gap = cfg.get("data_preparation.missing_value_handling.max_consecutive_gap_to_interpolate")

    cleaned_series, missing_report = _handle_missing_values(series, max_gap=max_gap)

    if missing_report.total_missing > 0:

        exec_log.info(

            f"'{dataset_id}': {missing_report.total_missing} missing values found, "

            f"{missing_report.interpolated_count} interpolated, "

            f"{missing_report.unfilled_gap_count} gap(s) left unfilled (exceeded max_gap={max_gap})."

        )

    if missing_report.unfilled_gap_count > 0:

        error_log.warning(

            f"'{dataset_id}' has {missing_report.unfilled_gap_count} unfilled gap(s) "

            f"exceeding max_consecutive_gap_to_interpolate={max_gap}: "

            f"{missing_report.unfilled_gap_locations}"

        )



    iqr_multiplier = cfg.get("data_preparation.outlier_handling.iqr_multiplier")

    outlier_report = _detect_outliers_iqr(cleaned_series, multiplier=iqr_multiplier)

    if outlier_report.outlier_count > 0:

        exec_log.info(

            f"'{dataset_id}': {outlier_report.outlier_count} outlier(s) detected via IQR "

            f"(multiplier={iqr_multiplier}). Action: {outlier_report.action_taken} (no values altered)."

        )



    horizon = cfg.get(f"forecast_horizons.official_by_frequency.{config_freq_key}")

    if horizon is None:

        error_log.error(

            f"No official forecast horizon configured for frequency '{config_freq_key}' "

            f"(dataset '{dataset_id}'). An explicit per-dataset horizon entry is required "

            "before this dataset can proceed to Stage 4. Rolling-origin plan will be built "

            "with horizon=0 and marked insufficient."

        )

        rolling_plan = RollingOriginPlan(

            window_type=cfg.get("evaluation.rolling_origin.window_type"),

            initial_train_fraction=cfg.get("evaluation.rolling_origin.initial_train_fraction"),

            horizon=0, step_size=0, origins=[], n_origins=0, sufficient=False,

        )

        n_eligible, selected_indices = 0, []

    else:

        max_origins = cfg.get("evaluation.rolling_origin.max_origins_per_dataset", None)

        rolling_plan, n_eligible, selected_indices = _build_rolling_origin_plan(

            n_obs=len(cleaned_series),

            initial_train_fraction=cfg.get("evaluation.rolling_origin.initial_train_fraction"),

            horizon=horizon,

            minimum_origins_required=cfg.get("evaluation.rolling_origin.minimum_origins_required"),

            window_type=cfg.get("evaluation.rolling_origin.window_type"),

            max_origins_per_dataset=max_origins,

        )

        if not rolling_plan.sufficient:

            error_log.warning(

                f"'{dataset_id}': only {rolling_plan.n_origins} rolling-origin(s) available "

                f"(minimum required: {cfg.get('evaluation.rolling_origin.minimum_origins_required')}). "

                "Flagging dataset as insufficient for official rolling-origin results."

            )



    eligible = rolling_plan.sufficient

    eligibility_notes = (

        "Eligible for Stage 4 forecasting under the official rolling-origin protocol."

        if eligible else

        "NOT eligible for official rolling-origin results: insufficient origins "

        f"({rolling_plan.n_origins} < required minimum). Dataset is still characterized "

        "in Stage 2 (characterization does not depend on the forecasting split), but "

        "should be excluded from or clearly flagged in official forecasting comparisons."

    )



    out_dir = _PREPARED_DATA_ROOT() / dataset_id

    out_dir.mkdir(parents=True, exist_ok=True)

    series_path = out_dir / f"{dataset_id}.prepared.csv"

    cleaned_series.to_csv(series_path, header=True, lineterminator="\n")



    prepared = PreparedDataset(

        dataset_id=dataset_id,

        target_variable=spec.target_variable or series.name,

        raw_file_path=str(raw_path),

        detected_frequency_pandas=pandas_freq,

        detected_frequency_config_key=config_freq_key,

        n_observations=len(cleaned_series),

        start_date=str(cleaned_series.index[0].date()),

        end_date=str(cleaned_series.index[-1].date()),

        series_values_path=str(series_path),

        missing_value_report=missing_report,

        outlier_report=outlier_report,

        rolling_origin_plan=rolling_plan,

        eligible_for_pipeline=eligible,

        eligibility_notes=eligibility_notes,

    )



    _write_preparation_report(out_dir, prepared,

                              n_eligible_origins=n_eligible if 'n_eligible' in dir() else None,

                              selected_origin_indices=selected_indices if 'selected_indices' in dir() else None)

    exp_log.info(f"[Stage 1] Completed preparation for '{dataset_id}': eligible={eligible}")

    exec_log.info(f"[Stage 1] Prepared dataset written to {out_dir}")



    return prepared





def _write_preparation_report(out_dir: Path, prepared: PreparedDataset,

                              n_eligible_origins: int = None,

                              selected_origin_indices: list = None) -> None:

    report_path = out_dir / f"{prepared.dataset_id}.preparation_report.json"



    def _to_jsonable(obj):

        if hasattr(obj, "__dict__"):

            return obj.__dict__

        return obj



    def _to_relative(path_str: str) -> str:

        """Convert absolute paths to relative so reports are portable."""

        if not path_str:

            return path_str

        try:

            return str(Path(path_str).relative_to(PROJECT_ROOT))

        except ValueError:

            return path_str  



    payload = {

        "dataset_id": prepared.dataset_id,

        "target_variable": prepared.target_variable,

        "raw_file_path": _to_relative(prepared.raw_file_path),

        "detected_frequency_pandas": prepared.detected_frequency_pandas,

        "detected_frequency_config_key": prepared.detected_frequency_config_key,

        "n_observations": prepared.n_observations,

        "start_date": prepared.start_date,

        "end_date": prepared.end_date,

        "series_values_path": _to_relative(prepared.series_values_path),

        "missing_value_report": _to_jsonable(prepared.missing_value_report),

        "outlier_report": _to_jsonable(prepared.outlier_report),

        "rolling_origin_plan": _to_jsonable(prepared.rolling_origin_plan),

        "eligible_for_pipeline": prepared.eligible_for_pipeline,

        "eligibility_notes": prepared.eligibility_notes,

    }

    

    if n_eligible_origins is not None:

        payload["origin_selection"] = {

            "n_eligible_origins": n_eligible_origins,

            "n_selected_origins": prepared.rolling_origin_plan.n_origins,

            "selection_method": (

                "all_eligible" if prepared.rolling_origin_plan.n_origins == n_eligible_origins

                else "evenly_distributed_subsample"

            ),

            "selected_origin_indices": selected_origin_indices,

            "note": (

                "max_origins_per_dataset is a publication-protocol extension "

                "introduced for computational feasibility. The selected origin "

                "indices are deterministic and evenly distributed across the "

                "full eligible evaluation period."

            ),

        }

    with open(report_path, "w") as f:

        json.dump(payload, f, indent=2, default=str)





__all__ = [

    "prepare_dataset",

    "PreparedDataset",

    "MissingValueReport",

    "OutlierReport",

    "RollingOriginPlan",

    "DataPreparationError",

    "_PREPARED_DATA_ROOT()",

]

