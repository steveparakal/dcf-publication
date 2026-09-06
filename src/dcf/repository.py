"""
repository.py

Artifact integrity, dataset-ID consistency, evidence-bundle loading,
prepared-series loading, and traceability verification for the DCF v1.2.0
pipeline.

v1.2.0 additions over v1.1.5:
  - ArtifactIntegrityError (closed classification set)
  - PreparedSeriesError
  - load_prepared_series(dataset_id, config=None)
  - load_and_verify_traceability(formal_output_path, expected_dataset_ids,
                                  config=None)

Removed in v1.2.0 (do not reinstate):
  - load_gate_summary()    # removed; sole loader is load_and_verify_traceability

MissingGateEvidenceError belongs in evidence_validation.py, not here.
"""



from __future__ import annotations



import hashlib

import json

from dataclasses import dataclass

from pathlib import Path

from typing import Optional



import numpy as np

import pandas as pd



from dcf.config import get_config

from dcf.evaluation_layer import load_evaluation_results

from dcf.logging_utils import get_error_logger, get_execution_logger



PROJECT_ROOT = Path(__file__).resolve().parents[2]

from dcf.pub_paths import sub as _sub

def _PREPARED_DATA_ROOT(): return _sub("01_prepared_data")

def _FORECASTS_ROOT(): return _sub("04_forecasts")  

def _DOMAIN_PROFILE_ROOT(): return _sub("03_domain_profiles")  

def _ANALYSIS_ROOT(): return _sub("05_analysis")













class ArtifactIntegrityError(Exception):

    """
    Raised when a DCF traceability/formal artifact fails integrity verification.

    failure_classification must be one of the closed set:
      "traceability_artifact_missing"
      "traceability_artifact_malformed"
      "filename_mismatch"
      "checksum_mismatch"
      "dataset_set_mismatch"
      "dataset_order_mismatch"
      "duplicate_dataset_ids"
      "gate_summary_malformed"
    """

    _VALID_CLASSIFICATIONS = frozenset({

        "traceability_artifact_missing",

        "traceability_artifact_malformed",

        "filename_mismatch",

        "checksum_mismatch",

        "dataset_set_mismatch",

        "dataset_order_mismatch",

        "duplicate_dataset_ids",

        "gate_summary_malformed",

    })



    def __init__(self, failure_classification: str, detail: str = ""):

        if failure_classification not in self._VALID_CLASSIFICATIONS:

            raise ValueError(

                f"ArtifactIntegrityError: unknown classification "

                f"'{failure_classification}'. Must be one of "

                f"{sorted(self._VALID_CLASSIFICATIONS)}"

            )

        self.failure_classification = failure_classification

        self.detail = detail

        super().__init__(f"{failure_classification}: {detail}")





class PreparedSeriesError(Exception):

    """Raised when load_prepared_series() cannot return a valid prepared series."""













class ConsistencyVerificationError(Exception):

    """Raised when dataset-ID consistency verification fails critically."""





@dataclass

class ConsistencyReport:

    successfully_matched: list

    domain_profile_only: list

    evaluation_only: list

    total_domain_profile: int

    total_evaluation: int

    report_path: Optional[str] = None





@dataclass

class DatasetEvidenceBundle:

    dataset_id: str

    domain_profile: dict

    evaluation: dict













def _list_domain_profile_dataset_ids():

    dp_root = _DOMAIN_PROFILE_ROOT()

    if not dp_root.exists():

        return []

    return sorted(p.name for p in dp_root.iterdir() if p.is_dir())





def _list_evaluation_dataset_ids():

    ev_root = _FORECASTS_ROOT()

    if not ev_root.exists():

        return []

    return sorted(p.name for p in ev_root.iterdir() if p.is_dir())





def _load_domain_profile(dataset_id: str) -> dict:

    path = _DOMAIN_PROFILE_ROOT() / dataset_id / f"{dataset_id}.domain_profile.json"

    with open(path) as f:

        return json.load(f)





def _sha256_of_file(path: Path) -> str:

    h = hashlib.sha256()

    with open(path, "rb") as f:

        for chunk in iter(lambda: f.read(65536), b""):

            h.update(chunk)

    return h.hexdigest()













def verify_dataset_id_consistency(dataset_ids: Optional[list] = None) -> ConsistencyReport:

    exec_log = get_execution_logger()

    exec_log.info("[Stage 6] Repository — verify_dataset_id_consistency()")



    dp_ids  = set(_list_domain_profile_dataset_ids())

    ev_ids  = set(_list_evaluation_dataset_ids())



    if dataset_ids is not None:

        dp_ids = dp_ids & set(dataset_ids)

        ev_ids = ev_ids & set(dataset_ids)



    matched   = sorted(dp_ids & ev_ids)

    dp_only   = sorted(dp_ids - ev_ids)

    ev_only   = sorted(ev_ids - dp_ids)



    report = ConsistencyReport(

        successfully_matched=matched,

        domain_profile_only=dp_only,

        evaluation_only=ev_only,

        total_domain_profile=len(dp_ids),

        total_evaluation=len(ev_ids),

    )

    _write_consistency_report(report)

    return report





def _write_consistency_report(report: ConsistencyReport):

    _ANALYSIS_ROOT().mkdir(parents=True, exist_ok=True)

    path = _ANALYSIS_ROOT() / "consistency_verification_report.json"

    with open(path, "w") as f:

        json.dump({

            "successfully_matched": report.successfully_matched,

            "domain_profile_only":  report.domain_profile_only,

            "evaluation_only":      report.evaluation_only,

            "total_domain_profile": report.total_domain_profile,

            "total_evaluation":     report.total_evaluation,

        }, f, indent=2)

    report.report_path = str(path)





def load_evidence_bundles(report: Optional[ConsistencyReport] = None) -> dict:

    """
    Load DatasetEvidenceBundles for every jointly available dataset.
    Raises ConsistencyVerificationError if no datasets are jointly available.
    """

    if report is None:

        report = verify_dataset_id_consistency()



    if not report.successfully_matched:

        raise ConsistencyVerificationError(

            "No datasets passed consistency verification across the Domain "

            "Profile and Evaluation repositories. Relationship analysis "

            "cannot proceed. See the consistency report for detail: "

            f"{report.to_dict() if hasattr(report,'to_dict') else vars(report)}"

        )



    bundles = {}

    for dataset_id in report.successfully_matched:

        profile    = _load_domain_profile(dataset_id)

        evaluation = load_evaluation_results(dataset_id)

        bundles[dataset_id] = DatasetEvidenceBundle(

            dataset_id=dataset_id, domain_profile=profile, evaluation=evaluation,

        )



    return bundles













def load_prepared_series(dataset_id: str, config=None) -> pd.Series:

    """
    Load and validate the Stage-1 prepared series for dataset_id.

    Validation steps:
      1. Reject path traversal: dataset_id must not contain '..' or '/'.
      2. Locate preparation report JSON; raise PreparedSeriesError if absent.
      3. Verify report["dataset_id"] == dataset_id.
      4. Read prepared CSV; raise PreparedSeriesError if absent.
      5. Verify "VALUE" column present.
      6. Verify len(series) == report["n_observations"].
      7. Reject zero-row series (empty).
      8. Check for Inf values (non-NaN non-finite); raise on any Inf.
      9. Reject all-NaN series.

    Returns pd.Series with DatetimeIndex and name "VALUE".
    All-zero finite series are accepted; epsilon_i = 0.0 in that case.
    """

    error_log = get_error_logger()



    

    if ".." in dataset_id or "/" in dataset_id or "\\" in dataset_id:

        raise PreparedSeriesError(

            f"path traversal rejected: dataset_id '{dataset_id}' contains unsafe characters"

        )



    base = _PREPARED_DATA_ROOT() / dataset_id

    report_path = base / f"{dataset_id}.preparation_report.json"



    

    if not report_path.exists():

        raise PreparedSeriesError(

            f"preparation report not found for '{dataset_id}' at {report_path}"

        )



    with open(report_path) as f:

        report = json.load(f)



    

    if report.get("dataset_id") != dataset_id:

        raise PreparedSeriesError(

            f"dataset_id mismatch: report says '{report.get('dataset_id')}', "

            f"requested '{dataset_id}'"

        )



    n_observations = report.get("n_observations")



    

    csv_path = base / f"{dataset_id}.prepared.csv"

    if not csv_path.exists():

        raise PreparedSeriesError(

            f"prepared CSV not found for '{dataset_id}' at {csv_path}"

        )



    try:

        df = pd.read_csv(csv_path, index_col=0, parse_dates=True)

    except Exception as exc:

        raise PreparedSeriesError(

            f"could not read prepared CSV for '{dataset_id}': {exc}"

        ) from exc



    

    if "VALUE" not in df.columns:

        raise PreparedSeriesError(

            f"prepared CSV for '{dataset_id}' has no 'VALUE' column; "

            f"columns found: {list(df.columns)}"

        )



    series = df["VALUE"]



    

    if n_observations is not None and len(series) != n_observations:

        raise PreparedSeriesError(

            f"observation count mismatch for '{dataset_id}': "

            f"report says {n_observations}, CSV has {len(series)}"

        )



    

    if len(series) == 0:

        raise PreparedSeriesError(

            f"prepared series is empty for '{dataset_id}'"

        )



    

    finite_values = series.dropna()

    if len(finite_values) > 0 and np.any(np.isinf(finite_values.values)):

        raise PreparedSeriesError(

            f"prepared series contains Inf values for '{dataset_id}'"

        )



    

    if finite_values.empty:

        raise PreparedSeriesError(

            f"prepared series has no finite values after dropping NaN for '{dataset_id}'"

        )



    series.name = "VALUE"

    return series













def load_and_verify_traceability(

    formal_output_path: Path,

    expected_dataset_ids: list,

    config=None,

) -> dict:

    """
    Load and integrity-verify the Stage 7 traceability artifact
    (forecasting_behaviour_traceability.json), checking:
      - artifact file exists;
      - checksum of the formal output matches stored SHA-256;
      - formal output filename matches;
      - dataset_ids list in artifact matches expected_dataset_ids (set and order);
      - no duplicate dataset_ids in artifact.

    Returns the gate_summary dict (from traceability["gate_summary"]).
    Raises ArtifactIntegrityError on any verification failure.
    """

    formal_output_path = Path(formal_output_path)

    traceability_path = formal_output_path.parent / "forecasting_behaviour_traceability.json"



    

    if not traceability_path.exists():

        raise ArtifactIntegrityError(

            "traceability_artifact_missing",

            f"no traceability artifact at {traceability_path}",

        )



    try:

        with open(traceability_path) as f:

            traceability = json.load(f)

    except Exception as exc:

        raise ArtifactIntegrityError(

            "traceability_artifact_malformed",

            f"could not parse traceability artifact: {exc}",

        ) from exc



    

    linked_outputs = traceability.get("formal_outputs_linked", [])

    if not isinstance(linked_outputs, list) or len(linked_outputs) == 0:

        raise ArtifactIntegrityError(

            "traceability_artifact_malformed",

            "traceability artifact has no 'formal_outputs_linked' list",

        )



    linked = linked_outputs[0]

    stored_filename = linked.get("filename", "")

    if stored_filename != formal_output_path.name:

        raise ArtifactIntegrityError(

            "filename_mismatch",

            f"traceability says '{stored_filename}', actual file is '{formal_output_path.name}'",

        )



    

    if not formal_output_path.exists():

        raise ArtifactIntegrityError(

            "traceability_artifact_missing",

            f"formal output file not found: {formal_output_path}",

        )

    actual_sha256 = _sha256_of_file(formal_output_path)

    stored_sha256 = linked.get("sha256", "")

    if actual_sha256 != stored_sha256:

        raise ArtifactIntegrityError(

            "checksum_mismatch",

            f"formal output SHA-256 mismatch: stored={stored_sha256}, actual={actual_sha256}",

        )



    

    artifact_ids = traceability.get("dataset_ids", [])

    if len(artifact_ids) != len(set(artifact_ids)):

        raise ArtifactIntegrityError(

            "duplicate_dataset_ids",

            f"traceability artifact contains duplicate dataset_ids: {artifact_ids}",

        )



    

    if set(artifact_ids) != set(expected_dataset_ids):

        raise ArtifactIntegrityError(

            "dataset_set_mismatch",

            f"artifact dataset_ids {sorted(artifact_ids)} != expected {sorted(expected_dataset_ids)}",

        )



    

    if artifact_ids != list(expected_dataset_ids):

        raise ArtifactIntegrityError(

            "dataset_order_mismatch",

            f"artifact dataset_ids order {artifact_ids} != expected {list(expected_dataset_ids)}",

        )



    

    gate_summary = traceability.get("gate_summary")

    if gate_summary is None:

        raise ArtifactIntegrityError(

            "gate_summary_malformed",

            "traceability artifact has no 'gate_summary' field",

        )



    return gate_summary





__all__ = [

    "ArtifactIntegrityError",

    "PreparedSeriesError",

    "ConsistencyVerificationError",

    "ConsistencyReport",

    "DatasetEvidenceBundle",

    "verify_dataset_id_consistency",

    "load_evidence_bundles",

    "load_prepared_series",

    "load_and_verify_traceability",

]

