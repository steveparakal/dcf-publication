"""
stl_decomposition.py

Shared STL decomposition wrapper, per DCF specification.

X = T + S + R

where T = trend component, S = temporal pattern (seasonal) component,
R = residual component, all obtained from `statsmodels.tsa.seasonal.STL`.

This module's output is computed ONCE per dataset and reused by
`trend_strength.py`, `pattern_strength.py`, and `volatility.py` --
per the DCF specification's explicit requirement that "decomposition outputs
shall be reused by downstream modules and shall not be recomputed
independently."

STL period rule (DCF specification.1): the seasonal period is
determined from dataset frequency via the frozen config
(`stl.default_periods_by_frequency`). If no valid period can be
determined for a dataset's frequency, STL is not executed, a warning is
logged, and the dataset is flagged for manual review -- this module
raises `STLPeriodError` in that case rather than guessing a period.
"""



from __future__ import annotations



from dataclasses import dataclass

from typing import Optional



import numpy as np

import pandas as pd

from statsmodels.tsa.seasonal import STL



from dcf.config import Config, get_config

from dcf.logging_utils import get_error_logger, get_execution_logger





class STLPeriodError(Exception):

    """Raised when no valid STL seasonal period can be determined for a
    dataset's detected frequency. Per DCF specification.1, STL
    decomposition must not be executed in this case."""





@dataclass

class STLResult:

    dataset_id: str

    period_used: int

    frequency_key: str

    trend: pd.Series

    pattern: pd.Series

    residual: pd.Series

    robust: bool



    def to_summary_dict(self) -> dict:

        return {

            "dataset_id": self.dataset_id,

            "period_used": self.period_used,

            "frequency_key": self.frequency_key,

            "robust": self.robust,

            "n_observations": len(self.trend),

            "trend_var": float(np.var(self.trend, ddof=0)),

            "pattern_var": float(np.var(self.pattern, ddof=0)),

            "residual_var": float(np.var(self.residual, ddof=0)),

        }





def get_stl_period(frequency_key: str, config: Optional[Config] = None) -> int:

    cfg = config or get_config(allow_draft=False)

    period = cfg.get(f"stl.default_periods_by_frequency.{frequency_key}")

    if period is None:

        raise STLPeriodError(

            f"No STL seasonal period configured for frequency '{frequency_key}'. "

            "Per DCF specification.1, STL decomposition shall not be "

            "executed without a valid period; add an entry to "

            "stl.default_periods_by_frequency in version1_defaults.yaml or "

            "provide a dataset-specific override."

        )

    return int(period)





def run_stl(series, dataset_id, frequency_key, config=None):

    cfg = config or get_config(allow_draft=False)

    exec_log = get_execution_logger()

    error_log = get_error_logger()



    if series.isna().any():

        n_na = int(series.isna().sum())

        error_log.warning(

            f"STL input for '{dataset_id}' contains {n_na} NaN value(s) "

            "(likely an unfilled gap from Stage 1). Dropping NaNs before "

            "decomposition; STL requires a complete series."

        )

        series = series.dropna()



    period = get_stl_period(frequency_key, config=cfg)



    min_required = 2 * period

    if len(series) < min_required:

        raise STLPeriodError(

            f"Series '{dataset_id}' has {len(series)} observations, fewer than "

            f"the {min_required} required for STL with period={period} "

            f"(statsmodels requires at least 2 full cycles)."

        )



    robust = bool(cfg.get("stl.robust", True))

    seasonal_len = cfg.get("stl.seasonal_smoother_length")

    trend_len = cfg.get("stl.trend_smoother_length")



    stl_kwargs = {"period": period, "robust": robust}

    if seasonal_len is not None:

        stl_kwargs["seasonal"] = int(seasonal_len)

    if trend_len is not None:

        stl_kwargs["trend"] = int(trend_len)



    exec_log.info(

        f"Running STL for '{dataset_id}': period={period}, robust={robust}, "

        f"n_observations={len(series)}"

    )



    stl_model = STL(series, **stl_kwargs)

    fit = stl_model.fit()



    result = STLResult(

        dataset_id=dataset_id,

        period_used=period,

        frequency_key=frequency_key,

        trend=fit.trend,

        pattern=fit.seasonal,

        residual=fit.resid,

        robust=robust,

    )



    exec_log.info(f"STL complete for '{dataset_id}': {result.to_summary_dict()}")

    return result





__all__ = ["STLResult", "STLPeriodError", "get_stl_period", "run_stl"]

