"""
final_evidence_package.py

Stage 9 of the DCF pipeline: Final Evidence Package Generation,
per DCF specification

Assembles all repository outputs into one complete, traceable package
at results/final_evidence_package/ containing:

  - Characterization Repository outputs
  - Domain Profile Repository outputs
  - Forecast Results Repository outputs
  - Performance Evidence Repository outputs
  - Forecasting Behavior Repository outputs
  - Relationship Evidence Repository outputs
  - Evidence Validation Repository outputs
  - Final summary reports
  - Generated tables and figures
  - Experiment logs
  - Configuration summary (config version, framework version)

Each run receives a unique Experiment ID; all outputs are traceable
to their originating experiment via a manifest.

The pipeline generates evidence for human interpretation.
It does not write the paper, claim scientific success, or make
judgments about whether the framework is validated -- those are human
tasks performed AFTER reviewing the Final Evidence Package.

Under the No Forced Positive Validation principle, the package includes ALL
outputs including Inconclusive, Unsupported, and placeholder
outputs. Nothing is suppressed.
"""

from __future__ import annotations



import json

import platform

import shutil

from dataclasses import dataclass

from datetime import datetime, timezone

from pathlib import Path

from typing import Optional



import pandas as pd



from dcf.config import Config, get_config

from dcf.logging_utils import get_execution_logger, get_experiment_logger



PROJECT_ROOT = Path(__file__).resolve().parents[2]

from dcf.pub_paths import sub as _sub



def _FEP_ROOT(): return _sub("final_evidence_package")



def _REPOSITORY_DIRS():

    return {

        "characterization": _sub("02_characterization"),

        "domain_profiles":  _sub("03_domain_profiles"),

        "forecasts":        _sub("04_forecasts"),

        "analysis":         _sub("05_analysis"),

        "validation":       _sub("06_validation"),

    }







FILE_EXTENSIONS_TO_INCLUDE = {".json", ".csv", ".png", ".yaml", ".yml", ".md", ".log"}





@dataclass

class FinalEvidencePackage:

    experiment_id: str

    generated_at: str

    framework_version: str

    config_version: str

    python_version: str

    dataset_ids_found: list

    files_included: list

    missing_repositories: list

    summary_report_path: str





def _collect_repository_files(repo_name: str, repo_path: Path, dest: Path) -> list:

    """Recursively copy files from one repository into the FEP, return copied paths."""

    copied = []

    if not repo_path.exists():

        return copied

    repo_dest = dest / repo_name

    repo_dest.mkdir(parents=True, exist_ok=True)

    for src in sorted(repo_path.rglob("*")):

        if src.is_file() and src.suffix in FILE_EXTENSIONS_TO_INCLUDE:

            rel = src.relative_to(repo_path)

            dst = repo_dest / rel

            dst.parent.mkdir(parents=True, exist_ok=True)

            shutil.copy2(src, dst)

            copied.append(str(dst.relative_to(_FEP_ROOT())))

    return copied





def _collect_logs(dest: Path) -> list:

    """Copy experiment logs from logs/ directory."""

    logs_src = PROJECT_ROOT / "logs"

    copied = []

    if not logs_src.exists():

        return copied

    logs_dest = dest / "logs"

    logs_dest.mkdir(parents=True, exist_ok=True)

    for log_file in sorted(logs_src.glob("*.log")):

        dst = logs_dest / log_file.name

        shutil.copy2(log_file, dst)

        copied.append(str(dst.relative_to(_FEP_ROOT())))

    return copied





def _collect_config(dest: Path) -> list:

    """Copy frozen config file."""

    cfg_src = PROJECT_ROOT / "configs" / "version1_defaults.yaml"

    copied = []

    if cfg_src.exists():

        cfg_dest = dest / "config" / "version1_defaults.yaml"

        cfg_dest.parent.mkdir(parents=True, exist_ok=True)

        shutil.copy2(cfg_src, cfg_dest)

        copied.append(str(cfg_dest.relative_to(_FEP_ROOT())))

    return copied





def _discover_dataset_ids() -> list:

    """Return all dataset_ids that have at least a Domain Profile."""

    dp_root = _REPOSITORY_DIRS()["domain_profiles"]

    if not dp_root.exists():

        return []

    return sorted([p.name for p in dp_root.iterdir() if p.is_dir()])





def _write_summary_report(fep: FinalEvidencePackage, dest: Path) -> Path:

    """Write a human-readable summary report (JSON + text)."""

    report_path = dest / "final_evidence_summary.json"

    with open(report_path, "w") as f:

        json.dump({

            "experiment_id": fep.experiment_id,

            "generated_at": fep.generated_at,

            "framework_version": fep.framework_version,

            "config_version": fep.config_version,

            "python_version": fep.python_version,

            "dataset_ids_found": fep.dataset_ids_found,

            "total_files_included": len(fep.files_included),

            "missing_repositories": fep.missing_repositories,

            "files_included": fep.files_included,

        }, f, indent=2)



    txt_path = dest / "final_evidence_summary.txt"

    lines = [

        "=" * 70,

        "DCF FRAMEWORK -- FINAL EVIDENCE PACKAGE",

        "=" * 70,

        f"Experiment ID:     {fep.experiment_id}",

        f"Generated at:      {fep.generated_at}",

        f"Framework version: {fep.framework_version}",

        f"Config version:    {fep.config_version}",

        f"Python version:    {fep.python_version}",

        "",

        f"Datasets with Domain Profiles: {fep.dataset_ids_found}",

        f"Total files included: {len(fep.files_included)}",

        "",

    ]

    if fep.missing_repositories:

        lines += [

            "MISSING REPOSITORIES (outputs not yet generated):",

            *[f"  - {r}" for r in fep.missing_repositories],

            "",

        ]

    lines += [

        "IMPORTANT: This package contains evidence for human interpretation.",

        "The pipeline does not claim scientific success or failure.",

        "All findings including Inconclusive and Unsupported results are",

        "included under the No Forced Positive Validation principle.",

        "=" * 70,

    ]

    with open(txt_path, "w") as f:

        f.write("\n".join(lines) + "\n")



    return report_path





def generate_final_evidence_package(

    experiment_id: Optional[str] = None,

    config: Optional[Config] = None,

) -> FinalEvidencePackage:

    """
    Stage 9 entry point. Collects all repository outputs into
    results/final_evidence_package/, generating a manifest and
    summary report. This is the complete set of outputs
    needed for later human interpretation and paper preparation.
    """

    cfg = config or get_config(allow_draft=False)

    exec_log = get_execution_logger()

    exp_log = get_experiment_logger()



    timestamp = datetime.now(timezone.utc)

    if experiment_id is None:

        experiment_id = f"DCF-v1-{timestamp.strftime('%Y%m%d-%H%M%S')}"



    exec_log.info(f"[Stage 9] Final Evidence Package Generation -- experiment_id={experiment_id}")



    config_version = cfg.get("version", "1.0.0")

    framework_version = "1.0.0"

    python_version = platform.python_version()

    generated_at = timestamp.isoformat()



    

    dest = _FEP_ROOT() / experiment_id

    dest.mkdir(parents=True, exist_ok=True)



    all_files = []

    missing_repos = []



    

    for repo_name, repo_path in _REPOSITORY_DIRS().items():

        if repo_path.exists():

            copied = _collect_repository_files(repo_name, repo_path, dest)

            all_files.extend(copied)

            exec_log.info(f"[Stage 9] Collected {len(copied)} file(s) from {repo_name}")

        else:

            try:

                try:

                    missing_path = str(repo_path.relative_to(PROJECT_ROOT))

                except ValueError:

                    missing_path = str(repo_path)

            except ValueError:

                missing_path = str(repo_path)

            missing_repos.append(missing_path)

            exec_log.info(f"[Stage 9] Repository not yet available: {repo_name} ({repo_path})")



    

    all_files.extend(_collect_logs(dest))

    all_files.extend(_collect_config(dest))



    dataset_ids = _discover_dataset_ids()



    fep = FinalEvidencePackage(

        experiment_id=experiment_id,

        generated_at=generated_at,

        framework_version=framework_version,

        config_version=config_version,

        python_version=python_version,

        dataset_ids_found=dataset_ids,

        files_included=sorted(all_files),

        missing_repositories=missing_repos,

        summary_report_path=str(dest / "final_evidence_summary.json"),

    )



    _write_summary_report(fep, dest)



    

    manifest_path = _FEP_ROOT() / "latest_experiment_manifest.json"

    with open(manifest_path, "w") as f:

        json.dump({

            "latest_experiment_id": experiment_id,

            "generated_at": generated_at,

            "experiment_dir": str(dest) if not dest.is_relative_to(PROJECT_ROOT)

                else str(dest.relative_to(PROJECT_ROOT)),

        }, f, indent=2)



    exp_log.info(

        f"[Stage 9] Final Evidence Package complete: experiment_id={experiment_id}, "

        f"{len(all_files)} files, {len(dataset_ids)} dataset(s), "

        f"{len(missing_repos)} missing repositories."

    )



    return fep





def load_latest_manifest() -> dict:

    path = _FEP_ROOT() / "latest_experiment_manifest.json"

    if not path.exists():

        raise FileNotFoundError(

            f"No Final Evidence Package manifest found at {path}. "

            "Has generate_final_evidence_package() been run?"

        )

    with open(path) as f:

        return json.load(f)





__all__ = [

    "FinalEvidencePackage",

    "generate_final_evidence_package",

    "load_latest_manifest",

    "_FEP_ROOT()",

]

