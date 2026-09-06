# Domain Characterization Framework (DCF)

This repository contains the publication software and compact machine-readable reference evidence for the ten-dataset Domain Characterization Framework (DCF) forecasting study.

## Repository structure

- `run_publication_pipeline.py` — publication pipeline entry point.
- `configs/` — frozen publication configuration and defaults.
- `src/dcf/` — DCF implementation: data preparation, characterization, forecasting, evaluation, relationship analysis, and evidence validation.
- `data_acquisition/` — dataset source registry and input validation.
- `scripts/` — dataset-preparation support and downstream publication reproduction.
- `reference_evidence/` — compact machine-readable reference results from the qualified publication execution.
- `RESULTS_GUIDE.md` — reviewer-oriented map from manuscript results to the corresponding machine-readable evidence.
- `environment/`, `requirements.txt`, `pyproject.toml` — reproducible software environment.

## Reproduce the publication run

Use Python 3.12.x, 64-bit. Install the dependencies, acquire the ten datasets listed in `data_acquisition/dataset_registry.yaml`, place them at the documented local paths, and run:

```bash
pip install -r requirements.txt
pip install -e .
python run_publication_pipeline.py --config configs/publication.yaml --output reproduction_runs/publication_run
```

The pipeline performs the environment and prepared-series identity gates before forecasting. A valid publication execution must pass all required gates and complete Stages 1–9.

## Reproduce the downstream publication analyses

After a successful Stage 1–9 run:

```bash
python scripts/reproduce_downstream_publication_analyses.py \
  --results-root reproduction_runs/publication_run \
  --output-dir reproduction_runs/publication_run/downstream_publication
```

This regenerates the machine-readable objects supporting Supplement Tables S13–S17 and the prespecified S1–S7 analyses. Reference objects are included under `reference_evidence/downstream/`. See `RESULTS_GUIDE.md` for a direct map from reported results to evidence files.

## Data

Raw datasets are not redistributed in this repository. `data_acquisition/dataset_registry.yaml` records the provider, source location, expected local path, target definition, date range, and accepted prepared-series identity for each dataset. Third-party data remain subject to their original provider terms. See `DATA.md`.

## Reproducibility qualification

The publication software in this package was executed on the authoritative ten-dataset input bundle in a fresh output directory. The run passed the environment preflight, verified all 10 prepared-series identities, completed all 12 models across all datasets, completed Stages 1–9, and reproduced the accepted publication evidence. See `QUALIFICATION.json` and `REPRODUCIBILITY.md`.

## License

Source code is provided under the MIT License in `LICENSE`. Third-party datasets are not covered by this code license.
