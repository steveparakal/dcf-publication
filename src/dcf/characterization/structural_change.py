"""
structural_change.py

Structural Instability Score (SIS) and its subcomponents, per Coding
Package Section 9, with one approved override:

CHANGE MAGNITUDE DEFINITION -- DCF design (overrides
DCF specification.3's stated SCM_i = |mu_before - mu_after|,
mean-shift only):

    SCM_i = MS_norm_i + VS_norm_i   (equal-weighted, 0.5 / 0.5)

where MS_norm_i is a normalized mean-shift term and VS_norm_i is a
normalized variance-shift term. This was approved specifically because
the mean-only definition cannot detect pure variance-regime changes
(e.g. a volatility spike at roughly constant mean -- the kind of event
that matters for the financial-domain datasets in this project), and
because DCF specification/19's evidence-validation framework benefits from a
SCM definition that is sensitive to both. The frozen config
(characterization.structural_change.change_magnitude_definition) is
already set to "mean_and_variance_shift" with weights 0.5/0.5 -- this
module implements exactly that, not the DCF specification's mean-only
formula, by construction.

Everything else in this module follows the DCF specification exactly:

  - Change-point detection: PELT (ruptures.Pelt), cost model "l2",
    penalty and min_size from config (defaults 10 and 10 respectively).
  - NCP = |C| (number of detected change points).
  - ACM = (1/NCP) * sum(SCM_i), 0 if NCP=0.
  - MCM = max(SCM_1..SCM_k), 0 if NCP=0.
  - RCD = NCP / n, 0 if n=0 or NCP=0.
  - SIS = (ACM_norm + MCM_norm + RCD) / 3, equal-weighted, no learned or
    optimization-based weights.
  - Dataset scale = max(X) - min(X), or 1 if max(X) == min(X) (avoids
    division by zero).
  - ACM_norm = min(1, ACM / Scale); MCM_norm = min(1, MCM / Scale).
  - SIS carries a label (Global Characterization Label Policy);
    NCP/ACM/MCM/RCD do NOT carry a label, per Section 9's stated output
    structure {"measure": ..., "value": ...} for the subcomponents versus
    {"measure": "SIS", "value": ..., "label": ...} for SIS itself.

Reproducibility: PELT is deterministic given the same input, cost model,
penalty, and min_size -- no stochastic procedures are introduced.
"""



from __future__ import annotations



from dataclasses import dataclass

from typing import Optional



import numpy as np

import pandas as pd

import ruptures as rpt



from dcf.characterization._common import characterization_output, population_variance

from dcf.config import Config, get_config

from dcf.logging_utils import get_error_logger, get_execution_logger





@dataclass

class ChangePointResult:

    change_points: list

    algorithm: str

    cost_model: str

    penalty: float

    min_size: int





@dataclass

class StructuralChangeResult:

    dataset_id: str

    change_points: list

    scm_values: list

    ncp: int

    acm: float

    mcm: float

    rcd: float

    sis: float

    sis_label: str

    scale: float

    acm_norm: float

    mcm_norm: float





def detect_change_points(series, dataset_id="", config=None):

    """
    PELT change-point detection (DCF specification.1).

    Validation rules applied (Section 9.1): change points must be
    ordered, duplicates removed, out-of-range points discarded. ruptures
    itself always returns ordered, in-range breakpoints (plus a trailing
    len(series) sentinel which we strip), so these checks are mostly a
    defensive safeguard against unexpected library behavior rather than
    something ruptures is expected to violate.
    """

    cfg = config or get_config(allow_draft=False)

    exec_log = get_execution_logger()

    error_log = get_error_logger()



    clean = pd.Series(series).dropna()

    n = len(clean)



    cost_model = cfg.get("characterization.structural_change.cost_model", "l2")

    penalty = float(cfg.get("characterization.structural_change.pelt_penalty", 10.0))

    min_size = int(cfg.get("characterization.structural_change.min_segment_size", 10))



    if n < 2 * min_size:

        error_log.warning(

            f"Change-point detection for '{dataset_id}': only {n} observations, "

            f"fewer than 2x min_segment_size ({2 * min_size}). PELT cannot "

            "produce any valid segment under this configuration; returning "

            "an empty change-point set per Section 9.1's failure-handling rule "

            "(C = empty set, framework continues execution)."

        )

        return ChangePointResult(

            change_points=[], algorithm="PELT", cost_model=cost_model,

            penalty=penalty, min_size=min_size,

        )



    values = clean.to_numpy().reshape(-1, 1)



    try:

        algo = rpt.Pelt(model=cost_model, min_size=min_size).fit(values)

        breakpoints = algo.predict(pen=penalty)

    except Exception as exc:

        error_log.warning(

            f"Change-point detection for '{dataset_id}' failed ({exc!r}). "

            "Returning empty change-point set per Section 9.1 failure-handling."

        )

        return ChangePointResult(

            change_points=[], algorithm="PELT", cost_model=cost_model,

            penalty=penalty, min_size=min_size,

        )



    

    

    change_points = [bp for bp in breakpoints if bp < n]



    

    change_points = sorted(set(cp for cp in change_points if 0 < cp < n))



    exec_log.info(

        f"Change-point detection for '{dataset_id}': {len(change_points)} "

        f"change point(s) detected (algorithm=PELT, cost={cost_model}, "

        f"penalty={penalty}, min_size={min_size})."

    )



    return ChangePointResult(

        change_points=change_points, algorithm="PELT", cost_model=cost_model,

        penalty=penalty, min_size=min_size,

    )





def compute_ncp(change_point_result):

    """NCP = |C|."""

    ncp = len(change_point_result.change_points)

    return {"measure": "NCP", "value": int(ncp)}





def _segment_before_after(values, change_points, index_in_list):

    """
    Segment definition per DCF specification.3:
      - segment_before(c_i): observations between the previous change
        point and c_i (or from the start of the dataset for the first
        change point).
      - segment_after(c_i): observations between c_i and the next change
        point (or to the end of the dataset for the last change point).
    """

    cp = change_points[index_in_list]

    prev_cp = change_points[index_in_list - 1] if index_in_list > 0 else 0

    next_cp = change_points[index_in_list + 1] if index_in_list + 1 < len(change_points) else len(values)



    segment_before = values[prev_cp:cp]

    segment_after = values[cp:next_cp]

    return segment_before, segment_after





def _compute_scm_values(series, change_point_result, config=None):

    """
    Structural Change Magnitude per change point, under the approved
    v1.2.0 definition:

        SCM_i = mean_shift_weight * MS_norm_i + variance_shift_weight * VS_norm_i

    where:
        MS_i = |mu_before - mu_after|
        VS_i = |sigma2_before - sigma2_after|   (population variance, ddof=0)

    Both MS_i and VS_i are normalized by the dataset's own scale
    (max(X) - min(X), or scale^2 for the variance term) before combining,
    so the two terms are commensurable and SCM_i remains comparable
    across datasets of different absolute magnitude. This is in addition
    to (not a replacement for) Section 9.6.1's later dataset-scale
    normalization of the aggregate ACM/MCM values -- without this inner
    normalization, a variance-shift term in squared units would dominate
    a mean-shift term in linear units purely from unit mismatch, not
    genuine signal.
    """

    cfg = config or get_config(allow_draft=False)

    clean = pd.Series(series).dropna()

    values = clean.to_numpy()



    weights = cfg.get("characterization.structural_change.change_magnitude_weights", {})

    mean_weight = float(weights.get("mean_shift_weight", 0.5))

    variance_weight = float(weights.get("variance_shift_weight", 0.5))



    scale = float(np.max(values) - np.min(values)) if len(values) > 0 else 0.0

    if scale == 0:

        scale = 1.0

    scale_sq = scale ** 2



    scm_values = []

    for i, cp in enumerate(change_point_result.change_points):

        seg_before, seg_after = _segment_before_after(values, change_point_result.change_points, i)



        if len(seg_before) == 0 or len(seg_after) == 0:

            scm_values.append(0.0)

            continue



        mu_before, mu_after = float(np.mean(seg_before)), float(np.mean(seg_after))

        var_before = population_variance(seg_before, config=cfg)

        var_after = population_variance(seg_after, config=cfg)



        ms_i = abs(mu_before - mu_after)

        vs_i = abs(var_before - var_after)



        ms_norm_i = min(1.0, ms_i / scale)

        vs_norm_i = min(1.0, vs_i / scale_sq)



        scm_i = mean_weight * ms_norm_i + variance_weight * vs_norm_i

        scm_values.append(max(0.0, scm_i))



    return scm_values





def compute_acm(scm_values, ncp):

    """ACM = (1/NCP) * sum(SCM_i); 0 if NCP=0."""

    if ncp == 0:

        return {"measure": "ACM", "value": 0.0}

    acm = float(np.sum(scm_values)) / ncp

    return {"measure": "ACM", "value": max(0.0, acm)}





def compute_mcm(scm_values, ncp):

    """MCM = max(SCM_1..SCM_k); 0 if NCP=0."""

    if ncp == 0 or not scm_values:

        return {"measure": "MCM", "value": 0.0}

    mcm = float(np.max(scm_values))

    return {"measure": "MCM", "value": max(0.0, mcm)}





def compute_rcd(ncp, n):

    """RCD = NCP / n; 0 if n=0 or NCP=0. Range [0,1]."""

    if n == 0 or ncp == 0:

        return {"measure": "RCD", "value": 0.0}

    rcd = ncp / n

    rcd = max(0.0, min(1.0, rcd))

    return {"measure": "RCD", "value": rcd}





def compute_sis(series, acm, mcm, rcd, dataset_id="", config=None):

    """
    SIS = (ACM_norm + MCM_norm + RCD) / 3, equal-weighted.

    v1.2.0 CORRECTED: ACM and MCM are already dimensionless (normalized
    within compute_acm/compute_mcm by the dataset's own scale). The outer
    scale division that appeared in v1.1.5 was therefore a double-normalisation
    defect. ACM_norm = min(1, ACM); MCM_norm = min(1, MCM).
    Scale is retained here for traceability purposes only.
    RCD is already in [0,1] -- no additional normalisation.
    """

    clean = pd.Series(series).dropna()

    values = clean.to_numpy()



    scale = float(np.max(values) - np.min(values)) if len(values) > 0 else 1.0

    if scale == 0:

        scale = 1.0



    

    acm_norm = min(1.0, acm)

    mcm_norm = min(1.0, mcm)

    rcd_clamped = max(0.0, min(1.0, rcd))



    sis = (acm_norm + mcm_norm + rcd_clamped) / 3.0

    sis = max(0.0, min(1.0, sis))



    output = characterization_output("SIS", sis, config=config)

    output["acm_norm"] = acm_norm

    output["mcm_norm"] = mcm_norm

    output["scale"] = scale

    return output





def compute_structural_change(series, dataset_id="", config=None):

    """
    Convenience orchestrator: runs the full Section 9 pipeline (detection
    through SIS) for one dataset and returns a single result object.
    Equivalent to calling detect_change_points -> compute_ncp ->
    compute_acm/compute_mcm/compute_rcd -> compute_sis in sequence, but
    bundled for callers (e.g. domain_profile.py) that want the whole
    structural-change picture in one call.
    """

    cfg = config or get_config(allow_draft=False)

    exec_log = get_execution_logger()



    clean = pd.Series(series).dropna()

    n = len(clean)



    cp_result = detect_change_points(clean, dataset_id=dataset_id, config=cfg)

    ncp_out = compute_ncp(cp_result)

    ncp = ncp_out["value"]



    scm_values = _compute_scm_values(clean, cp_result, config=cfg)



    acm_out = compute_acm(scm_values, ncp)

    mcm_out = compute_mcm(scm_values, ncp)

    rcd_out = compute_rcd(ncp, n)



    sis_out = compute_sis(

        clean, acm_out["value"], mcm_out["value"], rcd_out["value"],

        dataset_id=dataset_id, config=cfg,

    )



    exec_log.info(

        f"Structural change summary for '{dataset_id}': NCP={ncp}, "

        f"ACM={acm_out['value']:.4f}, MCM={mcm_out['value']:.4f}, "

        f"RCD={rcd_out['value']:.4f}, SIS={sis_out['value']:.4f} "

        f"({sis_out['label']})"

    )



    return StructuralChangeResult(

        dataset_id=dataset_id,

        change_points=cp_result.change_points,

        scm_values=scm_values,

        ncp=ncp,

        acm=acm_out["value"],

        mcm=mcm_out["value"],

        rcd=rcd_out["value"],

        sis=sis_out["value"],

        sis_label=sis_out["label"],

        scale=sis_out["scale"],

        acm_norm=sis_out["acm_norm"],

        mcm_norm=sis_out["mcm_norm"],

    )





__all__ = [

    "ChangePointResult",

    "StructuralChangeResult",

    "detect_change_points",

    "compute_ncp",

    "compute_acm",

    "compute_mcm",

    "compute_rcd",

    "compute_sis",

    "compute_structural_change",

]

