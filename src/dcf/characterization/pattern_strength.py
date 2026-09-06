"""
pattern_strength.py

Temporal Pattern Strength Score (PSS), per DCF specification.

Formula:
    PSS = Var(S) / [Var(S) + Var(R)]

where S = temporal pattern (seasonal) component, R = residual component,
both from STL decomposition (shared, computed once).

Boundary condition: if Var(S) + Var(R) = 0, PSS = 0.
Range: 0 <= PSS <= 1.
"""



from __future__ import annotations



from typing import Optional



from dcf.characterization._common import characterization_output, population_variance

from dcf.config import Config

from dcf.stl_decomposition import STLResult





def compute_pss(stl_result: STLResult, config: Optional[Config] = None) -> dict:

    var_s = population_variance(stl_result.pattern, config=config)

    var_r = population_variance(stl_result.residual, config=config)



    denominator = var_s + var_r

    if denominator == 0:

        pss = 0.0

    else:

        pss = var_s / denominator



    pss = max(0.0, min(1.0, pss))



    return characterization_output("PSS", pss, config=config)





__all__ = ["compute_pss"]

