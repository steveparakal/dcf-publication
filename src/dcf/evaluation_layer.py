"""
evaluation_layer.py

Stage 5 of the DCF pipeline: the Evaluation Layer, per DCF specification
Section 16.

Primary function: evaluate_forecasts(), which consumes the Forecast
Results Repository (forecasting_layer.py's output) and computes, for
every Dataset x Model combination: MAE, RMSE, MAPE, sMAPE, then derives
rankings and best-model identification.

v1.2.0 METRIC DEFINITIONS (corrected from v1.1.5):

MAE  = mean(|actual - predicted|)
RMSE = sqrt(mean((actual - predicted)^2)); primary ranking metric.
MAPE = mean(|actual - predicted| / |actual|) * 100,
       computed with scale-aware near-zero exclusion:
       epsilon_mape = max(1e-8, 1e-4 * median(|series_i|))
       Points with |actual| < epsilon_mape are excluded and counted;
       negative actual values are accepted and flagged via mape_sign_warning.
sMAPE = mean(|actual - predicted| / ((|actual| + |predicted|) / 2)) * 100,
        computed only over points where (|actual| + |predicted|) != 0.
        sMAPE must lie in [0%, 200%]; values exceeding 200% by more than
        1e-9 are an implementation error and raise a RuntimeWarning.

MAPE is descriptive only and must never control primary model eligibility
or formal evidence classification.

Metric-validity semantics (Part 9.3 and OI-6 APPROVED):
  mape_valid:        True if at least one point has |actual| >= epsilon_mape.
  mape_unstable:     True if n_excluded / n_total > 0.10.
  smape_valid:       True if at least one point has nonzero denominator.
  mape_sign_warning: True if any valid actual value is negative.
  dataset_mape_unreliable: written to evaluation manifest if >6/12 models
                           have mape_unstable=True (descriptive-only flag).
"""



from __future__ import annotations



import json

import warnings

from dataclasses import asdict, dataclass

from pathlib import Path

from typing import Optional



import numpy as np

import pandas as pd



from dcf.config import Config, get_config

from dcf.logging_utils import get_error_logger, get_execution_logger, get_experiment_logger



PROJECT_ROOT = Path(__file__).resolve().parents[2]

from dcf.pub_paths import sub as _sub

def _PERFORMANCE_EVIDENCE_ROOT(): return _sub("04_forecasts")





def _is_genuine_int(v) -> bool:

    """True iff v is a genuine Python int with bool excluded."""

    return type(v) is int





def is_complete(n_origins_total, n_origins_succeeded) -> bool:

    """
    Scientific completion predicate (frozen v1.2.0 rule — v1.2.0/101):
      - all three values must be genuine Python int (bool excluded)
      - n_origins_total > 0 (from RollingOriginPlan.n_origins)
      - n_origins_succeeded == n_origins_total (all scheduled origins succeeded)
    """

    if not (_is_genuine_int(n_origins_total) and _is_genuine_int(n_origins_succeeded)):

        return False

    return n_origins_total > 0 and n_origins_succeeded == n_origins_total





def is_accounting_valid(n_origins_total, n_origins_succeeded, n_origins_failed) -> bool:

    """
    Accounting/integrity predicate (v1.2.0):
      - all three must be genuine Python int (bool excluded)
      - n_origins_total > 0 (from RollingOriginPlan.n_origins)
      - 0 <= n_origins_succeeded <= n_origins_total
      - 0 <= n_origins_failed <= n_origins_total
      - n_origins_succeeded + n_origins_failed == n_origins_total
    If not, at least one scheduled origin is unaccounted for, or counts conflict.
    """

    if not (_is_genuine_int(n_origins_total) and

            _is_genuine_int(n_origins_succeeded) and

            _is_genuine_int(n_origins_failed)):

        return False

    if n_origins_total <= 0:

        return False

    if n_origins_succeeded < 0 or n_origins_succeeded > n_origins_total:

        return False

    if n_origins_failed < 0 or n_origins_failed > n_origins_total:

        return False

    return n_origins_succeeded + n_origins_failed == n_origins_total





@dataclass

class ModelMetrics:

    model_name: str

    mae: Optional[float]

    rmse: Optional[float]

    mape: Optional[float]

    smape: Optional[float]

    n_points_evaluated: int

    n_points_excluded_from_mape: int

    n_points_excluded_from_smape: int

    

    mape_valid: bool = True

    mape_unstable: bool = False    

    smape_valid: bool = True

    mape_sign_warning: bool = False  

    

    

    

    

    

    

    n_origins_total: Optional[int] = None

    n_origins_succeeded: Optional[int] = None

    n_origins_failed: Optional[int] = None





@dataclass

class DatasetEvaluationResult:

    dataset_id: str

    model_metrics: dict

    ranking: list

    best_model: Optional[str]

    ranking_metric: str





def _mae(actual, predicted):

    return float(np.mean(np.abs(actual - predicted)))





def _rmse(actual, predicted):

    return float(np.sqrt(np.mean((actual - predicted) ** 2)))





def _mape(actual, predicted, series_median_abs=None):

    """
    v1.2.0: scale-aware near-zero exclusion (OI-6 APPROVED, Part 9.4).

    epsilon_mape = max(1e-8, 1e-4 * median(|series|))

    Points with |actual| < epsilon_mape are excluded (in addition to the
    pre-existing exact-zero exclusion).  Returns (value, n_excluded,
    mape_valid, mape_unstable, mape_sign_warning).
    """

    actual = np.asarray(actual, dtype=float)

    predicted = np.asarray(predicted, dtype=float)



    if series_median_abs is None:

        series_median_abs = float(np.median(np.abs(actual))) if len(actual) > 0 else 0.0



    epsilon_mape = max(1e-8, 1e-4 * series_median_abs)

    mask = np.abs(actual) >= epsilon_mape

    n_excluded = int(np.sum(~mask))

    mape_valid = bool(np.any(mask))

    mape_unstable = (n_excluded / max(1, len(actual))) > 0.10

    mape_sign_warning = bool(np.any(actual[mask] < 0)) if mape_valid else False



    if not mape_valid:

        return None, n_excluded, False, mape_unstable, mape_sign_warning



    value = float(

        np.mean(np.abs((actual[mask] - predicted[mask]) / actual[mask])) * 100.0

    )

    return value, n_excluded, mape_valid, mape_unstable, mape_sign_warning





def _smape(actual, predicted):

    """
    v1.2.0: sMAPE in [0%, 200%].  Any per-point value nominally exceeding 200%
    by more than 1e-9 is an implementation error and triggers a logged warning.
    Returns (value, n_excluded, smape_valid).
    """

    actual = np.asarray(actual, dtype=float)

    predicted = np.asarray(predicted, dtype=float)

    denom = (np.abs(actual) + np.abs(predicted)) / 2.0

    mask = denom != 0

    n_excluded = int(np.sum(~mask))

    smape_valid = bool(np.any(mask))



    if not smape_valid:

        return None, n_excluded, False



    per_point = np.abs(actual[mask] - predicted[mask]) / denom[mask] * 100.0



    

    if np.any(per_point > 200.0 + 1e-9):

        warnings.warn(

            "sMAPE per-point value exceeds 200% — implementation error.",

            RuntimeWarning, stacklevel=3

        )



    value = float(np.mean(per_point))

    return value, n_excluded, smape_valid





def compute_metrics_for_model(

    actual, predicted, model_name, series_median_abs=None,

    n_origins_total=None, n_origins_succeeded=None, n_origins_failed=None,

):

    """
    Compute evaluation metrics for one model on one dataset.

    n_origins_total:    authoritative scheduled count (from RollingOriginPlan.n_origins).
    n_origins_succeeded: actual successful origins (from ModelForecastResult).
    n_origins_failed:   actual failed origins (from ModelForecastResult).
    Pass genuine Python int values (bool excluded) when authoritative evidence
    is available. Pass None for diagnostic/legacy records.
    """

    if len(actual) == 0 or len(predicted) == 0:

        return ModelMetrics(

            model_name=model_name, mae=None, rmse=None, mape=None, smape=None,

            n_points_evaluated=0, n_points_excluded_from_mape=0,

            n_points_excluded_from_smape=0,

            n_origins_total=n_origins_total, n_origins_succeeded=n_origins_succeeded,

            n_origins_failed=n_origins_failed,

        )



    actual = np.asarray(actual, dtype=float)

    predicted = np.asarray(predicted, dtype=float)

    if series_median_abs is None:

        series_median_abs = float(np.median(np.abs(actual))) if len(actual) > 0 else 0.0



    mape_val, mape_excluded, mape_valid, mape_unstable, mape_sign_w = _mape(

        actual, predicted, series_median_abs=series_median_abs

    )

    smape_val, smape_excluded, smape_valid = _smape(actual, predicted)



    return ModelMetrics(

        model_name=model_name,

        mae=_mae(actual, predicted),

        rmse=_rmse(actual, predicted),

        mape=mape_val,

        smape=smape_val,

        n_points_evaluated=len(actual),

        n_points_excluded_from_mape=mape_excluded,

        n_points_excluded_from_smape=smape_excluded,

        mape_valid=mape_valid,

        mape_unstable=mape_unstable,

        smape_valid=smape_valid,

        mape_sign_warning=mape_sign_w,

        n_origins_total=n_origins_total,

        n_origins_succeeded=n_origins_succeeded,

        n_origins_failed=n_origins_failed,

    )





def evaluate_forecasts(dataset_forecasting_result, config=None):

    cfg = config or get_config(allow_draft=False)

    exec_log = get_execution_logger()

    exp_log = get_experiment_logger()

    error_log = get_error_logger()



    dataset_id = dataset_forecasting_result.dataset_id

    ranking_metric = cfg.get("evaluation_metrics.ranking_metric", "RMSE").lower()



    exec_log.info(f"[Stage 5] Evaluation Layer -- dataset_id={dataset_id}")



    model_metrics = {}

    for model_name, model_result in dataset_forecasting_result.model_results.items():

        actual = model_result.all_actual()

        predicted = model_result.all_predicted()



        

        

        

        

        

        _n_total = dataset_forecasting_result.n_origins  

        _n_succ  = model_result.n_origins_succeeded      

        _n_fail  = model_result.n_origins_failed         



        metrics = compute_metrics_for_model(

            actual, predicted, model_name,

            n_origins_total=_n_total,

            n_origins_succeeded=_n_succ,

            n_origins_failed=_n_fail,

        )

        model_metrics[model_name] = metrics



        if metrics.mae is None:

            error_log.warning(

                f"Dataset '{dataset_id}', model '{model_name}': no valid points to "

                "evaluate (zero successful origins or empty actual/predicted arrays). "

                "Excluded from ranking."

            )



    

    n_mape_unstable = sum(1 for m in model_metrics.values() if m.mape_unstable)

    dataset_mape_unreliable = (n_mape_unstable > 6)



    rankable = {

        name: m for name, m in model_metrics.items()

        if getattr(m, ranking_metric, None) is not None

    }

    ranking = sorted(rankable.keys(), key=lambda name: getattr(rankable[name], ranking_metric))



    best_model = ranking[0] if ranking else None



    result = DatasetEvaluationResult(

        dataset_id=dataset_id,

        model_metrics=model_metrics,

        ranking=ranking,

        best_model=best_model,

        ranking_metric=ranking_metric,

    )



    exp_log.info(

        f"[Stage 5] dataset_id={dataset_id} ranking={ranking} best_model={best_model}"

    )



    _write_evaluation_results(result, dataset_mape_unreliable=dataset_mape_unreliable)



    return result





def _write_evaluation_results(result, dataset_mape_unreliable=False):

    out_dir = _PERFORMANCE_EVIDENCE_ROOT() / result.dataset_id

    out_dir.mkdir(parents=True, exist_ok=True)



    payload = {

        "dataset_id": result.dataset_id,

        "ranking_metric": result.ranking_metric,

        "ranking": result.ranking,

        "best_model": result.best_model,

        "dataset_mape_unreliable": dataset_mape_unreliable,

        "model_metrics": {name: asdict(m) for name, m in result.model_metrics.items()},

    }

    json_path = out_dir / f"{result.dataset_id}.evaluation.json"

    with open(json_path, "w") as f:

        json.dump(payload, f, indent=2, default=str)



    rows = []

    for name, m in result.model_metrics.items():

        rows.append({

            "dataset_id": result.dataset_id, "model": name,

            "MAE": m.mae, "RMSE": m.rmse, "MAPE": m.mape, "sMAPE": m.smape,

            "rank": (result.ranking.index(name) + 1) if name in result.ranking else None,

        })

    csv_path = out_dir / f"{result.dataset_id}.evaluation.csv"

    pd.DataFrame(rows).to_csv(csv_path, index=False)





def load_evaluation_results(dataset_id):

    path = _PERFORMANCE_EVIDENCE_ROOT() / dataset_id / f"{dataset_id}.evaluation.json"

    if not path.exists():

        raise FileNotFoundError(

            f"No evaluation results found for '{dataset_id}' at {path}. "

            "Has evaluate_forecasts() been run for this dataset yet?"

        )

    with open(path, "r") as f:

        return json.load(f)





__all__ = [

    "ModelMetrics",

    "DatasetEvaluationResult",

    "compute_metrics_for_model",

    "evaluate_forecasts",

    "load_evaluation_results",

    "_PERFORMANCE_EVIDENCE_ROOT()",

    "is_complete",

    "is_accounting_valid",

    "_is_genuine_int",

]

