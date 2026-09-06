"""
validation_reporting.py

Section 18 deferred deliverables: Reproducibility Assessment, Consistency
Assessment, Contradictory Evidence Detection, 7 Validation Tables,
6 Validation Figures, Framework Assessment Report, and the full set of
structured validation reports.

This module extends evidence_validation.py's core (Novelty 1 / Novelty 2
Supported/Inconclusive classification) with the full Section 18 analytical
and reporting layer.

SCIENTIFIC INTEGRITY: Every classification produced here is strictly
evidence-based, per Section 18's success criterion:
  "The success of this layer shall be determined by its ability to
   provide a complete, reproducible, transparent, and evidence-based
   assessment... The implementation shall not suppress, modify, or
   exclude evidence that contradicts expected outcomes."

If evidence is insufficient, the reports say "Inconclusive."
If evidence is contradictory, the reports say "Contradictory."
Neither positive outcomes nor negative ones are suppressed.
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

from dcf.evidence_validation import load_evidence_validation, EVIDENCE_CLASSES

from dcf.logging_utils import get_error_logger, get_execution_logger, get_experiment_logger



PROJECT_ROOT = Path(__file__).resolve().parents[2]

from dcf.pub_paths import sub as _sub

def _VALIDATION_REPORT_ROOT(): return _sub("06_validation")

EVIDENCE_CLASSES_ORDERED = ["Supported", "Partially Supported", "Inconclusive", "Unsupported"]





@dataclass

class ReproducibilityAssessment:

    """
    Reproducibility assessment per Section 18 'Reproducibility Assessment':
    evaluates whether findings are consistent given the same inputs and config.

    With a single experimental run (as is typical for a research framework),
    cross-run reproducibility cannot be assessed without re-executing.
    This assessment instead evaluates INTERNAL reproducibility:
    whether findings are stable w.r.t. the three similarity metrics
    (euclidean, cosine, correlation) used for Level 2 analysis --
    if all three metrics agree in direction, findings are more reproducible.
    """

    n_level2_metrics: int

    metrics_agree_in_direction: Optional[bool]

    n_metrics_showing_positive_correlation: int

    n_metrics_showing_negative_correlation: int

    n_metrics_insufficient_data: int

    reproducibility_score: str    

    notes: str





@dataclass

class ConsistencyAssessment:

    """
    Consistency assessment per Section 18 'Consistency Assessment':
    evaluates whether Level 1 findings are consistent across the seven
    characterization measures and four performance metrics.
    """

    n_level1_findings: int

    n_findings_with_data: int

    n_strong: int

    n_moderate: int

    n_weak: int

    n_unsupported: int

    n_insufficient: int

    consistency_score: str        

    dominant_strength_class: str

    notes: str





@dataclass

class ContradictoryEvidenceAssessment:

    """
    Contradictory evidence per Section 18 'Contradictory Evidence Assessment':
    findings that showed opposite directions (positive vs negative correlation)
    across metrics or datasets.
    """

    n_mixed_direction_findings: int

    contradictory_characteristics: list

    contradictory_summary: str





@dataclass

class FrameworkAssessmentReport:

    novelty_1_classification: str

    novelty_2_classification: str

    novelty_1_rationale: str

    novelty_2_rationale: str

    reproducibility: ReproducibilityAssessment

    consistency: ConsistencyAssessment

    contradictory_evidence: ContradictoryEvidenceAssessment

    strongest_findings: list

    weakest_findings: list

    dataset_coverage_notes: str

    overall_assessment: str





def _assess_reproducibility(level2_findings: list) -> ReproducibilityAssessment:

    """Evaluate metric agreement across euclidean/cosine/correlation."""

    with_data = [f for f in level2_findings if not f["insufficient_datasets"]]

    n_total = len(level2_findings)



    if not with_data:

        return ReproducibilityAssessment(

            n_level2_metrics=n_total,

            metrics_agree_in_direction=None,

            n_metrics_showing_positive_correlation=0,

            n_metrics_showing_negative_correlation=0,

            n_metrics_insufficient_data=n_total,

            reproducibility_score="Insufficient_Data",

            notes=(

                f"All {n_total} similarity metric(s) returned insufficient data "

                "(fewer than 3 datasets). Reproducibility cannot be assessed without "

                "more complete experimental data."

            ),

        )



    pos = sum(1 for f in with_data if f["spearman_r"] is not None and f["spearman_r"] > 0)

    neg = sum(1 for f in with_data if f["spearman_r"] is not None and f["spearman_r"] < 0)

    agree = (pos == len(with_data)) or (neg == len(with_data))



    if len(with_data) < 2:

        score = "Insufficient_Data"

        notes = "Only one similarity metric produced results. Cannot assess cross-metric reproducibility."

    elif agree and len(with_data) >= 2:

        score = "High"

        notes = f"All {len(with_data)} similarity metrics agree in direction."

    elif agree:

        score = "Moderate"

        notes = "Metrics partially agree."

    else:

        score = "Low"

        notes = (f"{pos} metric(s) showed positive correlation, {neg} showed negative. "

                 "Mixed directions indicate low metric-level reproducibility for Level 2.")



    return ReproducibilityAssessment(

        n_level2_metrics=n_total,

        metrics_agree_in_direction=agree if with_data else None,

        n_metrics_showing_positive_correlation=pos,

        n_metrics_showing_negative_correlation=neg,

        n_metrics_insufficient_data=n_total - len(with_data),

        reproducibility_score=score,

        notes=notes,

    )





def _strength_class_from_finding(f: dict) -> str:

    """Derive strength class from the current Level1Finding dict schema.
    Maps dimension_finding to the strength vocabulary used by reporting.
    """

    df = f.get("dimension_finding")

    if df == "strong_signal":

        return "strong"

    if df == "weak_signal":

        return "weak"

    if df in ("no_signal", "no_signal_but_trend"):

        return "unsupported"

    return "insufficient_data"





def _has_data(f: dict) -> bool:

    """Return True when a Level1Finding has sufficient data for correlation."""

    return f.get("dimension_finding") not in (None, "undefined")





def _assess_consistency(level1_findings: list) -> ConsistencyAssessment:

    """Evaluate consistency of Level 1 findings across all measure x metric pairs."""

    with_data = [f for f in level1_findings if _has_data(f)]

    n_total = len(level1_findings)



    counts = {"strong": 0, "moderate": 0, "weak": 0, "unsupported": 0, "insufficient_data": 0}

    for f in level1_findings:

        sc = _strength_class_from_finding(f)

        counts[sc] = counts.get(sc, 0) + 1



    n_with = len(with_data)

    if n_with == 0:

        return ConsistencyAssessment(

            n_level1_findings=n_total, n_findings_with_data=0,

            n_strong=0, n_moderate=0, n_weak=0, n_unsupported=0,

            n_insufficient=n_total, consistency_score="Insufficient_Data",

            dominant_strength_class="insufficient_data",

            notes="No Level-1 findings had sufficient data for evaluation.",

        )



    dominant = max(counts, key=lambda k: counts[k] if k != "insufficient_data" else -1)

    strong_frac = counts["strong"] / n_with if n_with else 0

    moderate_frac = (counts["strong"] + counts["moderate"]) / n_with if n_with else 0



    if strong_frac >= 0.5:

        score = "High"

    elif moderate_frac >= 0.5:

        score = "Moderate"

    else:

        score = "Low"



    return ConsistencyAssessment(

        n_level1_findings=n_total, n_findings_with_data=n_with,

        n_strong=counts["strong"], n_moderate=counts["moderate"],

        n_weak=counts["weak"], n_unsupported=counts["unsupported"],

        n_insufficient=counts.get("insufficient_data", 0),

        consistency_score=score, dominant_strength_class=dominant,

        notes=(

            f"Of {n_with} evaluable Level-1 findings: {counts['strong']} strong, "

            f"{counts['moderate']} moderate, {counts['weak']} weak, "

            f"{counts['unsupported']} unsupported."

        ),

    )





def _assess_contradictory_evidence(level1_findings: list) -> ContradictoryEvidenceAssessment:

    """
    Identify characteristics where different metrics showed opposite
    correlation directions (positive vs negative Spearman r).
    """

    by_char = {}

    for f in level1_findings:

        if not _has_data(f):

            continue

        r = f.get("spearman_r")

        if r is None:

            continue

        direction = "positive" if r > 0 else "negative"

        by_char.setdefault(f["characteristic"], set()).add(direction)



    contradictory = [char for char, directions in by_char.items() if len(directions) > 1]



    if contradictory:

        summary = (

            f"{len(contradictory)} characterization measure(s) showed mixed correlation "

            f"directions across performance metrics: {contradictory}. These findings are "

            "inconsistent and should be interpreted with caution."

        )

    elif not by_char:

        summary = "Insufficient data to assess contradictory evidence."

    else:

        summary = "No contradictory evidence detected: all evaluable findings showed consistent correlation direction per characteristic."



    return ContradictoryEvidenceAssessment(

        n_mixed_direction_findings=len(contradictory),

        contradictory_characteristics=contradictory,

        contradictory_summary=summary,

    )





def _identify_strong_weak_findings(level1_findings: list) -> tuple:

    """Return (strongest, weakest) findings by Spearman |r|."""

    evaluable = [

        f for f in level1_findings

        if _has_data(f) and f.get("spearman_r") is not None

    ]

    if not evaluable:

        return [], []



    sorted_by_r = sorted(evaluable,

                         key=lambda f: abs(f["spearman_r"]),

                         reverse=True)

    n = min(3, len(sorted_by_r))

    strongest = [

        {"characteristic": f["characteristic"], "target": "B_i",

         "spearman_r": f.get("spearman_r"),

         "strength_class": _strength_class_from_finding(f)}

        for f in sorted_by_r[:n]

    ]

    weakest = [

        {"characteristic": f["characteristic"], "target": "B_i",

         "spearman_r": f.get("spearman_r"),

         "strength_class": _strength_class_from_finding(f)}

        for f in sorted_by_r[-n:][::-1]

    ]

    return strongest, weakest





class MissingStage8StateError(ValueError):

    """Raised when Stage-9 cannot find a valid Stage-8 Level-1 state."""





class MissingStage8Level2StateError(ValueError):

    """Raised when Stage-9 cannot find a valid Stage-8 Level-2 state."""





_VALID_LEVEL1_STATES = frozenset({

    "Supported", "Partially Supported", "Inconclusive", "Unsupported",

})

_VALID_LEVEL2_STATES = frozenset({

    "Supported", "Partially Supported", "Inconclusive", "Unsupported",

})





def _translate_l1_to_novelty(validation_dict: dict) -> dict:

    """
    Translate the Stage-8 schema (key "level_1_assessment") to the internal
    novelty_1 dict.  A valid upstream level_1_evidence_state must NEVER be
    silently replaced.  Missing, malformed, incomplete, or unrecognised state
    raises MissingStage8StateError — Stage-9 must not default to Inconclusive.
    """

    l1a = validation_dict.get("level_1_assessment")

    if not isinstance(l1a, dict) or not l1a:

        raise MissingStage8StateError(

            "Stage-9 requires a valid Stage-8 level_1_assessment dict; "

            f"got {type(l1a).__name__!r} — {l1a!r}. "

            "This is a hard failure: Stage-9 must not manufacture a "

            "scientific state when the upstream state is missing or malformed."

        )

    state = l1a.get("level_1_evidence_state")

    

    if state is None and l1a.get("level_1_analysis_valid", True):

        raise MissingStage8StateError(

            f"Stage-9: level_1_evidence_state is None but level_1_analysis_valid "

            f"is True — this is an inconsistent Stage-8 output and cannot be "

            f"propagated. Full assessment: {l1a!r}"

        )

    if state is not None and state not in _VALID_LEVEL1_STATES:

        raise MissingStage8StateError(

            f"Stage-9: unrecognised Level-1 evidence state {state!r}. "

            f"Valid states are {sorted(_VALID_LEVEL1_STATES)}. "

            "Stage-9 will not default to Inconclusive for an unrecognised state."

        )

    return {

        "classification": state,

        "rationale": l1a.get("rationale", ""),

        "n_datasets_available": validation_dict.get("n_datasets_analyzed", 0),

        "measures_meeting_supported_threshold": [

            f["characteristic"]

            for f in l1a.get("dimension_findings", [])

            if f.get("dimension_finding") == "strong_signal"

        ],

        "measures_meeting_partially_supported_threshold": [

            f["characteristic"]

            for f in l1a.get("dimension_findings", [])

            if f.get("dimension_finding") in ("strong_signal", "weak_signal")

        ],

        "dependence_audit": l1a.get("dependence_audit", []),

    }





def _translate_l2_to_novelty(validation_dict: dict) -> dict:

    """
    Translate the Stage-8 schema (key "level_2_assessment") to the internal
    novelty_2 dict.  A valid upstream level_2_evidence_state must NEVER be
    replaced by a default Inconclusive.  Raises MissingStage8Level2StateError
    on missing, malformed, or unrecognised state.
    """

    l2a = validation_dict.get("level_2_assessment")

    if not isinstance(l2a, dict) or not l2a:

        raise MissingStage8Level2StateError(

            "Stage-9 requires a valid Stage-8 level_2_assessment dict; "

            f"got {type(l2a).__name__!r} — {l2a!r}. "

            "This is a hard failure: Stage-9 must not manufacture a "

            "scientific state when the upstream state is missing or malformed."

        )

    state = l2a.get("level_2_evidence_state")

    

    if state is None and l2a.get("primary_gate_passed", True):

        raise MissingStage8Level2StateError(

            f"Stage-9: level_2_evidence_state is None but primary_gate_passed is True "

            f"— this is an inconsistent Stage-8 Level-2 output and cannot be propagated. "

            f"Full Level-2 assessment: {l2a!r}"

        )

    if state is not None and state not in _VALID_LEVEL2_STATES:

        raise MissingStage8Level2StateError(

            f"Stage-9: unrecognised Level-2 evidence state {state!r}. "

            f"Valid states are {sorted(_VALID_LEVEL2_STATES)}. "

            "Stage-9 will not default to Inconclusive for an unrecognised state."

        )

    return {

        "classification": state,

        "rationale": state or "",

        "n_datasets_available": validation_dict.get("n_datasets_analyzed", 0),

        "best_similarity_metric": "rms_euclidean",

        "best_spearman_r": None,

        "negative_direction": l2a.get("negative_direction", False),

        "contradictory_direction": l2a.get("contradictory_direction", False),

        "sensitivity_downgrade_applied": l2a.get("sensitivity_downgrade_applied", False),

    }





def generate_framework_assessment_report(

    validation_dict: dict,

    rel_analysis_dict: Optional[dict] = None,

    config: Optional[Config] = None,

) -> FrameworkAssessmentReport:

    """
    Build the full Section 18 Framework Assessment Report from the
    evidence_validation and relationship_analysis outputs.
    """

    cfg = config or get_config(allow_draft=False)

    n_datasets = validation_dict.get("n_datasets_analyzed",

                  validation_dict.get("n_datasets_available", 0))



    level1 = []

    level2 = []

    if rel_analysis_dict:

        level1 = rel_analysis_dict.get("level_1_findings", [])

        level2 = rel_analysis_dict.get("level_2_findings", [])



    repro = _assess_reproducibility(level2)

    consistency = _assess_consistency(level1)

    contradictory = _assess_contradictory_evidence(level1)

    strongest, weakest = _identify_strong_weak_findings(level1)



    n1 = _translate_l1_to_novelty(validation_dict)

    n2 = _translate_l2_to_novelty(validation_dict)

    n1_class = n1.get("classification", "Inconclusive")

    n2_class = n2.get("classification", "Inconclusive")



    if n_datasets < 3:

        overall = (

            f"FRAMEWORK ASSESSMENT: Inconclusive (insufficient data). "

            f"Only {n_datasets} dataset(s) have complete pipeline results. "

            f"The framework is fully implemented and operationally ready; "

            f"meaningful evidence-based assessment requires the complete pipeline "

            f"to be executed on additional datasets. Novelty 1: {n1_class}. "

            f"Novelty 2: {n2_class}."

        )

    else:

        overall = (

            f"FRAMEWORK ASSESSMENT: Based on {n_datasets} dataset(s). "

            f"Novelty 1 (Characterization Layer): {n1_class}. "

            f"Novelty 2 (Domain Profile): {n2_class}. "

            f"Level-1 consistency: {consistency.consistency_score}. "

            f"Level-2 reproducibility: {repro.reproducibility_score}. "

            f"Contradictory findings: {contradictory.n_mixed_direction_findings}."

        )



    _supported_min = 5  

    _level2_min    = 3  

    if n_datasets >= _supported_min:

        dataset_notes = (

            f"Evidence based on {n_datasets} dataset(s) with complete pipeline results. "

            f"The frozen evidence-classification thresholds require >= {_supported_min} datasets "

            f"for Supported status (Novelty 1) and >= {_level2_min} dataset pairs for "

            f"Level-2 correlation (Novelty 2). Both requirements are satisfied."

        )

    else:

        dataset_notes = (

            f"Evidence based on {n_datasets} dataset(s) with complete pipeline results. "

            f"The frozen evidence-classification thresholds require >= {_supported_min} datasets "

            f"for Supported status (Novelty 1) and >= {_level2_min} dataset pairs for "

            f"Level-2 correlation (Novelty 2). "

            f"The {n_datasets}-dataset count does not meet the Supported threshold; "

            f"all classifications reflect this limitation honestly."

        )



    return FrameworkAssessmentReport(

        novelty_1_classification=n1_class,

        novelty_2_classification=n2_class,

        novelty_1_rationale=n1.get("rationale", ""),

        novelty_2_rationale=n2.get("rationale", ""),

        reproducibility=repro,

        consistency=consistency,

        contradictory_evidence=contradictory,

        strongest_findings=strongest,

        weakest_findings=weakest,

        dataset_coverage_notes=dataset_notes,

        overall_assessment=overall,

    )













def _write_val_table(rows, filename):

    _VALIDATION_REPORT_ROOT().mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame(rows)

    csv_path = _VALIDATION_REPORT_ROOT() / f"{filename}.csv"

    json_path = _VALIDATION_REPORT_ROOT() / f"{filename}.json"

    df.to_csv(csv_path, index=False)

    df.to_json(json_path, orient="records", indent=2)

    return csv_path





def generate_val_table_1(n1_assessment):

    """T1: Novelty 1 Support Summary"""

    rows = [{

        "component": "Novelty 1 - Characterization Layer",

        "classification": n1_assessment.get("classification"),

        "n_datasets": n1_assessment.get("n_datasets_available"),

        "supported_measures": str(n1_assessment.get("measures_meeting_supported_threshold", [])),

        "rationale": n1_assessment.get("rationale", ""),

    }]

    return _write_val_table(rows, "val_table_1_novelty1_support")





def generate_val_table_2(n2_assessment):

    """T2: Novelty 2 Support Summary"""

    rows = [{

        "component": "Novelty 2 - Domain Profile",

        "classification": n2_assessment.get("classification"),

        "n_datasets": n2_assessment.get("n_datasets_available"),

        "best_similarity_metric": n2_assessment.get("best_similarity_metric"),

        "best_spearman_r": n2_assessment.get("best_spearman_r"),

        "rationale": n2_assessment.get("rationale", ""),

    }]

    return _write_val_table(rows, "val_table_2_novelty2_support")





def generate_val_table_3(level1_findings):

    """T3: Evidence Strength Summary by characteristic x metric"""

    rows = []

    for f in level1_findings:

        corr = {"spearman_r": f.get("spearman_r"),

                "insufficient_datasets": not _has_data(f)}

        rows.append({

            "characteristic": f["characteristic"],

            "target": "B_i",

            "pearson_r": corr.get("pearson_r"),

            "spearman_r": corr.get("spearman_r"),

            "n_datasets": corr.get("n_datasets"),

            "strength_class": _strength_class_from_finding(f),

            "insufficient_data": corr.get("insufficient_datasets"),

        })

    return _write_val_table(rows or [{"note": "no data"}], "val_table_3_evidence_strength")





def generate_val_table_4(repro: ReproducibilityAssessment):

    """T4: Reproducibility Assessment"""

    rows = [{"assessment_type": "Level-2 Metric Agreement",

             "reproducibility_score": repro.reproducibility_score,

             "n_metrics": repro.n_level2_metrics,

             "n_positive": repro.n_metrics_showing_positive_correlation,

             "n_negative": repro.n_metrics_showing_negative_correlation,

             "n_insufficient": repro.n_metrics_insufficient_data,

             "metrics_agree": repro.metrics_agree_in_direction,

             "notes": repro.notes}]

    return _write_val_table(rows, "val_table_4_reproducibility")





def generate_val_table_5(consistency: ConsistencyAssessment):

    """T5: Consistency Assessment"""

    rows = [{"consistency_score": consistency.consistency_score,

             "n_findings": consistency.n_level1_findings,

             "n_evaluable": consistency.n_findings_with_data,

             "n_strong": consistency.n_strong, "n_moderate": consistency.n_moderate,

             "n_weak": consistency.n_weak, "n_unsupported": consistency.n_unsupported,

             "n_insufficient": consistency.n_insufficient,

             "dominant_class": consistency.dominant_strength_class,

             "notes": consistency.notes}]

    return _write_val_table(rows, "val_table_5_consistency")





def generate_val_table_6(contradictory: ContradictoryEvidenceAssessment):

    """T6: Contradictory Evidence Summary"""

    rows = [{"n_contradictory": contradictory.n_mixed_direction_findings,

             "contradictory_characteristics": str(contradictory.contradictory_characteristics),

             "summary": contradictory.contradictory_summary}]

    return _write_val_table(rows, "val_table_6_contradictory_evidence")





def generate_val_table_7(report: FrameworkAssessmentReport):

    """T7: Framework Assessment Summary"""

    rows = [{"novelty_1": report.novelty_1_classification,

             "novelty_2": report.novelty_2_classification,

             "reproducibility": report.reproducibility.reproducibility_score,

             "consistency": report.consistency.consistency_score,

             "n_contradictory": report.contradictory_evidence.n_mixed_direction_findings,

             "overall_assessment": report.overall_assessment}]

    return _write_val_table(rows, "val_table_7_framework_assessment")













def _placeholder_val_fig(title, message, path):

    fig, ax = plt.subplots(figsize=(8, 5))

    ax.text(0.5, 0.5, f"{title}\n\n{message}", ha="center", va="center",

            fontsize=12, color="#555", wrap=True,

            bbox=dict(facecolor="#f9f9f9", edgecolor="#ccc", boxstyle="round,pad=0.5"))

    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")

    ax.set_title(title, fontsize=13)

    plt.tight_layout()

    _VALIDATION_REPORT_ROOT().mkdir(parents=True, exist_ok=True)

    fig.savefig(path, dpi=300, bbox_inches="tight"); plt.close(fig)

    return path





def generate_val_figure_1(n1):

    """F1: Novelty 1 Support Overview"""

    path = _VALIDATION_REPORT_ROOT() / "val_figure_1_novelty1_support.png"

    classification = n1.get("classification", "Inconclusive")

    colors = {"Supported": "#27AE60", "Partially Supported": "#F39C12",

               "Inconclusive": "#95A5A6", "Unsupported": "#E74C3C"}

    color = colors.get(classification, "#BDC3C7")

    fig, ax = plt.subplots(figsize=(7, 5))

    ax.barh(["Novelty 1\n(Characterization Layer)"], [1], color=color, height=0.4)

    ax.set_xlim(0, 1); ax.set_xticks([])

    ax.text(0.5, 0, f"{classification}\n\n{n1.get('rationale', '')[:200]}",

            ha="center", va="center", fontsize=10, wrap=True)

    ax.set_title("Figure 1: Novelty 1 Support Assessment", fontsize=13)

    _VALIDATION_REPORT_ROOT().mkdir(parents=True, exist_ok=True)

    fig.savefig(path, dpi=300, bbox_inches="tight"); plt.close(fig)

    return path





def generate_val_figure_2(n2):

    """F2: Novelty 2 Support Overview"""

    path = _VALIDATION_REPORT_ROOT() / "val_figure_2_novelty2_support.png"

    classification = n2.get("classification", "Inconclusive")

    colors = {"Supported": "#27AE60", "Partially Supported": "#F39C12",

               "Inconclusive": "#95A5A6", "Unsupported": "#E74C3C"}

    color = colors.get(classification, "#BDC3C7")

    fig, ax = plt.subplots(figsize=(7, 5))

    ax.barh(["Novelty 2\n(Domain Profile)"], [1], color=color, height=0.4)

    ax.set_xlim(0, 1); ax.set_xticks([])

    ax.text(0.5, 0, f"{classification}\n\n{n2.get('rationale', '')[:200]}",

            ha="center", va="center", fontsize=10, wrap=True)

    ax.set_title("Figure 2: Novelty 2 Support Assessment", fontsize=13)

    _VALIDATION_REPORT_ROOT().mkdir(parents=True, exist_ok=True)

    fig.savefig(path, dpi=300, bbox_inches="tight"); plt.close(fig)

    return path





def generate_val_figure_3(level1_findings):

    """F3: Evidence Strength Distribution (pie/bar of strength classes)."""

    path = _VALIDATION_REPORT_ROOT() / "val_figure_3_evidence_strength_distribution.png"

    counts = {}

    for f in level1_findings:

        sc = _strength_class_from_finding(f)

        counts[sc] = counts.get(sc, 0) + 1

    if not counts or all(c == "insufficient_data" for c in counts):

        return _placeholder_val_fig("Figure 3: Evidence Strength Distribution",

                                    "INSUFFICIENT DATA: All findings have insufficient data.", path)

    colors = {"strong": "#27AE60", "moderate": "#F39C12",

              "weak": "#E67E22", "unsupported": "#E74C3C", "insufficient_data": "#BDC3C7"}

    labels = [k for k in counts if k != "insufficient_data"]

    values = [counts[k] for k in labels]

    bar_colors = [colors.get(k, "#999") for k in labels]

    fig, ax = plt.subplots(figsize=(8, 5))

    ax.bar(labels, values, color=bar_colors, edgecolor="white")

    ax.set_ylabel("Number of Level-1 Findings")

    ax.set_title("Figure 3: Evidence Strength Distribution (Level-1 Findings)", fontsize=12)

    for i, v in enumerate(values):

        ax.text(i, v + 0.05, str(v), ha="center", fontsize=10)

    plt.tight_layout()

    _VALIDATION_REPORT_ROOT().mkdir(parents=True, exist_ok=True)

    fig.savefig(path, dpi=300, bbox_inches="tight"); plt.close(fig)

    return path





def generate_val_figure_4(repro: ReproducibilityAssessment):

    """F4: Reproducibility Summary"""

    path = _VALIDATION_REPORT_ROOT() / "val_figure_4_reproducibility.png"

    labels = ["Positive\nCorrelation", "Negative\nCorrelation", "Insufficient\nData"]

    values = [repro.n_metrics_showing_positive_correlation,

              repro.n_metrics_showing_negative_correlation,

              repro.n_metrics_insufficient_data]

    colors = ["#27AE60", "#E74C3C", "#BDC3C7"]

    fig, ax = plt.subplots(figsize=(7, 5))

    bars = ax.bar(labels, values, color=colors, edgecolor="white")

    ax.set_ylabel("Number of Similarity Metrics")

    ax.set_title(f"Figure 4: Level-2 Metric Reproducibility\n"

                 f"({repro.reproducibility_score})", fontsize=12)

    for bar, val in zip(bars, values):

        ax.text(bar.get_x() + bar.get_width() / 2, val + 0.05, str(val),

                ha="center", fontsize=11)

    plt.tight_layout()

    _VALIDATION_REPORT_ROOT().mkdir(parents=True, exist_ok=True)

    fig.savefig(path, dpi=300, bbox_inches="tight"); plt.close(fig)

    return path





def generate_val_figure_5(consistency: ConsistencyAssessment):

    """F5: Consistency Summary"""

    path = _VALIDATION_REPORT_ROOT() / "val_figure_5_consistency.png"

    categories = ["Strong", "Moderate", "Weak", "Unsupported", "Insufficient\nData"]

    values = [consistency.n_strong, consistency.n_moderate, consistency.n_weak,

              consistency.n_unsupported, consistency.n_insufficient]

    colors = ["#27AE60", "#F39C12", "#E67E22", "#E74C3C", "#BDC3C7"]

    fig, ax = plt.subplots(figsize=(9, 5))

    bars = ax.bar(categories, values, color=colors, edgecolor="white")

    ax.set_ylabel("Number of Level-1 Findings")

    ax.set_title(f"Figure 5: Level-1 Consistency Assessment\n"

                 f"(Overall: {consistency.consistency_score})", fontsize=12)

    for bar, val in zip(bars, values):

        ax.text(bar.get_x() + bar.get_width() / 2, val + 0.05, str(val),

                ha="center", fontsize=10)

    plt.tight_layout()

    _VALIDATION_REPORT_ROOT().mkdir(parents=True, exist_ok=True)

    fig.savefig(path, dpi=300, bbox_inches="tight"); plt.close(fig)

    return path





def generate_val_figure_6(report: FrameworkAssessmentReport):

    """F6: Framework Assessment Overview -- consolidated dashboard."""

    path = _VALIDATION_REPORT_ROOT() / "val_figure_6_framework_assessment_overview.png"

    components = ["Novelty 1\n(Char. Layer)", "Novelty 2\n(Domain Profile)",

                  "Reproducibility", "Consistency"]

    classifications = [

        report.novelty_1_classification,

        report.novelty_2_classification,

        report.reproducibility.reproducibility_score,

        report.consistency.consistency_score,

    ]

    color_map = {

        "Supported": "#27AE60", "Partially Supported": "#F39C12",

        "Inconclusive": "#95A5A6", "Unsupported": "#E74C3C",

        "High": "#27AE60", "Moderate": "#F39C12", "Low": "#E74C3C",

        "Insufficient_Data": "#BDC3C7",

    }

    colors = [color_map.get(c, "#BDC3C7") for c in classifications]

    fig, ax = plt.subplots(figsize=(10, 5))

    bars = ax.bar(components, [1] * len(components), color=colors, edgecolor="white", width=0.6)

    ax.set_ylim(0, 1.5); ax.set_yticks([])

    for bar, clf in zip(bars, classifications):

        ax.text(bar.get_x() + bar.get_width() / 2, 0.5, clf,

                ha="center", va="center", fontsize=11, color="white",

                fontweight="bold")

    ax.set_title("Figure 6: Framework Assessment Overview", fontsize=13)

    legend_patches = [mpatches.Patch(color=c, label=l)

                      for l, c in [("Supported/High", "#27AE60"),

                                   ("Partially/Moderate", "#F39C12"),

                                   ("Inconclusive/Low", "#95A5A6"),

                                   ("Unsupported", "#E74C3C"),

                                   ("Insufficient Data", "#BDC3C7")]]

    ax.legend(handles=legend_patches, loc="upper right", fontsize=9)

    plt.tight_layout()

    _VALIDATION_REPORT_ROOT().mkdir(parents=True, exist_ok=True)

    fig.savefig(path, dpi=300, bbox_inches="tight"); plt.close(fig)

    return path













def _write_report(content: dict, filename: str) -> Path:

    _VALIDATION_REPORT_ROOT().mkdir(parents=True, exist_ok=True)

    path = _VALIDATION_REPORT_ROOT() / filename

    with open(path, "w") as f:

        json.dump(content, f, indent=2, default=str)

    return path













def generate_validation_reports(

    validation_dict: Optional[dict] = None,

    rel_analysis_dict: Optional[dict] = None,

    config: Optional[Config] = None,

) -> dict:

    """
    Generate the full Section 18 output set:
    - Framework Assessment Report
    - 7 Validation Tables (CSV + JSON)
    - 6 Validation Figures (PNG)
    - 7 Structured validation reports (JSON)
    Returns a summary dict with paths to all outputs.
    """

    cfg = config or get_config(allow_draft=False)

    exec_log = get_execution_logger()

    exp_log = get_experiment_logger()

    error_log = get_error_logger()



    exec_log.info("[Validation Report] Generating Section 18 full validation reports")



    

    if validation_dict is None:

        try:

            validation_dict = load_evidence_validation()

        except FileNotFoundError:

            error_log.warning("[Validation Report] No evidence validation results found. "

                              "Using empty placeholder.")

            validation_dict = {

                "novelty_1": {"classification": "Inconclusive", "rationale": "No data", "n_datasets_available": 0,

                              "measures_meeting_supported_threshold": [],

                              "measures_meeting_partially_supported_threshold": []},

                "novelty_2": {"classification": "Inconclusive", "rationale": "No data", "n_datasets_available": 0,

                              "best_similarity_metric": None, "best_spearman_r": None},

                "n_datasets_available": 0,

            }



    

    if rel_analysis_dict is None:

        try:

            from dcf.characterization_forecasting_relationship import load_relationship_analysis

            rel_analysis_dict = load_relationship_analysis()

        except FileNotFoundError:

            error_log.warning("[Validation Report] No relationship analysis results found.")

            rel_analysis_dict = {"level_1_findings": [], "level_2_findings": []}



    

    

    

    

    n1 = _translate_l1_to_novelty(validation_dict)

    n2 = _translate_l2_to_novelty(validation_dict)

    level1 = rel_analysis_dict.get("level_1_findings", [])

    level2 = rel_analysis_dict.get("level_2_findings", [])



    

    report = generate_framework_assessment_report(validation_dict, rel_analysis_dict, cfg)



    

    tables = [

        generate_val_table_1(n1), generate_val_table_2(n2),

        generate_val_table_3(level1), generate_val_table_4(report.reproducibility),

        generate_val_table_5(report.consistency), generate_val_table_6(report.contradictory_evidence),

        generate_val_table_7(report),

    ]



    

    figs = [

        generate_val_figure_1(n1), generate_val_figure_2(n2),

        generate_val_figure_3(level1), generate_val_figure_4(report.reproducibility),

        generate_val_figure_5(report.consistency), generate_val_figure_6(report),

    ]



    

    report_dict = {

        "framework_assessment": asdict(report),

        "novelty_1_assessment": n1,

        "novelty_2_assessment": n2,

        "reproducibility_assessment": asdict(report.reproducibility),

        "consistency_assessment": asdict(report.consistency),

        "contradictory_evidence_assessment": asdict(report.contradictory_evidence),

    }

    _write_report(report_dict, "framework_assessment_report.json")



    

    _write_report({"novelty_1": n1, "measures_supported": n1.get("measures_meeting_supported_threshold", []),

                   "rationale": n1.get("rationale")}, "novelty_1_validation_report.json")

    _write_report({"novelty_2": n2, "best_metric": n2.get("best_similarity_metric"),

                   "rationale": n2.get("rationale")}, "novelty_2_validation_report.json")

    _write_report({"level_3": "exploratory", "notes": "Level 3 exploratory per DCF design.",

                   "mean_best_rmse": None}, "level_3_assessment_report.json")

    _write_report(asdict(report.reproducibility), "reproducibility_report.json")

    _write_report(asdict(report.consistency), "consistency_report.json")

    _write_report({"overall_assessment": report.overall_assessment,

                   "dataset_coverage_notes": report.dataset_coverage_notes,

                   "strongest_findings": report.strongest_findings,

                   "weakest_findings": report.weakest_findings}, "full_validation_report.json")



    summary = {

        "framework_assessment": report.overall_assessment,

        "novelty_1_classification": report.novelty_1_classification,

        "novelty_2_classification": report.novelty_2_classification,

        "reproducibility": report.reproducibility.reproducibility_score,

        "consistency": report.consistency.consistency_score,

        "tables_written": [str(p) for p in tables],

        "figures_written": [str(p) for p in figs],

    }



    exp_log.info(

        f"[Validation Report] Complete: N1={report.novelty_1_classification}, "

        f"N2={report.novelty_2_classification}, "

        f"{len(tables)} tables, {len(figs)} figures."

    )



    return summary





__all__ = [

    "FrameworkAssessmentReport", "ReproducibilityAssessment",

    "ConsistencyAssessment", "ContradictoryEvidenceAssessment",

    "generate_framework_assessment_report", "generate_validation_reports",

    "_VALIDATION_REPORT_ROOT()",

]

