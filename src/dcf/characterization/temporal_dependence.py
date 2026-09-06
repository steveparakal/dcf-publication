"""
temporal_dependence.py

Temporal Dependence Score (TDS), per DCF specification.

Formula:
    TDS = (1/|L|) * sum_{k in L} |rho_k|

LAG SET -- DCF specification, U1 resolution (overrides DCF specification
Section 12's stated default L={1,2,3,4,5}):
    L = {2, 3, 4, 5}

v1.2.0 is authoritative: lag 1 is reserved exclusively for PS, to
preserve the conceptual distinction between immediate persistence (PS)
and broader temporal dependence (TDS). The contradictory wording in
v1.2.0 (which would have included lag 1) was identified during
the publication specification and is not used. This module reads
the lag set from the frozen config
(characterization.temporal_dependence_score.lag_set), which is already
set to [2, 3, 4, 5] -- so this module enforces the resolution by
construction rather than by a hardcoded literal that could drift out of
sync with the config.

Boundary conditions (DCF specification):
    - If one or more lag autocorrelations cannot be computed, use all
      valid lag values available.
    - If no lag autocorrelations can be computed, TDS = 0.

Range: 0 <= TDS <= 1.
"""



from __future__ import annotations



import numpy as np

import pandas as pd

from statsmodels.tsa.stattools import acf



from dcf.characterization._common import characterization_output

from dcf.config import get_config

from dcf.logging_utils import get_error_logger





def compute_tds(series, dataset_id="", config=None):

    cfg = config or get_config(allow_draft=False)

    error_log = get_error_logger()

    clean = pd.Series(series).dropna()



    lag_set = cfg.get("characterization.temporal_dependence_score.lag_set", [2, 3, 4, 5])

    lag_set = sorted(int(k) for k in lag_set)



    if 1 in lag_set:

        raise ValueError(

            "Temporal Dependence Score lag set must not include lag 1 "

            "(reserved exclusively for Persistence Score per DCF specification "

            f"U1 resolution / v1.2.0). Configured lag_set={lag_set}."

        )



    max_lag = max(lag_set) if lag_set else 0



    if len(clean) <= max_lag:

        error_log.warning(

            f"TDS for '{dataset_id}': only {len(clean)} valid observations, "

            f"insufficient for max configured lag {max_lag}. Returning TDS=0 "

            "per boundary condition."

        )

        return characterization_output("TDS", 0.0, config=config)



    try:

        acf_values = acf(clean, nlags=max_lag, fft=True)

    except Exception as exc:

        error_log.warning(

            f"TDS for '{dataset_id}': autocorrelation computation failed "

            f"({exc!r}). Returning TDS=0 per boundary condition."

        )

        return characterization_output("TDS", 0.0, config=config)



    valid_abs_rhos = []

    for k in lag_set:

        if k < len(acf_values):

            rho_k = acf_values[k]

            if not np.isnan(rho_k):

                valid_abs_rhos.append(abs(float(rho_k)))

            else:

                error_log.warning(

                    f"TDS for '{dataset_id}': autocorrelation at lag {k} is NaN; "

                    "excluding this lag per Section 12's 'use all valid lag "

                    "values available' boundary rule."

                )

        else:

            error_log.warning(

                f"TDS for '{dataset_id}': lag {k} exceeds the computed ACF "

                "range; excluding this lag per Section 12's boundary rule."

            )



    if not valid_abs_rhos:

        error_log.warning(

            f"TDS for '{dataset_id}': no valid lag autocorrelations available "

            "in the configured lag set. Returning TDS=0 per boundary condition."

        )

        return characterization_output("TDS", 0.0, config=config)



    tds = float(np.mean(valid_abs_rhos))

    tds = max(0.0, min(1.0, tds))



    return characterization_output("TDS", tds, config=config)





__all__ = ["compute_tds"]

