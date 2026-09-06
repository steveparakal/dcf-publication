"""
dcf.characterization

The seven Domain Characterization measures (DCF specification):
TSS, PSS, VS, SIS (+ NCP/ACM/MCM/RCD supplementary attributes), PS, SS, TDS.
"""



from dcf.characterization._common import assign_label, characterization_output, population_variance

from dcf.characterization.pattern_strength import compute_pss

from dcf.characterization.persistence_stationarity import compute_ps, compute_ss

from dcf.characterization.structural_change import (

    ChangePointResult,

    StructuralChangeResult,

    compute_acm,

    compute_mcm,

    compute_ncp,

    compute_rcd,

    compute_sis,

    compute_structural_change,

    detect_change_points,

)

from dcf.characterization.temporal_dependence import compute_tds

from dcf.characterization.trend_strength import compute_tss

from dcf.characterization.volatility import compute_vs



__all__ = [

    "assign_label",

    "characterization_output",

    "population_variance",

    "compute_tss",

    "compute_pss",

    "compute_vs",

    "compute_ps",

    "compute_ss",

    "compute_tds",

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

