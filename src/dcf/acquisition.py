"""
acquisition.py

Dataset acquisition module for the Domain Characterization Framework.

DESIGN PRINCIPLE (for reproducible dataset acquisition):
This module is written as normal, reproducible Python code intended to
run in a standard research environment with ordinary internet access.
When bytes are supplied externally rather than downloaded by this module,
the same preservation, hashing, collision checking, and provenance rules
still apply.

Every acquisition produces:
  1. The raw file, written byte-for-byte unchanged under `data/raw/`.
  2. A provenance metadata record (see `ProvenanceRecord`) capturing
     dataset name, official source URL, retrieval method, retrieval date,
     version/release info where available, a file hash, how the bytes were obtained, and any
     preprocessing performed before the file entered the pipeline (for
     raw acquisition, this is "none" by design -- see Raw Data
     Preservation rule below).

RAW DATA PRESERVATION:
Files written by this module under `data/raw/<dataset_id>/` are never
modified after being written. All cleaning, transformation, resampling,
and preparation happen elsewhere (`data_preparation.py`), reading from
`data/raw/` and writing to `data/working/` or directly into
`results/01_prepared_data/`. This module enforces that distinction by
making its raw-output paths the only thing it writes to, and by refusing
to overwrite an existing raw file with different content silently (see
`acquire_dataset`'s collision check below) -- a changed upstream file is
reported, not silently replaced.

RESTRICTED OR UNAVAILABLE SOURCES:
If retrieval fails, this module raises `AcquisitionBlockedError` with a
structured explanation rather than falling back to an alternative source.
Callers (the pipeline, or a human operator) are responsible for deciding
how to proceed; this module never substitutes datasets on its own.
"""



from __future__ import annotations



import hashlib

import json

from dataclasses import asdict, dataclass

from datetime import datetime, timezone

from pathlib import Path

from typing import Optional



import requests



from dcf.dataset_registry import DatasetSpec, get_dataset_spec

from dcf.logging_utils import get_error_logger, get_execution_logger, get_experiment_logger



PROJECT_ROOT = Path(__file__).resolve().parents[2]

RAW_DATA_ROOT = PROJECT_ROOT / "data" / "raw"





class AcquisitionBlockedError(Exception):

    """
    Raised when a dataset cannot be obtained from its official/accepted
    public source. Carries enough structured information for a human
    operator to decide how to proceed. This module never catches this
    exception internally to substitute an alternative source; that decision
    is never made silently.
    """



    def __init__(self, dataset_id: str, reason: str, attempted_url: str, options: list):

        self.dataset_id = dataset_id

        self.reason = reason

        self.attempted_url = attempted_url

        self.options = options

        message = (

            f"Acquisition blocked for dataset '{dataset_id}'.\n"

            f"  Attempted URL: {attempted_url}\n"

            f"  Reason: {reason}\n"

            f"  Proposed options:\n" + "\n".join(f"    - {opt}" for opt in options)

        )

        super().__init__(message)





@dataclass

class ProvenanceRecord:

    dataset_id: str

    display_name: str

    official_source_name: str

    official_source_url: str

    retrieval_url: str

    retrieval_method: str

    retrieval_date_utc: str

    dataset_version_or_release: Optional[str]

    file_hash_sha256: Optional[str]

    file_path: str

    file_size_bytes: Optional[int]

    obtained_via: str

    preprocessing_before_pipeline_entry: str

    license_or_terms_url: Optional[str]

    citation: Optional[str]

    notes: str



    def to_dict(self) -> dict:

        return asdict(self)





def _raw_dataset_dir(dataset_id: str) -> Path:

    d = RAW_DATA_ROOT / dataset_id

    d.mkdir(parents=True, exist_ok=True)

    return d





def _sha256_of_file(path: Path) -> str:

    h = hashlib.sha256()

    with open(path, "rb") as f:

        for chunk in iter(lambda: f.read(8192), b""):

            h.update(chunk)

    return h.hexdigest()





def _provenance_path(dataset_id: str) -> Path:

    return _raw_dataset_dir(dataset_id) / "provenance.json"





def _raw_file_path(dataset_id: str, retrieval_format: str) -> Path:

    ext_map = {

        "csv": "csv",

        "zip_containing_csv": "zip",

        "gz_containing_csv": "txt.gz",

        "txt": "txt",

        "xlsx": "xlsx",

    }

    ext = ext_map.get(retrieval_format, "bin")

    return _raw_dataset_dir(dataset_id) / f"{dataset_id}.raw.{ext}"





def acquire_dataset(

    dataset_id: str,

    raw_bytes: Optional[bytes] = None,

    obtained_via: str = "normal_acquisition_code",

    retrieval_method_description: Optional[str] = None,

) -> ProvenanceRecord:

    """
    Acquire a dataset and record its provenance.

    Normal usage (standard research environment, ordinary internet
    access): call with `raw_bytes=None`. This function performs an HTTP
    GET against the dataset's registered `retrieval_url` using `requests`,
    exactly as it would in any other Python environment.

    Externally supplied bytes: a caller that has already obtained the
    source bytes through an authorized retrieval mechanism may pass them
    via `raw_bytes` and record the method through `obtained_via` and
    `retrieval_method_description`. The function then applies the same raw
    preservation, hashing, collision checks, and provenance recording as
    for direct HTTP acquisition.

    Raises
    ------
    AcquisitionBlockedError
        If `raw_bytes` is None and the direct HTTP GET fails (e.g. due to
        network restriction, 404, or any other retrieval failure), OR if
        an existing raw file is found on disk with different content than
        what was just retrieved (a silent-overwrite guard -- an upstream
        change to a "frozen" public dataset is a reportable event, not
        something to apply quietly).
    """

    spec = get_dataset_spec(dataset_id)

    exec_log = get_execution_logger()

    exp_log = get_experiment_logger()

    error_log = get_error_logger()



    exec_log.info(f"Acquiring dataset '{dataset_id}' from {spec.retrieval_url}")



    if raw_bytes is None:

        try:

            response = requests.get(spec.retrieval_url, timeout=60)

            response.raise_for_status()

            raw_bytes = response.content

            retrieval_method_description = (

                retrieval_method_description

                or f"requests.get('{spec.retrieval_url}') -- normal acquisition code"

            )

        except requests.exceptions.RequestException as exc:

            error_log.error(f"Acquisition failed for '{dataset_id}': {exc!r}")

            raise AcquisitionBlockedError(

                dataset_id=dataset_id,

                reason=f"HTTP request failed: {exc!r}",

                attempted_url=spec.retrieval_url,

                options=[

                    "Retry once network connectivity to the official source is available.",

                    "If direct HTTP access is unavailable, obtain the source bytes through "

                    "an authorized retrieval mechanism and pass them via raw_bytes= while "

                    "recording the method with obtained_via and retrieval_method_description.",

                    "If the official source has permanently moved or is discontinued, "

                    "report this explicitly and await approval before using any "

                    "alternative source.",

                ],

            )



    raw_path = _raw_file_path(dataset_id, spec.retrieval_format)



    if raw_path.exists():

        existing_hash = _sha256_of_file(raw_path)

        new_hash = hashlib.sha256(raw_bytes).hexdigest()

        if existing_hash != new_hash:

            error_log.error(

                f"Raw file for '{dataset_id}' already exists at {raw_path} with a "

                f"DIFFERENT hash than the newly retrieved content "

                f"(existing={existing_hash[:12]}..., new={new_hash[:12]}...). "

                "Refusing to silently overwrite -- this indicates the upstream "

                "source has changed since the original acquisition, which must "

                "be reported and reviewed, not applied automatically."

            )

            raise AcquisitionBlockedError(

                dataset_id=dataset_id,

                reason=(

                    "Existing raw file has a different content hash than the newly "

                    "retrieved data. The official source may have been updated/revised."

                ),

                attempted_url=spec.retrieval_url,

                options=[

                    "Inspect both versions and confirm which should be treated as "

                    "the accepted publication dataset before proceeding.",

                    "If the revision is expected and acceptable, explicitly approve "

                    "overwriting and re-run acquisition with an explicit override flag "

                    "(not yet implemented -- requires an explicit decision first).",

                ],

            )

        else:

            exec_log.info(

                f"Raw file for '{dataset_id}' already exists at {raw_path} with "

                "matching content hash -- re-using existing raw file, not re-downloading."

            )

    else:

        with open(raw_path, "wb") as f:

            f.write(raw_bytes)

        exec_log.info(f"Wrote raw file for '{dataset_id}' to {raw_path} ({len(raw_bytes)} bytes).")



    file_hash = _sha256_of_file(raw_path)



    record = ProvenanceRecord(

        dataset_id=dataset_id,

        display_name=spec.display_name,

        official_source_name=spec.official_source_name,

        official_source_url=spec.official_source_url,

        retrieval_url=spec.retrieval_url,

        retrieval_method=retrieval_method_description or "unknown",

        retrieval_date_utc=datetime.now(timezone.utc).isoformat(),

        dataset_version_or_release=spec.version_or_release_note,

        file_hash_sha256=file_hash,

        file_path=str(raw_path),

        file_size_bytes=raw_path.stat().st_size,

        obtained_via=obtained_via,

        preprocessing_before_pipeline_entry="none -- raw file preserved byte-for-byte as retrieved",

        license_or_terms_url=spec.license_or_terms_url,

        citation=spec.citation,

        notes=spec.notes,

    )



    provenance_path = _provenance_path(dataset_id)

    with open(provenance_path, "w") as f:

        json.dump(record.to_dict(), f, indent=2)



    exp_log.info(f"Provenance recorded for '{dataset_id}': {record.to_dict()}")

    exec_log.info(f"Provenance metadata written to {provenance_path}")



    return record





def load_provenance(dataset_id: str) -> dict:

    """Load a previously-written provenance record for a dataset, if present."""

    path = _provenance_path(dataset_id)

    if not path.exists():

        raise FileNotFoundError(

            f"No provenance record found for '{dataset_id}' at {path}. "

            "Has acquire_dataset() been run for this dataset yet?"

        )

    with open(path, "r") as f:

        return json.load(f)





__all__ = [

    "AcquisitionBlockedError",

    "ProvenanceRecord",

    "acquire_dataset",

    "load_provenance",

    "RAW_DATA_ROOT",

]

