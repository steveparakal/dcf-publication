"""
trend_strength.py

Trend Strength Score (TSS), per DCF specification.

Formula:
    TSS = Var(T) / [Var(T) + Var(R)]

where T = trend component, R = residual component, both from STL
decomposition (shared, computed once -- see stl_decomposition.py).

Boundary condition: if Var(T) + Var(R) = 0, TSS = 0.
Range: 0 <= TSS <= 1.

Direction-agnostic by construction (variance has no sign), consistent
with the published score definition: language elsewhere about "directional
behavior" describes the intuition behind the measure, not a signed
quantity in the formula itself.
"""



from __future__ import annotations



from typing import Optional



from dcf.characterization._common import characterization_output, population_variance

from dcf.config import Config

from dcf.stl_decomposition import STLResult





def compute_tss(stl_result: STLResult, config: Optional[Config] = None) -> dict:

    """
    Compute TSS from a precomputed STLResult.

    Per DCF specification, STL decomposition shall be reused by
    downstream modules and not recomputed independently -- this function
    therefore takes an STLResult, not a raw series.
    """

    var_t = population_variance(stl_result.trend, config=config)

    var_r = population_variance(stl_result.residual, config=config)



    denominator = var_t + var_r

    if denominator == 0:

        tss = 0.0

    else:

        tss = var_t / denominator



    tss = max(0.0, min(1.0, tss))



    return characterization_output("TSS", tss, config=config)





__all__ = ["compute_tss"]

