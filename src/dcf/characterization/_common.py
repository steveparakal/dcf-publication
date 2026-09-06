"""
characterization/_common.py

Shared helpers used by every characterization measure module, implementing
the cross-cutting rules from DCF specification:

  - 5.4 Global Characterization Label Policy (Low/Moderate/High cuts)
  - 5.5 Variance Calculation Rule (population variance, ddof=0)
  - 5.7 Characterization Output Standard ({"measure", "value", "label"})

Centralising these here means every measure module applies identical
rules rather than each reimplementing its own rounding/labeling logic --
this is itself a reproducibility safeguard, since a label-boundary bug
fixed in one measure is fixed in all of them.
"""



from __future__ import annotations



from typing import Optional



import numpy as np



from dcf.config import Config, get_config





def population_variance(values, config: Optional[Config] = None) -> float:

    """
    Population variance (ddof=0), per DCF specification.5.
    Accepts any array-like; NaNs must already be removed by the caller
    (Section 5.6 -- missing-value handling is each module's
    responsibility, not this shared helper's).
    """

    arr = np.asarray(values, dtype=float)

    if arr.size == 0:

        return 0.0

    return float(np.var(arr, ddof=0))





def assign_label(value: float, config: Optional[Config] = None) -> str:

    """
    Apply the Global Characterization Label Policy (DCF specification
    Section 5.4):
        0.00-0.33 -> Low
        0.34-0.66 -> Moderate
        0.67-1.00 -> High

    The cut points are read from the frozen config
    (characterization.label_thresholds) rather than hardcoded here, so a
    documented config change is the only way to alter them.
    """

    cfg = config or get_config(allow_draft=False)

    low_high_cut = float(cfg.get("characterization.label_thresholds.low_high_cut", 0.33))

    high_medium_cut = float(cfg.get("characterization.label_thresholds.high_medium_cut", 0.66))



    if value <= low_high_cut:

        return "Low"

    elif value <= high_medium_cut:

        return "Moderate"

    else:

        return "High"





def characterization_output(measure: str, value: float, include_label: bool = True, config: Optional[Config] = None) -> dict:

    """
    Build the standard characterization output structure (DCF specification
    Section 5.7): {"measure": ..., "value": ..., "label": ...}.

    `include_label=False` is used for the structural-change subcomponents
    (NCP, ACM, MCM, RCD) which the DCF specification's own output structure
    in Section 9 ({"measure": ..., "value": ...}) defines WITHOUT a label
    -- only SIS and the seven Domain Profile measures carry a label.
    """

    out = {"measure": measure, "value": float(value)}

    if include_label:

        out["label"] = assign_label(float(value), config=config)

    return out





__all__ = ["population_variance", "assign_label", "characterization_output"]

