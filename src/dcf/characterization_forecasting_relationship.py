"""
characterization_forecasting_relationship.py

Stage 7 of the DCF pipeline: Characterization-Forecasting Relationship
Analysis, per DCF specification.

v1.2.0 implementation (bounded-functional reconstruction):

LEVEL 1 — B_i / Spearman / permutation / bootstrap / Holm analysis:
  For each of the seven Domain Profile components (TSS, PSS, VS, SIS,
  PS, SS, TDS), compute:
    B_i = median of 11 z_im values = sixth ordered value (index 5)
    z_im = log(RMSE_im / RMSE_i_naive) for each canonical non-naive model m
  Compute Spearman correlation between [B_i values] and [characterization
  dimension values], with 9,999 valid permutations (+1 correction) and
  1,000 valid bootstrap resamples. Apply Holm correction across 7 dimensions.

LEVEL 2 — z_im / RMS-Euclidean / Mantel analysis:
  z_im vector: 11 entries in CANONICAL_NON_NAIVE order.
  Pairwise RMS-Euclidean distance: sqrt((1/11) * sum((z_im - z_jm)^2)).
  Pairwise DP Euclidean distance over 7-component Domain Profile vectors.
  Spearman correlation + Mantel permutation test (9,999 valid permutations,
  +1 correction, fresh RNG42). 10 LODO analyses, 11 LOMO analyses.

STAGE 7 / STAGE 8 SEPARATION:
  Stage 7 (this file): numerical computation only.
  Stage 8 (evidence_validation.py): evidence-state classification only.
  Stage 7 must NOT assign level_1_evidence_state or level_2_evidence_state.

FORMAL OUTPUT: relationship_analysis.json with exactly five top-level keys:
  dataset_ids, consistency_report, level_1_findings, level_2_findings,
  level_3_summary.

TRACEABILITY: forecasting_behaviour_traceability.json (separate, checksum-
  linked to formal output).
"""



from __future__ import annotations



import hashlib

import json

import math

import logging

from dataclasses import asdict, dataclass

from itertools import combinations

from pathlib import Path

from typing import Optional



import numpy as np

from scipy.stats import spearmanr

from statsmodels.stats.multitest import multipletests



from dcf.config import get_config

from dcf.logging_utils import get_error_logger, get_execution_logger, get_experiment_logger

from dcf.evaluation_layer import is_complete, is_accounting_valid, _is_genuine_int

from dcf.repository import (

    ConsistencyReport,

    DatasetEvidenceBundle,

    load_evidence_bundles,

    load_prepared_series,

    verify_dataset_id_consistency,

)



PROJECT_ROOT = Path(__file__).resolve().parents[2]

from dcf.pub_paths import sub as _sub

def _RELATIONSHIP_EVIDENCE_ROOT(): return _sub("05_analysis/relationship")



CHARACTERIZATION_MEASURES = ["TSS", "PSS", "VS", "SIS", "PS", "SS", "TDS"]





CANONICAL_NON_NAIVE = [

    "seasonal_naive", "drift", "arima", "sarima", "ets",

    "random_forest", "xgboost", "svr", "lstm", "gru", "tcn",

]  



_N_PERMUTATIONS = 9999

_BOOTSTRAP_N    = 1000

_MANTEL_SEED    = 42

_L1_PERM_SEED   = 42





_MIN_LEVEL1_DATASETS = 3   

_MIN_LEVEL2_DATASETS = 3   













@dataclass

class GateRecord:

    dataset_id: str

    gate_id: str

    passed: bool

    failure_reason: Optional[str] = None





@dataclass

class RelativeRepresentationGateSummary:

    gate_records: list          

    eligible_dataset_ids: list

    excluded_dataset_ids: list













@dataclass

class DimensionFinding:

    dimension: str

    spearman_r: Optional[float]

    nominal_permutation_p: Optional[float]

    holm_corrected_p: Optional[float]

    bootstrap_ci_95_low: Optional[float]

    bootstrap_ci_95_high: Optional[float]

    n_discarded_bootstrap_resamples: int

    leave_one_out_correlation: list     

    leave_one_out_sign_stable: Optional[bool]

    sign_consistent_with_secondary: Optional[bool]

    dimension_finding: str              





@dataclass

class Level1Finding:

    characteristic: str

    b_i_values: dict           

    dimension_values: dict     

    spearman_r: Optional[float]

    nominal_permutation_p: Optional[float]

    holm_corrected_p: Optional[float]

    bootstrap_ci_95_low: Optional[float]

    bootstrap_ci_95_high: Optional[float]

    n_discarded_bootstrap_resamples: int

    leave_one_out_sign_stable: Optional[bool]

    sign_consistent_with_secondary: Optional[bool]

    dimension_finding: str

    n_valid_datasets: int





@dataclass

class Level2Finding:

    spearman_r: Optional[float]

    p_parametric: Optional[float]

    p_mantel: Optional[float]

    n_dataset_pairs: int

    n_permutations: int

    n_discarded_permutations: int

    negative_direction: bool

    contradictory_direction: bool

    leave_one_out_states: list   

    insufficient_datasets: bool

    distance_type: str           

    vector_type: str             





@dataclass

class Level3ExploratorySummary:

    n_datasets: int

    mean_best_model_rmse: Optional[float]

    notes: str





@dataclass

class RelationshipAnalysisResult:

    dataset_ids: list

    consistency_report: ConsistencyReport

    level_1_findings: list

    level_2_findings: list

    level_3_summary: Level3ExploratorySummary













def _compute_z_im(evaluation_dict: dict, epsilon_i: float):

    """
    Compute z_im vector for one dataset.
    Returns (z_im_list, None) on success — 11 entries in CANONICAL_NON_NAIVE order.
    Returns (None, reason_str) on gate failure.

    v1.2.0 corrected gate order (frozen v1.2.0 rule):
      GC0: naive present in model_metrics
      GC1: naive completion valid (genuine int, bool excluded, total>0, succeeded==total)
      GC2: naive RMSE finite and strictly > epsilon_i
      GC3: each canonical non-naive model present
      GC4: each non-naive completion valid (same predicate as GC1)
      GC5: each non-naive RMSE finite and strictly > 0 (explicit structured gate)
      Then: z_im[k] = log(rmse_m / naive_rmse)

    epsilon_i must be the exact np.finfo(float).eps * max(abs(series_i)) value.
    No epsilon_i = 0.0 fallback is accepted here; caller is responsible for
    providing the exact value or failing the dataset before calling.

    Completion metadata is read from model_metrics[name]["n_origins_total"]
    and model_metrics[name]["n_origins_succeeded"].  Missing or non-genuine-int
    values fail closed (GC1/GC4).
    """

    model_metrics = evaluation_dict.get("model_metrics", {})



    

    if "naive" not in model_metrics:

        return None, "GC0: naive model absent from model_metrics"



    naive_entry = model_metrics["naive"]



    

    n_tot = naive_entry.get("n_origins_total")

    n_suc = naive_entry.get("n_origins_succeeded")

    n_fai = naive_entry.get("n_origins_failed")

    if not is_accounting_valid(n_tot, n_suc, n_fai):

        return None, (

            f"GC1: naive completion/accounting invalid "

            f"(n_origins_total={n_tot!r}, n_origins_succeeded={n_suc!r}, "

            f"n_origins_failed={n_fai!r})"

        )

    if not is_complete(n_tot, n_suc):

        return None, (

            f"GC1: naive scientifically incomplete "

            f"(n_origins_total={n_tot!r}, n_origins_succeeded={n_suc!r})"

        )



    

    naive_rmse = naive_entry.get("rmse")

    if naive_rmse is None or not math.isfinite(naive_rmse) or naive_rmse <= epsilon_i:

        return None, (

            f"GC2: naive RMSE invalid "

            f"({naive_rmse!r}; must be finite and > epsilon_i={epsilon_i!r})"

        )



    z_im = []

    for m in CANONICAL_NON_NAIVE:

        

        if m not in model_metrics:

            return None, f"GC3: model '{m}' absent from model_metrics"



        entry = model_metrics[m]



        

        n_tot_m = entry.get("n_origins_total")

        n_suc_m = entry.get("n_origins_succeeded")

        n_fai_m = entry.get("n_origins_failed")

        if not is_accounting_valid(n_tot_m, n_suc_m, n_fai_m):

            return None, (

                f"GC4: model '{m}' completion/accounting invalid "

                f"(n_origins_total={n_tot_m!r}, n_origins_succeeded={n_suc_m!r}, "

                f"n_origins_failed={n_fai_m!r})"

            )

        if not is_complete(n_tot_m, n_suc_m):

            return None, (

                f"GC4: model '{m}' scientifically incomplete "

                f"(n_origins_total={n_tot_m!r}, n_origins_succeeded={n_suc_m!r})"

            )



        

        rmse_m = entry.get("rmse")

        if rmse_m is None or not math.isfinite(rmse_m):

            return None, f"GC5: model '{m}' RMSE non-finite ({rmse_m!r})"

        if rmse_m <= 0.0:

            return None, f"GC5: model '{m}' RMSE non-positive ({rmse_m!r}); must be > 0"



        z_im.append(math.log(rmse_m / naive_rmse))



    assert len(z_im) == 11

    return z_im, None





def _compute_B_i(z_im: list) -> float:

    """B_i = median of 11 z_im values = sixth ordered value (index 5)."""

    assert len(z_im) == 11

    return sorted(z_im)[5]





def _compute_secondary_response(evaluation_dict: dict, epsilon_i: float = 0.0) -> Optional[float]:

    """
    Secondary Level 1 response: best_log_relative_rmse_i =
    log(RMSE_i,best / RMSE_i,naive), where best is the RMSE winner
    among eligible models. Returns None if not computable.
    """

    model_metrics = evaluation_dict.get("model_metrics", {})

    naive_rmse = model_metrics.get("naive", {}).get("rmse")

    if naive_rmse is None or not math.isfinite(naive_rmse) or naive_rmse <= epsilon_i:

        return None

    

    best_rmse = None

    for name, m in model_metrics.items():

        if name == "naive":

            continue

        r = m.get("rmse") if isinstance(m, dict) else getattr(m, "rmse", None)

        if r is None or not math.isfinite(r):

            continue

        if best_rmse is None or r < best_rmse:

            best_rmse = r

    if best_rmse is None:

        return None

    return math.log(best_rmse / naive_rmse)













def _rms_euclidean(z_a: list, z_b: list) -> float:

    """d_ij = sqrt((1/11) * sum((z_im - z_jm)^2)); both must have 11 entries."""

    assert len(z_a) == 11 and len(z_b) == 11

    return math.sqrt(sum((a - b) ** 2 for a, b in zip(z_a, z_b)) / 11)





def _dp_euclidean(dp_a: list, dp_b: list) -> float:

    """Standard Euclidean distance on 7-component Domain Profile vectors."""

    assert len(dp_a) == 7 and len(dp_b) == 7

    return math.sqrt(sum((a - b) ** 2 for a, b in zip(dp_a, dp_b)))





def _extract_dp_vector(domain_profile: dict) -> Optional[list]:

    """
    Extract [TSS, PSS, VS, SIS, PS, SS, TDS] from a domain profile dict.
    Uses the canonical vector/vector_order representation (same as Level-1).
    Returns None and fails explicitly if the canonical fields are absent,
    malformed, lengths disagree, a required dimension is missing, or a
    required value is non-finite.  Does not fall back to named lowercase fields.
    """

    vec = domain_profile.get("vector")

    vo  = domain_profile.get("vector_order")

    if vec is None or vo is None:

        raise ValueError(

            "Domain Profile is missing required 'vector' or 'vector_order' fields."

        )

    if len(vec) != len(vo):

        raise ValueError(

            f"Domain Profile 'vector' length ({len(vec)}) does not match "

            f"'vector_order' length ({len(vo)})."

        )

    result = []

    for dim in CHARACTERIZATION_MEASURES:

        if dim not in vo:

            raise ValueError(

                f"Required dimension '{dim}' absent from Domain Profile 'vector_order' {vo}."

            )

        val_raw = vec[vo.index(dim)]

        try:

            val = float(val_raw)

        except (TypeError, ValueError):

            return None

        if not math.isfinite(val):

            return None

        result.append(val)

    return result













def _two_sided_permutation_p(x, y, n_perm, seed):

    """
    Two-sided permutation p-value for Spearman(x, y).
    Hold x fixed, permute y. +1/+1 correction. Discard/replace undefined.
    Returns (r_obs, p_perm, n_discarded).
    """

    x = np.array(x, dtype=float)

    y = np.array(y, dtype=float)

    r_obs, _ = spearmanr(x, y)

    if not math.isfinite(r_obs):

        return None, None, 0



    rng = np.random.default_rng(seed)

    count_extreme = 0

    n_discarded = 0

    valid_count = 0



    while valid_count < n_perm:

        y_perm = rng.permutation(y)

        r_perm, _ = spearmanr(x, y_perm)

        if not math.isfinite(r_perm):

            n_discarded += 1

            continue

        if abs(r_perm) >= abs(r_obs):

            count_extreme += 1

        valid_count += 1



    p = (count_extreme + 1) / (n_perm + 1)

    return float(r_obs), float(p), n_discarded





def _bootstrap_ci(x, y, n_bootstrap, seed):

    """
    Bootstrap 95% CI for Spearman(x, y). Resample dataset indices with
    replacement until exactly n_bootstrap valid correlations obtained.
    Returns (ci_low, ci_high, n_discarded).
    """

    x = np.array(x, dtype=float)

    y = np.array(y, dtype=float)

    n = len(x)

    rng = np.random.default_rng(seed)

    rs = []

    n_discarded = 0

    while len(rs) < n_bootstrap:

        idx = rng.integers(0, n, size=n)

        r, _ = spearmanr(x[idx], y[idx])

        if not math.isfinite(r):

            n_discarded += 1

            continue

        rs.append(r)

    rs = sorted(rs)

    lo = rs[int(0.025 * n_bootstrap)]

    hi = rs[int(0.975 * n_bootstrap)]

    return float(lo), float(hi), n_discarded













def _compute_epsilon_i(series) -> tuple:

    """
    Compute exact epsilon_i = np.finfo(float).eps * max(abs(series)).

    Returns (epsilon_i, None) on success.
    Returns (None, reason_str) if the series cannot support the exact computation:
      - series is None / missing
      - series has no finite values after dropna()
      - series is malformed (non-finite values in max computation)

    A genuinely complete all-zero series is valid: max(abs) = 0, epsilon_i = 0.0.
    This is not a fallback — it is the exact formula applied to a zero series.
    """

    if series is None:

        return None, "epsilon_i: authoritative prepared series missing/unavailable"

    finite_vals = series.dropna().values

    if len(finite_vals) == 0:

        return None, "epsilon_i: prepared series has no finite values after dropna"

    max_abs = float(np.max(np.abs(finite_vals)))

    if not math.isfinite(max_abs):

        return None, f"epsilon_i: max(abs(series)) is non-finite ({max_abs!r})"

    

    

    epsilon_i = float(np.finfo(float).eps * max_abs)

    return epsilon_i, None





def _compute_gates(bundles: dict, prepared_series_map: dict) -> RelativeRepresentationGateSummary:

    """
    For each dataset: compute exact epsilon_i from authoritative prepared series
    (fail closed if series missing/malformed), then run GC0–GC5 gates via
    _compute_z_im. Returns gate summary with eligible/excluded.

    v1.2.0 correction: no epsilon_i = 0.0 fallback; missing series fails closed.
    """

    gate_records = []

    eligible = []

    excluded = []



    for did, bundle in bundles.items():

        series = prepared_series_map.get(did)

        epsilon_i, eps_reason = _compute_epsilon_i(series)



        if epsilon_i is None:

            

            failure = eps_reason

        else:

            eval_dict = bundle.evaluation

            _, failure = _compute_z_im(eval_dict, epsilon_i=epsilon_i)



        passed = (failure is None)

        gate_records.append(GateRecord(

            dataset_id=did,

            gate_id="completion_epsilon_rmse_fixed_model_set",

            passed=passed,

            failure_reason=failure,

        ))

        if passed:

            eligible.append(did)

        else:

            excluded.append(did)



    return RelativeRepresentationGateSummary(

        gate_records=[asdict(g) for g in gate_records],

        eligible_dataset_ids=sorted(eligible),

        excluded_dataset_ids=sorted(excluded),

    )













def _level_1_analysis(bundles: dict, gate_summary: RelativeRepresentationGateSummary,

                      prepared_series_map: dict, config=None) -> list:

    """
    Compute Level 1 findings: one per CHARACTERIZATION_MEASURES dimension.
    Returns list of Level1Finding dicts.
    Stage 7 only: no evidence-state assignment.
    """

    eligible_ids = gate_summary.eligible_dataset_ids

    if not eligible_ids:

        return []



    

    epsilon_map = {}

    for did in eligible_ids:

        series = prepared_series_map.get(did)

        if series is not None:

            finite_vals = series.dropna().values

            if len(finite_vals) > 0 and np.any(np.abs(finite_vals) > 0):

                max_abs = float(np.max(np.abs(finite_vals)))

                epsilon_map[did] = float(np.finfo(float).eps * max_abs)

            else:

                epsilon_map[did] = 0.0

        else:

            epsilon_map[did] = 0.0



    z_im_map = {}

    b_i_map  = {}

    sec_map  = {}

    for did in eligible_ids:

        eval_dict = bundles[did].evaluation

        eps = epsilon_map[did]

        z_im, _ = _compute_z_im(eval_dict, epsilon_i=eps)

        if z_im is not None:

            z_im_map[did] = z_im

            b_i_map[did]  = _compute_B_i(z_im)

            sec_map[did]  = _compute_secondary_response(eval_dict, epsilon_i=eps)



    if not b_i_map:

        return []



    b_vals = [b_i_map[did] for did in sorted(b_i_map)]

    b_ids  = sorted(b_i_map)



    findings = []

    nominal_ps = []

    dim_r_map  = {}



    for dim_idx, dim in enumerate(CHARACTERIZATION_MEASURES):

        

        

        

        dim_vals = []

        dim_ids  = []

        dim_b    = []

        for did in b_ids:

            dp    = bundles[did].domain_profile

            vec   = dp.get("vector")

            vo    = dp.get("vector_order")

            if vec is None or vo is None:

                raise ValueError(

                    f"Domain Profile for '{did}' is missing the required "

                    "'vector'/'vector_order' fields. These fields are required for "

                    "Stage 7 characterization access. Check Domain Profile serialization."

                )

            if len(vec) != len(vo):

                raise ValueError(

                    f"Domain Profile for '{did}': 'vector' length ({len(vec)}) "

                    f"does not match 'vector_order' length ({len(vo)})."

                )

            if dim not in vo:

                raise ValueError(

                    f"Domain Profile for '{did}': required dimension '{dim}' "

                    f"is absent from 'vector_order' {vo}."

                )

            val_raw = vec[vo.index(dim)]

            if val_raw is None:

                continue

            try:

                val = float(val_raw)

            except (TypeError, ValueError):

                continue

            if not math.isfinite(val):

                continue

            dim_vals.append(val)

            dim_ids.append(did)

            dim_b.append(b_i_map[did])



        if len(dim_vals) < 3:

            

            dim_r_map[dim] = None

            nominal_ps.append(None)

            findings.append(Level1Finding(

                characteristic=dim,

                b_i_values=b_i_map,

                dimension_values={did: bundles[did].domain_profile.get(dim) for did in b_ids},

                spearman_r=None,

                nominal_permutation_p=None,

                holm_corrected_p=None,

                bootstrap_ci_95_low=None,

                bootstrap_ci_95_high=None,

                n_discarded_bootstrap_resamples=0,

                leave_one_out_sign_stable=None,

                sign_consistent_with_secondary=None,

                dimension_finding="undefined",

                n_valid_datasets=len(dim_vals),

            ))

            continue



        

        seed = _L1_PERM_SEED + dim_idx * 10000

        r_obs, p_perm, n_disc_perm = _two_sided_permutation_p(dim_vals, dim_b, _N_PERMUTATIONS, seed)



        nominal_ps.append(p_perm)

        dim_r_map[dim] = r_obs



        

        if r_obs is not None:

            boot_lo, boot_hi, n_disc_boot = _bootstrap_ci(

                dim_vals, dim_b, _BOOTSTRAP_N, seed=_L1_PERM_SEED + dim_idx * 10000 + 1

            )

        else:

            boot_lo, boot_hi, n_disc_boot = None, None, 0



        

        loo_rs = []

        for loo_did in dim_ids:

            loo_x = [v for v, d in zip(dim_vals, dim_ids) if d != loo_did]

            loo_y = [b for b, d in zip(dim_b, dim_ids) if d != loo_did]

            if len(loo_x) < 3:

                continue

            r_loo, _ = spearmanr(loo_x, loo_y)

            if math.isfinite(r_loo):

                loo_rs.append(float(r_loo))



        if r_obs is not None and loo_rs:

            sign_r = 1 if r_obs >= 0 else -1

            n_same_sign = sum(1 for r in loo_rs if (r >= 0) == (r_obs >= 0))

            loo_stable = (n_same_sign >= 8) if len(loo_rs) >= 8 else None

        else:

            loo_rs = []

            loo_stable = None



        

        sec_sign_consistent = None

        if r_obs is not None:

            sec_vals = [sec_map.get(did) for did in dim_ids if sec_map.get(did) is not None]

            sec_b    = [dim_b[i] for i, did in enumerate(dim_ids) if sec_map.get(did) is not None]

            if len(sec_vals) >= 3:

                r_sec, _ = spearmanr(dim_vals[:len(sec_vals)], sec_b)

                if math.isfinite(r_sec):

                    sec_sign_consistent = ((r_obs >= 0) == (r_sec >= 0))



        findings.append(Level1Finding(

            characteristic=dim,

            b_i_values={did: b_i_map[did] for did in dim_ids},

            dimension_values={did: v for did, v in zip(dim_ids, dim_vals)},

            spearman_r=r_obs,

            nominal_permutation_p=p_perm,

            holm_corrected_p=None,  

            bootstrap_ci_95_low=boot_lo,

            bootstrap_ci_95_high=boot_hi,

            n_discarded_bootstrap_resamples=n_disc_boot,

            leave_one_out_sign_stable=loo_stable,

            sign_consistent_with_secondary=sec_sign_consistent,

            dimension_finding="pending_holm",  

            n_valid_datasets=len(dim_vals),

        ))



    

    defined_idx = [i for i, p in enumerate(nominal_ps) if p is not None]

    defined_ps  = [nominal_ps[i] for i in defined_idx]



    if defined_ps:

        _, holm_ps, _, _ = multipletests(defined_ps, method="holm")

        holm_iter = iter(holm_ps)

    else:

        holm_iter = iter([])



    final_findings = []

    for i, f in enumerate(findings):

        if nominal_ps[i] is None:

            final_findings.append(asdict(f))

            continue

        holm_p = float(next(holm_iter))

        r = f.spearman_r



        

        if r is None:

            df = "undefined"

        elif holm_p < 0.05 and abs(r) >= 0.50:

            df = "strong_signal"

        elif f.nominal_permutation_p < 0.05 and abs(r) >= 0.30:

            df = "weak_signal"

        else:

            df = "no_signal"



        fd = asdict(f)

        fd["holm_corrected_p"] = holm_p

        fd["dimension_finding"] = df

        final_findings.append(fd)



    return final_findings













def _level_2_analysis(bundles: dict, gate_summary: RelativeRepresentationGateSummary,

                      prepared_series_map: dict, config=None) -> list:

    """
    Compute Level 2 findings: RMS-Euclidean Mantel test.
    Returns list containing one Level2Finding dict.
    Stage 7 only: no evidence-state assignment.
    """

    eligible_ids = sorted(gate_summary.eligible_dataset_ids)



    if len(eligible_ids) < _MIN_LEVEL2_DATASETS:

        return [asdict(Level2Finding(

            spearman_r=None, p_parametric=None, p_mantel=None,

            n_dataset_pairs=0, n_permutations=_N_PERMUTATIONS,

            n_discarded_permutations=0,

            negative_direction=False, contradictory_direction=False,

            leave_one_out_states=[], insufficient_datasets=True,

            distance_type="rms_euclidean", vector_type="log_relative_rmse",

        ))]



    

    epsilon_map = {}

    for did in eligible_ids:

        series = prepared_series_map.get(did)

        if series is not None:

            finite_vals = series.dropna().values

            if len(finite_vals) > 0 and np.any(np.abs(finite_vals) > 0):

                max_abs = float(np.max(np.abs(finite_vals)))

                epsilon_map[did] = float(np.finfo(float).eps * max_abs)

            else:

                epsilon_map[did] = 0.0

        else:

            epsilon_map[did] = 0.0



    z_im_map = {}

    dp_map   = {}

    for did in eligible_ids:

        z_im, _ = _compute_z_im(bundles[did].evaluation, epsilon_i=epsilon_map[did])

        if z_im is None:

            continue

        dp = _extract_dp_vector(bundles[did].domain_profile)

        if dp is None:

            continue

        z_im_map[did] = z_im

        dp_map[did]   = dp



    valid_ids = sorted(set(z_im_map) & set(dp_map))

    n = len(valid_ids)

    pairs = list(combinations(range(n), 2))



    if n < _MIN_LEVEL2_DATASETS:

        return [asdict(Level2Finding(

            spearman_r=None, p_parametric=None, p_mantel=None,

            n_dataset_pairs=len(pairs), n_permutations=_N_PERMUTATIONS,

            n_discarded_permutations=0,

            negative_direction=False, contradictory_direction=False,

            leave_one_out_states=[], insufficient_datasets=True,

            distance_type="rms_euclidean", vector_type="log_relative_rmse",

        ))]



    beh_dists = [_rms_euclidean(z_im_map[valid_ids[i]], z_im_map[valid_ids[j]]) for i, j in pairs]

    prof_dists = [_dp_euclidean(dp_map[valid_ids[i]], dp_map[valid_ids[j]]) for i, j in pairs]



    r_obs, p_param = spearmanr(prof_dists, beh_dists)

    r_obs = float(r_obs) if math.isfinite(r_obs) else None



    

    rng = np.random.default_rng(_MANTEL_SEED)

    count_extreme = 0

    n_discarded   = 0

    valid_perms   = 0

    dp_arr = [dp_map[did] for did in valid_ids]



    while valid_perms < _N_PERMUTATIONS:

        perm = rng.permutation(n)

        perm_prof = [_dp_euclidean(dp_arr[perm[i]], dp_arr[perm[j]]) for i, j in pairs]

        r_perm, _ = spearmanr(perm_prof, beh_dists)

        if not math.isfinite(r_perm):

            n_discarded += 1

            continue

        if r_obs is not None and abs(r_perm) >= abs(r_obs):

            count_extreme += 1

        valid_perms += 1



    p_mantel = (count_extreme + 1) / (_N_PERMUTATIONS + 1)



    negative_direction   = (r_obs is not None and r_obs < 0)

    contradictory_direction = (

        r_obs is not None and r_obs < -0.10 and p_mantel < 0.05

    )



    

    lodo_states = []

    for excl_did in valid_ids:

        sub_ids = [d for d in valid_ids if d != excl_did]

        sub_pairs = list(combinations(range(len(sub_ids)), 2))

        if len(sub_ids) < 3 or not sub_pairs:

            lodo_states.append({"excluded": excl_did, "r": None, "p_mantel": None, "n": len(sub_ids)})

            continue

        sub_beh  = [_rms_euclidean(z_im_map[sub_ids[i]], z_im_map[sub_ids[j]]) for i, j in sub_pairs]

        sub_prof = [_dp_euclidean(dp_map[sub_ids[i]], dp_map[sub_ids[j]]) for i, j in sub_pairs]

        r_sub, _ = spearmanr(sub_prof, sub_beh)

        

        lodo_states.append({

            "excluded": excl_did,

            "r": float(r_sub) if math.isfinite(r_sub) else None,

            "p_mantel": None,  

            "n": len(sub_ids),

        })



    return [asdict(Level2Finding(

        spearman_r=r_obs,

        p_parametric=float(p_param) if r_obs is not None and math.isfinite(p_param) else None,

        p_mantel=float(p_mantel),

        n_dataset_pairs=len(pairs),

        n_permutations=_N_PERMUTATIONS,

        n_discarded_permutations=n_discarded,

        negative_direction=negative_direction,

        contradictory_direction=contradictory_direction,

        leave_one_out_states=lodo_states,

        insufficient_datasets=False,

        distance_type="rms_euclidean",

        vector_type="log_relative_rmse",

    ))]













def _level_3_exploratory_summary(bundles: dict) -> dict:

    best_rmses = []

    for bundle in bundles.values():

        ev = bundle.evaluation

        best = ev.get("best_model")

        if best:

            rmse = ev.get("model_metrics", {}).get(best, {}).get("rmse")

            if rmse is not None:

                best_rmses.append(rmse)

    mean_rmse = float(np.mean(best_rmses)) if best_rmses else None

    return asdict(Level3ExploratorySummary(

        n_datasets=len(bundles),

        mean_best_model_rmse=mean_rmse,

        notes="Exploratory level 3 summary. Not used for formal evidence classification.",

    ))













def run_relationship_analysis(dataset_ids=None, config=None) -> RelationshipAnalysisResult:

    cfg = config or get_config(allow_draft=False)

    exec_log = get_execution_logger()

    exec_log.info("[Stage 7] Characterization-Forecasting Relationship Analysis")



    report  = verify_dataset_id_consistency(dataset_ids)

    bundles = load_evidence_bundles(report)



    

    prepared_series_map = {}

    for did in sorted(bundles):

        try:

            prepared_series_map[did] = load_prepared_series(did, config=cfg)

        except Exception:

            prepared_series_map[did] = None



    gate_summary = _compute_gates(bundles, prepared_series_map)



    l1_findings = _level_1_analysis(bundles, gate_summary, prepared_series_map, config=cfg)

    l2_findings = _level_2_analysis(bundles, gate_summary, prepared_series_map, config=cfg)

    l3_summary  = _level_3_exploratory_summary(bundles)



    

    

    _z_im_map     = {}

    _epsilon_map  = {}

    _naive_rmse_map = {}

    for did in gate_summary.eligible_dataset_ids:

        series = prepared_series_map.get(did)

        eps, _ = _compute_epsilon_i(series)

        if eps is None:

            continue

        eval_dict = bundles[did].evaluation

        z_im, fail = _compute_z_im(eval_dict, epsilon_i=eps)

        if z_im is None:

            continue

        _z_im_map[did]     = z_im

        _epsilon_map[did]  = eps

        naive_rmse = eval_dict.get("model_metrics", {}).get("naive", {}).get("rmse")

        _naive_rmse_map[did] = naive_rmse



    result = RelationshipAnalysisResult(

        dataset_ids=sorted(bundles.keys()),

        consistency_report=report,

        level_1_findings=l1_findings,

        level_2_findings=l2_findings,

        level_3_summary=l3_summary,

    )



    _write_relationship_results(result, gate_summary,

                                z_im_map=_z_im_map,

                                epsilon_map=_epsilon_map,

                                naive_rmse_map=_naive_rmse_map)

    return result













def _write_relationship_results(result: RelationshipAnalysisResult,

                                  gate_summary: RelativeRepresentationGateSummary,

                                  z_im_map: dict = None,

                                  epsilon_map: dict = None,

                                  naive_rmse_map: dict = None):

    _RELATIONSHIP_EVIDENCE_ROOT().mkdir(parents=True, exist_ok=True)



    

    formal_path = _RELATIONSHIP_EVIDENCE_ROOT() / "relationship_analysis.json"

    payload = {

        "dataset_ids": result.dataset_ids,

        "consistency_report": {

            "successfully_matched": result.consistency_report.successfully_matched,

            "domain_profile_only": result.consistency_report.domain_profile_only,

            "evaluation_only": result.consistency_report.evaluation_only,

            "total_domain_profile": result.consistency_report.total_domain_profile,

            "total_evaluation": result.consistency_report.total_evaluation,

        },

        "level_1_findings": result.level_1_findings,

        "level_2_findings": result.level_2_findings,

        "level_3_summary": result.level_3_summary,

    }

    with open(formal_path, "w") as f:

        json.dump(payload, f, indent=2, default=str)



    

    formal_sha256 = _sha256_of_file(formal_path)



    

    

    

    z_im_by_dataset       = z_im_map      if z_im_map      is not None else {}

    epsilon_i_by_dataset  = epsilon_map   if epsilon_map   is not None else {}

    naive_rmse_by_dataset = naive_rmse_map if naive_rmse_map is not None else {}

    b_i_by_dataset = {did: _compute_B_i(z_im_map[did])

                      for did in (z_im_map or {})} if z_im_map else {}

    

    for f in result.level_1_findings:

        if isinstance(f, dict):

            for did, bv in f.get("b_i_values", {}).items():

                if did not in b_i_by_dataset:

                    b_i_by_dataset[did] = bv



    

    traceability_path = _RELATIONSHIP_EVIDENCE_ROOT() / "forecasting_behaviour_traceability.json"

    traceability = {

        "traceability_artifact": True,

        "dataset_ids": result.dataset_ids,

        "formal_outputs_linked": [

            {

                "filename": formal_path.name,

                "sha256": formal_sha256,

            }

        ],

        "gate_summary": asdict(gate_summary) if hasattr(gate_summary, "__dataclass_fields__") else (gate_summary if isinstance(gate_summary, dict) else {}),

        "b_i_by_dataset": b_i_by_dataset,

        "z_im_by_dataset": z_im_by_dataset,

        "naive_rmse_by_dataset": naive_rmse_by_dataset,

        "epsilon_i_by_dataset": epsilon_i_by_dataset,

        "canonical_model_order": CANONICAL_NON_NAIVE,

    }

    with open(traceability_path, "w") as f:

        json.dump(traceability, f, indent=2, default=str)





def _sha256_of_file(path: Path) -> str:

    h = hashlib.sha256()

    with open(path, "rb") as f:

        for chunk in iter(lambda: f.read(65536), b""):

            h.update(chunk)

    return h.hexdigest()





def load_relationship_analysis() -> dict:

    path = _RELATIONSHIP_EVIDENCE_ROOT() / "relationship_analysis.json"

    if not path.exists():

        raise FileNotFoundError(f"No relationship analysis found at {path}")

    with open(path) as f:

        return json.load(f)





__all__ = [

    "CANONICAL_NON_NAIVE",

    "CHARACTERIZATION_MEASURES",

    "GateRecord",

    "RelativeRepresentationGateSummary",

    "Level1Finding",

    "Level2Finding",

    "Level3ExploratorySummary",

    "RelationshipAnalysisResult",

    "run_relationship_analysis",

    "load_relationship_analysis",

    "_RELATIONSHIP_EVIDENCE_ROOT()",

]

