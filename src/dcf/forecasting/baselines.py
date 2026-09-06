"""
forecasting/baselines.py

Naive, Seasonal Naive, and Drift baseline forecasting models.

Per DCF specification (Decisions 11, 30, 55), these three baselines are
mandatory members of the forecasting model registry, used as the floor
against which every other model is evaluated. They are not part of the
DCF specification's base Section 15 model list, but were explicitly added
in the publication specification.

All three are deterministic (no randomness), so reproducibility is
trivial -- no seed is needed.
"""



from __future__ import annotations



import numpy as np

import pandas as pd



from dcf.config import get_config





def naive_fit_predict(train, horizon):

    """Naive forecast: repeat the last observed training value for every
    step of the horizon."""

    last_value = float(train.iloc[-1])

    return np.full(horizon, last_value, dtype=float)





def seasonal_naive_fit_predict(train, horizon, season_length):

    """
    Seasonal Naive forecast: forecast for step h is the value observed
    exactly one season-length back, cycling through the most recent
    season if horizon > season_length.

    If the training series is shorter than one full season, falls back
    to the plain Naive forecast (an explicit, documented fallback rather
    than an error, since this can legitimately occur for short pilot
    datasets).
    """

    n = len(train)

    if n < season_length:

        return naive_fit_predict(train, horizon)



    last_season_values = train.iloc[-season_length:].to_numpy()

    forecasts = np.array(

        [last_season_values[i % season_length] for i in range(horizon)],

        dtype=float,

    )

    return forecasts





def drift_fit_predict(train, horizon):

    """
    Drift forecast: linear extrapolation of the average trend over the
    full training window.

        drift = (train[-1] - train[0]) / (n - 1)
        forecast[h] = train[-1] + (h + 1) * drift

    Falls back to Naive if the training window has fewer than 2
    observations (drift undefined).
    """

    n = len(train)

    if n < 2:

        return naive_fit_predict(train, horizon)



    last_value = float(train.iloc[-1])

    first_value = float(train.iloc[0])

    drift = (last_value - first_value) / (n - 1)



    steps = np.arange(1, horizon + 1)

    return last_value + steps * drift





def make_seasonal_naive_adapter(frequency_key, config=None):

    """
    Returns a fit_predict(train, horizon) closure with season_length
    resolved from the frozen config's STL period table for the dataset's
    frequency.
    """

    cfg = config or get_config(allow_draft=False)

    season_length = cfg.get(f"stl.default_periods_by_frequency.{frequency_key}")

    if season_length is None:

        season_length = 1



    def _adapter(train, horizon):

        return seasonal_naive_fit_predict(train, horizon, season_length=int(season_length))



    return _adapter





__all__ = [

    "naive_fit_predict",

    "seasonal_naive_fit_predict",

    "drift_fit_predict",

    "make_seasonal_naive_adapter",

]

