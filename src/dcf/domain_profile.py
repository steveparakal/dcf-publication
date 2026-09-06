"""
domain_profile.py

Domain Profile construction, per DCF specification.

Assembles the fixed-order Domain Profile vector:

    DP = [TSS, PSS, VS, SIS, PS, SS, TDS]

plus supplementary structural-change attributes (NCP, ACM, MCM, RCD)
retained for reporting and analysis but NOT included in the vector
itself (DCF specification / DCF design).

This module is the single orchestration point for Stage 2 of the
pipeline: it runs STL once, reuses it for TSS/PSS/VS, and computes
PS/SS/TDS/structural-change directly from the prepared series, then
assembles everything into one DomainProfile record.

Under the publication specification, characterization and
Domain Profile construction operate on the single selected target series
per dataset (domain_profile.multivariate_scope = "single_target_series"
in the frozen config). One Domain Profile is produced per target series.
"""



from __future__ import annotations



import json

from dataclasses import asdict, dataclass

from pathlib import Path

from typing import Optional



import pandas as pd



from dcf.characterization import (

    compute_pss,

    compute_ps,

    compute_ss,

    compute_structural_change,

    compute_tds,

    compute_tss,

    compute_vs,

)

from dcf.config import Config, get_config

from dcf.logging_utils import get_execution_logger, get_experiment_logger

from dcf.stl_decomposition import run_stl



PROJECT_ROOT = Path(__file__).resolve().parents[2]

from dcf.pub_paths import sub as _sub

def _DOMAIN_PROFILE_ROOT(): return _sub("03_domain_profiles")

def _CHARACTERIZATION_ROOT(): return _sub("02_characterization")





@dataclass

class DomainProfile:

    dataset_id: str

    vector_order: list

    vector: list

    tss: float

    pss: float

    vs: float

    sis: float

    ps: float

    ss: float

    tds: float

    tss_label: str

    pss_label: str

    vs_label: str

    sis_label: str

    ps_label: str

    ss_label: str

    tds_label: str

    ncp: int

    acm: float

    mcm: float

    rcd: float

    n_change_points_detail: list

    stl_period_used: int

    n_observations: int



    def to_dict(self) -> dict:

        return asdict(self)





def construct_domain_profile(series, dataset_id, frequency_key, config=None):

    cfg = config or get_config(allow_draft=False)

    exec_log = get_execution_logger()

    exp_log = get_experiment_logger()



    clean_series = pd.Series(series).dropna()

    n_obs = len(clean_series)



    exec_log.info(f"[Stage 2] Constructing Domain Profile for '{dataset_id}' (n={n_obs})")



    stl_result = run_stl(clean_series, dataset_id=dataset_id, frequency_key=frequency_key, config=cfg)



    tss_out = compute_tss(stl_result, config=cfg)

    pss_out = compute_pss(stl_result, config=cfg)

    vs_out = compute_vs(stl_result, config=cfg)

    ps_out = compute_ps(clean_series, dataset_id=dataset_id, config=cfg)

    ss_out = compute_ss(clean_series, dataset_id=dataset_id, config=cfg)

    tds_out = compute_tds(clean_series, dataset_id=dataset_id, config=cfg)

    sc_result = compute_structural_change(clean_series, dataset_id=dataset_id, config=cfg)



    vector_order = cfg.get(

        "domain_profile.vector_order",

        ["TSS", "PSS", "VS", "SIS", "PS", "SS", "TDS"],

    )

    value_lookup = {

        "TSS": tss_out["value"], "PSS": pss_out["value"], "VS": vs_out["value"],

        "SIS": sc_result.sis, "PS": ps_out["value"], "SS": ss_out["value"],

        "TDS": tds_out["value"],

    }

    vector = [value_lookup[name] for name in vector_order]



    profile = DomainProfile(

        dataset_id=dataset_id,

        vector_order=vector_order,

        vector=vector,

        tss=tss_out["value"], pss=pss_out["value"], vs=vs_out["value"],

        sis=sc_result.sis, ps=ps_out["value"], ss=ss_out["value"], tds=tds_out["value"],

        tss_label=tss_out["label"], pss_label=pss_out["label"], vs_label=vs_out["label"],

        sis_label=sc_result.sis_label, ps_label=ps_out["label"], ss_label=ss_out["label"],

        tds_label=tds_out["label"],

        ncp=sc_result.ncp, acm=sc_result.acm, mcm=sc_result.mcm, rcd=sc_result.rcd,

        n_change_points_detail=sc_result.change_points,

        stl_period_used=stl_result.period_used,

        n_observations=n_obs,

    )



    exp_log.info(f"[Stage 2] Domain Profile for '{dataset_id}': vector={dict(zip(vector_order, vector))}")



    _write_domain_profile(profile)



    return profile





def _write_domain_profile(profile):

    out_dir = _DOMAIN_PROFILE_ROOT() / profile.dataset_id

    out_dir.mkdir(parents=True, exist_ok=True)

    out_path = out_dir / f"{profile.dataset_id}.domain_profile.json"

    with open(out_path, "w") as f:

        json.dump(profile.to_dict(), f, indent=2, default=str)





def load_domain_profile(dataset_id):

    path = _DOMAIN_PROFILE_ROOT() / dataset_id / f"{dataset_id}.domain_profile.json"

    if not path.exists():

        raise FileNotFoundError(

            f"No Domain Profile found for '{dataset_id}' at {path}. "

            "Has construct_domain_profile() been run for this dataset yet?"

        )

    with open(path, "r") as f:

        return json.load(f)





__all__ = ["DomainProfile", "construct_domain_profile", "load_domain_profile", "_DOMAIN_PROFILE_ROOT()"]

