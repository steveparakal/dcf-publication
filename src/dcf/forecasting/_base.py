"""
forecasting/_base.py

Shared model-adapter interface and rolling-origin execution harness for
the Forecasting Layer (DCF specification).

ARCHITECTURAL INVARIANT (DCF design principle): "The Forecasting Layer shall operate independently of the
Domain Profile. The Domain Profile shall not influence: model training;
model selection; forecasting execution." Every adapter in this module
therefore receives ONLY the prepared series and per-model hyperparameters
from config -- never a Domain Profile, never any characterization output.
This is enforced architecturally (no adapter function accepts one), not
just by convention.

Each model adapter implements a fit_predict(train, horizon) -> array
function, returning a length-horizon array of point forecasts. This is
the minimal common interface across statistical, ML, and DL models; each
adapter handles its own internal feature engineering (e.g. lag features
for tree models, windowing for DL models).

The rolling-origin execution harness (run_rolling_origin_forecast)
consumes the rolling-origin plan already computed by Stage 1
(data_preparation.RollingOriginPlan), so the train/test split logic
itself is NOT reimplemented here -- only the per-origin fit/predict loop
and result aggregation.

EXPERIMENTAL CONSISTENCY (DCF specification): identical splits,
horizons, and preprocessing outputs are used for every model, since every
model adapter is run against the exact same RollingOriginPlan object.
"""



from __future__ import annotations



from dataclasses import dataclass

from typing import Callable, Optional



import numpy as np

import pandas as pd



from dcf.config import Config, get_config

from dcf.logging_utils import get_error_logger, get_execution_logger





class ForecastingModelError(Exception):

    """
    Raised when a single model fails on a single dataset/origin. Per
    DCF design ("log and continue"), callers catch this and
    record the failure rather than letting it abort the whole experiment.
    """





@dataclass

class OriginForecastResult:

    origin_index: int

    train_end_idx: int

    test_start_idx: int

    test_end_idx: int

    predicted_values: list

    actual_values: list

    success: bool

    error_message: Optional[str] = None





@dataclass

class ModelForecastResult:

    dataset_id: str

    model_name: str

    horizon: int

    origins: list

    hyperparameters_used: dict

    random_seed: Optional[int]

    selected_order: Optional[dict] = None

    n_origins_succeeded: int = 0

    n_origins_failed: int = 0



    def all_predicted(self):

        out = []

        for o in self.origins:

            if o.success:

                out.extend(o.predicted_values)

        return np.array(out, dtype=float)



    def all_actual(self):

        out = []

        for o in self.origins:

            if o.success:

                out.extend(o.actual_values)

        return np.array(out, dtype=float)





def run_rolling_origin_forecast(

    series,

    rolling_origin_plan,

    model_name,

    fit_predict_fn,

    dataset_id="",

    hyperparameters_used=None,

    random_seed=None,

    config=None,

):

    cfg = config or get_config(allow_draft=False)

    exec_log = get_execution_logger()

    error_log = get_error_logger()



    clean_series = pd.Series(series).dropna().reset_index(drop=True)

    horizon = rolling_origin_plan.horizon



    origin_results = []

    n_succeeded = 0

    n_failed = 0



    for origin in rolling_origin_plan.origins:

        train = clean_series.iloc[: origin["train_end_idx"]]

        actual = clean_series.iloc[origin["test_start_idx"]: origin["test_end_idx"]]



        try:

            predicted = fit_predict_fn(train, horizon)

            predicted = np.asarray(predicted, dtype=float).flatten()



            if len(predicted) != horizon:

                raise ForecastingModelError(

                    f"Model '{model_name}' returned {len(predicted)} predictions, "

                    f"expected horizon={horizon}."

                )

            if len(actual) != horizon:

                raise ForecastingModelError(

                    f"Actual values length {len(actual)} does not match "

                    f"horizon={horizon} at origin {origin['origin_index']}."

                )



            origin_results.append(OriginForecastResult(

                origin_index=origin["origin_index"],

                train_end_idx=origin["train_end_idx"],

                test_start_idx=origin["test_start_idx"],

                test_end_idx=origin["test_end_idx"],

                predicted_values=predicted.tolist(),

                actual_values=actual.tolist(),

                success=True,

            ))

            n_succeeded += 1



        except Exception as exc:

            error_log.error(

                f"Model '{model_name}' failed for dataset '{dataset_id}' at "

                f"origin {origin['origin_index']} (train_end_idx={origin['train_end_idx']}): "

                f"{exc!r}. Recording as failed origin; continuing with remaining origins."

            )

            origin_results.append(OriginForecastResult(

                origin_index=origin["origin_index"],

                train_end_idx=origin["train_end_idx"],

                test_start_idx=origin["test_start_idx"],

                test_end_idx=origin["test_end_idx"],

                predicted_values=[],

                actual_values=actual.tolist() if len(actual) else [],

                success=False,

                error_message=repr(exc),

            ))

            n_failed += 1



    exec_log.info(

        f"Model '{model_name}' on dataset '{dataset_id}': "

        f"{n_succeeded} origin(s) succeeded, {n_failed} failed, "

        f"out of {len(rolling_origin_plan.origins)} total."

    )



    return ModelForecastResult(

        dataset_id=dataset_id,

        model_name=model_name,

        horizon=horizon,

        origins=origin_results,

        hyperparameters_used=hyperparameters_used or {},

        random_seed=random_seed,

        n_origins_succeeded=n_succeeded,

        n_origins_failed=n_failed,

    )





__all__ = [

    "ForecastingModelError",

    "OriginForecastResult",

    "ModelForecastResult",

    "run_rolling_origin_forecast",

]

