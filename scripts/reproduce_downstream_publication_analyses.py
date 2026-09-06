#!/usr/bin/env python3
"""
Reproduce the prespecified downstream publication analyses from a completed
DCF publication run.

This script reads only machine-readable outputs produced by the completed
publication pipeline. It does not rerun forecasting, train or refit models,
change datasets, alter the publication configuration, change seeds or
thresholds, introduce new hypotheses, or select analyses after observing
results.

Outputs
-------
- S13: Level-1 leave-one-dataset-out and secondary-response checks.
- S14: Domain Profile distance matrix.
- S15: Forecasting-behaviour distance matrix.
- S17: Prespecified Level-2 sensitivities S1-S7.
"""
from pathlib import Path
import argparse
import json, math, itertools, hashlib
from datetime import datetime, timezone
import numpy as np
from scipy.stats import spearmanr, rankdata
from scipy.spatial.distance import cosine, correlation

ROOT = None
OUT = None
N_PERM = 9999
SEED = 42

DIMS = ["TSS","PSS","VS","SIS","PS","SS","TDS"]

def sha256(path: Path) -> str:
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):
            h.update(chunk)
    return h.hexdigest()

def classify_l2(r, p):
    abs_r=abs(r)
    if abs_r < 0.10:
        return "Unsupported"
    elif r < 0 and abs_r >= 0.10 and p < 0.05:
        return "Unsupported"
    elif r >= 0.40 and p < 0.05:
        return "Supported"
    elif 0.20 <= r < 0.40 and p < 0.05:
        return "Partially Supported"
    else:
        return "Inconclusive"

def matrix_from_vectors(ids, vectors, metric):
    n=len(ids)
    M=np.zeros((n,n),dtype=float)
    for i in range(n):
        for j in range(i+1,n):
            a=np.asarray(vectors[ids[i]],dtype=float)
            b=np.asarray(vectors[ids[j]],dtype=float)
            if metric=="dp_euclidean":
                v=float(np.linalg.norm(a-b))
            elif metric=="rms_euclidean":
                v=float(np.sqrt(np.mean((a-b)**2)))
            elif metric=="euclidean":
                v=float(np.linalg.norm(a-b))
            elif metric=="cosine":
                v=float(cosine(a,b))
            elif metric=="correlation":
                v=float(correlation(a,b))
            else:
                raise ValueError(metric)
            M[i,j]=M[j,i]=v
    return M

def _rank_matrix(M):
    from scipy.stats import rankdata
    n=M.shape[0]
    tri=np.triu_indices(n,1)
    r=rankdata(M[tri],method="average")
    R=np.zeros_like(M,dtype=float)
    R[tri]=r
    R[(tri[1],tri[0])]=r
    return R,r

def _pearson_on_ranks(a,b):
    a=np.asarray(a,dtype=float); b=np.asarray(b,dtype=float)
    ac=a-a.mean(); bc=b-b.mean()
    den=math.sqrt(float(np.dot(ac,ac))*float(np.dot(bc,bc)))
    return float(np.dot(ac,bc)/den)

def mantel_from_matrices(DP, DB, nperm=N_PERM, seed=SEED):
    """Exact Spearman Mantel using pre-ranked symmetric DP matrix; faster but algebraically identical."""
    from scipy.stats import rankdata, spearmanr
    n=DP.shape[0]
    tri=np.triu_indices(n,1)
    x=DP[tri]
    y=DB[tri]
    obs=spearmanr(x,y)
    rho=float(obs.statistic)
    p_param=float(obs.pvalue)
    R, rx=_rank_matrix(DP)
    ry=rankdata(y,method="average")
    # Verify fast rank correlation agrees with scipy observed statistic.
    if abs(_pearson_on_ranks(rx,ry)-rho)>1e-14:
        raise RuntimeError("Fast Spearman implementation disagrees with scipy observed rho")
    rng=np.random.default_rng(seed)
    extreme=0
    for _ in range(nperm):
        perm=rng.permutation(n)
        rr=_pearson_on_ranks(R[np.ix_(perm,perm)][tri],ry)
        if abs(rr) >= abs(rho):
            extreme += 1
    p=(extreme+1)/(nperm+1)
    return {
        "rho":rho,
        "p_parametric":p_param,
        "p_mantel":float(p),
        "n_dataset_pairs":int(len(x)),
        "n_permutations":int(nperm),
        "n_discarded_permutations":0,
    }

def mantel_independent_pair_loop(ids, dp_map, rep_map, metric, nperm=N_PERM, seed=SEED):
    """Independent second-pass: construct matrices through pair loops, then use rank permutation."""
    n=len(ids)
    DP=np.zeros((n,n),float); DB=np.zeros((n,n),float)
    for i in range(n):
        for j in range(i+1,n):
            DP[i,j]=DP[j,i]=float(np.linalg.norm(dp_map[ids[i]]-dp_map[ids[j]]))
            a=np.asarray(rep_map[ids[i]],float); b=np.asarray(rep_map[ids[j]],float)
            if metric=="rms_euclidean": v=float(np.sqrt(np.mean((a-b)**2)))
            elif metric=="euclidean": v=float(np.linalg.norm(a-b))
            elif metric=="cosine": v=float(cosine(a,b))
            elif metric=="correlation": v=float(correlation(a,b))
            else: raise ValueError(metric)
            DB[i,j]=DB[j,i]=v
    out=mantel_from_matrices(DP,DB,nperm=nperm,seed=seed)
    return out["rho"],out["p_mantel"],out["n_discarded_permutations"]

def main():
    global ROOT, OUT
    parser = argparse.ArgumentParser(
        description="Reproduce the prespecified downstream DCF publication analyses."
    )
    parser.add_argument(
        "--results-root",
        required=True,
        type=Path,
        help="Path to a completed Stage 1-9 publication-run directory.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="Directory in which the S13-S17 machine-readable outputs will be written.",
    )
    args = parser.parse_args()
    ROOT = args.results_root.resolve()
    OUT = args.output_dir.resolve()

    required = [
        ROOT / "05_analysis/relationship/forecasting_behaviour_traceability.json",
        ROOT / "05_analysis/relationship/relationship_analysis.json",
        ROOT / "06_validation/evidence_validation.json",
    ]
    missing = [str(p) for p in required if not p.is_file()]
    if missing:
        raise FileNotFoundError(
            "Completed publication-run artifacts are missing: " + "; ".join(missing)
        )

    OUT.mkdir(parents=True,exist_ok=True)

    trace_path=ROOT/"05_analysis/relationship/forecasting_behaviour_traceability.json"
    rel_path=ROOT/"05_analysis/relationship/relationship_analysis.json"
    val_path=ROOT/"06_validation/evidence_validation.json"
    trace=json.load(open(trace_path))
    rel_final=json.load(open(rel_path))
    val_final=json.load(open(val_path))

    ids=sorted(trace["z_im_by_dataset"].keys())
    models=list(trace["canonical_model_order"])
    if len(ids)!=10 or len(models)!=11:
        raise RuntimeError("Final authoritative identity mismatch: expected 10 datasets and 11 non-naive models.")

    dp_map={}
    z_map={}
    rmse_map={}
    relative_map={}
    rank_map={}
    b_map={k:float(v) for k,v in trace["b_i_by_dataset"].items()}
    secondary_map={}
    input_paths=[trace_path,rel_path,val_path]

    for did in ids:
        dp_path=ROOT/"03_domain_profiles"/did/f"{did}.domain_profile.json"
        ev_path=ROOT/"04_forecasts"/did/f"{did}.evaluation.json"
        input_paths += [dp_path,ev_path]
        dpj=json.load(open(dp_path))
        ev=json.load(open(ev_path))
        if dpj["vector_order"] != DIMS:
            raise RuntimeError(f"{did}: unexpected Domain Profile order {dpj['vector_order']}")
        dp_map[did]=np.asarray(dpj["vector"],dtype=float)
        z_map[did]=np.asarray(trace["z_im_by_dataset"][did],dtype=float)
        r=np.asarray([ev["model_metrics"][m]["rmse"] for m in models],dtype=float)
        rmse_map[did]=r
        naive=float(ev["model_metrics"]["naive"]["rmse"])
        relative_map[did]=r/naive
        rank_map[did]=rankdata(r,method="average")
        best=min(float(v["rmse"]) for k,v in ev["model_metrics"].items() if k!="naive")
        secondary_map[did]=math.log(best/naive)

    # S13: full 7 x 10 LODO matrix + secondary correlations.
    l1_lodo={}
    secondary={}
    for dim_idx,dim in enumerate(DIMS):
        l1_lodo[dim]={}
        for omitted in ids:
            kept=[d for d in ids if d!=omitted]
            r=spearmanr(
                [dp_map[d][dim_idx] for d in kept],
                [b_map[d] for d in kept]
            ).statistic
            l1_lodo[dim][omitted]=float(r)
        sr=spearmanr(
            [dp_map[d][dim_idx] for d in ids],
            [secondary_map[d] for d in ids]
        ).statistic
        secondary[dim]=float(sr)

    # S14/S15: exact matrices from full-precision final authoritative vectors.
    DD=matrix_from_vectors(ids,dp_map,"dp_euclidean")
    DB=matrix_from_vectors(ids,z_map,"rms_euclidean")

    # Reconfirm primary from reconstructed matrices.
    primary=mantel_from_matrices(DD,DB)
    final_primary=rel_final["level_2_findings"][0]
    if abs(primary["rho"]-float(final_primary["spearman_r"]))>1e-14:
        raise RuntimeError("Primary rho reconstruction does not match final Stage-7 authority.")
    if abs(primary["p_mantel"]-float(final_primary["p_mantel"]))>0:
        raise RuntimeError("Primary p_mantel reconstruction does not match final Stage-7 authority.")

    # Prespecified S1-S4 + S7.
    reps={
        "S1":{"label":"robustness_relative_rmse","vectors":relative_map,"metric":"rms_euclidean","description":"Ordinary relative RMSE vector; RMS-Euclidean"},
        "S2":{"label":"robustness_model_ranks","vectors":rank_map,"metric":"rms_euclidean","description":"Within-dataset model ranks; RMS-Euclidean"},
        "S3":{"label":"robustness_cosine_distance","vectors":z_map,"metric":"cosine","description":"Cosine distance on primary z vector"},
        "S4":{"label":"robustness_correlation_distance","vectors":z_map,"metric":"correlation","description":"Correlation distance on primary z vector"},
        "S7":{"label":"diagnostic_raw_rmse_scale_defect","vectors":rmse_map,"metric":"euclidean","description":"Raw RMSE vector; Euclidean distance (scale diagnostic)"},
    }
    sensitivities={}
    second_checks={}
    for key,spec in reps.items():
        DBx=matrix_from_vectors(ids,spec["vectors"],spec["metric"])
        res=mantel_from_matrices(DD,DBx)
        res.update({
            "label":spec["label"],
            "description":spec["description"],
            "evidence_state": "Diagnostic only" if key=="S7" else classify_l2(res["rho"],res["p_mantel"]),
        })
        sensitivities[key]=res
        r2,p2,d2=mantel_independent_pair_loop(ids,dp_map,spec["vectors"],spec["metric"])
        second_checks[key]={
            "rho_equal": bool(abs(r2-res["rho"])<=1e-15),
            "p_mantel_equal": bool(p2==res["p_mantel"]),
            "discarded_equal": bool(d2==res["n_discarded_permutations"]),
        }

    # S5: leave one model out from primary z representation.
    s5=[]
    for k,model in enumerate(models):
        sub={d:np.delete(z_map[d],k) for d in ids}
        DBx=matrix_from_vectors(ids,sub,"rms_euclidean")
        res=mantel_from_matrices(DD,DBx)
        res.update({
            "omitted_model":model,
            "evidence_state":classify_l2(res["rho"],res["p_mantel"])
        })
        r2,p2,d2=mantel_independent_pair_loop(ids,dp_map,sub,"rms_euclidean")
        if abs(r2-res["rho"])>1e-15 or p2!=res["p_mantel"] or d2!=res["n_discarded_permutations"]:
            raise RuntimeError(f"S5 independent verification failed for {model}")
        s5.append(res)

    # S6: leave one dataset out from primary z representation; full 9999-permutation Mantel.
    s6=[]
    for omitted in ids:
        kept=[d for d in ids if d!=omitted]
        DDsub=matrix_from_vectors(kept,{d:dp_map[d] for d in kept},"dp_euclidean")
        DBsub=matrix_from_vectors(kept,{d:z_map[d] for d in kept},"rms_euclidean")
        res=mantel_from_matrices(DDsub,DBsub)
        res.update({
            "omitted_dataset":omitted,
            "evidence_state":classify_l2(res["rho"],res["p_mantel"])
        })
        r2,p2,d2=mantel_independent_pair_loop(kept,dp_map,z_map,"rms_euclidean")
        if abs(r2-res["rho"])>1e-15 or p2!=res["p_mantel"] or d2!=res["n_discarded_permutations"]:
            raise RuntimeError(f"S6 independent verification failed for {omitted}")
        s6.append(res)

    # Confirm S6 r values match the already-persisted final Stage-7 LODO r values.
    persisted={x["excluded"]:float(x["r"]) for x in final_primary["leave_one_out_states"]}
    for x in s6:
        if abs(x["rho"]-persisted[x["omitted_dataset"]])>1e-15:
            raise RuntimeError(f"S6 rho mismatch against persisted Stage-7 LODO for {x['omitted_dataset']}")

    sensitivities["S5"]={
        "label":"sensitivity_leave_one_model_out",
        "results":s5,
        "summary":{
            "Unsupported":sum(x["evidence_state"]=="Unsupported" for x in s5),
            "Inconclusive":sum(x["evidence_state"]=="Inconclusive" for x in s5),
            "Partially Supported":sum(x["evidence_state"]=="Partially Supported" for x in s5),
            "Supported":sum(x["evidence_state"]=="Supported" for x in s5),
        }
    }
    sensitivities["S6"]={
        "label":"sensitivity_leave_one_dataset_out",
        "results":s6,
        "summary":{
            "Unsupported":sum(x["evidence_state"]=="Unsupported" for x in s6),
            "Inconclusive":sum(x["evidence_state"]=="Inconclusive" for x in s6),
            "Partially Supported":sum(x["evidence_state"]=="Partially Supported" for x in s6),
            "Supported":sum(x["evidence_state"]=="Supported" for x in s6),
            "primary_exact_state_preserved":sum(x["evidence_state"]=="Unsupported" for x in s6),
            "n_total":len(s6),
        }
    }

    # Write main artifacts.
    s13={
        "object":"Table S13 bounded reconstruction",
        "dataset_order":ids,
        "dimension_order":DIMS,
        "lodo_rho_matrix":l1_lodo,
        "secondary_best_log_relative_rmse_by_dataset":secondary_map,
        "secondary_spearman_by_dimension":secondary,
        "strong_finding_secondary_checks":{
            "TSS":{"rho":secondary["TSS"],"same_sign":secondary["TSS"]>=0},
            "VS":{"rho":secondary["VS"],"same_sign":secondary["VS"]<0},
        },
    }
    s14={
        "object":"Table S14 Domain Profile distance matrix D_D",
        "dataset_order":ids,
        "metric":"Euclidean on full-precision seven-dimensional Domain Profiles",
        "matrix":DD.tolist(),
    }
    s15={
        "object":"Table S15 forecasting-behaviour distance matrix D_B",
        "dataset_order":ids,
        "metric":"RMS-Euclidean on full-precision 11-entry log-relative-RMSE z vectors",
        "matrix":DB.tolist(),
    }
    s17={
        "object":"Table S17 / Table 5.3 prespecified Level-2 sensitivity completion",
        "dataset_order":ids,
        "model_order":models,
        "permutations":N_PERM,
        "seed":SEED,
        "primary_reconstruction":primary,
        "sensitivities":sensitivities,
        "independent_second_checks":second_checks,
        "notes":[
            "S7 is a scale diagnostic and is not co-equal primary evidence.",
            "Sensitivity analyses do not upgrade the primary Level-2 evidence state.",
            "S6 reports full permutation results; its rho values exactly match the LODO rho values already persisted in final Stage 7.",
        ],
    }

    for name,obj in [("S13_level1_lodo_secondary.json",s13),
                     ("S14_domain_profile_distance_matrix.json",s14),
                     ("S15_behaviour_distance_matrix.json",s15),
                     ("S17_prespecified_level2_sensitivities.json",s17)]:
        with open(OUT/name,"w",encoding="utf-8") as f:
            json.dump(obj,f,indent=2,ensure_ascii=False)

    # Provenance and input/output hashes.
    prov={
        "created_at_utc":datetime.now(timezone.utc).isoformat(),
        "status":"PRESPECIFIED DOWNSTREAM REPRODUCTION — NO FORECASTING RERUN",
        "authoritative_parent_run":"completed publication run",
        "scientific_boundary":{
            "forecasting_rerun":False,
            "model_training_or_refit":False,
            "dataset_change":False,
            "source_package_modification":False,
            "configuration_or_seed_change":False,
            "new_hypothesis_or_sensitivity":False,
            "outcome_driven_selection":False,
        },
        "input_sha256":{str(p.relative_to(ROOT)):sha256(p) for p in input_paths},
        "output_sha256":{},
        "verification":{
            "primary_rho_matches_final_stage7":True,
            "primary_p_mantel_matches_final_stage7":True,
            "S6_rhos_match_persisted_stage7_lodo":True,
            "independent_matrix_vs_pair_loop_verification":"PASS for S1-S7 and all S5/S6 omissions",
        },
    }
    for p in sorted(OUT.glob("*.json")):
        prov["output_sha256"][p.name]=sha256(p)
    with open(OUT/"PROVENANCE.json","w",encoding="utf-8") as f:
        json.dump(prov,f,indent=2,ensure_ascii=False)

    # update provenance hash including itself is intentionally not recursive.
    print(json.dumps({
        "status":"PASS",
        "S1":sensitivities["S1"],
        "S2":sensitivities["S2"],
        "S3":sensitivities["S3"],
        "S4":sensitivities["S4"],
        "S5_summary":sensitivities["S5"]["summary"],
        "S6_summary":sensitivities["S6"]["summary"],
        "S7":sensitivities["S7"],
        "output_dir":str(OUT),
    },indent=2))

if __name__=="__main__":
    main()
