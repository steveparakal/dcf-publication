"""
persistence_stationarity.py

Persistence Score (PS) and Stationarity Score (SS), per DCF specification
Sections 10 and 11.

PS:
    PS = |rho_1|   (absolute lag-1 autocorrelation)
    Boundary: if lag-1 autocorrelation cannot be computed, PS = 0.
    Range: 0 <= PS <= 1.

SS:
    Based on the Augmented Dickey-Fuller (ADF) test.
    If p <= alpha:      SS = 1
    Otherwise:          SS = max(0, 1 - p)
    Boundary: if the ADF test cannot be computed, SS = 0.
    Range: 0 <= SS <= 1.
    Default alpha = 0.05 (configurable).

Both functions operate on the prepared time series X directly (not on
STL components) -- per Sections 10/11's stated "Input: Prepared time
series X."
"""



from __future__ import annotations



from typing import Optional



import numpy as np

import pandas as pd

from statsmodels.tsa.stattools import acf, adfuller



from dcf.characterization._common import characterization_output

from dcf.config import Config, get_config

from dcf.logging_utils import get_error_logger





def compute_ps(series, dataset_id="", config=None):

    error_log = get_error_logger()

    clean = pd.Series(series).dropna()



    if len(clean) < 2:

        error_log.warning(

            f"PS for '{dataset_id}': fewer than 2 valid observations "

            "after dropping NaNs; lag-1 autocorrelation cannot be "

            "computed. Returning PS=0 per DCF specification "

            "boundary condition."

        )

        return characterization_output("PS", 0.0, config=config)



    try:

        acf_values = acf(clean, nlags=1, fft=True)

        rho_1 = acf_values[1]

        if np.isnan(rho_1):

            raise ValueError("acf() returned NaN for lag 1")

    except Exception as exc:

        error_log.warning(

            f"PS for '{dataset_id}': lag-1 autocorrelation could not be "

            f"computed ({exc!r}). Returning PS=0 per boundary condition."

        )

        return characterization_output("PS", 0.0, config=config)



    ps = abs(float(rho_1))

    ps = max(0.0, min(1.0, ps))



    return characterization_output("PS", ps, config=config)





def compute_ss(series, dataset_id="", config=None):

    cfg = config or get_config(allow_draft=False)

    error_log = get_error_logger()

    clean = pd.Series(series).dropna()



    alpha = float(cfg.get("characterization.stationarity_score.adf_alpha", 0.05))

    autolag = cfg.get("characterization.stationarity_score.adf_autolag", "AIC")

    regression = cfg.get("characterization.stationarity_score.adf_regression", "c")



    def _undefined(reason: str) -> dict:

        error_log.warning(f"SS for '{dataset_id}': {reason}. SS = undefined.")

        return {

            "measure": "SS",

            "value": None,

            "label": None,

            "stationarity_test_valid": False,

            "adf_stat": None,

            "p_value": None,

            "alpha": alpha,

        }



    if len(clean) < 10:

        return _undefined(

            f"only {len(clean)} valid observations; too few for ADF test"

        )



    try:

        adf_stat, p_value, *_ = adfuller(clean, autolag=autolag, regression=regression)

        if np.isnan(p_value):

            raise ValueError("adfuller() returned NaN p-value")

    except Exception as exc:

        return _undefined(f"ADF test could not be computed ({exc!r})")



    p_value = float(np.clip(float(p_value), 0.0, 1.0))



    

    ss = 1.0 if p_value <= alpha else 0.0



    

    ss_bounded = max(0.0, (alpha - p_value) / alpha) if p_value <= alpha else 0.0



    out = characterization_output("SS", ss, config=config)

    out["stationarity_test_valid"] = True

    out["adf_stat"] = float(adf_stat)

    out["p_value"] = p_value

    out["alpha"] = alpha

    out["ss_bounded"] = ss_bounded

    return out





__all__ = ["compute_ps", "compute_ss"]

