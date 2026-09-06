#!/usr/bin/env python3

"""
validate_acquisition.py — DCF Dataset Acquisition Prerequisite Validator
Release: v1.2.0-rc20

For each of the ten final publication datasets, this script:
  1. Checks whether the required raw source file exists at the expected path.
  2. Where legally and technically appropriate, attempts auto-download.
  3. After preparation, verifies the prepared-series SHA-256 against the
     ACCEPTED PUBLICATION IDENTITY recorded here.

CRITICAL: A successful download or file-size check is NOT sufficient.
The pipeline must not proceed to forecasting unless the prepared series
matches the accepted publication SHA-256. If a live source has changed
and cannot reproduce the accepted hash, this is a reproduction-source
problem that must be reported, not silently bypassed.

Usage:
    python data_acquisition/validate_acquisition.py          # check all
    python data_acquisition/validate_acquisition.py --check-only  # no download
    python data_acquisition/validate_acquisition.py --verify-sha  # also run prepare+hash
    python data_acquisition/validate_acquisition.py CPIAUCSL WTI  # subset
"""

import argparse, hashlib, json, pathlib, sys, time

try:

    import requests

    HAS_REQUESTS = True

except ImportError:

    HAS_REQUESTS = False



DATA_ROOT = pathlib.Path("data/raw")















ACCEPTED_SHA256 = {

    "CPIAUCSL":             "41da299404c177ef7ce85428971e2342fdec7cc50f80001e26a29be5a81039e0",

    "INDPRO":               "b47c3667d421ac110c783d92f5017a705d7679b18dedac7ba429917992692986",

    "WTI":                  "52bf3396665be6100bc47488ca395c5f3676b85b50ea549b40f341f90a02b57b",

    "Jena_Climate":         "31579b38f75a5e7381699992ab18a681af8e663ba1bc7cf6273f9a9dc21a06dd",

    "Beijing_PM25":         "86d70852d1f003a356f2cc21e969ebfd03e1a87d39db7d689965494a1010da91",

    "SP500":                "97981d46c39d451ade4ca6214119aae5b0f34fd31b3e71fe7568a44dcc57b619",

    "EUR_USD":              "4a340c9ec574f69b6cae1391e032c0afba6a02f39610c8e167eaf87a92686fb1",

    "Bike_Sharing":         "0b60cbf938867885644f9c0f461b7036ce665bcab33b7fddd1b3a71c5985b366",

    "EIA_Energy_Production":"1d54c09f8151edaff4693f510185395ab45315289cd0b40e9f3b5f2f12608485",

    "FAO_Food_Price":       "f6f74d1698c3fff962ce5f3d425b926936fbeb9e6524f78e867cccd489dee46d",

}





DATASETS = {

    "CPIAUCSL": {

        "raw_path": DATA_ROOT / "CPIAUCSL" / "CPIAUCSL.raw.csv",

        "method": "auto_download",

        "url": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=CPIAUCSL",

        "min_bytes": 10_000,

        "description": "CPI (All Urban Consumers, SA) — FRED CPIAUCSL",

    },

    "INDPRO": {

        "raw_path": DATA_ROOT / "INDPRO" / "INDPRO.raw.csv",

        "method": "auto_download",

        "url": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=INDPRO",

        "min_bytes": 10_000,

        "description": "Industrial Production Index — FRED INDPRO",

    },

    "WTI": {

        "raw_path": DATA_ROOT / "WTI" / "WTI.raw.csv",

        "method": "auto_download",

        "url": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=WTISPLC",

        "min_bytes": 5_000,

        "description": "WTI Crude Oil Price — FRED WTISPLC (monthly; NOT DCOILWTICO)",

    },

    "Jena_Climate": {

        "raw_path": DATA_ROOT / "Jena_Climate" / "jena_climate_2009_2016.csv",

        "method": "manual",

        "instructions": (

            "Download jena_climate_2009_2016.csv from:\n"

            "  https://storage.googleapis.com/tensorflow/tf-keras-datasets/jena_climate_2009_2016.csv.zip\n"

            "  (ZIP; extract the CSV)\n"

            "  Place at: data/raw/Jena_Climate/jena_climate_2009_2016.csv"

        ),

        "min_bytes": 1_000_000,

        "description": "Jena Climate 10-min T (degC) — MPI Jena",

    },

    "Beijing_PM25": {

        "raw_path": DATA_ROOT / "Beijing_PM25" / "Beijing_PM25_daily.csv",

        "method": "manual_with_preprocessing",

        "instructions": (

            "1. Download Beijing Multi-Site Air-Quality Data (UCI #501, NOT UCI #381) from:\n"

            "   https://archive.ics.uci.edu/dataset/501\n"

            "2. Extract the multi-station hourly CSVs.\n"

            "3. Run: python scripts/preprocess_beijing_pm25.py\n"

            "   This produces: data/raw/Beijing_PM25/Beijing_PM25_daily.csv\n"

            "   Target: Dongsi station, PM2.5 daily mean, 2013-03-01 to 2017-02-28\n"

            "WARNING: UCI #381 (PRSA_data_2010.1.1-2014.12.31.csv) is a different"

            " dataset. Do NOT use it."

        ),

        "min_bytes": 30_000,

        "description": "Beijing PM2.5 — UCI #501 Dongsi daily mean (NOT UCI #381)",

    },

    "SP500": {

        "raw_path": DATA_ROOT / "SP500" / "SP500.csv",

        "method": "auto_download",

        "url": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=SP500",

        "min_bytes": 45_000,

        "description": "S&P 500 — FRED SP500 (2016-07-25 to 2026-07-24; NOT Yahoo Finance)",

    },

    "EUR_USD": {

        "raw_path": DATA_ROOT / "EUR_USD" / "EUR_USD.csv",

        "method": "auto_download",

        "url": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DEXUSEU",

        "min_bytes": 100_000,

        "description": "EUR/USD Exchange Rate — FRED DEXUSEU",

    },

    "Bike_Sharing": {

        "raw_path": DATA_ROOT / "Bike_Sharing" / "day.csv",

        "method": "manual",

        "instructions": (

            "Download from: https://archive.ics.uci.edu/dataset/275/bike+sharing+dataset\n"

            "  Extract day.csv and place at: data/raw/Bike_Sharing/day.csv"

        ),

        "min_bytes": 50_000,

        "description": "Bike Sharing daily cnt — UCI #275",

    },

    "EIA_Energy_Production": {

        "raw_path": DATA_ROOT / "EIA_Energy_Production" / "EIA_T01_02_Primary_Energy_Production.csv",

        "method": "manual",

        "instructions": (

            "Download EIA Monthly Energy Review Table 1.2 (CSV/bulk download) from:\n"

            "  https://www.eia.gov/totalenergy/data/monthly/\n"

            "  Place at: data/raw/EIA_Energy_Production/EIA_T01_02_Primary_Energy_Production.csv"

        ),

        "min_bytes": 50_000,

        "description": "EIA Primary Energy Production TEPRBUS — EIA Monthly Energy Review",

    },

    "FAO_Food_Price": {

        "raw_path": DATA_ROOT / "FAO_Food_Price" / "FAO_Food_Price_Index.xlsx",

        "method": "manual",

        "instructions": (

            "Download from: https://www.fao.org/worldfoodsituation/foodpricesindex/en/\n"

            "  Place at: data/raw/FAO_Food_Price/FAO_Food_Price_Index.xlsx"

        ),

        "min_bytes": 50_000,

        "description": "FAO Food Price Index monthly — FAO",

    },

}



PUBLICATION_ORDER = [

    "CPIAUCSL","INDPRO","WTI","Jena_Climate","Beijing_PM25",

    "SP500","EUR_USD","Bike_Sharing","EIA_Energy_Production","FAO_Food_Price",

]





def sha256f(p: pathlib.Path) -> str:

    h = hashlib.sha256()

    with open(p, "rb") as f:

        for chunk in iter(lambda: f.read(65536), b""): h.update(chunk)

    return h.hexdigest()





def _auto_download(ds_id: str, spec: dict, check_only: bool) -> dict:

    """
    Handle auto_download datasets (CPIAUCSL, INDPRO, WTI, SP500, EUR_USD).

    Cached file (exists and passes size sanity check):
      - provenance.json present, SHA-256 consistent: return READY (idempotent).
      - provenance.json absent: call acquire_dataset() to create it.
        acquire_dataset() is the sole authorised provenance writer.
      - provenance.json present but SHA-256 mismatched: FAIL (fail-closed;
        never silently overwrite an inconsistent provenance record).

    Fresh download (file absent or below size sanity threshold):
      - Download bytes; call acquire_dataset() to write provenance after saving.
      - The size threshold is a sanity check against empty/truncated network
        responses only; the decisive identity gate is the prepared-series SHA-256.
    """

    import sys as _sys, json as _json

    _sys.path.insert(0, "src")



    url  = spec["url"]

    dest = pathlib.Path(spec["raw_path"])



    def _ensure_provenance(raw_bytes: bytes, obtained_via: str) -> dict:

        """Call acquire_dataset() to write provenance; return a result dict."""

        try:

            from dcf.acquisition import acquire_dataset

        except ImportError as _ie:

            return {"status": "FAIL",

                    "error": "Cannot import acquire_dataset: " + str(_ie)}

        try:

            acquire_dataset(

                ds_id,

                raw_bytes=raw_bytes,

                obtained_via=obtained_via,

                retrieval_method_description=(

                    "Dataset '" + ds_id + "' staged via publication acquisition "

                    "protocol. Bytes passed unchanged to acquire_dataset() "

                    "(source SHA-256: " + sha256f(dest) + ")."

                ),

            )

            return {"ok": True}

        except Exception as _exc:

            return {"status": "FAIL", "error": str(_exc)}



    

    if dest.exists() and dest.stat().st_size >= spec["min_bytes"]:

        try:

            from dcf.acquisition import _provenance_path, _raw_file_path

            from dcf.dataset_registry import get_dataset_spec as _get_spec

        except ImportError as _ie:

            return {"status": "FAIL",

                    "error": "Cannot import acquisition helpers: " + str(_ie)}



        prov_path = _provenance_path(ds_id)

        spec_reg  = _get_spec(ds_id)

        raw_path  = _raw_file_path(ds_id, spec_reg.retrieval_format)

        raw_sha   = sha256f(dest)



        if prov_path.exists() and raw_path.exists():

            

            

            try:

                prov = _json.loads(prov_path.read_text())

            except Exception as _pe:

                return {"status": "FAIL",

                        "error": "provenance.json unreadable: " + str(_pe)}

            prov_sha = prov.get("file_hash_sha256", "")

            can_sha  = sha256f(raw_path)

            if raw_sha == prov_sha == can_sha:

                return {"status": "READY", "path": str(dest),

                        "source": "cached",

                        "source_sha256": raw_sha,

                        "provenance_sha256": prov_sha}

            mismatches = []

            if raw_sha != prov_sha:

                mismatches.append(

                    "staged raw SHA (" + raw_sha[:16] + "...) != "

                    "provenance SHA (" + prov_sha[:16] + "...)")

            if can_sha != prov_sha:

                mismatches.append(

                    "canonical raw SHA (" + can_sha[:16] + "...) != "

                    "provenance SHA (" + prov_sha[:16] + "...)")

            return {"status": "FAIL",

                    "error": "SHA mismatch in cached provenance — will not overwrite: "

                             + "; ".join(mismatches)}



        if prov_path.exists() and not raw_path.exists():

            return {"status": "FAIL",

                    "error": "provenance.json present but canonical raw file absent: "

                             + str(raw_path)}



        

        if check_only:

            return {"status": "MANUAL_REQUIRED", "path": str(dest),

                    "instructions":

                        "Re-run without --check-only to register provenance for " + ds_id}

        raw_bytes = dest.read_bytes()

        res = _ensure_provenance(raw_bytes, obtained_via="cached_historical_file")

        if res.get("status") == "FAIL":

            return res

        return {"status": "READY", "path": str(dest),

                "source": "cached_provenance_registered",

                "source_sha256": raw_sha,

                "provenance_written": str(prov_path)}



    

    if check_only:

        return {"status": "MANUAL_REQUIRED", "path": str(dest),

                "instructions": "Re-run without --check-only to auto-download from " + url}

    if not HAS_REQUESTS:

        return {"status": "FAIL", "error": "requests not installed (pip install requests)"}

    dest.parent.mkdir(parents=True, exist_ok=True)

    try:

        resp = requests.get(url, timeout=60, headers={"User-Agent": "DCF-publication/1.2.0"})

        resp.raise_for_status()

        dest.write_bytes(resp.content)

        if dest.stat().st_size < spec["min_bytes"]:

            return {"status": "FAIL",

                    "error": ("Downloaded file too small (" + str(dest.stat().st_size)

                              + " bytes); minimum sanity threshold is "

                              + str(spec["min_bytes"]) + " bytes.")}

        raw_bytes = dest.read_bytes()

        res = _ensure_provenance(raw_bytes, obtained_via="auto_download")

        if res.get("status") == "FAIL":

            return res

        return {"status": "READY", "path": str(dest), "source": "downloaded",

                "bytes": dest.stat().st_size,

                "source_sha256": sha256f(dest)}

    except Exception as e:

        return {"status": "FAIL", "error": str(e)}





def _check_manual(ds_id: str, spec: dict, check_only: bool) -> dict:

    """
    Check a manually-supplied dataset and — in full mode — bridge to
    acquire_dataset(..., raw_bytes=...) so provenance.json and the canonical
    raw file are created before Stage 1 runs.

    check_only=True  : non-mutating; reports presence only, writes nothing.
    check_only=False : full mode; if provenance/raw-file are absent or
                       inconsistent, reads source bytes and calls
                       acquire_dataset() to create the canonical artifacts.
    """

    import sys as _sys

    _sys.path.insert(0, "src")



    source_path = pathlib.Path(spec["raw_path"])   

    min_bytes   = spec["min_bytes"]



    

    if not source_path.exists() or source_path.stat().st_size < min_bytes:

        return {

            "status": "MANUAL_REQUIRED",

            "path": str(source_path),

            "instructions": spec.get("instructions", "See dataset_registry.yaml"),

        }



    

    if check_only:

        return {"status": "READY", "path": str(source_path), "source": "pre-existing"}



    

    from dcf.acquisition import acquire_dataset, _provenance_path, _raw_file_path

    from dcf.dataset_registry import get_dataset_spec as _get_spec



    prov_path = _provenance_path(ds_id)

    spec_reg  = _get_spec(ds_id)

    raw_path  = _raw_file_path(ds_id, spec_reg.retrieval_format)



    

    source_bytes = source_path.read_bytes()

    source_sha   = sha256f(source_path)



    

    

    if prov_path.exists() and raw_path.exists():

        import json as _json

        try:

            prov = _json.loads(prov_path.read_text())

        except Exception as _e:

            return {"status": "FAIL",

                    "error": "provenance.json is unreadable: " + str(_e)}



        

        

        

        

        prov_file_path_str = prov.get("file_path")

        if not prov_file_path_str:

            return {"status": "FAIL",

                    "error": "provenance.json missing or empty file_path field"}

        try:

            prov_file_path = pathlib.Path(prov_file_path_str).resolve()

        except Exception as _pe:

            return {"status": "FAIL",

                    "error": "provenance.json file_path cannot be resolved: " + str(_pe)}

        expected_raw_resolved = raw_path.resolve()

        if prov_file_path != expected_raw_resolved:

            return {"status": "FAIL",

                    "error": (

                        "provenance.json file_path does not match expected canonical "

                        "raw path: provenance records '" + str(prov_file_path) + "', "

                        "expected '" + str(expected_raw_resolved) + "'"

                    )}



        

        

        

        if not prov_file_path.exists():

            return {"status": "FAIL",

                    "error": "Canonical raw file referenced by provenance does not exist: "

                             + str(prov_file_path)}



        

        prov_sha = prov.get("file_hash_sha256")

        raw_sha  = sha256f(raw_path)



        if not prov_sha:

            return {"status": "FAIL",

                    "error": "provenance.json missing file_hash_sha256 field"}



        if source_sha == prov_sha == raw_sha:

            return {"status": "READY", "path": str(source_path),

                    "source": "already_acquired",

                    "source_sha256": source_sha,

                    "canonical_sha256": raw_sha,

                    "provenance_sha256": prov_sha}



        

        mismatches = []

        if source_sha != prov_sha:

            mismatches.append(

                "source SHA (" + source_sha[:16] + "...) != provenance SHA ("

                + prov_sha[:16] + "...)"

            )

        if raw_sha != prov_sha:

            mismatches.append(

                "canonical raw SHA (" + raw_sha[:16] + "...) != provenance SHA ("

                + prov_sha[:16] + "...)"

            )

        if source_sha != raw_sha:

            mismatches.append(

                "source SHA (" + source_sha[:16] + "...) != canonical raw SHA ("

                + raw_sha[:16] + "...)"

            )

        return {"status": "FAIL",

                "error": "Three-way SHA-256 identity check failed: " + "; ".join(mismatches)}



    if prov_path.exists() and not raw_path.exists():

        return {"status": "FAIL",

                "error": "provenance.json exists but canonical raw file is absent: "

                         + str(raw_path)}



    

    

    

    try:

        acquire_dataset(

            ds_id,

            raw_bytes=source_bytes,

            obtained_via="manual_placement",

            retrieval_method_description=(

                "Operator manually placed source file '" + source_path.name + "' "

                "per publication acquisition protocol. Bytes passed unchanged "

                "to acquire_dataset() (source SHA-256: " + source_sha + ")."

            ),

        )

        return {"status": "READY", "path": str(source_path),

                "source": "manual_acquired",

                "source_sha256": source_sha,

                "provenance_written": str(prov_path),

                "canonical_raw_written": str(raw_path)}

    except Exception as _exc:

        return {"status": "FAIL", "error": str(_exc)}





def _verify_prepared_sha(ds_id: str) -> dict:

    """Run prepare_dataset and verify the prepared-series SHA-256."""

    import sys

    sys.path.insert(0, "src")

    try:

        from dcf.data_preparation import prepare_dataset

        prep = prepare_dataset(ds_id)

        actual_sha = sha256f(prep.series_values_path)

        accepted_full_sha = ACCEPTED_SHA256[ds_id]

        

        match = (actual_sha == accepted_full_sha)

        return {

            "prepared_sha256": actual_sha,

            "accepted_sha256": accepted_full_sha,

            "sha_match": match,  

            "series_values_path": str(prep.series_values_path),

        }

    except Exception as e:

        return {"prepared_sha256": None, "accepted_sha256": ACCEPTED_SHA256[ds_id],

                "sha_match": False, "error": str(e)}





def validate(datasets_to_check: list, check_only: bool, verify_sha: bool) -> dict:

    results = {}

    for ds_id in datasets_to_check:

        spec = DATASETS[ds_id]

        print("  [" + ds_id + "] " + spec["description"])

        method = spec["method"]

        if method == "auto_download":

            r = _auto_download(ds_id, spec, check_only)

        else:

            r = _check_manual(ds_id, spec, check_only)



        if r["status"] == "READY" and verify_sha:

            sha_result = _verify_prepared_sha(ds_id)

            r["sha_verification"] = sha_result

            if not sha_result["sha_match"]:

                r["status"] = "SHA_MISMATCH"

                r["sha_error"] = (

                    "Prepared series SHA mismatch for " + ds_id + ": "

                    "expected SHA-256 " + sha_result.get("accepted_sha256", "UNKNOWN") + ", "

                    "got " + (sha_result["prepared_sha256"][:16]

                               if sha_result["prepared_sha256"] else "None") + "... "

                    "This indicates a different source or version. "

                    "Do NOT proceed to forecasting. Report as a reproduction-source problem."

                )

                print("    SHA_MISMATCH: " + r["sha_error"])

            else:

                print("    SHA OK: " + sha_result["prepared_sha256"][:12]

                      + "... matches accepted SHA-256")



        results[ds_id] = r

        s = r["status"]

        if s == "READY":

            print("    READY — " + str(r.get("path")))

        elif s == "MANUAL_REQUIRED":

            instr = r.get("instructions", "")[:120]

            print("    MANUAL_REQUIRED: " + instr)

        elif s == "SHA_MISMATCH":

            pass  

        else:

            print("    " + s + ": " + str(r.get("error", "")))

    return results





def main():

    parser = argparse.ArgumentParser(description="DCF dataset acquisition validator v1.2.0-rc20")

    parser.add_argument("datasets", nargs="*", default=PUBLICATION_ORDER,

                        help="Dataset IDs to check (default: all ten)")

    parser.add_argument("--check-only", action="store_true",

                        help="Only check existence; do not attempt download")

    parser.add_argument("--verify-sha", action="store_true",

                        help="Run prepare_dataset and verify accepted SHA-256")

    parser.add_argument("--output", default=None, help="Write results JSON to path")

    args = parser.parse_args()



    unknown = set(args.datasets) - set(DATASETS)

    if unknown:

        print("[ERROR] Unknown dataset IDs: " + str(unknown))

        sys.exit(1)



    print("=" * 70)

    print("DCF Dataset Acquisition Validator — v1.2.0-rc20")

    print("Checking " + str(len(args.datasets)) + " dataset(s)"

          + (" (check-only)" if args.check_only else "")

          + (" [+SHA verify]" if args.verify_sha else ""))

    print("=" * 70)



    results = validate(args.datasets, check_only=args.check_only, verify_sha=args.verify_sha)



    ready        = [k for k,v in results.items() if v["status"] == "READY"]

    manual       = [k for k,v in results.items() if v["status"] == "MANUAL_REQUIRED"]

    sha_mismatch = [k for k,v in results.items() if v["status"] == "SHA_MISMATCH"]

    failed       = [k for k,v in results.items() if v["status"] == "FAIL"]



    if args.output:

        pathlib.Path(args.output).write_text(json.dumps(results, indent=2))



    print("\n" + "=" * 70)

    print("READY:           " + str(len(ready)) + "/" + str(len(args.datasets))

          + "  " + str(ready))

    if manual:

        print("MANUAL_REQUIRED: " + str(len(manual)) + "  " + str(manual))

    if sha_mismatch:

        print("SHA_MISMATCH:    " + str(len(sha_mismatch)) + "  "

              + str(sha_mismatch) + "  <- REPRODUCTION FAILURE")

    if failed:

        print("FAILED:          " + str(len(failed)) + "  " + str(failed))



    if sha_mismatch or failed:

        print("\nRESULT: FAIL")

        if sha_mismatch:

            print("  One or more prepared series do not match the accepted publication identity.")

            print("  Do NOT begin forecasting. Report the mismatch as a reproduction-source problem.")

        sys.exit(1)

    elif manual:

        print("\nRESULT: PARTIAL — " + str(len(manual)) + " dataset(s) require manual download")

        sys.exit(0)

    else:

        print("\nRESULT: ALL READY")

        sys.exit(0)





if __name__ == "__main__":

    main()

