#!/usr/bin/env python3

"""
run_publication_pipeline.py — DCF Complete Publication Pipeline
Release: v1.2.0-rc20

Full ten-dataset, 12-model reproduction entry point for the DCF publication study.
Writes ALL outputs to the directory specified by --output. NEVER writes to
publication_results/ (the accepted evidence directory).

This is the single authoritative entry point for the complete Stage 1–9 DCF
publication reproduction. It calls run_full_pipeline(dataset_ids, config_path)
which executes all nine stages in sequence: data preparation, characterization,
Domain Profile construction, forecasting, evaluation, forecasting-behaviour
analysis, relationship analysis (Level 1/Level 2), evidence validation, and
final evidence package generation. All stages are mandatory and fail-closed.

Usage:
    python run_publication_pipeline.py \\
        --config configs/publication.yaml \\
        --output reproduction_runs/publication_run

Requirements:
    - Python 3.12.x, 64-bit
    - pip install -e .[dev]
    - Dataset files acquired per data_acquisition/dataset_registry.yaml
    - GPU strongly recommended for LSTM, GRU, TCN

Expected runtime: 12–36 hours depending on hardware.
"""

import argparse

import json

import pathlib

import sys

import time



sys.path.insert(0, str(pathlib.Path(__file__).parent / "src"))





PUBLICATION_DATASETS = [

    "CPIAUCSL", "INDPRO", "WTI", "Jena_Climate", "Beijing_PM25",

    "SP500", "EUR_USD", "Bike_Sharing", "EIA_Energy_Production", "FAO_Food_Price",

]





MODEL_ORDER = [

    "naive", "seasonal_naive", "drift", "arima", "sarima", "ets",

    "random_forest", "xgboost", "svr", "lstm", "gru", "tcn",

]





_PROTECTED_DIRS = {"publication_results", "publication_evidence"}





def _guard_output_dir(output_dir: pathlib.Path) -> None:

    """Fail immediately if output_dir is inside the accepted evidence tree."""

    for part in output_dir.parts:

        if part in _PROTECTED_DIRS:

            print(

                f"[ERROR] --output '{output_dir}' resolves inside the accepted "

                f"evidence tree ({_PROTECTED_DIRS}).\n"

                f"Reproduction must write to a fresh directory, e.g.:\n"

                f"  --output reproduction_runs/publication_run"

            )

            sys.exit(1)





def _load_manifest(manifest_path: pathlib.Path) -> dict:

    """Load and minimally validate publication_manifest.json."""

    if not manifest_path.exists():

        print(f"[ERROR] publication_manifest.json not found at '{manifest_path}'.\n"

              f"Run from the publication repository root.")

        sys.exit(1)

    manifest = json.loads(manifest_path.read_text())

    expected_id = "v1.2.0-rc20"

    if manifest.get("publication_release_id") != expected_id:

        print(f"[ERROR] Manifest release ID is '{manifest.get('publication_release_id')}'; "

              f"expected '{expected_id}'.")

        sys.exit(1)

    return manifest





def main() -> None:

    parser = argparse.ArgumentParser(

        description="DCF complete publication pipeline",

        formatter_class=argparse.RawDescriptionHelpFormatter,

        epilog=__doc__,

    )

    parser.add_argument("--config", required=True,

                        help="Path to configs/publication.yaml")

    parser.add_argument("--output", required=True,

                        help="Fresh output directory for this reproduction run")

    parser.add_argument("--resume", action="store_true",

                        help="Resume an interrupted checkpoint-based run")

    parser.add_argument("--datasets", nargs="+", default=None,

                        help="Dataset subset (not for publication qualification)")

    args = parser.parse_args()



    config_path = pathlib.Path(args.config)

    output_dir  = pathlib.Path(args.output)



    

    _guard_output_dir(output_dir)



    if not config_path.exists():

        print(f"[ERROR] Configuration file not found: {config_path}")

        sys.exit(1)



    manifest = _load_manifest(pathlib.Path("publication_manifest.json"))



    datasets = args.datasets or PUBLICATION_DATASETS

    unknown = set(datasets) - set(PUBLICATION_DATASETS)

    if unknown:

        print(f"[ERROR] Unknown dataset(s): {unknown}")

        sys.exit(1)

    if args.datasets:

        print(f"[WARN] Partial dataset run ({datasets}). "

              f"This is NOT a publication-qualification run.")



    if output_dir.exists() and not args.resume:

        if any(output_dir.iterdir()):

            print(f"[ERROR] Output directory '{output_dir}' already exists and is not empty.\n"

                  f"Use a fresh directory or --resume to continue an interrupted run.")

            sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)



    

    run_meta = {

        "publication_release_id": "v1.2.0-rc20",

        "datasets_ordered": datasets,

        "model_order": MODEL_ORDER,

        "config_file": str(config_path),

        "output_dir": str(output_dir.resolve()),

        "start_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),

        "random_seed": manifest["random_seeds"]["global_seed"],

    }

    (output_dir / "run_metadata.json").write_text(json.dumps(run_meta, indent=2))



    

    

    

    

    import platform, struct, json as _json_env, importlib.metadata as _imeta

    _py_major = sys.version_info.major

    _py_minor = sys.version_info.minor

    _py_full  = platform.python_version()

    _arch     = platform.machine()

    _bits     = struct.calcsize("P") * 8

    _impl     = platform.python_implementation()



    

    if _py_major != 3 or _py_minor != 12:

        print(f"[PREFLIGHT FAIL] Python 3.12.x required; this is Python {_py_full}.")

        sys.exit(1)

    if _bits != 64:

        print(f"[PREFLIGHT FAIL] 64-bit Python required; this is {_bits}-bit.")

        sys.exit(1)



    

    try:

        import yaml as _yaml

        _env_yaml_path = pathlib.Path("environment/approved_environment.yaml")

        if not _env_yaml_path.exists():

            raise FileNotFoundError(f"{_env_yaml_path} not found")

        with open(_env_yaml_path) as _f:

            _env_spec = _yaml.safe_load(_f)

        if not _env_spec or "packages" not in _env_spec:

            raise ValueError("approved_environment.yaml missing 'packages' section")

        _approved = _env_spec["packages"]

    except Exception as _e:

        print(f"[PREFLIGHT FAIL] Cannot load approved environment contract: {_e}")

        print("  environment/approved_environment.yaml must be present and parseable.")

        sys.exit(1)



    _dep_names = ["numpy","pandas","scipy","statsmodels","pmdarima","ruptures",

                  "scikit-learn","xgboost","torch"]

    

    _import_names = {"scikit-learn": "sklearn"}



    _dep_versions, _dep_import_versions, _preflight_errors = {}, {}, []

    for _dep in _dep_names:

        

        try:

            _dep_versions[_dep] = _imeta.version(_dep)

        except _imeta.PackageNotFoundError:

            _dep_versions[_dep] = "NOT_INSTALLED"

            _preflight_errors.append(f"{_dep}: NOT INSTALLED")

            continue

        

        if _dep != "torch":  

            _approved_ver = _approved.get(_dep)

            if _approved_ver and _dep_versions[_dep] != _approved_ver:

                _preflight_errors.append(

                    f"{_dep}: version mismatch (installed={_dep_versions[_dep]}, "

                    f"approved={_approved_ver})"

                )

        

        if _dep != "torch":

            _import_name = _import_names.get(_dep, _dep)

            try:

                _mod = __import__(_import_name)

                _dep_import_versions[_dep] = getattr(_mod, "__version__", "imported_ok")

            except Exception as _ie:

                _preflight_errors.append(f"{_dep}: import failed — {_ie}")



    

    _torch_info = {

        "metadata_version": _dep_versions.get("torch", "NOT_INSTALLED"),

        "approved_version": _approved.get("torch"),

        "import_ok": False, "runtime_version": None,

        "use_deterministic_algorithms_callable": False,

        "cpu_tensor_test": False, "cuda_available": False,

    }

    _torch_approved_ver = _approved.get("torch")

    if _dep_versions.get("torch") not in ("NOT_INSTALLED", None):

        

        if _torch_approved_ver and _dep_versions["torch"] != _torch_approved_ver:

            _preflight_errors.append(

                f"torch: version mismatch (installed={_dep_versions['torch']}, "

                f"approved={_torch_approved_ver})"

            )

        try:

            import torch as _torch_mod

            _torch_info["import_ok"] = True

            _torch_info["runtime_version"] = getattr(_torch_mod, "__version__", "UNKNOWN")

            

            _det_fn = getattr(_torch_mod, "use_deterministic_algorithms", None)

            if _det_fn is None or not callable(_det_fn):

                _preflight_errors.append("torch: use_deterministic_algorithms not callable")

            else:

                _torch_info["use_deterministic_algorithms_callable"] = True

                _det_fn(True, warn_only=True)

            

            _t = _torch_mod.tensor([1.0, 2.0, 3.0])

            _result = float(_t.sum().item())

            if abs(_result - 6.0) > 1e-6:

                _preflight_errors.append(f"torch: CPU tensor sum returned {_result}, expected 6.0")

            else:

                _torch_info["cpu_tensor_test"] = True

            _torch_info["cuda_available"] = (

                _torch_mod.cuda.is_available() if hasattr(_torch_mod, "cuda") else False

            )

        except Exception as _te:

            _torch_info["import_error"] = str(_te)

            _preflight_errors.append(f"torch: import/functional check failed — {_te}")



    

    if _preflight_errors:

        print("[PREFLIGHT FAIL] Environment does not satisfy the approved contract:")

        for _err in _preflight_errors:

            print(f"  {_err}")

        print("\nRecreate the approved environment:")

        print("  pip install -r requirements.txt  # or pip install -e .[dev]")

        sys.exit(1)



    

    _env_fingerprint = {

        "preflight_result": "PASS",

        "python_version": _py_full,

        "python_implementation": _impl,

        "python_major_minor": f"{_py_major}.{_py_minor}",

        "python_exact": _py_full,  

        "architecture": _arch,

        "bits": _bits,

        "platform": platform.platform(),

        "approved_env_file": "environment/approved_environment.yaml",

        "dependency_metadata_versions": _dep_versions,

        "dependency_import_versions": _dep_import_versions,

        "torch": _torch_info,

    }

    (output_dir / "environment_fingerprint.json").write_text(

        _json_env.dumps(_env_fingerprint, indent=2)

    )

    print(f"[PREFLIGHT PASS] Python {_py_full} {_impl} {_bits}-bit on {_arch}")

    print(f"  Torch {_torch_info.get('runtime_version')} | "

          f"CPU tensor: {'OK' if _torch_info['cpu_tensor_test'] else 'FAIL'} | "

          f"deterministic API: {'OK' if _torch_info['use_deterministic_algorithms_callable'] else 'FAIL'}")

    print(f"  Fingerprint: environment_fingerprint.json")



    print("=" * 70)

    print("DCF Publication Pipeline — v1.2.0-rc20")

    print(f"Datasets ({len(datasets)}): {', '.join(datasets)}")

    print(f"Models ({len(MODEL_ORDER)}): {', '.join(MODEL_ORDER)}")

    print(f"Config: {config_path}")

    print(f"Output: {output_dir.resolve()}")

    print("=" * 70)



    

    

    

    import os, subprocess, json as _json

    os.environ["DCF_RESULTS_ROOT"] = str(output_dir.resolve())



    

    

    

    

    REQUIRED_DATASETS = [

        "CPIAUCSL","INDPRO","WTI","Jena_Climate","Beijing_PM25",

        "SP500","EUR_USD","Bike_Sharing","EIA_Energy_Production","FAO_Food_Price",

    ]

    gate_output = output_dir / "acquisition_identity_gate.json"



    print("\nRunning mandatory prepared-series identity preflight...")

    print(f"  DCF_RESULTS_ROOT: {output_dir.resolve()}")

    try:

        proc = subprocess.run(

            [sys.executable, "data_acquisition/validate_acquisition.py",

             "--verify-sha", "--output", str(gate_output)],

            capture_output=True, text=True, timeout=600,

            env={**os.environ, "DCF_RESULTS_ROOT": str(output_dir.resolve())},

        )

        print(proc.stdout.rstrip())

    except subprocess.TimeoutExpired:

        print("[ERROR] Identity preflight timed out after 600s.")

        sys.exit(1)

    except FileNotFoundError:

        print("[ERROR] validate_acquisition.py not found. Run from the repository root.")

        sys.exit(1)



    

    gate_results = {}

    if gate_output.exists():

        try:

            gate_results = _json.loads(gate_output.read_text())

        except Exception as e:

            print(f"[ERROR] Cannot parse identity gate output: {e}")

            sys.exit(1)



    verified = []

    failures = []

    for ds_id in REQUIRED_DATASETS:

        r = gate_results.get(ds_id, {})

        status    = r.get("status", "MISSING")

        sha_check = r.get("sha_verification", {})

        sha_ok    = sha_check.get("sha_match", False)

        if status == "READY" and sha_ok:

            verified.append(ds_id)

        else:

            reason = r.get("sha_error") or r.get("error") or f"status={status}, sha_match={sha_ok}"

            failures.append(f"  {ds_id}: {reason}")



    n_verified = len(verified)

    print(f"\nIdentity gate: {n_verified}/{len(REQUIRED_DATASETS)} datasets VERIFIED")



    if n_verified < len(REQUIRED_DATASETS):

        print("[ERROR] Mandatory identity gate FAILED — not all 10 datasets verified.")

        print("  Datasets that did not pass:")

        for f in failures:

            print(f)

        print("  Acquire all datasets and run validate_acquisition.py --verify-sha.")

        print("  Do NOT begin forecasting until 10/10 datasets are VERIFIED.")

        sys.exit(1)



    print("[OK] 10/10 VERIFIED — all prepared series match accepted SHA-256. Proceeding.")



    

    try:

        from dcf.pipeline import run_full_pipeline

    except ImportError as e:

        print(f"[ERROR] Cannot import DCF pipeline: {e}\n"

              f"Ensure the package is installed: pip install -e .[dev]")

        sys.exit(1)

    



    

    

    try:

        run_full_pipeline(

            dataset_ids=datasets,

            config_path=config_path,

        )

    except Exception as e:

        print(f"\n[PIPELINE ERROR] {e}")

        import traceback

        traceback.print_exc()

        (output_dir / "pipeline_error.log").write_text(

            f"Error: {e}\n\n{traceback.format_exc()}"

        )

        sys.exit(1)



    

    print(f"\n{'='*70}")

    print("PIPELINE COMPLETE")

    print(f"Outputs written to: {output_dir.resolve()}")

    print(f"\nNext — compare against accepted evidence:")

    print(f"  python compare_reproduction.py \\")

    print(f"      --candidate {output_dir} \\")

    print(f"      --reference publication_results")

    print(f"{'='*70}")





if __name__ == "__main__":

    main()

