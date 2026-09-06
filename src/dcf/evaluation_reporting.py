"""
evaluation_reporting.py

Section 16 deferred deliverables: Model Performance Summaries,
Dataset Performance Summaries, Dataset Difficulty Analysis,
Cross-Model Comparison, Cross-Dataset Comparison, 7 Tables,
6 Figures, and Evaluation Summary Report.

This module extends evaluation_layer.py's core (MAE/RMSE/MAPE/sMAPE,
ranking, best-model) with the full Section 16 analytical output layer.

It reads from the Performance Evidence Repository already written by
evaluate_forecasts() -- it does NOT recompute metrics. This preserves
the Section 16 mandate that "identical configuration produces identical
outputs" by deriving everything from the already-frozen metric records.

DIFFICULTY CLASSIFICATION: follows the same thresholds as
forecasting_behavior_analysis.py (best_model_rmse / naive_rmse):
  < 0.5  -> Easy
  < 0.9  -> Moderate
  >= 0.9 -> Difficult
These are the publication implementation defaults and are
shared by both modules via the frozen config key
characterization.difficulty_thresholds (falling back to these values
if the key is absent, for backward compatibility).

RANKING STABILITY: worst_rmse / best_rmse <= 2.0 -> Stable, else Unstable.
Same threshold as forecasting_behavior_analysis.py, shared for consistency.

All figures use matplotlib Agg backend (headless, no X server).
Figures requiring >= 3 datasets produce clearly-labelled placeholders
when fewer datasets are available.
"""

from __future__ import annotations



import json

import warnings

from dataclasses import asdict, dataclass

from pathlib import Path

from typing import Optional



import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt

import matplotlib.patches as mpatches

import numpy as np

import pandas as pd



from dcf.config import Config, get_config

from dcf.evaluation_layer import load_evaluation_results

from dcf.logging_utils import get_error_logger, get_execution_logger, get_experiment_logger

from dcf.repository import _list_evaluation_dataset_ids



PROJECT_ROOT = Path(__file__).resolve().parents[2]



from dcf.pub_paths import sub as _sub

def _EVAL_REPORT_ROOT(): return _sub("04_forecasts/_reports")





DIFFICULTY_EASY = 0.5

DIFFICULTY_MODERATE = 0.9

STABILITY_THRESHOLD = 2.0





@dataclass

class ModelPerformanceSummary:

    model_name: str

    avg_mae: Optional[float]

    avg_rmse: Optional[float]

    avg_mape: Optional[float]

    avg_smape: Optional[float]

    avg_rank: Optional[float]

    rank_frequency: dict           

    n_datasets: int

    n_datasets_best: int           





@dataclass

class DatasetPerformanceSummary:

    dataset_id: str

    avg_rmse_across_models: Optional[float]

    rmse_std_across_models: Optional[float]

    best_model: Optional[str]

    best_rmse: Optional[float]

    naive_rmse: Optional[float]

    difficulty: str

    ranking_stability: str

    n_models_evaluated: int

    model_agreement: str           





@dataclass

class EvaluationReport:

    dataset_ids: list

    model_summaries: dict          

    dataset_summaries: dict        

    cross_model_findings: dict

    cross_dataset_findings: dict

    evaluation_narrative: list

    tables_written: list

    figures_written: list





def _load_all_evaluations(dataset_ids: Optional[list] = None) -> dict:

    """Load evaluation JSON for all available datasets."""

    if dataset_ids is None:

        dataset_ids = _list_evaluation_dataset_ids()

    results = {}

    error_log = get_error_logger()

    for did in dataset_ids:

        try:

            results[did] = load_evaluation_results(did)

        except FileNotFoundError:

            error_log.warning(f"No evaluation results for '{did}'; skipping.")

    return results





def _classify_difficulty(best_rmse, naive_rmse):

    if best_rmse is None or naive_rmse is None or naive_rmse == 0:

        return "Insufficient_Data"

    ratio = best_rmse / naive_rmse

    if ratio < DIFFICULTY_EASY:

        return "Easy"

    elif ratio < DIFFICULTY_MODERATE:

        return "Moderate"

    else:

        return "Difficult"





def _classify_stability_and_agreement(model_metrics):

    rmses = [v.get("rmse") for v in model_metrics.values() if v.get("rmse") is not None]

    if len(rmses) < 2:

        return "Insufficient_Data", "Insufficient_Data"

    spread = max(rmses) / min(rmses) if min(rmses) > 0 else float("inf")

    stability = "Stable" if spread <= STABILITY_THRESHOLD else "Unstable"

    agreement = "High" if spread < 1.5 else ("Moderate" if spread < 3.0 else "Low")

    return stability, agreement





def build_model_performance_summaries(evals: dict) -> dict:

    """Aggregate per-model performance across all datasets."""

    model_stats = {}  



    for did, ev in evals.items():

        ranking = ev.get("ranking", [])

        best = ev.get("best_model")

        for model, metrics in ev.get("model_metrics", {}).items():

            if model not in model_stats:

                model_stats[model] = {"mae": [], "rmse": [], "mape": [], "smape": [],

                                      "ranks": [], "freq": {}, "n_best": 0, "n_ds": 0}

            s = model_stats[model]

            s["n_ds"] += 1

            for k in ("mae", "rmse", "mape", "smape"):

                v = metrics.get(k)

                if v is not None:

                    s[k].append(v)

            if model in ranking:

                rank = ranking.index(model) + 1

                s["ranks"].append(rank)

                s["freq"][rank] = s["freq"].get(rank, 0) + 1

            if model == best:

                s["n_best"] += 1



    summaries = {}

    for model, s in model_stats.items():

        summaries[model] = ModelPerformanceSummary(

            model_name=model,

            avg_mae=float(np.mean(s["mae"])) if s["mae"] else None,

            avg_rmse=float(np.mean(s["rmse"])) if s["rmse"] else None,

            avg_mape=float(np.mean(s["mape"])) if s["mape"] else None,

            avg_smape=float(np.mean(s["smape"])) if s["smape"] else None,

            avg_rank=float(np.mean(s["ranks"])) if s["ranks"] else None,

            rank_frequency=s["freq"],

            n_datasets=s["n_ds"],

            n_datasets_best=s["n_best"],

        )

    return summaries





def build_dataset_performance_summaries(evals: dict) -> dict:

    summaries = {}

    for did, ev in evals.items():

        metrics = ev.get("model_metrics", {})

        best = ev.get("best_model")

        rmses = [v.get("rmse") for v in metrics.values() if v.get("rmse") is not None]

        best_rmse = metrics.get(best, {}).get("rmse") if best else None

        naive_rmse = metrics.get("naive", {}).get("rmse")

        stability, agreement = _classify_stability_and_agreement(metrics)

        summaries[did] = DatasetPerformanceSummary(

            dataset_id=did,

            avg_rmse_across_models=float(np.mean(rmses)) if rmses else None,

            rmse_std_across_models=float(np.std(rmses, ddof=0)) if len(rmses) > 1 else None,

            best_model=best,

            best_rmse=best_rmse,

            naive_rmse=naive_rmse,

            difficulty=_classify_difficulty(best_rmse, naive_rmse),

            ranking_stability=stability,

            n_models_evaluated=len(metrics),

            model_agreement=agreement,

        )

    return summaries





def build_cross_model_findings(model_summaries: dict) -> dict:

    """Cross-model comparison per Section 16."""

    if not model_summaries:

        return {}

    ranked_by_rmse = sorted(

        [(m, s.avg_rmse) for m, s in model_summaries.items() if s.avg_rmse is not None],

        key=lambda x: x[1]

    )

    ranked_by_consistency = sorted(

        [(m, s.avg_rank) for m, s in model_summaries.items() if s.avg_rank is not None],

        key=lambda x: x[1]

    )

    return {

        "strongest_model": ranked_by_rmse[0][0] if ranked_by_rmse else None,

        "weakest_model": ranked_by_rmse[-1][0] if ranked_by_rmse else None,

        "most_consistent_model": ranked_by_consistency[0][0] if ranked_by_consistency else None,

        "most_variable_model": ranked_by_consistency[-1][0] if ranked_by_consistency else None,

        "rmse_ranking": [m for m, _ in ranked_by_rmse],

        "consistency_ranking": [m for m, _ in ranked_by_consistency],

    }





def build_cross_dataset_findings(dataset_summaries: dict) -> dict:

    """Cross-dataset comparison per Section 16."""

    if not dataset_summaries:

        return {}

    difficulty_map = {}

    for did, s in dataset_summaries.items():

        difficulty_map.setdefault(s.difficulty, []).append(did)



    rmse_pairs = [(did, s.avg_rmse_across_models)

                  for did, s in dataset_summaries.items()

                  if s.avg_rmse_across_models is not None]

    ranked = sorted(rmse_pairs, key=lambda x: x[1]) if rmse_pairs else []



    return {

        "easy_datasets": difficulty_map.get("Easy", []),

        "moderate_datasets": difficulty_map.get("Moderate", []),

        "difficult_datasets": difficulty_map.get("Difficult", []),

        "easiest_dataset": ranked[0][0] if ranked else None,

        "hardest_dataset": ranked[-1][0] if ranked else None,

        "difficulty_distribution": {k: len(v) for k, v in difficulty_map.items()},

    }





def generate_evaluation_narrative(

    model_summaries: dict,

    dataset_summaries: dict,

    cross_model: dict,

    cross_dataset: dict,

) -> list:

    """Auto-generated evaluation summary per Section 16 'Required Evaluation Summary Report'."""

    findings = []

    n_ds = len(dataset_summaries)

    n_models = len(model_summaries)



    findings.append(

        f"EVALUATION COVERAGE: {n_ds} dataset(s) evaluated across {n_models} forecasting model(s)."

    )



    if cross_model.get("strongest_model"):

        best_ms = model_summaries[cross_model["strongest_model"]]

        findings.append(

            f"BEST MODEL (lowest avg RMSE across datasets): "

            f"{cross_model['strongest_model']} "

            f"(avg RMSE={best_ms.avg_rmse:.4f} over {best_ms.n_datasets} dataset(s))."

        )



    if cross_model.get("most_consistent_model"):

        findings.append(

            f"MOST CONSISTENT MODEL (lowest avg rank): {cross_model['most_consistent_model']}."

        )



    if cross_model.get("weakest_model") and cross_model["weakest_model"] != cross_model.get("strongest_model"):

        worst_ms = model_summaries[cross_model["weakest_model"]]

        findings.append(

            f"WEAKEST MODEL (highest avg RMSE): {cross_model['weakest_model']} "

            f"(avg RMSE={worst_ms.avg_rmse:.4f})."

        )



    if cross_dataset.get("difficulty_distribution"):

        findings.append(

            f"DIFFICULTY DISTRIBUTION: {cross_dataset['difficulty_distribution']}."

        )



    for did, s in sorted(dataset_summaries.items()):

        best_rmse_s = f"{s.best_rmse:.4f}" if s.best_rmse is not None else "N/A"

        naive_rmse_s = f"{s.naive_rmse:.4f}" if s.naive_rmse is not None else "N/A"

        findings.append(

            f"DATASET [{did}]: best_model={s.best_model}, "

            f"best_RMSE={best_rmse_s}, "

            f"naive_RMSE={naive_rmse_s}, "

            f"difficulty={s.difficulty}, ranking_stability={s.ranking_stability}, "

            f"model_agreement={s.model_agreement}."

        )



    if n_ds < 3:

        findings.append(

            "INSUFFICIENT DATA FOR CROSS-DATASET STATISTICAL COMPARISON: "

            f"Only {n_ds} dataset(s) have complete evaluation results. "

            "Cross-dataset pattern analysis requires >= 3 datasets. "

            "This report will expand automatically when additional datasets "

            "complete the full pipeline."

        )

    return findings













def _write_eval_table(rows, filename):

    _EVAL_REPORT_ROOT().mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame(rows)

    csv_path = _EVAL_REPORT_ROOT() / f"{filename}.csv"

    json_path = _EVAL_REPORT_ROOT() / f"{filename}.json"

    df.to_csv(csv_path, index=False)

    df.to_json(json_path, orient="records", indent=2)

    return csv_path





def generate_eval_table_1(evals):

    """T1: Dataset x Model x MAE/RMSE/MAPE/sMAPE"""

    rows = []

    for did, ev in sorted(evals.items()):

        for m, met in ev.get("model_metrics", {}).items():

            rows.append({"dataset_id": did, "model": m,

                         "MAE": met.get("mae"), "RMSE": met.get("rmse"),

                         "MAPE": met.get("mape"), "sMAPE": met.get("smape")})

    return _write_eval_table(rows or [{"note": "no data"}], "eval_table_1_performance")





def generate_eval_table_2(evals):

    """T2: Dataset-wise model rankings"""

    rows = []

    for did, ev in sorted(evals.items()):

        for rank, model in enumerate(ev.get("ranking", []), 1):

            rmse = ev.get("model_metrics", {}).get(model, {}).get("rmse")

            rows.append({"dataset_id": did, "rank": rank, "model": model, "rmse": rmse})

    return _write_eval_table(rows or [{"note": "no data"}], "eval_table_2_rankings")





def generate_eval_table_3(evals):

    """T3: Best-performing model per dataset"""

    rows = []

    for did, ev in sorted(evals.items()):

        best = ev.get("best_model")

        rmse = ev.get("model_metrics", {}).get(best, {}).get("rmse") if best else None

        rows.append({"dataset_id": did, "best_model": best, "best_rmse": rmse})

    return _write_eval_table(rows or [{"note": "no data"}], "eval_table_3_best_models")





def generate_eval_table_4(model_summaries):

    """T4: Model performance summaries"""

    rows = []

    for m, s in sorted(model_summaries.items()):

        rows.append({

            "model": m, "avg_mae": s.avg_mae, "avg_rmse": s.avg_rmse,

            "avg_mape": s.avg_mape, "avg_smape": s.avg_smape,

            "avg_rank": s.avg_rank, "n_datasets": s.n_datasets,

            "n_datasets_best": s.n_datasets_best,

        })

    return _write_eval_table(rows or [{"note": "no data"}], "eval_table_4_model_summaries")





def generate_eval_table_5(dataset_summaries):

    """T5: Dataset performance summaries"""

    rows = []

    for did, s in sorted(dataset_summaries.items()):

        rows.append({

            "dataset_id": did, "avg_rmse": s.avg_rmse_across_models,

            "rmse_std": s.rmse_std_across_models, "best_model": s.best_model,

            "best_rmse": s.best_rmse, "naive_rmse": s.naive_rmse,

            "n_models": s.n_models_evaluated, "model_agreement": s.model_agreement,

        })

    return _write_eval_table(rows or [{"note": "no data"}], "eval_table_5_dataset_summaries")





def generate_eval_table_6(dataset_summaries):

    """T6: Dataset difficulty classification"""

    rows = []

    for did, s in sorted(dataset_summaries.items()):

        rows.append({

            "dataset_id": did, "difficulty": s.difficulty,

            "ranking_stability": s.ranking_stability,

            "best_rmse": s.best_rmse, "naive_rmse": s.naive_rmse,

        })

    return _write_eval_table(rows or [{"note": "no data"}], "eval_table_6_difficulty")





def generate_eval_table_7(dataset_summaries):

    """T7: Cross-dataset comparison"""

    rows = []

    for did, s in sorted(dataset_summaries.items()):

        rows.append({

            "dataset_id": did, "avg_rmse": s.avg_rmse_across_models,

            "difficulty": s.difficulty, "best_model": s.best_model,

        })

    return _write_eval_table(rows or [{"note": "no data"}], "eval_table_7_cross_dataset")













def _placeholder_eval_fig(title, message, path):

    fig, ax = plt.subplots(figsize=(8, 5))

    ax.text(0.5, 0.5, f"{title}\n\n{message}", ha="center", va="center",

            fontsize=12, color="#555", wrap=True,

            bbox=dict(facecolor="#f9f9f9", edgecolor="#ccc", boxstyle="round,pad=0.5"))

    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")

    ax.set_title(title, fontsize=13)

    plt.tight_layout()

    _EVAL_REPORT_ROOT().mkdir(parents=True, exist_ok=True)

    fig.savefig(path, dpi=300, bbox_inches="tight")

    plt.close(fig)

    return path





def generate_eval_figure_1(evals):

    """F1: Forecasting performance comparison charts (RMSE per model per dataset)."""

    path = _EVAL_REPORT_ROOT() / "eval_figure_1_performance_comparison.png"

    if not evals:

        return _placeholder_eval_fig("Figure 1: Performance Comparison", "No data.", path)

    n = len(evals)

    fig, axes = plt.subplots(1, n, figsize=(max(8, 5 * n), 6), squeeze=False)

    axes = axes[0]

    fam_colors = {"naive": "#95A5A6", "seasonal_naive": "#BDC3C7", "drift": "#AAB7B8",

                  "arima": "#2B6CB0", "sarima": "#1A4F7A", "ets": "#4A90D9",

                  "random_forest": "#27AE60", "xgboost": "#1E8449", "svr": "#A9DFBF",

                  "lstm": "#E74C3C", "gru": "#CB4335", "tcn": "#F1948A"}

    for ax, (did, ev) in zip(axes, sorted(evals.items())):

        metrics = ev.get("model_metrics", {})

        valid = sorted([(m, v.get("rmse")) for m, v in metrics.items() if v.get("rmse") is not None],

                       key=lambda x: x[1])

        if not valid:

            ax.text(0.5, 0.5, "No data", ha="center", va="center"); ax.set_title(did); continue

        labels, values = zip(*valid)

        colors = [fam_colors.get(m, "#999") for m in labels]

        ax.barh(range(len(labels)), values, color=colors, edgecolor="white")

        ax.set_yticks(range(len(labels))); ax.set_yticklabels(labels, fontsize=7)

        ax.set_xlabel("RMSE"); ax.set_title(did, fontsize=10)

    fig.suptitle("Figure 1: Forecasting Performance Comparison (RMSE)", fontsize=13)

    plt.tight_layout()

    _EVAL_REPORT_ROOT().mkdir(parents=True, exist_ok=True)

    fig.savefig(path, dpi=300, bbox_inches="tight"); plt.close(fig)

    return path





def generate_eval_figure_2(model_summaries):

    """F2: Ranking comparison - avg rank per model."""

    path = _EVAL_REPORT_ROOT() / "eval_figure_2_ranking_comparison.png"

    if not model_summaries:

        return _placeholder_eval_fig("Figure 2: Ranking Comparison", "No data.", path)

    ranked = sorted([(m, s.avg_rank) for m, s in model_summaries.items() if s.avg_rank is not None],

                    key=lambda x: x[1])

    if not ranked:

        return _placeholder_eval_fig("Figure 2: Ranking Comparison", "No ranking data.", path)

    labels, values = zip(*ranked)

    fig, ax = plt.subplots(figsize=(max(8, len(labels) * 0.7), 5))

    colors = ["#2B6CB0" if i == 0 else "#BDC3C7" for i in range(len(labels))]

    ax.bar(range(len(labels)), values, color=colors, edgecolor="white")

    ax.set_xticks(range(len(labels))); ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=8)

    ax.set_ylabel("Average Rank (lower = better)"); ax.invert_yaxis()

    ax.set_title("Figure 2: Forecasting Model Ranking Comparison (best model in blue)", fontsize=12)

    plt.tight_layout()

    _EVAL_REPORT_ROOT().mkdir(parents=True, exist_ok=True)

    fig.savefig(path, dpi=300, bbox_inches="tight"); plt.close(fig)

    return path





def generate_eval_figure_3(evals):

    """F3: RMSE distribution across models per dataset (box-style bar charts)."""

    path = _EVAL_REPORT_ROOT() / "eval_figure_3_metric_distributions.png"

    if not evals:

        return _placeholder_eval_fig("Figure 3: Metric Distributions", "No data.", path)

    

    fig, axes = plt.subplots(1, max(1, len(evals)), figsize=(max(8, 4 * len(evals)), 5), squeeze=False)

    axes = axes[0]

    for ax, (did, ev) in zip(axes, sorted(evals.items())):

        rmses = [v.get("rmse") for v in ev.get("model_metrics", {}).values() if v.get("rmse") is not None]

        if not rmses:

            ax.text(0.5, 0.5, "No data", ha="center", va="center"); ax.set_title(did); continue

        ax.hist(rmses, bins=min(8, len(rmses)), color="#2B6CB0", alpha=0.75, edgecolor="white")

        ax.axvline(np.mean(rmses), color="#E74C3C", linestyle="--", label=f"Mean={np.mean(rmses):.3f}")

        ax.set_xlabel("RMSE"); ax.set_ylabel("Model count"); ax.set_title(did, fontsize=10)

        ax.legend(fontsize=8)

    fig.suptitle("Figure 3: RMSE Distribution Across Models", fontsize=13)

    plt.tight_layout()

    _EVAL_REPORT_ROOT().mkdir(parents=True, exist_ok=True)

    fig.savefig(path, dpi=300, bbox_inches="tight"); plt.close(fig)

    return path





def generate_eval_figure_4(model_summaries):

    """F4: Model performance summary -- avg RMSE per model (heatmap-style)."""

    path = _EVAL_REPORT_ROOT() / "eval_figure_4_model_performance_summary.png"

    if not model_summaries:

        return _placeholder_eval_fig("Figure 4: Model Performance Summary", "No data.", path)

    models = sorted(model_summaries.keys())

    metrics = ["avg_mae", "avg_rmse", "avg_mape", "avg_smape"]

    data = [[getattr(model_summaries[m], met) or 0 for met in metrics] for m in models]

    arr = np.array(data, dtype=float)

    with warnings.catch_warnings():

        warnings.simplefilter("ignore", RuntimeWarning)

        col_min, col_max = np.nanmin(arr, axis=0), np.nanmax(arr, axis=0)

    denom = np.where(col_max - col_min == 0, 1, col_max - col_min)

    arr_norm = np.where(np.isnan(arr), 0.5, (arr - col_min) / denom)

    fig, ax = plt.subplots(figsize=(max(8, len(metrics) * 1.5), max(4, len(models) * 0.5)))

    im = ax.imshow(arr_norm, aspect="auto", cmap="RdYlGn_r", vmin=0, vmax=1)

    ax.set_xticks(range(len(metrics))); ax.set_xticklabels([m.upper() for m in metrics], fontsize=9)

    ax.set_yticks(range(len(models))); ax.set_yticklabels(models, fontsize=8)

    plt.colorbar(im, ax=ax, label="Normalized (0=best, 1=worst)")

    ax.set_title("Figure 4: Model Performance Summary (normalized)", fontsize=12)

    plt.tight_layout()

    _EVAL_REPORT_ROOT().mkdir(parents=True, exist_ok=True)

    fig.savefig(path, dpi=300, bbox_inches="tight"); plt.close(fig)

    return path





def generate_eval_figure_5(dataset_summaries):

    """F5: Dataset difficulty visualization."""

    path = _EVAL_REPORT_ROOT() / "eval_figure_5_difficulty.png"

    if not dataset_summaries:

        return _placeholder_eval_fig("Figure 5: Dataset Difficulty", "No data.", path)

    diff_colors = {"Easy": "#27AE60", "Moderate": "#F39C12",

                   "Difficult": "#E74C3C", "Insufficient_Data": "#BDC3C7"}

    datasets = sorted(dataset_summaries.keys())

    difficulties = [dataset_summaries[d].difficulty for d in datasets]

    best_rmses = [dataset_summaries[d].best_rmse or 0 for d in datasets]

    colors = [diff_colors.get(d, "#999") for d in difficulties]

    fig, ax = plt.subplots(figsize=(max(6, len(datasets) * 1.2), 5))

    bars = ax.bar(datasets, best_rmses, color=colors, edgecolor="white")

    ax.set_ylabel("Best Model RMSE"); ax.set_xlabel("Dataset")

    ax.set_title("Figure 5: Dataset Difficulty (best model RMSE)", fontsize=12)

    patches = [mpatches.Patch(color=c, label=l) for l, c in diff_colors.items() if l != "Insufficient_Data"]

    ax.legend(handles=patches, fontsize=9)

    plt.tight_layout()

    _EVAL_REPORT_ROOT().mkdir(parents=True, exist_ok=True)

    fig.savefig(path, dpi=300, bbox_inches="tight"); plt.close(fig)

    return path





def generate_eval_figure_6(dataset_summaries):

    """F6: Cross-dataset comparison visualization."""

    path = _EVAL_REPORT_ROOT() / "eval_figure_6_cross_dataset.png"

    if len(dataset_summaries) < 2:

        return _placeholder_eval_fig(

            "Figure 6: Cross-Dataset Comparison",

            f"INSUFFICIENT DATA: {len(dataset_summaries)} dataset(s) available.\n"

            "Cross-dataset comparison requires >= 2 datasets.",

            path)

    datasets = sorted(dataset_summaries.keys())

    metrics = ["avg_rmse_across_models", "best_rmse", "naive_rmse"]

    labels = ["Avg RMSE (all models)", "Best Model RMSE", "Naive RMSE"]

    fig, ax = plt.subplots(figsize=(max(8, len(datasets) * 1.5), 5))

    x = np.arange(len(datasets))

    width = 0.25

    colors = ["#2B6CB0", "#27AE60", "#95A5A6"]

    for i, (met, label) in enumerate(zip(metrics, labels)):

        vals = [getattr(dataset_summaries[d], met) or 0 for d in datasets]

        ax.bar(x + i * width, vals, width, label=label, color=colors[i], alpha=0.85)

    ax.set_xticks(x + width)

    ax.set_xticklabels(datasets, rotation=30, ha="right", fontsize=9)

    ax.set_ylabel("RMSE"); ax.set_title("Figure 6: Cross-Dataset RMSE Comparison", fontsize=12)

    ax.legend(fontsize=9)

    plt.tight_layout()

    _EVAL_REPORT_ROOT().mkdir(parents=True, exist_ok=True)

    fig.savefig(path, dpi=300, bbox_inches="tight"); plt.close(fig)

    return path













def generate_evaluation_report(

    dataset_ids: Optional[list] = None,

    config: Optional[Config] = None,

) -> EvaluationReport:

    """
    Generate the full Section 16 Evaluation Layer reporting outputs:
    7 Tables, 6 Figures, model/dataset/cross summaries, narrative report.
    Reads from the Performance Evidence Repository -- does not recompute metrics.
    """

    cfg = config or get_config(allow_draft=False)

    exec_log = get_execution_logger()

    exp_log = get_experiment_logger()



    exec_log.info("[Eval Report] Generating Section 16 full evaluation report")



    evals = _load_all_evaluations(dataset_ids)



    model_summaries = build_model_performance_summaries(evals)

    dataset_summaries = build_dataset_performance_summaries(evals)

    cross_model = build_cross_model_findings(model_summaries)

    cross_dataset = build_cross_dataset_findings(dataset_summaries)

    narrative = generate_evaluation_narrative(model_summaries, dataset_summaries, cross_model, cross_dataset)



    

    tables = [

        generate_eval_table_1(evals), generate_eval_table_2(evals),

        generate_eval_table_3(evals), generate_eval_table_4(model_summaries),

        generate_eval_table_5(dataset_summaries), generate_eval_table_6(dataset_summaries),

        generate_eval_table_7(dataset_summaries),

    ]



    

    figs = [

        generate_eval_figure_1(evals), generate_eval_figure_2(model_summaries),

        generate_eval_figure_3(evals), generate_eval_figure_4(model_summaries),

        generate_eval_figure_5(dataset_summaries), generate_eval_figure_6(dataset_summaries),

    ]



    

    _EVAL_REPORT_ROOT().mkdir(parents=True, exist_ok=True)

    narrative_path = _EVAL_REPORT_ROOT() / "evaluation_summary_report.json"

    with open(narrative_path, "w") as f:

        json.dump({

            "dataset_ids": sorted(evals.keys()),

            "cross_model_findings": cross_model,

            "cross_dataset_findings": cross_dataset,

            "narrative": narrative,

        }, f, indent=2, default=str)



    

    ms_path = _EVAL_REPORT_ROOT() / "model_performance_summaries.json"

    with open(ms_path, "w") as f:

        json.dump({m: asdict(s) for m, s in model_summaries.items()}, f, indent=2, default=str)



    

    ds_path = _EVAL_REPORT_ROOT() / "dataset_performance_summaries.json"

    with open(ds_path, "w") as f:

        json.dump({d: asdict(s) for d, s in dataset_summaries.items()}, f, indent=2, default=str)



    result = EvaluationReport(

        dataset_ids=sorted(evals.keys()),

        model_summaries=model_summaries,

        dataset_summaries=dataset_summaries,

        cross_model_findings=cross_model,

        cross_dataset_findings=cross_dataset,

        evaluation_narrative=narrative,

        tables_written=[str(p) for p in tables],

        figures_written=[str(p) for p in figs],

    )



    exp_log.info(

        f"[Eval Report] Complete: {len(evals)} dataset(s), "

        f"{len(tables)} tables, {len(figs)} figures, {len(narrative)} findings."

    )



    return result





def load_evaluation_report() -> dict:

    path = _EVAL_REPORT_ROOT() / "evaluation_summary_report.json"

    if not path.exists():

        raise FileNotFoundError(

            f"No evaluation report found at {path}. "

            "Has generate_evaluation_report() been run?"

        )

    with open(path) as f:

        return json.load(f)





__all__ = [

    "ModelPerformanceSummary", "DatasetPerformanceSummary", "EvaluationReport",

    "generate_evaluation_report", "load_evaluation_report",

    "build_model_performance_summaries", "build_dataset_performance_summaries",

    "build_cross_model_findings", "build_cross_dataset_findings",

    "_EVAL_REPORT_ROOT()", "DIFFICULTY_EASY", "DIFFICULTY_MODERATE", "STABILITY_THRESHOLD",

]

