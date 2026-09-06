"""
volatility.py

Volatility Score (VS), per DCF specification.

Formula:
    VS = Var(R) / [Var(T) + Var(S) + Var(R)]

where T = trend, S = temporal pattern, R = residual, all from STL
decomposition (shared, computed once).

Boundary condition: if Var(T) + Var(S) + Var(R) = 0, VS = 0.
Range: 0 <= VS <= 1.
"""



from __future__ import annotations



from typing import Optional



from dcf.characterization._common import characterization_output, population_variance

from dcf.config import Config

from dcf.stl_decomposition import STLResult





def compute_vs(stl_result: STLResult, config: Optional[Config] = None) -> dict:

    var_t = population_variance(stl_result.trend, config=config)

    var_s = population_variance(stl_result.pattern, config=config)

    var_r = population_variance(stl_result.residual, config=config)



    denominator = var_t + var_s + var_r

    if denominator == 0:

        vs = 0.0

    else:

        vs = var_r / denominator



    vs = max(0.0, min(1.0, vs))



    return characterization_output("VS", vs, config=config)





__all__ = ["compute_vs"]

