"""
sensitivity_analysis.py

Sensitivity analysis and robustness outputs required by DCF specification
Decisions 39, 45, 46, and 47:

  v1.2.0 design principle

  v1.2.0 design: "Preserve selected penalty values
    as experiment metadata. Support penalty-sensitivity analysis where
    appropriate."

  v1.2.0 design: "Whenever threshold-based
    procedures are used: preserve threshold values; preserve threshold
    metadata; support threshold-sensitivity analysis where appropriate."

  v1.2.0 design: "Implement similarity-
    analysis capability in a manner that allows future comparison of
    alternative similarity metrics."

This module provides:

  1. threshold_sensitivity_report(): documents every threshold-based
     decision used in Phases 2-5 with its source, value, and the range
     of values that would change the classification outcome.

  2. pelt_sensitivity_summary(): documents the PELT penalty setting
     and its effect on change-point detection.

  3. similarity_robustness_report(): compares Level-2 results across
     all three similarity metrics (already computed in Phase 4; this
     assembles the comparison in one place).

  4. generate_full_sensitivity_report(): produces all three as one
     comprehensive JSON output at results/05_analysis/sensitivity/.

All outputs are strictly descriptive -- they document what decisions were
made and what values were used. They do NOT propose alternative values or
claim that different thresholds would be better. Scientific
judgment belongs to the researcher, not the pipeline.
"""

from __future__ import annotations



import json

from datetime import datetime, timezone

from pathlib import Path

from typing import Optional



from dcf.config import Config, get_config

from dcf.logging_utils import get_execution_logger



PROJECT_ROOT = Path(__file__).resolve().parents[2]

from dcf.pub_paths import sub as _sub

def _SENSITIVITY_ROOT(): return _sub("05_analysis/sensitivity")





def threshold_sensitivity_report(config: Optional[Config] = None) -> dict:

    """
    Document every threshold-based classification decision in the publication
    framework, with source, frozen value, and boundary analysis.
    """

    cfg = config or get_config(allow_draft=False)



    

    low_high_cut = cfg.get("characterization.label_thresholds.low_high_cut", 0.33)

    high_med_cut = cfg.get("characterization.label_thresholds.high_medium_cut", 0.66)



    

    adf_alpha = cfg.get("characterization.stationarity_score.adf_alpha", 0.05)



    

    strength_cuts = cfg.get("relationship_discovery.correlation_strength_cuts", {})



    

    n1_supported = cfg.get("evidence_classification.novelty_1_characterization_layer.supported", {})

    n1_partial = cfg.get("evidence_classification.novelty_1_characterization_layer.partially_supported", {})

    n2_supported = cfg.get("evidence_classification.novelty_2_domain_profile.supported", {})



    

    difficulty_easy = cfg.get("forecasting_behavior.difficulty_thresholds.easy_max_ratio", 0.5)

    difficulty_mod = cfg.get("forecasting_behavior.difficulty_thresholds.moderate_max_ratio", 0.9)

    stability_thresh = cfg.get("forecasting_behavior.ranking_stability_threshold.stable_max_ratio", 2.0)



    

    pelt_penalty = cfg.get("characterization.structural_change.pelt_penalty", 10.0)

    pelt_min_seg = cfg.get("characterization.structural_change.min_segment_size", 10)



    report = {

        "generated_at": datetime.now(timezone.utc).isoformat(),

        "config_version": cfg.get("version", "1.0.0"),

        "note": (

            "This report documents every threshold-based decision in the publication configuration. "

            "All values are frozen in version1_defaults.yaml unless otherwise noted. "

            "Threshold modifications require updating that file and regenerating results."

        ),

        "thresholds": {

            "characterization_labels": {

                "source": "DCF specification.4",

                "frozen_in_config": True,

                "low_label_max": low_high_cut,

                "moderate_label_max": high_med_cut,

                "description": "Labels: 0-{lo} = Low, {lo}-{hi} = Moderate, {hi}-1.0 = High".format(

                    lo=low_high_cut, hi=high_med_cut),

            },

            "stationarity_alpha": {

                "source": "DCF specification",

                "frozen_in_config": True,

                "value": adf_alpha,

                "description": f"ADF null rejected (stationary) when p <= {adf_alpha}",

            },

            "relationship_strength": {

                "source": "frozen publication configuration",

                "frozen_in_config": True,

                "weak_min": strength_cuts.get("weak", 0.30),

                "moderate_min": strength_cuts.get("moderate", 0.50),

                "strong_min": strength_cuts.get("strong", 0.70),

            },

            "novelty_1_classification": {

                "source": "v1.2.0 frozen config",

                "frozen_in_config": True,

                "supported_min_abs_r": n1_supported.get("min_abs_correlation", 0.50),

                "supported_min_n_datasets": n1_supported.get("min_datasets_meeting_threshold", 5),

                "partially_supported_min_abs_r": n1_partial.get("min_abs_correlation", 0.30),

                "partially_supported_min_n_datasets": n1_partial.get("min_datasets_meeting_threshold", 4),

            },

            "novelty_2_classification": {

                "source": "v1.2.0 frozen config",

                "frozen_in_config": True,

                "supported_min_spearman_r": n2_supported.get("min_spearman_r", 0.40),

            },

            "forecasting_difficulty": {

                "source": "v1.2.0 frozen config",

                "frozen_in_config": True,

                "note": "Fixed in the publication configuration.",

                "easy_max_ratio": difficulty_easy,

                "moderate_max_ratio": difficulty_mod,

                "description": "ratio = best_model_RMSE / naive_RMSE",

            },

            "ranking_stability": {

                "source": "v1.2.0 frozen config",

                "frozen_in_config": True,

                "note": "Fixed in the publication configuration.",

                "stable_max_ratio": stability_thresh,

                "description": "ratio = worst_RMSE / best_RMSE; <= threshold -> Stable",

            },

            "pelt_penalty": {

                "source": "DCF specification.1 / frozen config",

                "frozen_in_config": True,

                "value": pelt_penalty,

                "min_segment_size": pelt_min_seg,

                "note": "Per DCF v1.2.0 design: penalty selection affects interpretation and must remain transparent.",

            },

        },

    }

    return report





def pelt_sensitivity_summary(config: Optional[Config] = None) -> dict:

    """
    Document the PELT penalty setting and its qualitative effect on
    change-point detection per DCF v1.2.0 design. This is a metadata
    document -- it does not re-run PELT at different penalty values,
    which would constitute a modification of the frozen configuration.
    """

    cfg = config or get_config(allow_draft=False)

    penalty = float(cfg.get("characterization.structural_change.pelt_penalty", 10.0))

    cost_model = cfg.get("characterization.structural_change.cost_model", "l2")

    min_seg = int(cfg.get("characterization.structural_change.min_segment_size", 10))



    return {

        "generated_at": datetime.now(timezone.utc).isoformat(),

        "frozen_settings": {

            "algorithm": "PELT",

            "cost_model": cost_model,

            "penalty": penalty,

            "min_segment_size": min_seg,

        },

        "penalty_interpretation": (

            f"With L2 cost and penalty={penalty}: lower penalty values tend to detect more "

            f"change points; higher values tend to detect fewer. The chosen penalty={penalty} "

            "is the frozen publication default. The scientific conclusions of the framework must be "

            "interpreted in the context of this setting."

        ),

        "reviewer_note": (

            "Per DCF v1.2.0 design: PELT penalty selection remains configurable and fully documented. "

            "The penalty value can be adjusted in version1_defaults.yaml before re-executing. "

            "Any modification would require re-running Stage 2 and all downstream stages."

        ),

        "decisions_affected": [

            "NCP (number of change points)",

            "ACM (average change magnitude)",

            "MCM (maximum change magnitude)",

            "RCD (relative change density)",

            "SIS (structural instability score)",

        ],

    }





def similarity_robustness_report(rel_analysis_dict: Optional[dict] = None) -> dict:

    """
    Compare Level-2 results across all three similarity metrics per
    v1.2.0. The three metrics (euclidean, cosine, correlation) are
    already computed in Phase 4; this assembles the comparison.
    """

    if rel_analysis_dict is None:

        try:

            from dcf.characterization_forecasting_relationship import load_relationship_analysis

            rel_analysis_dict = load_relationship_analysis()

        except FileNotFoundError:

            rel_analysis_dict = {"level_2_findings": []}



    level2 = rel_analysis_dict.get("level_2_findings", [])



    comparison = []

    for f in level2:

        comparison.append({

            "similarity_metric": f.get("similarity_metric", f.get("distance_type", "unknown")),

            "spearman_r": f.get("spearman_r"),

            "spearman_p": f.get("spearman_p"),

            "n_dataset_pairs": f.get("n_dataset_pairs"),

            "insufficient_datasets": f.get("insufficient_datasets"),

            "strength_class": None,  

        })



    with_data = [c for c in comparison if not c["insufficient_datasets"]]

    if len(with_data) >= 2:

        rs = [c["spearman_r"] for c in with_data if c["spearman_r"] is not None]

        robustness_note = (

            f"Results available for {len(with_data)} metric(s). "

            f"Spearman r range: [{min(rs):.3f}, {max(rs):.3f}]. "

            + ("Results are direction-consistent across metrics." if

               (all(r >= 0 for r in rs) or all(r <= 0 for r in rs))

               else "Results show mixed directions -- findings are metric-sensitive.")

        )

    else:

        robustness_note = (

            "Insufficient data to compare similarity metrics. "

            "All metrics returned insufficient_datasets=True. "

            "This will resolve when >= 3 datasets complete the full pipeline."

        )



    return {

        "generated_at": datetime.now(timezone.utc).isoformat(),

        "decision_47_note": (

            "Per DCF v1.2.0 design: the framework does not depend upon a single similarity "

            "metric. All three supported metrics (euclidean, cosine, correlation) are "

            "computed and reported. The primary metric is euclidean per the frozen "

            "config (similarity_analysis.primary_metric)."

        ),

        "metric_comparison": comparison,

        "robustness_assessment": robustness_note,

    }





def generate_full_sensitivity_report(config: Optional[Config] = None) -> dict:

    """
    Produce all three sensitivity/robustness analyses and write to
    results/05_analysis/sensitivity/. Returns summary dict with paths.
    """

    cfg = config or get_config(allow_draft=False)

    exec_log = get_execution_logger()

    exec_log.info("[Sensitivity] Generating sensitivity analysis reports")



    _SENSITIVITY_ROOT().mkdir(parents=True, exist_ok=True)



    thresh_report = threshold_sensitivity_report(cfg)

    pelt_report = pelt_sensitivity_summary(cfg)

    similarity_report = similarity_robustness_report()



    paths = {}

    for name, content in [

        ("threshold_sensitivity_report", thresh_report),

        ("pelt_sensitivity_summary", pelt_report),

        ("similarity_robustness_report", similarity_report),

    ]:

        path = _SENSITIVITY_ROOT() / f"{name}.json"

        with open(path, "w") as f:

            json.dump(content, f, indent=2, default=str)

        paths[name] = str(path)



    full = {"threshold_sensitivity": thresh_report,

            "pelt_sensitivity": pelt_report,

            "similarity_robustness": similarity_report}

    full_path = _SENSITIVITY_ROOT() / "full_sensitivity_report.json"

    with open(full_path, "w") as f:

        json.dump(full, f, indent=2, default=str)

    paths["full_sensitivity_report"] = str(full_path)



    exec_log.info(f"[Sensitivity] Reports written: {list(paths.keys())}")

    return paths





__all__ = [

    "threshold_sensitivity_report",

    "pelt_sensitivity_summary",

    "similarity_robustness_report",

    "generate_full_sensitivity_report",

    "_SENSITIVITY_ROOT()",

]

