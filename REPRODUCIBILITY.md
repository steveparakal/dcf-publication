# Reproducibility

## Environment

The qualified execution used Python 3.12.10 (64-bit AMD64) and PyTorch 2.4.1+cpu. Exact package expectations are recorded in `environment/approved_environment.yaml`, `requirements.txt`, and `pyproject.toml`.

## Inputs

Acquire the ten source datasets using `data_acquisition/dataset_registry.yaml`. The acquisition validator checks the expected source/prepared identities before the publication run proceeds.

## Full publication execution

From the repository root:

```bash
pip install -r requirements.txt
pip install -e .
python run_publication_pipeline.py --config configs/publication.yaml --output reproduction_runs/publication_run
```

A valid run should report that all 10 datasets are ready and that the prepared-series identity gate is 10/10 VERIFIED. It should then complete Stages 1–9 and generate the final evidence package.

## Downstream publication objects

After Stages 1–9 complete:

```bash
python scripts/reproduce_downstream_publication_analyses.py \
  --results-root reproduction_runs/publication_run \
  --output-dir reproduction_runs/publication_run/downstream_publication
```

The downstream step reads only the completed publication outputs. It does not rerun forecasting, retrain models, change datasets, or change the publication configuration.

The qualified reference execution produced the accepted states:

- S1: Inconclusive
- S2: Supported
- S3: Supported
- S4: Supported
- S5: 10 Unsupported, 1 Inconclusive
- S6: 6 Unsupported, 4 Inconclusive
- S7: Diagnostic only

Floating-point serialization can differ at the final machine precision across equivalent executions/platforms. Publication comparisons should verify the numerical values at scientifically meaningful precision together with the exact evidence states and study rules.

## Reference evidence

`reference_evidence/` contains the compact reference objects required to inspect Domain Profiles, model evaluation results, forecasting-behaviour traceability, Level-1/Level-2 analysis, final evidence validation, and downstream publication analyses.

## Integrity

`SHA256_MANIFEST.json` records the SHA-256 hash of every file in this release package except the manifest itself.
