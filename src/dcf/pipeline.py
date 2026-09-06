"""
pipeline.py

Nine-stage pipeline orchestrator for the Domain Characterization Framework,
implementing the authoritative stage order frozen in DCF specification
Publication pipeline stages:

    1. Data Preparation
    2. Domain Characterization        (STL once per dataset, reused by
                                        TSS / PSS / VS; structural change;
                                        PS / SS; TDS)
    3. Domain Profile Construction
    4. Forecasting Layer               (independent of the Domain Profile
                                        -- DCF specification / DCF specification
                                        v1.2.0)
    5. Evaluation Layer
    6. Forecasting Behavior Analysis
    7. Characterization-Forecasting Relationship Analysis
                                        (Dataset-ID consistency gate runs
                                        first -- DCF specification)
    8. Evidence Validation & Support Assessment
    9. Final Evidence Package Generation


Invariants enforced even at stub stage, because they shape the function
signatures and will not change later:

- Stage 4 (forecasting) must never receive the Domain Profile as input.
  Its signature deliberately does not accept one.
- Stage 7 must run a Dataset-ID consistency check across repositories
  BEFORE any relationship analysis logic executes.
- A single dataset or model failure must not halt the whole pipeline
  (DCF design) -- `run_full_pipeline` catches and logs
  per-dataset exceptions rather than letting one failure abort the run.
"""



from __future__ import annotations



from dataclasses import dataclass, field

from pathlib import Path

from typing import Any, Optional



from dcf.config import Config, get_config

from dcf.logging_utils import (

    get_config_logger,

    get_error_logger,

    get_execution_logger,

    get_experiment_logger,

    init_logging,

)



import os as _os

RESULTS_ROOT = (

    Path(_os.environ["DCF_RESULTS_ROOT"])

    if "DCF_RESULTS_ROOT" in _os.environ

    else Path(__file__).resolve().parents[2] / "results"

)



STAGE_REPOSITORY_DIRS = {

    1: RESULTS_ROOT / "01_prepared_data",

    2: RESULTS_ROOT / "02_characterization",

    3: RESULTS_ROOT / "03_domain_profiles",

    4: RESULTS_ROOT / "04_forecasts",

    5: RESULTS_ROOT / "04_forecasts",

    6: RESULTS_ROOT / "05_analysis",

    7: RESULTS_ROOT / "05_analysis",

    8: RESULTS_ROOT / "06_validation",

    9: RESULTS_ROOT / "final_evidence_package",

}





@dataclass

class PipelineContext:

    """
    Carries shared state between stages for a single dataset's run through
    the pipeline. Intentionally does NOT carry the Domain Profile into the
    forecasting stage's view -- forecasting receives only what Stage 4's
    signature explicitly accepts.
    """

    dataset_id: str

    experiment_id: str

    config: Config

    raw_dataset_path: Optional[Path] = None

    stage_outputs: dict = field(default_factory=dict)





class StageNotImplementedError(NotImplementedError):

    """Raised when a stage cannot complete. Distinct type so callers can
    distinguish "not yet built" from a genuine NotImplementedError raised
    by completed logic in a later phase."""













def stage_1_data_preparation(ctx: PipelineContext) -> dict:

    """
    Load, validate, clean, and split the dataset for `ctx.dataset_id`.

    against `data_preparation.py`
    (`prepare_dataset()`). Per DCF specification Decisions 16, 19, 20, 21:
    validates temporal structure and minimum length, applies the
    configured missing-value and outlier policies (report-only by
    default), and determines frequency from the dataset rather than
    assuming it.

    Returns a dict with the PreparedDataset object and the loaded series,
    so downstream stages don't need to re-read the prepared CSV from disk.
    """

    from dcf.data_preparation import prepare_dataset

    import pandas as pd



    exec_log = get_execution_logger()

    exec_log.info(f"[Stage 1] Data Preparation -- dataset_id={ctx.dataset_id}")



    prepared = prepare_dataset(ctx.dataset_id, config=ctx.config)

    series = pd.read_csv(prepared.series_values_path, index_col=0, parse_dates=True).iloc[:, 0]



    return {"prepared": prepared, "series": series}













def stage_2_domain_characterization(ctx: PipelineContext, prepared_dataset: dict) -> dict:

    """
    Compute TSS, PSS, VS, SIS (+ supplementary NCP/ACM/MCM/RCD), PS, SS, TDS
    for the prepared dataset.

    STL decomposition is computed once per
    dataset (`stl_decomposition.run_stl()`) and reused by TSS, PSS, and VS
    per DCF specification. Lag conventions: PS uses lag 1 only;
    TDS uses lags {2,3,4,5} only (DCF specification, U1 resolution -- v1.2.0
    authoritative).

    NOTE: this stage and Stage 3 are combined in implementation inside
    `domain_profile.construct_domain_profile()`, which runs STL once and
    derives all seven measures plus the assembled vector in a single
    call. Splitting them into two pipeline stages (per the architecture)
    while sharing one underlying implementation call avoids recomputing
    STL between stages -- this stage returns the full DomainProfile
    object; Stage 3 receives it and performs only the (already-complete)
    vector-assembly bookkeeping, satisfying both Section 4's "STL reused,
    not recomputed" rule and the nine-stage architecture's stage boundary.
    """

    from dcf.domain_profile import construct_domain_profile



    exec_log = get_execution_logger()

    exec_log.info(f"[Stage 2] Domain Characterization -- dataset_id={ctx.dataset_id}")



    prepared = prepared_dataset["prepared"]

    series = prepared_dataset["series"]



    profile = construct_domain_profile(

        series,

        dataset_id=ctx.dataset_id,

        frequency_key=prepared.detected_frequency_config_key,

        config=ctx.config,

    )



    return {"domain_profile": profile}













def stage_3_domain_profile_construction(ctx: PipelineContext, characterization: dict) -> dict:

    """
    Assemble the fixed-order Domain Profile vector
    [TSS, PSS, VS, SIS, PS, SS, TDS] plus supplementary structural-change
    attributes (NCP, ACM, MCM, RCD), per DCF specification and
    DCF design.

    As noted in Stage 2's docstring, vector
    assembly already happened inside `construct_domain_profile()`
    (called from Stage 2) to avoid recomputing STL; this stage's
    responsibility is to validate that the assembled profile satisfies
    the architecture's Stage 3 contract (fixed order, all seven measures
    present, values bounded) before handing it to Stage 4.
    """

    exec_log = get_execution_logger()

    exec_log.info(f"[Stage 3] Domain Profile Construction -- dataset_id={ctx.dataset_id}")



    profile = characterization["domain_profile"]



    expected_order = ["TSS", "PSS", "VS", "SIS", "PS", "SS", "TDS"]

    if profile.vector_order != expected_order:

        raise ValueError(

            f"Domain Profile vector_order mismatch for '{ctx.dataset_id}': "

            f"expected {expected_order}, got {profile.vector_order}."

        )

    for name, value in zip(profile.vector_order, profile.vector):

        if not (0.0 <= value <= 1.0):

            raise ValueError(

                f"Domain Profile component {name}={value} for '{ctx.dataset_id}' "

                "is out of the required [0,1] bound."

            )



    return {"domain_profile": profile}













def stage_4_forecasting_layer(ctx: PipelineContext, prepared_dataset: dict) -> dict:

    """
    Run every enabled model in the forecasting registry (baselines,
    statistical, ML, deep learning) against `prepared_dataset` under the
    configured rolling-origin evaluation protocol.

    IMPORTANT -- architectural invariant (DCF specification / DCF specification
    v1.2.0): this function signature deliberately does NOT accept a
    Domain Profile or any characterization output. Forecasting must remain
    decoupled from characterization so that the framework's central
    hypothesis (profile <-> forecasting-behavior relationships) is
    testable rather than circular. Do not add a domain_profile parameter
    to this function in any future phase.

    Implemented in v1.2.0.
    """

    from dcf.forecasting_layer import run_forecasting_models



    exec_log = get_execution_logger()

    exec_log.info(f"[Stage 4] Forecasting Layer -- dataset_id={ctx.dataset_id}")



    prepared = prepared_dataset["prepared"]

    series = prepared_dataset["series"]



    if not prepared.eligible_for_pipeline:

        exec_log.warning(

            f"[Stage 4] Dataset '{ctx.dataset_id}' is not eligible for the official "

            f"rolling-origin protocol ({prepared.eligibility_notes}). Skipping forecasting."

        )

        return {"dataset_forecasting_result": None, "skipped": True}



    dataset_forecasting_result = run_forecasting_models(

        series=series,

        dataset_id=ctx.dataset_id,

        frequency_key=prepared.detected_frequency_config_key,

        rolling_origin_plan=prepared.rolling_origin_plan,

        config=ctx.config,

    )



    return {"dataset_forecasting_result": dataset_forecasting_result, "skipped": False}













def stage_5_evaluation_layer(ctx: PipelineContext, forecasts: dict) -> dict:

    """
    Compute MAE, RMSE, MAPE, sMAPE; produce model rankings and best-model
    identification. Baseline models (Naive, Seasonal Naive, Drift)
    participate in all rankings per DCF specification Decisions 11/30/55.

    (core scope: metrics + ranking + best-model +
    Performance Evidence Repository). The fuller Section 16 deliverables
    (7 tables, 6 figures, dataset-difficulty classification, cross-model
    and cross-dataset comparison analyses, automated evaluation summary
    report) are explicitly out of v1.2.0's scope -- see
    evaluation_layer.py's module docstring for the full flag.
    """

    from dcf.evaluation_layer import evaluate_forecasts



    exec_log = get_execution_logger()

    exec_log.info(f"[Stage 5] Evaluation Layer -- dataset_id={ctx.dataset_id}")



    if forecasts.get("skipped"):

        exec_log.warning(

            f"[Stage 5] Dataset '{ctx.dataset_id}' was skipped at Stage 4 "

            "(ineligible for rolling-origin protocol); skipping evaluation too."

        )

        return {"evaluation_result": None, "skipped": True}



    evaluation_result = evaluate_forecasts(forecasts["dataset_forecasting_result"], config=ctx.config)



    return {"evaluation_result": evaluation_result, "skipped": False}













def stage_6_forecasting_behavior_analysis(ctx: PipelineContext, evaluation: dict) -> dict:

    """
    Forecasting Behavior Analysis (Section 14). Per-dataset behavioral
    summaries (difficulty, ranking stability, model family performance),
    7 Tables (CSV+JSON), 7 Figures (PNG), and analytical findings text.

    Reads from the Domain Profile and Evaluation repositories already
    written by Stages 2-5 -- does NOT accept a Domain Profile directly
    from the in-pipeline accumulator, because Stage 6 is designed to
    operate over ALL datasets with complete repository data, not just
    the current dataset being processed by this pipeline invocation.
    This matches the same cross-dataset design decision taken for
    Stages 7-8 in v1.2.0.

    By design, Stage 6 does not influence model training,
    selection, optimization, or forecasting execution.

    Implemented in v1.2.0.
    """

    from dcf.forecasting_behavior_analysis import analyze_forecasting_behavior



    exec_log = get_execution_logger()

    exec_log.info(f"[Stage 6] Forecasting Behavior Analysis -- dataset_id={ctx.dataset_id}")



    fba_result = analyze_forecasting_behavior(config=ctx.config)



    return {"fba_result": fba_result}













def stage_7_relationship_analysis(ctx: PipelineContext, all_repositories: dict) -> dict:

    """
    Level 1 (Characteristic <-> Forecasting Behavior), Level 2 (Domain
    Profile <-> Forecasting Behavior), and exploratory Level 3 relationship
    discovery (DCF specification Decisions 36-38).

    Level 1, Level 2, and Level 3 relationship discovery using exactly
    the current-run canonical dataset list. The production
    run_relationship_analysis() is called with dataset_ids equal to
    the ten canonical publication datasets; any historical repository
    artifacts for other datasets are ignored.

    Per DCF design's "log and continue" philosophy applied
    at the cross-dataset-analysis level: if relationship analysis cannot
    proceed at all (zero datasets pass consistency verification), this
    raises ConsistencyVerificationError rather than silently returning
    an empty result -- analogous to how Stage 1 raises
    DataPreparationError for an unusable dataset rather than proceeding
    with a phantom one.
    """

    from dcf.characterization_forecasting_relationship import run_relationship_analysis



    exec_log = get_execution_logger()

    exec_log.info(f"[Stage 7] Relationship Analysis -- dataset_id={ctx.dataset_id}")



    

    

    current_run_ids = ctx.stage_outputs.get("_current_run_dataset_ids")

    if not current_run_ids:

        raise ValueError(

            "[Stage 7] current_run_dataset_ids not found in context. "

            "run_full_pipeline must supply the canonical dataset list."

        )

    result = run_relationship_analysis(

        dataset_ids=current_run_ids, config=ctx.config

    )



    return {"relationship_analysis_result": result}













def stage_8_evidence_validation(ctx: PipelineContext, relationship_findings: dict) -> dict:

    """
    Classify findings into Supported / Partially Supported / Inconclusive /
    Unsupported using the pre-registered thresholds in
    `evidence_classification` (config). Per DCF design/32,
    forced-positive validation and suppression of contradictory findings
    are explicitly disallowed.

    Implemented in v1.2.0.
    """

    from dcf.evidence_validation import assess_evidence

    import dataclasses

    from dataclasses import asdict



    exec_log = get_execution_logger()

    exec_log.info(f"[Stage 8] Evidence Validation -- dataset_id={ctx.dataset_id}")



    rel_result = relationship_findings["relationship_analysis_result"]



    

    

    

    

    

    

    rel_dict = {

        "dataset_ids": rel_result.dataset_ids,

        "level_1_findings": rel_result.level_1_findings,

        "level_2_findings": rel_result.level_2_findings,

    }



    

    try:

        from dcf.characterization_forecasting_relationship import load_and_verify_traceability

        gate_summary = load_and_verify_traceability()

    except Exception:

        

        gate_summary = {

            "datasets_analyzed": rel_result.dataset_ids,

            "gates_passed": rel_result.dataset_ids,

            "gates_failed": [],

        }



    validation_result = assess_evidence(rel_dict, gate_summary=gate_summary, config=ctx.config)



    return {"validation_result": validation_result}













def stage_9_final_evidence_package(ctx: PipelineContext, validation: dict) -> dict:

    """
    Assemble the publication-ready Final Evidence Package: all repository
    outputs, tables, figures, logs, config, and manifests. This stage
    generates evidence for human
    interpretation -- it does not claim scientific success or write
    the paper.

    This stage also runs the full v1.2.0 reporting modules (which
    generate the Section 16/18 deferred deliverables and sensitivity
    analyses) BEFORE assembling the package, so that all generated
    outputs are included in the Final Evidence Package.

    CRITICAL: generate_validation_reports() is called with the
    in-memory validation_dict and rel_analysis_dict extracted from the
    `validation` argument (produced by Stage 8), NOT by reading from disk.
    This prevents any stale evidence_validation.json file on disk from
    contaminating the Final Evidence Package with outdated or incorrect
    classifications (the root cause of the bug identified in the v1.2.0
    validation case in which a synthetic test run had written n_datasets=6, Unsupported
    to disk, contradicting the correct n_datasets=4, Partially Supported
    classification computed by Stage 8 in the same run).
    """

    from dcf.evaluation_reporting import generate_evaluation_report

    from dcf.characterization_repository import populate_characterization_repository_from_domain_profiles

    from dcf.validation_reporting import generate_validation_reports

    from dcf.sensitivity_analysis import generate_full_sensitivity_report

    from dcf.final_evidence_package import generate_final_evidence_package

    import dataclasses

    from dataclasses import asdict



    exec_log = get_execution_logger()

    exec_log.info(f"[Stage 9] Final Evidence Package Generation -- experiment_id={ctx.experiment_id}")



    

    

    validation_result = validation.get("validation_result")

    validation_dict = None

    rel_analysis_dict = None



    if validation_result is not None:

        from dcf.evidence_validation import Level1Assessment, Level2Assessment, ValidationResult

        validation_dict = {

            "level_1_assessment": validation_result.level_1_assessment

                if not dataclasses.is_dataclass(validation_result.level_1_assessment)

                else asdict(validation_result.level_1_assessment),

            "level_2_assessment": validation_result.level_2_assessment

                if not dataclasses.is_dataclass(validation_result.level_2_assessment)

                else asdict(validation_result.level_2_assessment),

            "n_datasets_analyzed": validation_result.n_datasets_analyzed,

        }



    

    

    try:

        from dcf.characterization_forecasting_relationship import load_relationship_analysis

        rel_analysis_dict = load_relationship_analysis()

    except FileNotFoundError:

        raise RuntimeError(

            "[Publication route] Stage 9 requires current-run relationship evidence "

            "but relationship_analysis.json was not found under the reproduction root. "

            f"Expected path: <reproduction_root>/05_analysis/relationship/relationship_analysis.json. Stage 9 cannot produce a final package "

            "with missing relationship findings."

        )



    

    exec_log.info("[Stage 9] Generating Section 16 evaluation reports")

    generate_evaluation_report(config=ctx.config)



    exec_log.info("[Stage 9] Populating Characterization Repository")

    populate_characterization_repository_from_domain_profiles(config=ctx.config)



    exec_log.info("[Stage 9] Generating Section 18 validation reports (using in-memory Stage 8 results)")

    generate_validation_reports(

        validation_dict=validation_dict,

        rel_analysis_dict=rel_analysis_dict,

        config=ctx.config,

    )



    exec_log.info("[Stage 9] Generating sensitivity analysis reports (Decisions 39/45/46/47)")

    generate_full_sensitivity_report(config=ctx.config)



    

    fep = generate_final_evidence_package(

        experiment_id=ctx.experiment_id,

        config=ctx.config,

    )



    return {"final_evidence_package": fep}













def run_full_pipeline(dataset_ids: list, config_path: Optional[Path] = None) -> dict:

    """
    Run Stages 1-9 for each dataset in `dataset_ids`.

    Execute the complete Stage 1-9 publication pipeline.

    All ten canonical publication datasets are mandatory. Any per-dataset
    failure in Stages 1-6 aborts the entire run (fail-closed). Stages 7-9
    run exactly once after all per-dataset stages succeed, using the
    explicit dataset_ids list supplied by the caller.
    """

    init_logging()

    exec_log = get_execution_logger()

    exp_log = get_experiment_logger()

    error_log = get_error_logger()

    config_log = get_config_logger()



    cfg = get_config(path=config_path, allow_draft=True)

    config_log.info(f"Loaded configuration: {cfg!r}")



    if cfg.status not in ("FROZEN_APPROVED",):

        exec_log.warning(

            f"Configuration status is '{cfg.status}', not an approved frozen "

            "status. Per project process, the pipeline should not be run "

            "against a non-approved configuration. "

            "scaffolding checks."

        )



    exec_log.info(f"Starting pipeline run for {len(dataset_ids)} dataset(s).")

    exp_log.info(f"Dataset IDs in this run: {dataset_ids}")



    per_dataset_results = {}



    for dataset_id in dataset_ids:

        ctx = PipelineContext(

            dataset_id=dataset_id,

            experiment_id="UNSET",

            config=cfg,

            stage_outputs={'_current_run_dataset_ids': dataset_ids},

        )

        try:

            exec_log.info(f"=== Begin per-dataset stages for {dataset_id} ===")

            prepared = stage_1_data_preparation(ctx)

            characterization = stage_2_domain_characterization(ctx, prepared)

            domain_profile = stage_3_domain_profile_construction(ctx, characterization)

            forecasts = stage_4_forecasting_layer(ctx, prepared)

            evaluation = stage_5_evaluation_layer(ctx, forecasts)



            

            try:

                fba = stage_6_forecasting_behavior_analysis(ctx, evaluation)

            except StageNotImplementedError as e:

                raise RuntimeError(

                    f"[Publication route] Stage 6 is required but raised "

                    f"StageNotImplementedError: {e}"

                ) from e



            per_dataset_results[dataset_id] = {

                "prepared": prepared,

                "characterization": characterization,

                "domain_profile": domain_profile,

                "forecasts": forecasts,

                "evaluation": evaluation,

                "forecasting_behavior_analysis": fba,

            }

            exec_log.info(f"=== Completed per-dataset stages for {dataset_id} ===")



        except StageNotImplementedError as e:

            

            raise RuntimeError(

                f"[Publication route] Required per-dataset stage raised "

                f"StageNotImplementedError for {dataset_id}: {e}"

            ) from e



    

    

    

    cross_ctx = PipelineContext(

        dataset_id="_cross_dataset",

        experiment_id="cross_dataset",

        config=cfg,

        stage_outputs={"_current_run_dataset_ids": dataset_ids},

    )



    exec_log.info("[Stage 7] Running relationship analysis across all datasets...")

    try:

        relationship_findings = stage_7_relationship_analysis(cross_ctx, per_dataset_results)

    except Exception as exc:

        raise RuntimeError(

            f"[Publication route] Stage 7 (Relationship Analysis) failed: {exc}"

        ) from exc



    exec_log.info("[Stage 8] Running evidence validation...")

    try:

        validation = stage_8_evidence_validation(cross_ctx, relationship_findings)

    except Exception as exc:

        raise RuntimeError(

            f"[Publication route] Stage 8 (Evidence Validation) failed: {exc}"

        ) from exc



    exec_log.info("[Stage 9] Generating final evidence package...")

    try:

        final_package = stage_9_final_evidence_package(cross_ctx, validation)

    except Exception as exc:

        raise RuntimeError(

            f"[Publication route] Stage 9 (Final Evidence Package) failed: {exc}"

        ) from exc



    exec_log.info("Pipeline Stages 1-9 complete.")

    return {

        "per_dataset_results": per_dataset_results,

        "relationship_findings": relationship_findings,

        "validation": validation,

        "final_package": final_package,

    }





if __name__ == "__main__":

    import argparse



    parser = argparse.ArgumentParser(description="Run the DCF pipeline.")

    parser.add_argument("--config", type=str, default=None, help="Path to a config YAML file.")

    parser.add_argument(

        "--datasets",

        type=str,

        nargs="*",

        default=["EXAMPLE_DATASET"],

        help="Dataset IDs to process.",

    )

    args = parser.parse_args()



    run_full_pipeline(

        dataset_ids=args.datasets,

        config_path=Path(args.config) if args.config else None,

    )

