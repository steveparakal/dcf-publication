# Results Guide

This repository includes compact machine-readable reference evidence so that the reported publication results can be inspected without rerunning the full forecasting experiment.

## Where to find the principal results

| Publication result | Reference evidence | What the file contains |
| --- | --- | --- |
| Domain Profiles and the values underlying the domain-profile landscape | `reference_evidence/03_domain_profiles/<dataset>/<dataset>.domain_profile.json` | The seven Domain Profile coordinates for each of the ten datasets. |
| Model evaluation and best-model results (Table 5.1) | `reference_evidence/04_forecasts/<dataset>/<dataset>.evaluation.json` | Model-level evaluation metrics, ranking, and best model for each dataset. |
| Forecasting-behaviour vectors and dataset summaries | `reference_evidence/05_analysis/relationship/forecasting_behaviour_traceability.json` | Canonical model order, naive RMSE, the 11-entry log-relative-RMSE vectors, and the dataset-level behavioural summary values. |
| Level 1 and primary Level 2 analysis (Tables 5.2–5.3) | `reference_evidence/05_analysis/relationship/relationship_analysis.json` | Dimension-level findings and the primary whole-profile relationship analysis. |
| Final Level 1 / Level 2 evidence states | `reference_evidence/06_validation/evidence_validation.json` | The final evidence-validation assessment, including Level 1 and Level 2 states. |
| Supplement Table S13 | `reference_evidence/downstream/S13_level1_lodo_secondary.json` | Level-1 leave-one-dataset-out results and secondary-response checks. |
| Supplement Table S14 | `reference_evidence/downstream/S14_domain_profile_distance_matrix.json` | The full Domain Profile distance matrix. |
| Supplement Table S15 | `reference_evidence/downstream/S15_behaviour_distance_matrix.json` | The full forecasting-behaviour distance matrix. |
| Supplement Table S17 and the S1–S7 analyses | `reference_evidence/downstream/S17_prespecified_level2_sensitivities.json` | The prespecified Level-2 sensitivity and diagnostic results. |

## Dataset-level inspection

For a single dataset, the two most useful files are:

1. `reference_evidence/03_domain_profiles/<dataset>/<dataset>.domain_profile.json` — structural characterization.
2. `reference_evidence/04_forecasts/<dataset>/<dataset>.evaluation.json` — forecasting evaluation.

The cross-dataset bridge is then provided by `forecasting_behaviour_traceability.json`, which assembles the model-behaviour representation used by the relationship analysis.

## Reproducing the evidence

To regenerate the full Stage 1–9 evidence, follow `REPRODUCIBILITY.md`. After a successful run, `scripts/reproduce_downstream_publication_analyses.py` regenerates the S13–S17 / S1–S7 machine-readable objects from the completed publication outputs.

The repository intentionally contains compact reference evidence rather than every execution log, temporary report, and intermediate file from the qualification run. Raw third-party datasets are also not redistributed; see `DATA.md` for acquisition requirements.
