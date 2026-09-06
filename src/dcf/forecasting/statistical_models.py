"""
forecasting/statistical_models.py

ARIMA, SARIMA, and ETS forecasting model adapters (DCF specification
Section 15, "Statistical Models").

ARIMA and SARIMA both use automated AIC/BIC-guided order search via
pmdarima.auto_arima(), per:
  - SARIMA: DCF specification's own model family + DCF design.
  - ARIMA: changed from a fixed starting order to automated search per
    the publication configuration,
    mirroring SARIMA's approach. ARIMA's search forces seasonal=False and
    all seasonal-order parameters to 0, since ARIMA by definition has no
    seasonal component (that's what distinguishes it from SARIMA).

Per the approval condition attached to that change: "the selected order
shall be recorded in experiment metadata for every dataset" -- each
adapter factory function below returns BOTH a fit_predict callable AND a
mutable holder dict that gets populated with the order actually selected
on each call, so the caller (forecasting_layer.py) can capture per-origin
selected orders into the ModelForecastResult.

ETS uses statsmodels ExponentialSmoothing with error/trend/seasonal
components set to "auto" per config -- since statsmodels has no built-in
"try every combination, pick by AIC" convenience the way pmdarima does
for ARIMA, this module implements that small selection loop directly.
"""



from __future__ import annotations



import warnings



import numpy as np

import pandas as pd

import pmdarima as pm

from statsmodels.tsa.holtwinters import ExponentialSmoothing



from dcf.config import get_config

from dcf.forecasting.exception_context import ExternalDependencyError, _raise_if_external_api_error

from dcf.logging_utils import get_error_logger





def make_arima_adapter(dataset_id="", config=None):

    cfg = config or get_config(allow_draft=False)

    settings = cfg.get("forecasting.models.arima.auto_arima_settings", {})

    selected_order_holder = {"order": None}



    def _fit_predict(train, horizon):

        try:

            with warnings.catch_warnings():

                warnings.simplefilter("ignore")

                model = pm.auto_arima(

                    train.to_numpy(),

                    start_p=settings.get("start_p", 0),

                    start_q=settings.get("start_q", 0),

                    max_p=settings.get("max_p", 5),

                    max_q=settings.get("max_q", 5),

                    max_d=settings.get("max_d", 2),

                    seasonal=False,

                    information_criterion=settings.get("information_criterion", "aic"),

                    stepwise=settings.get("stepwise", True),

                    suppress_warnings=settings.get("suppress_warnings", True),

                    error_action="warn",  

                )

        except Exception as exc:

            _raise_if_external_api_error("arima", exc, "arima.auto_arima")

            raise

        selected_order_holder["order"] = {"p": model.order[0], "d": model.order[1], "q": model.order[2]}

        try:

            forecasts = model.predict(n_periods=horizon)

        except Exception as exc:

            _raise_if_external_api_error("arima", exc, "arima.predict")

            raise

        return np.asarray(forecasts, dtype=float)



    return _fit_predict, selected_order_holder





def make_sarima_adapter(frequency_key, dataset_id="", config=None):

    cfg = config or get_config(allow_draft=False)

    settings = cfg.get("forecasting.models.sarima.auto_arima_settings", {})

    seasonal_period = cfg.get(f"stl.default_periods_by_frequency.{frequency_key}", 1)

    selected_order_holder = {"order": None, "seasonal_order": None}



    def _fit_predict(train, horizon):

        try:

            with warnings.catch_warnings():

                warnings.simplefilter("ignore")

                model = pm.auto_arima(

                    train.to_numpy(),

                    start_p=settings.get("start_p", 0),

                    start_q=settings.get("start_q", 0),

                    max_p=settings.get("max_p", 5),

                    max_q=settings.get("max_q", 5),

                    max_d=settings.get("max_d", 2),

                    seasonal=True,

                    m=int(seasonal_period) if seasonal_period and seasonal_period > 1 else 1,

                    max_P=settings.get("max_P", 2),

                    max_Q=settings.get("max_Q", 2),

                    max_D=settings.get("max_D", 1),

                    information_criterion=settings.get("information_criterion", "aic"),

                    stepwise=settings.get("stepwise", True),

                    suppress_warnings=settings.get("suppress_warnings", True),

                    error_action="warn",  

                )

        except Exception as exc:

            _raise_if_external_api_error("sarima", exc, "sarima.auto_arima")

            raise

        selected_order_holder["order"] = {"p": model.order[0], "d": model.order[1], "q": model.order[2]}

        selected_order_holder["seasonal_order"] = {

            "P": model.seasonal_order[0], "D": model.seasonal_order[1],

            "Q": model.seasonal_order[2], "s": model.seasonal_order[3],

        }

        try:

            forecasts = model.predict(n_periods=horizon)

        except Exception as exc:

            _raise_if_external_api_error("sarima", exc, "sarima.predict")

            raise

        return np.asarray(forecasts, dtype=float)



    return _fit_predict, selected_order_holder





def make_ets_adapter(frequency_key, dataset_id="", config=None):

    """
    ETS via statsmodels ExponentialSmoothing, with "auto" selection of
    error type, trend, seasonal, and damped-trend across the candidate
    set in config, picked by AIC. Multiplicative components require
    strictly positive data; skipped automatically if the training window
    contains non-positive values.
    """

    cfg = config or get_config(allow_draft=False)

    damped_candidates = cfg.get("forecasting.models.ets.damped_trend_candidates", [True, False])

    seasonal_period = cfg.get(f"stl.default_periods_by_frequency.{frequency_key}", 1)

    use_seasonal = seasonal_period and seasonal_period > 1



    selected_spec_holder = {"spec": None}



    def _fit_predict(train, horizon):

        values = train.to_numpy()

        all_positive = bool(np.all(values > 0))



        trend_candidates = ["add"] + (["mul"] if all_positive else [])

        seasonal_candidates = (["add"] + (["mul"] if all_positive else [])) if use_seasonal else [None]



        best_aic = np.inf

        best_fit = None

        best_spec = None



        for trend in trend_candidates + [None]:

            for seasonal in seasonal_candidates:

                for damped in (damped_candidates if trend is not None else [False]):

                    try:

                        with warnings.catch_warnings():

                            warnings.simplefilter("ignore")

                            model = ExponentialSmoothing(

                                values,

                                trend=trend,

                                seasonal=seasonal,

                                damped_trend=damped if trend is not None else False,

                                seasonal_periods=int(seasonal_period) if seasonal else None,

                                initialization_method="estimated",

                            )

                            fit = model.fit(optimized=True)

                        if fit.aic < best_aic:

                            best_aic = fit.aic

                            best_fit = fit

                            best_spec = {"trend": trend, "seasonal": seasonal, "damped": damped}

                    except Exception:

                        continue



        if best_fit is None:

            raise ValueError(f"ETS: no feasible model specification found for series of length {len(values)}.")



        selected_spec_holder["spec"] = best_spec

        try:

            forecasts = best_fit.forecast(horizon)

        except Exception as exc:

            _raise_if_external_api_error("ets", exc, "ets.forecast")

            raise

        return np.asarray(forecasts, dtype=float)



    return _fit_predict, selected_spec_holder





__all__ = ["make_arima_adapter", "make_sarima_adapter", "make_ets_adapter"]

