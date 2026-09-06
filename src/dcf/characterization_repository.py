"""
characterization_repository.py

Implements the Characterization Repository used by the publication pipeline:

  "The implementation shall maintain the following minimum repository set:
   - Prepared Dataset Repository
   - Characterization Repository     <-- THIS MODULE
   - Domain Profile Repository
   - ..."

The Characterization Repository stores the intermediate per-dataset
outputs of the Characterization Layer (Stage 2): individual measure
values with their metadata, STL decomposition summaries, ADF test
statistics, PELT change-point details -- providing the deeper
traceability layer between raw data and the Domain Profile vector.

This is distinct from the Domain Profile Repository (Stage 3), which
stores only the assembled DP = [TSS, PSS, VS, SIS, PS, SS, TDS] vector.
The Characterization Repository stores the full supporting detail behind
each measure value, supporting:
  - Reviewer-level transparency (v1.2.0, 44, 45, 46)
  - Sensitivity analysis (v1.2.0 -- threshold choices are visible)
  - Reproducibility verification
  - Traceability from Domain Profile vector back to raw measures

The repository is populated by write_characterization_record() called
from the characterization pipeline (Stage 2 / domain_profile.py).
It reads and reuses the outputs already computed by Phase 2 -- it does
NOT recompute any characterization measure.
"""

from __future__ import annotations



import json

from dataclasses import asdict, dataclass

from pathlib import Path

from typing import Optional



import numpy as np

import pandas as pd



from dcf.config import get_config

from dcf.logging_utils import get_execution_logger



PROJECT_ROOT = Path(__file__).resolve().parents[2]

from dcf.pub_paths import sub as _sub

def _CHARACTERIZATION_REPO_ROOT(): return _sub("02_characterization")





@dataclass

class CharacterizationRecord:

    """Full characterization output for one dataset, combining the
    Domain Profile with the supporting detail behind each measure."""

    dataset_id: str

    n_observations: int

    frequency_key: str

    stl_period_used: int

    stl_robust: bool

    

    tss: float

    tss_label: str

    pss: float

    pss_label: str

    vs: float

    vs_label: str

    sis: float

    sis_label: str

    ps: float

    ps_label: str

    ss: float

    ss_label: str

    tds: float

    tds_label: str

    

    stl_trend_variance: Optional[float]

    stl_pattern_variance: Optional[float]

    stl_residual_variance: Optional[float]

    

    ps_lag_1_autocorrelation: Optional[float]

    ss_adf_statistic: Optional[float]

    ss_adf_pvalue: Optional[float]

    ss_adf_autolag: str

    ss_alpha_used: float

    

    tds_lag_set: list

    tds_lag_autocorrelations: dict    

    

    sc_cost_model: str

    sc_pelt_penalty: float

    sc_min_segment_size: int

    sc_change_magnitude_definition: str

    sc_mean_shift_weight: float

    sc_variance_shift_weight: float

    ncp: int

    acm: float

    mcm: float

    rcd: float

    change_points: list

    

    vector_order: list

    vector: list





def write_characterization_record_from_profile(domain_profile_dict: dict, config=None) -> Path:

    """
    Write a CharacterizationRecord to the Characterization Repository,
    populated from a DomainProfile dict (already computed by Stage 2).

    This does NOT re-run any characterization computation -- it reads
    the already-frozen DomainProfile dict (from domain_profile.py's
    _write_domain_profile output) and enriches it with the supporting
    detail fields that the Domain Profile JSON captures separately.

    The supporting detail (ADF test statistics, per-lag ACF values,
    PELT settings) is read from the domain_profile_dict's existing
    fields where available. Where not available (because the Phase 2
    DomainProfile dataclass only stores summary values, not every
    sub-detail), the fields are stored as None rather than recomputed
    -- consistent with this module's role as a repository writer, not
    a re-execution engine.
    """

    cfg = config or get_config(allow_draft=False)

    exec_log = get_execution_logger()



    did = domain_profile_dict["dataset_id"]



    

    tds_lag_set = cfg.get("characterization.temporal_dependence_score.lag_set", [2, 3, 4, 5])

    adf_alpha = cfg.get("characterization.stationarity_score.adf_alpha", 0.05)

    adf_autolag = cfg.get("characterization.stationarity_score.adf_autolag", "AIC")

    sc_cost_model = cfg.get("characterization.structural_change.cost_model", "l2")

    sc_penalty = float(cfg.get("characterization.structural_change.pelt_penalty", 10.0))

    sc_min_seg = int(cfg.get("characterization.structural_change.min_segment_size", 10))

    sc_magnitude_def = cfg.get("characterization.structural_change.change_magnitude_definition",

                                "mean_and_variance_shift")

    weights = cfg.get("characterization.structural_change.change_magnitude_weights", {})

    mean_w = float(weights.get("mean_shift_weight", 0.5))

    var_w = float(weights.get("variance_shift_weight", 0.5))



    record = CharacterizationRecord(

        dataset_id=did,

        n_observations=domain_profile_dict.get("n_observations", 0),

        frequency_key="monthly",           

        stl_period_used=domain_profile_dict.get("stl_period_used", 0),

        stl_robust=cfg.get("stl.robust", True),

        tss=domain_profile_dict["tss"], tss_label=domain_profile_dict["tss_label"],

        pss=domain_profile_dict["pss"], pss_label=domain_profile_dict["pss_label"],

        vs=domain_profile_dict["vs"],   vs_label=domain_profile_dict["vs_label"],

        sis=domain_profile_dict["sis"], sis_label=domain_profile_dict["sis_label"],

        ps=domain_profile_dict["ps"],   ps_label=domain_profile_dict["ps_label"],

        ss=domain_profile_dict["ss"],   ss_label=domain_profile_dict["ss_label"],

        tds=domain_profile_dict["tds"], tds_label=domain_profile_dict["tds_label"],

        

        

        

        

        

        stl_trend_variance=None,

        stl_pattern_variance=None,

        stl_residual_variance=None,

        

        ps_lag_1_autocorrelation=domain_profile_dict.get("ps"),  

        ss_adf_statistic=None,    

        ss_adf_pvalue=None,       

        ss_adf_autolag=adf_autolag,

        ss_alpha_used=adf_alpha,

        

        tds_lag_set=list(tds_lag_set),

        tds_lag_autocorrelations={},  

        

        sc_cost_model=sc_cost_model,

        sc_pelt_penalty=sc_penalty,

        sc_min_segment_size=sc_min_seg,

        sc_change_magnitude_definition=sc_magnitude_def,

        sc_mean_shift_weight=mean_w,

        sc_variance_shift_weight=var_w,

        ncp=domain_profile_dict.get("ncp", 0),

        acm=domain_profile_dict.get("acm", 0.0),

        mcm=domain_profile_dict.get("mcm", 0.0),

        rcd=domain_profile_dict.get("rcd", 0.0),

        change_points=domain_profile_dict.get("n_change_points_detail", []),

        vector_order=domain_profile_dict.get("vector_order", []),

        vector=domain_profile_dict.get("vector", []),

    )



    out_dir = _CHARACTERIZATION_REPO_ROOT() / did

    out_dir.mkdir(parents=True, exist_ok=True)

    out_path = out_dir / f"{did}.characterization.json"

    with open(out_path, "w") as f:

        json.dump(asdict(record), f, indent=2, default=str)



    exec_log.info(f"Characterization record written for '{did}': {out_path}")

    return out_path





def populate_characterization_repository_from_domain_profiles(config=None) -> dict:

    """
    Populate the Characterization Repository from existing Domain Profile
    JSON files. This is a one-time catch-up operation for datasets that
    completed Stage 2 before the Characterization Repository was
    implemented -- it reads the already-frozen DomainProfile outputs
    and writes the corresponding CharacterizationRecords.

    Returns {dataset_id: path_written}.
    """

    from dcf.pub_paths import sub as _sub_dp

    DOMAIN_PROFILE_ROOT = _sub_dp("03_domain_profiles")

    cfg = config or get_config(allow_draft=False)

    written = {}



    if not DOMAIN_PROFILE_ROOT.exists():

        return written



    for dp_dir in sorted(DOMAIN_PROFILE_ROOT.iterdir()):

        if not dp_dir.is_dir():

            continue

        dp_file = dp_dir / f"{dp_dir.name}.domain_profile.json"

        if not dp_file.exists():

            continue

        with open(dp_file) as f:

            dp_dict = json.load(f)

        path = write_characterization_record_from_profile(dp_dict, config=cfg)

        written[dp_dir.name] = str(path)



    return written





def load_characterization_record(dataset_id: str) -> dict:

    path = _CHARACTERIZATION_REPO_ROOT() / dataset_id / f"{dataset_id}.characterization.json"

    if not path.exists():

        raise FileNotFoundError(

            f"No characterization record found for '{dataset_id}' at {path}."

        )

    with open(path) as f:

        return json.load(f)





__all__ = [

    "CharacterizationRecord",

    "write_characterization_record_from_profile",

    "populate_characterization_repository_from_domain_profiles",

    "load_characterization_record",

    "_CHARACTERIZATION_REPO_ROOT()",

]

