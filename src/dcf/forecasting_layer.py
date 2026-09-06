"""
forecasting_layer.py

Stage 4 of the DCF pipeline: the Forecasting Layer, per DCF specification
Section 15.

Primary function: run_forecasting_models(), which runs every enabled
model in the registry against a prepared dataset's rolling-origin plan,
records experiment metadata (including the selected order for ARIMA/
SARIMA/ETS where applicable), and writes results to the Forecast
Results Repository (results/04_forecasts/).

ARCHITECTURAL INVARIANT (DCF design):
this function's signature deliberately does NOT accept a Domain Profile
or characterization output -- only the prepared series and its rolling-
origin plan.

EXPERIMENTAL CONSISTENCY (DCF design): every model in the
registry is run against the EXACT SAME RollingOriginPlan object for a
given dataset, satisfying "identical train-test splits... identical
forecast horizons... for all models."

FAILURE HANDLING (DCF design): a model that fails entirely
is recorded with its failure and the pipeline continues with the
remaining models -- it does not abort the dataset's forecasting run.
"""



from __future__ import annotations



import json

from dataclasses import asdict, dataclass

from pathlib import Path

from typing import Optional



import pandas as pd



from dcf.config import Config, get_config

from dcf.forecasting import build_model_registry, run_rolling_origin_forecast

from dcf.logging_utils import get_error_logger, get_execution_logger, get_experiment_logger



PROJECT_ROOT = Path(__file__).resolve().parents[2]

from dcf.pub_paths import sub as _sub

def _FORECASTS_ROOT(): return _sub("04_forecasts")





@dataclass

class DatasetForecastingResult:

    dataset_id: str

    frequency_key: str

    horizon: int

    n_origins: int

    model_results: dict

    models_failed_entirely: list

    random_seed: int





def run_forecasting_models(series, dataset_id, frequency_key, rolling_origin_plan, config=None):

    """
    Run every enabled model in the registry against `series`, under
    `rolling_origin_plan`, and persist results to the Forecast Results
    Repository.
    """

    cfg = config or get_config(allow_draft=False)

    exec_log = get_execution_logger()

    exp_log = get_experiment_logger()

    error_log = get_error_logger()



    seed = int(cfg.get("reproducibility.global_random_seed", 42))



    exec_log.info(

        f"[Stage 4] Forecasting Layer -- dataset_id={dataset_id}, "

        f"horizon={rolling_origin_plan.horizon}, n_origins={rolling_origin_plan.n_origins}"

    )



    registry = build_model_registry(frequency_key, dataset_id=dataset_id, config=cfg)

    model_results = {}

    models_failed_entirely = []



    for model_name, entry in registry.items():

        fit_predict_fn = entry["fit_predict"]

        selected_order_holder = entry["selected_order_holder"]



        hyperparameters_used = cfg.get(f"forecasting.models.{model_name}", {})



        try:

            result = run_rolling_origin_forecast(

                series=series,

                rolling_origin_plan=rolling_origin_plan,

                model_name=model_name,

                fit_predict_fn=fit_predict_fn,

                dataset_id=dataset_id,

                hyperparameters_used=hyperparameters_used,

                random_seed=seed,

                config=cfg,

            )

        except Exception as exc:

            error_log.error(

                f"Model '{model_name}' failed catastrophically for dataset "

                f"'{dataset_id}' before any origin could run: {exc!r}. "

                "Recording as fully failed; continuing with remaining models."

            )

            models_failed_entirely.append(model_name)

            continue



        if selected_order_holder is not None:

            result.selected_order = dict(selected_order_holder)



        if result.n_origins_succeeded == 0:

            models_failed_entirely.append(model_name)

            error_log.error(

                f"Model '{model_name}' failed at ALL {result.n_origins_failed} "

                f"origin(s) for dataset '{dataset_id}'. Recording as fully "

                "failed; continuing with remaining models."

            )



        model_results[model_name] = result

        exp_log.info(

            f"[Stage 4] dataset_id={dataset_id} model={model_name} "

            f"n_succeeded={result.n_origins_succeeded} n_failed={result.n_origins_failed} "

            f"selected_order={result.selected_order}"

        )



    dataset_result = DatasetForecastingResult(

        dataset_id=dataset_id,

        frequency_key=frequency_key,

        horizon=rolling_origin_plan.horizon,

        n_origins=rolling_origin_plan.n_origins,

        model_results=model_results,

        models_failed_entirely=models_failed_entirely,

        random_seed=seed,

    )



    _write_forecast_results(dataset_result)



    exec_log.info(

        f"[Stage 4] Completed forecasting for '{dataset_id}': "

        f"{len(model_results)} model(s) produced results, "

        f"{len(models_failed_entirely)} failed entirely "

        f"({models_failed_entirely})."

    )



    return dataset_result





def _write_forecast_results(dataset_result):

    out_dir = _FORECASTS_ROOT() / dataset_result.dataset_id

    out_dir.mkdir(parents=True, exist_ok=True)



    json_payload = {

        "dataset_id": dataset_result.dataset_id,

        "frequency_key": dataset_result.frequency_key,

        "horizon": dataset_result.horizon,

        "n_origins": dataset_result.n_origins,

        "random_seed": dataset_result.random_seed,

        "models_failed_entirely": dataset_result.models_failed_entirely,

        "model_results": {

            name: {

                "model_name": r.model_name,

                "horizon": r.horizon,

                "hyperparameters_used": r.hyperparameters_used,

                "random_seed": r.random_seed,

                "selected_order": r.selected_order,

                "n_origins_succeeded": r.n_origins_succeeded,

                "n_origins_failed": r.n_origins_failed,

                "origins": [asdict(o) for o in r.origins],

            }

            for name, r in dataset_result.model_results.items()

        },

    }

    json_path = out_dir / f"{dataset_result.dataset_id}.forecasts.json"

    with open(json_path, "w") as f:

        json.dump(json_payload, f, indent=2, default=str)



    csv_rows = []

    for model_name, r in dataset_result.model_results.items():

        for o in r.origins:

            if not o.success:

                continue

            for step, (pred, actual) in enumerate(zip(o.predicted_values, o.actual_values)):

                csv_rows.append({

                    "dataset_id": dataset_result.dataset_id,

                    "model": model_name,

                    "origin_index": o.origin_index,

                    "horizon_step": step + 1,

                    "predicted": pred,

                    "actual": actual,

                })

    csv_path = out_dir / f"{dataset_result.dataset_id}.forecasts.csv"

    pd.DataFrame(csv_rows).to_csv(csv_path, index=False)





def load_forecast_results(dataset_id):

    path = _FORECASTS_ROOT() / dataset_id / f"{dataset_id}.forecasts.json"

    if not path.exists():

        raise FileNotFoundError(

            f"No forecast results found for '{dataset_id}' at {path}. "

            "Has run_forecasting_models() been run for this dataset yet?"

        )

    with open(path, "r") as f:

        return json.load(f)





__all__ = ["DatasetForecastingResult", "run_forecasting_models", "load_forecast_results", "_FORECASTS_ROOT()"]

