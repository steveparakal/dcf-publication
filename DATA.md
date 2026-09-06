# Data acquisition

The raw datasets used in the DCF publication study are not redistributed in this repository.

For each dataset, `data_acquisition/dataset_registry.yaml` records:

- provider and source location;
- expected local file path;
- target series definition;
- accepted date range and frequency;
- preprocessing notes where applicable;
- accepted prepared-series SHA-256 identity.

Place acquired files under the documented `data/raw/<dataset>/` paths. The publication runner invokes the acquisition/identity checks before forecasting begins.

The ten datasets are CPIAUCSL, INDPRO, WTI, Jena Climate, Beijing PM2.5, S&P 500, EUR/USD, Bike Sharing, EIA Energy Production, and FAO Food Price.

Third-party datasets remain subject to the terms of their respective providers.
