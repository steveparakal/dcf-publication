"""
pub_paths.py — Centralized publication-runtime path resolver.
Release: v1.2.0-rc20

All production modules that write pipeline output must use get_results_root()
rather than a module-level PROJECT_ROOT / "results" constant.

The resolution order is:
  1. DCF_RESULTS_ROOT environment variable (set by run_publication_pipeline.py)
  2. PROJECT_ROOT / "results" (default, used during development and testing)

Modules that previously used their own module-level constant should import
get_results_root() from here and call it at the start of each function that
needs to write output — not at module import time.
"""

import os

import pathlib



_PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]





def get_results_root() -> pathlib.Path:

    """Return the active reproduction output root.

    Returns DCF_RESULTS_ROOT if set, otherwise PROJECT_ROOT/results.
    Must be called at function time, not at module import time.
    """

    env = os.environ.get("DCF_RESULTS_ROOT")

    if env:

        return pathlib.Path(env)

    return _PROJECT_ROOT / "results"





def sub(path: str) -> pathlib.Path:

    """Return get_results_root() / path."""

    return get_results_root() / path









STAGE_01 = "01_prepared_data"

STAGE_02 = "02_characterization"

STAGE_03 = "03_domain_profiles"

STAGE_04 = "04_forecasts"

STAGE_05_FBA  = "05_analysis/fba"

STAGE_05_REL  = "05_analysis/relationship"

STAGE_06_VAL  = "06_validation"

STAGE_06_EVP  = "06_validation/evidence_package"

STAGE_06_SENS = "06_validation/sensitivity"

