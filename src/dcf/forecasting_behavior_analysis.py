"""
forecasting_behavior_analysis.py

Stage 6 of the DCF pipeline: Forecasting Behavior Analysis (FBA),
per DCF specification

Section 14 provides general analysis context while
Sections 17-18 control the final relationship-discovery implementation.
Stage 6 therefore:
  1. Produces per-dataset DatasetBehaviorSummary objects.
  2. Produces cross-dataset summary Tables 1-7 (CSV + JSON).
  3. Produces Figures 1-7 (PNG via matplotlib Agg backend).
  4. Generates analytical summary text.

Outputs go to results/05_analysis/fba/ and feed Stage 7.

IMPLEMENTATION-DEFAULT THRESHOLDS:
  Difficulty (relative to Naive RMSE):
    ratio < 0.5   -> Easy
    ratio < 0.9   -> Moderate
    ratio >= 0.9  -> Difficult
  Ranking stability (worst/best RMSE ratio):
    ratio <= 2.0  -> Stable
    ratio >  2.0  -> Unstable
  Stored as publication defaults in the frozen configuration.

INSUFFICIENT-DATA HANDLING: Figures 5-7 require >= 3 datasets.
Fewer produces clearly-labelled placeholder images.
"""

from __future__ import annotations



import json

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

from dcf.logging_utils import get_error_logger, get_execution_logger, get_experiment_logger

from dcf.repository import load_evidence_bundles, verify_dataset_id_consistency



PROJECT_ROOT = Path(__file__).resolve().parents[2]

from dcf.pub_paths import sub as _sub

def _FBA_ROOT(): return _sub("05_analysis/fba")



CHARACTERIZATION_MEASURES = ["TSS", "PSS", "VS", "SIS", "PS", "SS", "TDS"]

MODEL_FAMILIES = {

    "baseline": ["naive", "seasonal_naive", "drift"],

    "statistical": ["arima", "sarima", "ets"],

    "ml": ["random_forest", "xgboost", "svr"],

    "dl": ["lstm", "gru", "tcn"],

}













DIFFICULTY_THRESHOLD_EASY = 0.50

DIFFICULTY_THRESHOLD_MODERATE = 0.90

RANKING_STABILITY_THRESHOLD = 2.00





@dataclass

class DatasetBehaviorSummary:

    dataset_id: str

    domain_profile: dict

    best_model: Optional[str]

    best_model_rmse: Optional[float]

    naive_rmse: Optional[float]

    difficulty: str

    ranking_stability: str

    rmse_spread_ratio: Optional[float]

    mean_rmse_by_family: dict

    ranking: list

    all_model_metrics: dict





@dataclass

class FBAResult:

    dataset_ids: list

    dataset_summaries: dict

    analytical_findings: list

    tables_written: list

    figures_written: list





def _classify_difficulty(best_rmse, naive_rmse, cfg=None):

    if best_rmse is None or naive_rmse is None or naive_rmse == 0:

        return "Insufficient_Data", None

    ratio = best_rmse / naive_rmse

    easy_max = (cfg.get("forecasting_behavior.difficulty_thresholds.easy_max_ratio", DIFFICULTY_THRESHOLD_EASY)

                if cfg else DIFFICULTY_THRESHOLD_EASY)

    mod_max = (cfg.get("forecasting_behavior.difficulty_thresholds.moderate_max_ratio", DIFFICULTY_THRESHOLD_MODERATE)

               if cfg else DIFFICULTY_THRESHOLD_MODERATE)

    if ratio < easy_max:

        return "Easy", ratio

    elif ratio < mod_max:

        return "Moderate", ratio

    else:

        return "Difficult", ratio





def _classify_ranking_stability(all_rmses, cfg=None):

    valid = [r for r in all_rmses if r is not None and r > 0]

    if len(valid) < 2:

        return "Insufficient_Data", None

    ratio = max(valid) / min(valid)

    stable_max = (cfg.get("forecasting_behavior.ranking_stability_threshold.stable_max_ratio", RANKING_STABILITY_THRESHOLD)

                  if cfg else RANKING_STABILITY_THRESHOLD)

    return ("Stable", ratio) if ratio <= stable_max else ("Unstable", ratio)





def _mean_rmse_by_family(model_metrics):

    results = {}

    for family, models in MODEL_FAMILIES.items():

        rmses = [model_metrics[m]["rmse"] for m in models

                 if m in model_metrics and model_metrics[m].get("rmse") is not None]

        results[family] = float(np.mean(rmses)) if rmses else None

    return results





def build_dataset_behavior_summary(dataset_id, domain_profile, evaluation, cfg=None):

    model_metrics = evaluation.get("model_metrics", {})

    ranking = evaluation.get("ranking", [])

    best_model = evaluation.get("best_model")

    best_rmse = model_metrics.get(best_model, {}).get("rmse") if best_model else None

    naive_rmse = model_metrics.get("naive", {}).get("rmse")

    all_rmses = [m.get("rmse") for m in model_metrics.values()]

    difficulty, _ = _classify_difficulty(best_rmse, naive_rmse, cfg=cfg)

    ranking_stability, spread_ratio = _classify_ranking_stability(all_rmses, cfg=cfg)

    dp_scores = {m: domain_profile.get(m.lower()) for m in CHARACTERIZATION_MEASURES}

    return DatasetBehaviorSummary(

        dataset_id=dataset_id,

        domain_profile=dp_scores,

        best_model=best_model,

        best_model_rmse=best_rmse,

        naive_rmse=naive_rmse,

        difficulty=difficulty,

        ranking_stability=ranking_stability,

        rmse_spread_ratio=spread_ratio,

        mean_rmse_by_family=_mean_rmse_by_family(model_metrics),

        ranking=ranking,

        all_model_metrics={

            name: {k: v for k, v in m.items() if k in ("mae", "rmse", "mape", "smape")}

            for name, m in model_metrics.items()

        },

    )





def _write_table(data, filename):

    _FBA_ROOT().mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame(data)

    csv_path = _FBA_ROOT() / f"{filename}.csv"

    json_path = _FBA_ROOT() / f"{filename}.json"

    df.to_csv(csv_path, index=False)

    df.to_json(json_path, orient="records", indent=2)

    return csv_path





def generate_table_1(summaries):

    rows = []

    for did, s in sorted(summaries.items()):

        row = {"dataset_id": did}

        row.update({m: s.domain_profile.get(m) for m in CHARACTERIZATION_MEASURES})

        rows.append(row)

    return _write_table(rows or [{"note": "no datasets available"}], "table_1_domain_profile_summary")





def generate_table_2(summaries):

    rows = []

    for did, s in sorted(summaries.items()):

        for model, metrics in s.all_model_metrics.items():

            rows.append({"dataset_id": did, "model": model,

                         "MAE": metrics.get("mae"), "RMSE": metrics.get("rmse"),

                         "MAPE": metrics.get("mape"), "sMAPE": metrics.get("smape")})

    return _write_table(rows or [{"note": "no datasets available"}], "table_2_forecasting_performance_summary")





def generate_table_3(summaries):

    rows = []

    for did, s in sorted(summaries.items()):

        for rank, model in enumerate(s.ranking, 1):

            rmse = s.all_model_metrics.get(model, {}).get("rmse")

            rows.append({"dataset_id": did, "rank": rank, "model": model, "rmse": rmse})

    return _write_table(rows or [{"note": "no datasets available"}], "table_3_model_rankings")





def generate_table_4(summaries):

    rows = []

    for did, s in sorted(summaries.items()):

        for m in CHARACTERIZATION_MEASURES:

            rows.append({"dataset_id": did, "characteristic": m,

                         "value": s.domain_profile.get(m),

                         "best_model_rmse": s.best_model_rmse,

                         "difficulty": s.difficulty})

    return _write_table(rows or [{"note": "no datasets available"}], "table_4_profile_performance_correlation")





def generate_table_5(summaries):

    rows = []

    for did, s in sorted(summaries.items()):

        for m in CHARACTERIZATION_MEASURES:

            rows.append({"dataset_id": did, "characteristic": m,

                         "value": s.domain_profile.get(m),

                         "ranking_stability": s.ranking_stability,

                         "spread_ratio": s.rmse_spread_ratio})

    return _write_table(rows or [{"note": "no datasets available"}], "table_5_profile_ranking_correlation")





def generate_table_6(summaries):

    rows = []

    for did, s in sorted(summaries.items()):

        row = {"dataset_id": did, "best_model": s.best_model,

               "best_model_rmse": s.best_model_rmse, "naive_rmse": s.naive_rmse,

               "difficulty": s.difficulty, "ranking_stability": s.ranking_stability}

        row.update({f"mean_rmse_{fam}": s.mean_rmse_by_family.get(fam) for fam in MODEL_FAMILIES})

        rows.append(row)

    return _write_table(rows or [{"note": "no datasets available"}], "table_6_cross_domain_comparison")





def generate_table_7(summaries):

    ids = sorted(summaries.keys())

    rows = []

    for i, did_a in enumerate(ids):

        vec_a = np.array([summaries[did_a].domain_profile.get(m, 0) or 0 for m in CHARACTERIZATION_MEASURES])

        for did_b in ids[i + 1:]:

            vec_b = np.array([summaries[did_b].domain_profile.get(m, 0) or 0 for m in CHARACTERIZATION_MEASURES])

            rows.append({"dataset_a": did_a, "dataset_b": did_b,

                         "euclidean_distance": float(np.linalg.norm(vec_a - vec_b))})

    return _write_table(rows if rows else [{"note": "fewer than 2 datasets available"}],

                        "table_7_domain_profile_similarity")





def _placeholder_figure(title, message, filepath):

    fig, ax = plt.subplots(figsize=(8, 5))

    ax.text(0.5, 0.5, f"{title}\n\n{message}", ha="center", va="center",

            fontsize=12, color="#555555", wrap=True,

            bbox=dict(facecolor="#f9f9f9", edgecolor="#cccccc", boxstyle="round,pad=0.5"))

    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")

    ax.set_title(title, fontsize=13, pad=10)

    plt.tight_layout()

    _FBA_ROOT().mkdir(parents=True, exist_ok=True)

    fig.savefig(filepath, dpi=300, bbox_inches="tight")

    plt.close(fig)

    return filepath





def _safe_close():

    try:

        plt.close("all")

    except Exception:

        pass





def generate_figure_1(summaries):

    """Figure 1: Domain Profile Radar Charts."""

    path = _FBA_ROOT() / "figure_1_domain_profile_radar.png"

    n = len(summaries)

    if n == 0:

        return _placeholder_figure("Figure 1: Domain Profile Radar Charts",

                                   "INSUFFICIENT DATA: No datasets available.", path)

    measures = CHARACTERIZATION_MEASURES

    angles = np.linspace(0, 2 * np.pi, len(measures), endpoint=False).tolist()

    angles += angles[:1]

    cols = min(n, 3)

    rows_fig = (n + cols - 1) // cols

    fig, axes = plt.subplots(rows_fig, cols, figsize=(5 * cols, 5 * rows_fig),

                             subplot_kw=dict(polar=True))

    if n == 1:

        axes = np.array([[axes]])

    elif rows_fig == 1:

        axes = np.array([axes])

    for idx, (did, s) in enumerate(sorted(summaries.items())):

        ax = axes[idx // cols][idx % cols]

        values = [s.domain_profile.get(m, 0) or 0 for m in measures] + [s.domain_profile.get(measures[0], 0) or 0]

        ax.plot(angles, values, "o-", linewidth=2, color="#2B6CB0")

        ax.fill(angles, values, alpha=0.2, color="#2B6CB0")

        ax.set_xticks(angles[:-1])

        ax.set_xticklabels(measures, size=9)

        ax.set_ylim(0, 1)

        ax.set_title(did, size=11, pad=15)

    for idx in range(n, rows_fig * cols):

        try:

            fig.delaxes(axes[idx // cols][idx % cols])

        except Exception:

            pass

    fig.suptitle("Figure 1: Domain Profile Radar Charts", fontsize=14, y=1.02)

    plt.tight_layout()

    _FBA_ROOT().mkdir(parents=True, exist_ok=True)

    fig.savefig(path, dpi=300, bbox_inches="tight")

    _safe_close()

    return path





def generate_figure_2(summaries):

    """Figure 2: Forecasting Performance Comparison Charts."""

    path = _FBA_ROOT() / "figure_2_performance_comparison.png"

    if not summaries:

        return _placeholder_figure("Figure 2: Forecasting Performance Comparison",

                                   "INSUFFICIENT DATA: No datasets available.", path)

    n = len(summaries)

    fig, axes = plt.subplots(1, n, figsize=(max(8, 5 * n), 6))

    if n == 1:

        axes = [axes]

    fam_colors = {"baseline": "#95A5A6", "statistical": "#2B6CB0", "ml": "#27AE60", "dl": "#E74C3C"}

    for ax, (did, s) in zip(axes, sorted(summaries.items())):

        valid = [(m, r) for m, r in [(m, s.all_model_metrics[m].get("rmse")) for m in s.all_model_metrics]

                 if r is not None]

        if not valid:

            ax.text(0.5, 0.5, "No data", ha="center", va="center")

            ax.set_title(did)

            continue

        m_labels, m_rmses = zip(*sorted(valid, key=lambda x: x[1]))

        colors = []

        for m in m_labels:

            color = "#555"

            for fam, fam_models in MODEL_FAMILIES.items():

                if m in fam_models:

                    color = fam_colors.get(fam, "#555")

                    break

            colors.append(color)

        ax.barh(range(len(m_labels)), m_rmses, color=colors, edgecolor="white")

        ax.set_yticks(range(len(m_labels)))

        ax.set_yticklabels(m_labels, fontsize=8)

        ax.set_xlabel("RMSE")

        ax.set_title(did, fontsize=11)

    legend_patches = [mpatches.Patch(color=c, label=f.capitalize()) for f, c in fam_colors.items()]

    fig.legend(handles=legend_patches, loc="lower center", ncol=4, fontsize=9, bbox_to_anchor=(0.5, -0.05))

    fig.suptitle("Figure 2: Forecasting Performance Comparison (RMSE)", fontsize=14)

    plt.tight_layout()

    _FBA_ROOT().mkdir(parents=True, exist_ok=True)

    fig.savefig(path, dpi=300, bbox_inches="tight")

    _safe_close()

    return path





def generate_figure_3(summaries):

    """Figure 3: Domain Profile and Metric Value Heatmap."""

    path = _FBA_ROOT() / "figure_3_correlation_heatmap.png"

    if not summaries:

        return _placeholder_figure("Figure 3: Correlation Heatmap",

                                   "INSUFFICIENT DATA: No datasets available.", path)

    metrics_keys = ["mae", "rmse", "mape", "smape"]

    data, index_labels = [], []

    for did, s in sorted(summaries.items()):

        best = s.best_model

        if best and best in s.all_model_metrics:

            row = [s.domain_profile.get(m, np.nan) or np.nan for m in CHARACTERIZATION_MEASURES]

            row += [s.all_model_metrics[best].get(k, np.nan) for k in metrics_keys]

            data.append(row)

            index_labels.append(did)

    if not data:

        return _placeholder_figure("Figure 3: Correlation Heatmap",

                                   "INSUFFICIENT DATA: No metric data available.", path)

    all_labels = CHARACTERIZATION_MEASURES + [m.upper() for m in metrics_keys]

    arr = np.array(data, dtype=float)

    import warnings

    with warnings.catch_warnings():

        warnings.simplefilter("ignore", RuntimeWarning)

        col_min = np.nanmin(arr, axis=0)

        col_max = np.nanmax(arr, axis=0)

    denom = np.where(col_max - col_min == 0, 1, col_max - col_min)

    arr_norm = np.where(np.isnan(arr), 0.5, (arr - col_min) / denom)  

    fig, ax = plt.subplots(figsize=(max(10, len(all_labels) * 0.8), max(4, len(index_labels) * 0.8)))

    im = ax.imshow(arr_norm, aspect="auto", cmap="RdYlGn_r", vmin=0, vmax=1)

    ax.set_xticks(range(len(all_labels)))

    ax.set_xticklabels(all_labels, rotation=45, ha="right", fontsize=9)

    ax.set_yticks(range(len(index_labels)))

    ax.set_yticklabels(index_labels, fontsize=9)

    plt.colorbar(im, ax=ax, label="Normalized value")

    title = ("Figure 3: Domain Profile & Metric Values\n"

             "(cross-dataset correlation requires >=3 datasets; computed in Stage 7)"

             if len(data) < 3 else "Figure 3: Domain Profile & Metric Value Heatmap")

    ax.set_title(title, fontsize=11)

    plt.tight_layout()

    _FBA_ROOT().mkdir(parents=True, exist_ok=True)

    fig.savefig(path, dpi=300, bbox_inches="tight")

    _safe_close()

    return path





def generate_figure_4(summaries):

    """Figure 4: Forecasting Ranking Comparison Charts."""

    path = _FBA_ROOT() / "figure_4_ranking_comparison.png"

    if not summaries:

        return _placeholder_figure("Figure 4: Forecasting Ranking Comparison",

                                   "INSUFFICIENT DATA: No datasets available.", path)

    n = len(summaries)

    fig, axes = plt.subplots(1, n, figsize=(max(8, 5 * n), 6))

    if n == 1:

        axes = [axes]

    for ax, (did, s) in zip(axes, sorted(summaries.items())):

        if not s.ranking:

            ax.text(0.5, 0.5, "No ranking available", ha="center", va="center")

            ax.set_title(did)

            continue

        models = s.ranking[:12]

        for i, m in enumerate(models):

            color = "#2B6CB0" if m == s.best_model else "#BDC3C7"

            ax.barh(len(models) - i, 1, color=color, edgecolor="white")

            ax.text(0.02, len(models) - i, f"{i+1}. {m}", va="center", fontsize=8)

        ax.set_xlim(0, 1.5); ax.set_yticks([]); ax.set_xticks([])

        ax.set_title(f"{did}\n(diff: {s.difficulty}, stab: {s.ranking_stability})", fontsize=10)

    fig.suptitle("Figure 4: Model Rankings (best model in blue)", fontsize=13)

    plt.tight_layout()

    _FBA_ROOT().mkdir(parents=True, exist_ok=True)

    fig.savefig(path, dpi=300, bbox_inches="tight")

    _safe_close()

    return path





def generate_figure_5(summaries):

    """Figure 5: Domain Profile vs Forecasting Performance Scatter Plots."""

    path = _FBA_ROOT() / "figure_5_profile_vs_performance_scatter.png"

    if len(summaries) < 3:

        return _placeholder_figure(

            "Figure 5: Domain Profile vs Forecasting Performance Scatter Plots",

            f"INSUFFICIENT DATA: {len(summaries)} dataset(s) available.\n"

            "Meaningful scatter plots require >=3 datasets.\n"

            "Will be regenerated once sufficient datasets complete the pipeline.",

            path)

    dataset_ids = sorted(summaries.keys())

    measures = CHARACTERIZATION_MEASURES

    fig, axes = plt.subplots(2, (len(measures) + 1) // 2, figsize=(16, 8))

    axes_flat = axes.flatten()

    for i, m in enumerate(measures):

        ax = axes_flat[i]

        x = [summaries[did].domain_profile.get(m, np.nan) or np.nan for did in dataset_ids]

        y = [summaries[did].best_model_rmse for did in dataset_ids]

        ax.scatter(x, y, s=60, color="#2B6CB0", alpha=0.8)

        for did, xi, yi in zip(dataset_ids, x, y):

            if xi is not None and yi is not None:

                ax.annotate(did, (xi, yi), fontsize=7, ha="left")

        ax.set_xlabel(m, fontsize=9); ax.set_ylabel("Best RMSE", fontsize=9)

        ax.set_title(f"{m} vs Best RMSE", fontsize=9)

    for j in range(len(measures), len(axes_flat)):

        fig.delaxes(axes_flat[j])

    fig.suptitle("Figure 5: Domain Profile Measures vs Forecasting Performance", fontsize=13)

    plt.tight_layout()

    _FBA_ROOT().mkdir(parents=True, exist_ok=True)

    fig.savefig(path, dpi=300, bbox_inches="tight")

    _safe_close()

    return path





def generate_figure_6(summaries):

    """Figure 6: Cross-Domain Comparison Visualizations."""

    path = _FBA_ROOT() / "figure_6_cross_domain_comparison.png"

    if len(summaries) < 3:

        return _placeholder_figure(

            "Figure 6: Cross-Domain Comparison Visualizations",

            f"INSUFFICIENT DATA: {len(summaries)} dataset(s) available.\n"

            "Meaningful cross-domain comparison requires >=3 datasets.",

            path)

    dataset_ids = sorted(summaries.keys())

    families = list(MODEL_FAMILIES.keys())

    fig, ax = plt.subplots(figsize=(max(8, len(dataset_ids) * 1.5), 6))

    x = np.arange(len(dataset_ids))

    width = 0.2

    fam_colors = {"baseline": "#95A5A6", "statistical": "#2B6CB0", "ml": "#27AE60", "dl": "#E74C3C"}

    for i, fam in enumerate(families):

        vals = [summaries[did].mean_rmse_by_family.get(fam) or 0 for did in dataset_ids]

        ax.bar(x + i * width, vals, width, label=fam.capitalize(),

               color=fam_colors[fam], alpha=0.85)

    ax.set_xticks(x + width * 1.5)

    ax.set_xticklabels(dataset_ids, rotation=30, ha="right", fontsize=9)

    ax.set_ylabel("Mean RMSE"); ax.set_title("Figure 6: Mean RMSE by Model Family", fontsize=13)

    ax.legend(fontsize=9)

    plt.tight_layout()

    _FBA_ROOT().mkdir(parents=True, exist_ok=True)

    fig.savefig(path, dpi=300, bbox_inches="tight")

    _safe_close()

    return path





def generate_figure_7(summaries):

    """Figure 7: Domain Profile Similarity Visualizations."""

    path = _FBA_ROOT() / "figure_7_domain_profile_similarity.png"

    if len(summaries) < 3:

        return _placeholder_figure(

            "Figure 7: Domain Profile Similarity Visualizations",

            f"INSUFFICIENT DATA: {len(summaries)} dataset(s) available.\n"

            "Meaningful similarity visualizations require >=3 datasets.",

            path)

    ids = sorted(summaries.keys())

    n = len(ids)

    dist_matrix = np.zeros((n, n))

    for i, did_a in enumerate(ids):

        vec_a = np.array([summaries[did_a].domain_profile.get(m, 0) or 0 for m in CHARACTERIZATION_MEASURES])

        for j, did_b in enumerate(ids):

            vec_b = np.array([summaries[did_b].domain_profile.get(m, 0) or 0 for m in CHARACTERIZATION_MEASURES])

            dist_matrix[i, j] = float(np.linalg.norm(vec_a - vec_b))

    fig, ax = plt.subplots(figsize=(max(6, n), max(5, n)))

    im = ax.imshow(dist_matrix, cmap="YlOrRd")

    ax.set_xticks(range(n)); ax.set_yticks(range(n))

    ax.set_xticklabels(ids, rotation=45, ha="right", fontsize=9)

    ax.set_yticklabels(ids, fontsize=9)

    plt.colorbar(im, ax=ax, label="Euclidean distance")

    for i in range(n):

        for j in range(n):

            ax.text(j, i, f"{dist_matrix[i, j]:.2f}", ha="center", va="center",

                    fontsize=8, color="black" if dist_matrix[i, j] < dist_matrix.max() * 0.7 else "white")

    ax.set_title("Figure 7: Domain Profile Pairwise Similarity (Euclidean)", fontsize=13)

    plt.tight_layout()

    _FBA_ROOT().mkdir(parents=True, exist_ok=True)

    fig.savefig(path, dpi=300, bbox_inches="tight")

    _safe_close()

    return path





def generate_analytical_findings(summaries):

    """Auto-generate analytical findings per Section 14 'Required Analytical Findings'."""

    findings = []

    n = len(summaries)

    if n == 0:

        return ["No datasets available for analysis. Analytical findings cannot be generated."]



    findings.append(

        f"DATASET COVERAGE: FBA conducted over {n} dataset(s): "

        f"{', '.join(sorted(summaries.keys()))}."

    )

    for did, s in sorted(summaries.items()):

        dp_str = ", ".join(

            f"{m}={s.domain_profile.get(m):.3f}" if s.domain_profile.get(m) is not None else f"{m}=N/A"

            for m in CHARACTERIZATION_MEASURES

        )

        findings.append(f"DOMAIN PROFILE [{did}]: {dp_str}.")

        if s.best_model:

            findings.append(

                f"BEST MODEL [{did}]: {s.best_model} "

                f"(RMSE={s.best_model_rmse:.4f}), "

                f"Naive RMSE={s.naive_rmse:.4f}, "

                f"Difficulty={s.difficulty}, "

                f"Ranking Stability={s.ranking_stability}."

            )

    for did, s in sorted(summaries.items()):

        for fam, mean_rmse in s.mean_rmse_by_family.items():

            if mean_rmse is not None:

                findings.append(

                    f"MODEL FAMILY [{did}]: Mean RMSE ({fam}) = {mean_rmse:.4f}."

                )

    if n < 3:

        findings.append(

            "INSUFFICIENT DATA FOR CROSS-DATASET ANALYSIS: Meaningful cross-dataset "

            f"pattern discovery requires >=3 datasets. Currently {n} dataset(s) available. "

            "Findings will be regenerated automatically once additional datasets complete the pipeline."

        )

    else:

        diff_counts = {}

        stab_counts = {}

        for s in summaries.values():

            diff_counts[s.difficulty] = diff_counts.get(s.difficulty, 0) + 1

            stab_counts[s.ranking_stability] = stab_counts.get(s.ranking_stability, 0) + 1

        findings.append(f"DIFFICULTY DISTRIBUTION across {n} datasets: {diff_counts}.")

        findings.append(f"STABILITY DISTRIBUTION across {n} datasets: {stab_counts}.")

    return findings





def analyze_forecasting_behavior(dataset_ids=None, config=None):

    """
    Stage 6 entry point. Per Section 14: operates only after forecasting
    execution is complete, reads from repositories written by Stages 1-5,
    produces Tables 1-7, Figures 1-7, and analytical findings.
    Does NOT influence model training, selection, or forecasting
    execution by design.
    """

    cfg = config or get_config(allow_draft=False)

    exec_log = get_execution_logger()

    exp_log = get_experiment_logger()

    error_log = get_error_logger()



    exec_log.info("[Stage 6] Forecasting Behavior Analysis -- starting")



    consistency_report = verify_dataset_id_consistency(dataset_ids=dataset_ids)

    bundles = {}

    try:

        bundles = load_evidence_bundles(report=consistency_report)

    except Exception as exc:

        error_log.warning(

            f"[Stage 6] Could not load evidence bundles: {exc!r}. "

            "Proceeding with empty dataset set -- all outputs will use "

            "INSUFFICIENT DATA placeholders."

        )



    summaries = {}

    for did, bundle in bundles.items():

        try:

            summaries[did] = build_dataset_behavior_summary(

                did, bundle.domain_profile, bundle.evaluation, cfg=cfg

            )

            exp_log.info(

                f"[Stage 6] {did}: difficulty={summaries[did].difficulty}, "

                f"stability={summaries[did].ranking_stability}, "

                f"best_model={summaries[did].best_model}"

            )

        except Exception as exc:

            error_log.error(

                f"[Stage 6] Failed to build behavior summary for '{did}': {exc!r}. Skipping."

            )



    t1 = generate_table_1(summaries)

    t2 = generate_table_2(summaries)

    t3 = generate_table_3(summaries)

    t4 = generate_table_4(summaries)

    t5 = generate_table_5(summaries)

    t6 = generate_table_6(summaries)

    t7 = generate_table_7(summaries)

    tables_written = [str(p) for p in [t1, t2, t3, t4, t5, t6, t7]]



    f1 = generate_figure_1(summaries)

    f2 = generate_figure_2(summaries)

    f3 = generate_figure_3(summaries)

    f4 = generate_figure_4(summaries)

    f5 = generate_figure_5(summaries)

    f6 = generate_figure_6(summaries)

    f7 = generate_figure_7(summaries)

    figures_written = [str(p) for p in [f1, f2, f3, f4, f5, f6, f7]]



    findings = generate_analytical_findings(summaries)



    _FBA_ROOT().mkdir(parents=True, exist_ok=True)

    findings_path = _FBA_ROOT() / "analytical_findings.json"

    with open(findings_path, "w") as f:

        json.dump({"dataset_ids": sorted(summaries.keys()), "findings": findings}, f, indent=2)



    summaries_path = _FBA_ROOT() / "dataset_behavior_summaries.json"

    with open(summaries_path, "w") as f:

        json.dump({did: asdict(s) for did, s in summaries.items()}, f, indent=2, default=str)



    result = FBAResult(

        dataset_ids=sorted(summaries.keys()),

        dataset_summaries=summaries,

        analytical_findings=findings,

        tables_written=tables_written,

        figures_written=figures_written,

    )



    exec_log.info(

        f"[Stage 6] FBA complete: {len(summaries)} dataset(s), "

        f"{len(tables_written)} tables, {len(figures_written)} figures, "

        f"{len(findings)} findings."

    )

    return result





def load_fba_results():

    path = _FBA_ROOT() / "analytical_findings.json"

    if not path.exists():

        raise FileNotFoundError(

            f"No FBA results found at {path}. Has analyze_forecasting_behavior() been run?"

        )

    with open(path) as f:

        return json.load(f)





__all__ = [

    "DatasetBehaviorSummary", "FBAResult", "analyze_forecasting_behavior",

    "build_dataset_behavior_summary", "load_fba_results", "_FBA_ROOT()",

    "DIFFICULTY_THRESHOLD_EASY", "DIFFICULTY_THRESHOLD_MODERATE", "RANKING_STABILITY_THRESHOLD",

]

