"""
dataset_registry.py

Canonical registry of dataset definitions for the Domain Characterization
Framework publication study.

This module is pure specification: official source, expected format,
frequency, and (where applicable) target-variable selection for every
dataset named in the project documents. It contains NO environment-specific
logic and NO network workarounds -- those live in `acquisition.py`. This
separation exists so that the dataset *definitions* remain valid and
unchanged regardless of what environment ultimately runs the acquisition
code (for reproducible dataset acquisition section: the module
shall be designed for a standard research environment with ordinary
internet access).

Each entry records exactly the official/widely-accepted public source --
never a substitute -- per DCF specification and the dataset-acquisition
approval. If a dataset cannot be sourced from its official location, that
is reported as a blocking issue (see acquisition.py), not silently
worked around by changing this registry.
"""



from __future__ import annotations



from dataclasses import dataclass, field

from typing import Callable, Optional





@dataclass(frozen=True)

class DatasetSpec:

    dataset_id: str

    display_name: str

    official_source_name: str

    official_source_url: str

    

    

    

    retrieval_url: str

    retrieval_format: str          

    native_frequency: str          

    is_multivariate: bool

    target_variable: Optional[str] = None   

    license_or_terms_url: Optional[str] = None

    citation: Optional[str] = None

    version_or_release_note: Optional[str] = None

    

    

    

    

    

    acquisition_status: str = "not_yet_acquired"

    

    

    

    

    

    

    

    notes: str = ""













CPIAUCSL = DatasetSpec(

    dataset_id="CPIAUCSL",

    display_name="Consumer Price Index for All Urban Consumers: All Items in U.S. City Average",

    official_source_name="FRED (Federal Reserve Bank of St. Louis), originating from the U.S. Bureau of Labor Statistics",

    official_source_url="https://fred.stlouisfed.org/series/CPIAUCSL",

    retrieval_url="https://fred.stlouisfed.org/graph/fredgraph.csv?id=CPIAUCSL",

    retrieval_format="csv",

    native_frequency="monthly",

    is_multivariate=False,

    target_variable=None,  

    license_or_terms_url="https://fred.stlouisfed.org/legal/",

    citation=(

        "U.S. Bureau of Labor Statistics, Consumer Price Index for All Urban "

        "Consumers: All Items in U.S. City Average [CPIAUCSL], retrieved from "

        "FRED, Federal Reserve Bank of St. Louis; https://fred.stlouisfed.org/series/CPIAUCSL."

    ),

    version_or_release_note=(

        "FRED series CPIAUCSL has no discrete version number. The series page "

        "reports a 'Last Updated' timestamp reflecting the most recent BLS "

        "revision/release; at time of v1.2.0 pilot acquisition this was "

        "2026-05-12 08:03 CDT, with reported date range 1947-01-01 to "

        "2026-04-01. CPI data are subject to routine revision by the BLS; "

        "the exact retrieval-time 'Last Updated' value is the closest "

        "available substitute for a version identifier and is recorded in "

        "the provenance record's dataset_version_or_release field. ALFRED "

        "(https://alfred.stlouisfed.org/series?seid=CPIAUCSL) provides "

        "point-in-time vintages of this series for anyone needing to "

        "reproduce the exact historical revision used here."

    ),

    notes="Single-series, monthly, seasonally adjusted.",

    acquisition_status="acquired_and_validated",

)















INDPRO = DatasetSpec(

    dataset_id="INDPRO",

    display_name="Industrial Production: Total Index",

    official_source_name="FRED (Federal Reserve Bank of St. Louis), originating from the Board of Governors of the Federal Reserve System (US)",

    official_source_url="https://fred.stlouisfed.org/series/INDPRO",

    retrieval_url="https://fred.stlouisfed.org/graph/fredgraph.csv?id=INDPRO",

    retrieval_format="csv",

    native_frequency="monthly",

    is_multivariate=False,

    license_or_terms_url="https://fred.stlouisfed.org/legal/",

    citation=(

        "Board of Governors of the Federal Reserve System (US), Industrial "

        "Production: Total Index [INDPRO], retrieved from FRED, Federal "

        "Reserve Bank of St. Louis; https://fred.stlouisfed.org/series/INDPRO."

    ),

    version_or_release_note=(

        "FRED series INDPRO has no discrete version number. Index base "

        "2017=100. Published as part of the G.17 Industrial Production and "

        "Capacity Utilization release, subject to routine revision. "

        "ALFRED (https://alfred.stlouisfed.org/series?seid=INDPRO) provides "

        "point-in-time vintages back to the first vintage (1927-01-26) for "

        "anyone needing to reproduce an exact historical revision."

    ),

    notes=(

        "Verified via web search prior to acquisition (matches DCF specification's "

        "dataset list). Single-series, monthly, seasonally adjusted."

    ),

    acquisition_status="acquired_and_validated",

)



WTI = DatasetSpec(

    dataset_id="WTI",

    display_name="Spot Crude Oil Price: West Texas Intermediate (WTI)",

    official_source_name="Federal Reserve Bank of St. Louis (FRED), constructed series combining two U.S. Energy Information Administration source series",

    official_source_url="https://fred.stlouisfed.org/series/WTISPLC",

    retrieval_url="https://fred.stlouisfed.org/graph/fredgraph.csv?id=WTISPLC",

    retrieval_format="csv",

    native_frequency="monthly",

    is_multivariate=False,

    license_or_terms_url="https://fred.stlouisfed.org/legal/",

    citation=(

        "Federal Reserve Bank of St. Louis, Spot Crude Oil Price: West Texas "

        "Intermediate (WTI) [WTISPLC], retrieved from FRED, Federal Reserve "

        "Bank of St. Louis; https://fred.stlouisfed.org/series/WTISPLC."

    ),

    version_or_release_note=(

        "IMPORTANT PROVENANCE NOTE verified via web search prior to "

        "acquisition: WTISPLC is not a single EIA-published series -- it is "

        "constructed by the Federal Reserve Bank of St. Louis itself by "

        "splicing two underlying FRED series to extend history: OILPRICE "

        "is used from January 1946 through July 2013, and MCOILWTICO from "

        "August 2013 to present. Both underlying series originate from the "

        "U.S. Energy Information Administration. This splice is disclosed "

        "by FRED on the series page itself, so WTISPLC remains an official, "

        "documented FRED series, not a third-party reconstruction -- but it "

        "is recorded here explicitly since 'WTI' could otherwise be assumed "

        "to be a single EIA series with no splice point. No discrete version "

        "number; subject to routine revision."

    ),

    notes="Series ID and splice construction verified via web search prior to acquisition.",

    acquisition_status="acquired_and_validated",

)



BRENT = DatasetSpec(

    dataset_id="Brent",

    display_name="Crude Oil Prices: Brent - Europe",

    official_source_name="FRED (Federal Reserve Bank of St. Louis), originating from the U.S. Energy Information Administration",

    official_source_url="https://fred.stlouisfed.org/series/DCOILBRENTEU",

    retrieval_url="https://fred.stlouisfed.org/graph/fredgraph.csv?id=DCOILBRENTEU",

    retrieval_format="csv",

    native_frequency="daily",

    is_multivariate=False,

    license_or_terms_url="https://fred.stlouisfed.org/legal/",

    citation=(

        "U.S. Energy Information Administration, Crude Oil Prices: Brent - "

        "Europe [DCOILBRENTEU], retrieved from FRED, Federal Reserve Bank "

        "of St. Louis; https://fred.stlouisfed.org/series/DCOILBRENTEU."

    ),

    notes=(

        "Registry entry retained for compatibility; not part of the final publication dataset set. "

        "Acquisition requires access to the registered public source."

    ),

    acquisition_status="deferred_large_dataset",

)



SP500 = DatasetSpec(

    dataset_id="SP500",

    display_name="S&P 500 Historical Prices",

    official_source_name="Yahoo Finance (widely accepted public source for historical equity index prices)",

    official_source_url="https://finance.yahoo.com/quote/%5EGSPC/history",

    retrieval_url="https://query1.finance.yahoo.com/v7/finance/download/%5EGSPC",

    retrieval_format="csv",

    native_frequency="daily",

    is_multivariate=False,

    notes=(

        "Registry entry retained for compatibility; not part of the final publication dataset set. "

        "Acquisition requires access to the registered public source."

    ),

    acquisition_status="deferred_large_dataset",

)











ECL = DatasetSpec(

    dataset_id="ECL",

    display_name="ElectricityLoadDiagrams20112014 (UCI ML Repository)",

    official_source_name="UCI Machine Learning Repository",

    official_source_url="https://archive.ics.uci.edu/dataset/321/electricityloaddiagrams20112014",

    retrieval_url="https://archive.ics.uci.edu/static/public/321/electricityloaddiagrams20112014.zip",

    retrieval_format="zip_containing_csv",

    native_frequency="15min",

    is_multivariate=True,

    target_variable="aggregate_sum_all_clients",

    license_or_terms_url="https://archive.ics.uci.edu/dataset/321/electricityloaddiagrams20112014",

    notes=(

        "370 Portuguese electricity client series at 15-minute resolution, "

        "2011-2014. Target variable: aggregate sum of all 370 clients "

        "(total electricity load). Pipeline aggregation: sum across all "

        "client columns, resample 15min -> hourly (mean), yielding ~35,040 "

        "hourly observations. Forecast horizon: 24 hours. "

        "Acquisition: ~250MB compressed binary ZIP from UCI ML Repository. "

        "In restricted network environments the raw file must be user-provided "

        "(copy to data/raw/ECL/ld2011_2014.txt and write provenance.json). "

        "The _prepare_ecl() function in data_preparation.py handles the "

        "tab-separated semicolon-decimal format used by this dataset. "

        "Citation: UCI ML Repository, dataset #321. "

        "Domain: Energy/Electricity -- genuinely distinct from commodity prices "

        "(WTI, Brent) and weather (Jena_Climate)."

    ),

    acquisition_status="ready_for_user_provided",

)















_SOLAR_DEPRECATED = DatasetSpec(

    dataset_id="Solar",

    display_name="[DEPRECATED — use Solar_Energy] Solar-Energy benchmark (Lai et al., 137 plants)",

    official_source_name="Originating repository accompanying Lai et al. (2018)",

    official_source_url="https://github.com/laiguokun/multivariate-time-series-data",

    retrieval_url="https://github.com/laiguokun/multivariate-time-series-data/raw/master/solar-energy/solar_AL.txt.gz",

    retrieval_format="gz_containing_csv",

    native_frequency="10min",

    is_multivariate=True,

    target_variable="aggregate_sum_all_plants",  

    notes=(

        "DEPRECATED. This entry used aggregate_sum_all_plants as the target, "

        "which has been superseded by the approved publication target "

        "mean_solar_production_all_plants (cross-series mean followed by hourly "

        "averaging). The active publication entry is SOLAR_ENERGY. This entry "

        "is not included in REGISTRY and cannot be selected via get_dataset_spec()."

    ),

    acquisition_status="deferred_large_dataset",

)



JENA_CLIMATE = DatasetSpec(

    dataset_id="Jena_Climate",

    display_name="Jena Climate Dataset (Max Planck Institute for Biogeochemistry)",

    official_source_name="Max Planck Institute for Biogeochemistry, Jena",

    official_source_url="https://www.bgc-jena.mpg.de/wetter/",

    retrieval_url="https://storage.googleapis.com/tensorflow/tf-keras-datasets/jena_climate_2009_2016.csv.zip",

    retrieval_format="csv",

    native_frequency="10min",

    is_multivariate=True,

    target_variable="T (degC)",

    notes=(

        "Climate domain dataset. 10-minute meteorological measurements from "

        "the MPI-BGC weather station, Jena, Germany, 2009-2016. Target "

        "variable: T (degC) (2-metre air temperature). Pipeline uses daily "

        "mean aggregation, yielding ~2921 daily observations. "

        "Provenance note: the user-uploaded file matches the widely-distributed "

        "Google/TensorFlow mirror. Whether to cite the MPI-BGC institutional "

        "source or the Google mirror is an open provenance question requiring "

        "confirmation before final publication (for the publication study)."

    ),

    acquisition_status="acquired_and_validated",

)



UNRATE = DatasetSpec(

    dataset_id="UNRATE",

    display_name="US Civilian Unemployment Rate (FRED)",

    official_source_name="U.S. Bureau of Labor Statistics via FRED",

    official_source_url="https://fred.stlouisfed.org/series/UNRATE",

    retrieval_url="https://fred.stlouisfed.org/graph/fredgraph.csv?id=UNRATE",

    retrieval_format="csv",

    native_frequency="monthly",

    is_multivariate=False,

    target_variable="UNRATE",

    notes=(

        "Monthly US civilian unemployment rate (%), seasonally adjusted. "

        "Available 1948-present. Bounded series [0, 25%], slow-moving, "

        "exhibits strong cyclicality following business cycles. "

        "Scientifically distinct from CPIAUCSL and INDPRO: bounded, "

        "mean-reverting over long horizons, highly persistent within "

        "recession/recovery cycles. Adds a third macroeconomic dataset "

        "with meaningfully different dynamics from prices (CPIAUCSL) "

        "and industrial activity (INDPRO). "

        "Acquisition: FRED CSV direct download, same format as CPIAUCSL/INDPRO "

        "(DATE, VALUE columns). Acquisition path: acquire_dataset('UNRATE')."

    ),

    acquisition_status="deferred_pending_acquisition",

)



NASDAQ = DatasetSpec(

    dataset_id="NASDAQ",

    display_name="NASDAQ Composite Index (FRED)",

    official_source_name="NASDAQ OMX Group via FRED",

    official_source_url="https://fred.stlouisfed.org/series/NASDAQCOM",

    retrieval_url="https://fred.stlouisfed.org/graph/fredgraph.csv?id=NASDAQCOM",

    retrieval_format="csv",

    native_frequency="daily",

    is_multivariate=False,

    target_variable="NASDAQCOM",

    notes=(

        "NASDAQ Composite daily closing index, 1971-present. Non-stationary "

        "trending series with high volatility, structural breaks at dotcom "

        "bubble and 2008 GFC. Domain: Finance/Equity. "

        "Scientific note: NASDAQ and SP500 are highly correlated (r > 0.95) "

        "over most periods. If both are included, the panel should acknowledge "

        "this correlation and reviewers may question the independence assumption. "

        "NASDAQ exhibits higher volatility and tech-sector concentration. "

        "Consider using one equity index and EUR/USD instead for better "

        "domain diversity. "

        "Acquisition: FRED CSV direct download."

    ),

    acquisition_status="deferred_pending_acquisition",

)



EUR_USD = DatasetSpec(

    dataset_id="EUR_USD",

    display_name="EUR/USD Exchange Rate (FRED)",

    official_source_name="Board of Governors of the Federal Reserve System via FRED",

    official_source_url="https://fred.stlouisfed.org/series/DEXUSEU",

    retrieval_url="https://fred.stlouisfed.org/graph/fredgraph.csv?id=DEXUSEU",

    retrieval_format="csv",

    native_frequency="daily",

    is_multivariate=False,

    target_variable="DEXUSEU",

    notes=(

        "EUR/USD daily exchange rate, 1999-present. Near-random-walk in "

        "levels, stationary in returns. Domain: Finance/FX. "

        "Scientifically distinct from equity indices (different data-generating "

        "process: FX rates driven by interest rate differentials and capital "

        "flows, not corporate earnings). Recommended over NASDAQ for the "

        "finance domain slot if avoiding within-domain correlation. "

        "Acquisition: FRED CSV direct download."

    ),

    acquisition_status="deferred_pending_acquisition",

)





HENRY_HUB = DatasetSpec(

    dataset_id="Henry_Hub",

    display_name="Henry Hub Natural Gas Spot Price (FRED / EIA)",

    official_source_name="U.S. Energy Information Administration via FRED",

    official_source_url="https://fred.stlouisfed.org/series/MHHNGSP",

    retrieval_url="https://fred.stlouisfed.org/graph/fredgraph.csv?id=MHHNGSP",

    retrieval_format="csv",

    native_frequency="monthly",

    is_multivariate=False,

    target_variable="MHHNGSP",

    notes=(

        "Monthly Henry Hub natural gas spot price, USD per million BTU. "

        "Available from January 1997 via FRED (series MHHNGSP). "

        "Domain: Energy/Commodity — genuinely distinct from crude oil (WTI) "

        "in its seasonal pattern (strong winter heating demand peak), "

        "supply shocks (US shale gas revolution ca. 2008-2012), and "

        "price formation mechanism (domestic US market, less globally "

        "integrated than crude oil). Adds meaningful domain diversity "

        "alongside WTI. "

        "Acquisition: FRED CSV direct download, same format as CPIAUCSL/INDPRO "

        "(DATE, VALUE columns). Path: acquire_dataset('Henry_Hub')."

    ),

    acquisition_status="deferred_pending_acquisition",

)



ELECTRICITY_SPOT = DatasetSpec(

    dataset_id="Electricity_Spot",

    display_name="US Average Retail Electricity Price (EIA / FRED)",

    official_source_name="U.S. Energy Information Administration via FRED",

    official_source_url="https://fred.stlouisfed.org/series/APU000072610",

    retrieval_url="https://fred.stlouisfed.org/graph/fredgraph.csv?id=APU000072610",

    retrieval_format="csv",

    native_frequency="monthly",

    is_multivariate=False,

    target_variable="APU000072610",

    notes=(

        "Monthly US average retail electricity price, cents per kWh "

        "(FRED series APU000072610, published by BLS from EIA data). "

        "Available from 1978. "

        "NOTE ON NAMING: The requested dataset 'Electricity Spot Price' likely "

        "refers to wholesale spot electricity prices (e.g. PJM, CAISO, MISO "

        "day-ahead markets). These are NOT available on FRED and require direct "

        "access to ISO/RTO APIs or commercial data providers (SNL Energy, "

        "Refinitiv, etc.). They are also hourly, highly volatile, and exhibit "

        "negative prices and extreme spikes that require special preprocessing. "

        "The FRED retail price series (monthly, smooth, publicly available) "

        "is a scientifically cleaner alternative. "

        "RECOMMENDATION: If the intent is 'electricity market data' that is "

        "genuinely distinct from ECL (load) and Henry Hub (gas prices), "

        "the retail price series is the pragmatic, reproducible choice. "

        "If true wholesale spot prices are required, acquisition from ISO APIs "

        "is a separate engineering task. "

        "Acquisition: FRED CSV direct download."

    ),

    acquisition_status="deferred_pending_acquisition",

)





REGISTRY: dict[str, DatasetSpec] = {

    spec.dataset_id: spec

    for spec in [

        

        CPIAUCSL, INDPRO, WTI, BRENT, ECL, JENA_CLIMATE,

        UNRATE, NASDAQ, EUR_USD, HENRY_HUB, ELECTRICITY_SPOT,

        

        

    ]

}































ETTH1 = DatasetSpec(

    dataset_id="ETTh1",

    display_name="Electricity Transformer Temperature – hourly h1 (Informer benchmark)",

    official_source_name="Informer paper (Zhou et al., 2021), zhouhaoyi/ETDataset on GitHub",

    official_source_url="https://github.com/zhouhaoyi/ETDataset",

    retrieval_url="https://github.com/zhouhaoyi/ETDataset/raw/main/ETT-small/ETTh1.csv",

    retrieval_format="csv",

    native_frequency="hourly",

    is_multivariate=False,

    target_variable="OT",

    notes=(

        "Hourly oil temperature of an electricity transformer, July 2016 – "

        "June 2018 (~17,420 observations). Widely adopted long-horizon "

        "forecasting benchmark (Informer, Autoformer, PatchTST). "

        "Target: OT (oil temperature, °C). "

        "File: date,HUFL,HULL,MUFL,MULL,LUFL,LULL,OT. "

        "OT column extracted by _prepare_etth1(). "

        "Modelling frequency: hourly, period: 24, horizon: 24. "

        "Domain: Energy."

    ),

    acquisition_status="deferred_pending_acquisition",

)



SOLAR_ENERGY = DatasetSpec(

    dataset_id="Solar_Energy",

    display_name="Solar Energy Production – Alabama 2006 (NREL / LSTNet benchmark)",

    official_source_name="NREL via LSTNet GitHub (Lai et al., 2018)",

    official_source_url="https://github.com/laiguokun/multivariate-time-series-data",

    retrieval_url="https://github.com/laiguokun/multivariate-time-series-data",

    retrieval_format="txt",

    native_frequency="hourly",

    is_multivariate=False,   

    target_variable="mean_solar_production_all_plants",

    notes=(

        "10-minute solar power production from 137 PV plants in Alabama, "

        "year 2006 (~8,760 hourly observations after pre-aggregation). "

        "Raw file: solar_AL.txt (~55 MB, multivariate). "

        "The researcher pre-aggregates using scripts/preprocess_solar.py: "

        "mean across 137 plants at each 10-min timestamp, then hourly mean. "

        "Target: mean recorded solar-production value across all 137 series, "

        "followed by hourly averaging. Not described as a capacity factor "

        "unless source units establish capacity normalisation. "

        "Pipeline input: Solar_hourly.csv (DATE, VALUE, ~180 KB). "

        "Modelling frequency: hourly, period: 24, horizon: 24. "

        "Domain: Energy."

    ),

    acquisition_status="deferred_pending_acquisition",

)



BEIJING_PM25 = DatasetSpec(

    dataset_id="Beijing_PM25",

    display_name="Beijing Dongsi Station PM2.5 daily means (UCI #501)",

    official_source_name="UCI ML Repository #501 (Zhang et al., 2017)",

    official_source_url="https://archive.ics.uci.edu/dataset/501",

    retrieval_url="https://archive.ics.uci.edu/dataset/501",

    retrieval_format="csv",

    native_frequency="daily",

    is_multivariate=False,   

    target_variable="PM2.5_daily_mean_Dongsi",

    notes=(

        "Hourly PM2.5 from 12 Beijing stations, March 2013 – February 2017. "

        "Station: Dongsi (central urban Beijing; selected before examining "

        "any forecasting results). "

        "The researcher pre-aggregates using scripts/preprocess_beijing_pm25.py: "

        "75% completeness threshold (day valid when >= 18/24 hourly readings "

        "are non-NaN); days below threshold are set to NaN. Conservative "

        "quality-control choice, not a regulatory requirement. "

        "After daily aggregation the frozen linear-interpolation handler is "

        "applied (max_gap=5). "

        "Pipeline input: Beijing_PM25_daily.csv (DATE, VALUE, ~50 KB). "

        "Modelling frequency: daily, period: 7, horizon: 7. "

        "Domain: Climate, Weather and Environment."

    ),

    acquisition_status="deferred_pending_acquisition",

)



ECL_PUB = DatasetSpec(

    dataset_id="ECL",

    display_name="ElectricityLoadDiagrams20112014 – avg aggregate hourly load (UCI #321)",

    official_source_name="UCI ML Repository #321",

    official_source_url="https://archive.ics.uci.edu/dataset/321/electricityloaddiagrams20112014",

    retrieval_url="https://archive.ics.uci.edu/static/public/321/electricityloaddiagrams20112014.zip",

    retrieval_format="zip_containing_txt",

    native_frequency="hourly",   

    is_multivariate=False,       

    target_variable="avg_aggregate_hourly_load_kW",

    notes=(

        "370 Portuguese electricity client series at 15-minute resolution, "

        "January 2011 – December 2014. Raw file: ld2011_2014.txt (~600 MB). "

        "The researcher pre-aggregates using scripts/preprocess_ecl.py: "

        "(1) sum all 370 client columns at each 15-min timestamp, "

        "(2) take the hourly mean → average aggregate hourly load in kW. "

        "This is the approved target definition. "

        "Pipeline input: ECL_hourly.csv (DATE, VALUE, ~700 KB). "

        "Raw frequency: 15-min. Modelling frequency: hourly. "

        "Seasonal period: 24. Forecast horizon: 24. "

        "Domain: Energy."

    ),

    license_or_terms_url="https://archive.ics.uci.edu/dataset/321/electricityloaddiagrams20112014",

    acquisition_status="ready_for_user_provided",

)



SP500_PUB = DatasetSpec(

    dataset_id="SP500",

    display_name="S&P 500 Index daily closing level (FRED)",

    official_source_name="S&P Dow Jones Indices via FRED",

    official_source_url="https://fred.stlouisfed.org/series/SP500",

    retrieval_url="https://fred.stlouisfed.org/graph/fredgraph.csv?id=SP500",

    retrieval_format="csv",

    native_frequency="business_day",

    is_multivariate=False,

    target_variable="SP500",

    notes=(

        "Daily S&P 500 closing level, FRED series SP500 (from Jan 2013, "

        "~3,000 business-day observations). "

        "FRED CSV marks weekends and market holidays as '.' (NaN). "

        "These structurally absent non-trading days are dropped as part of "

        "target construction, yielding a business-day series. "

        "Genuine missing business-day observations (data-feed outages on a "

        "trading day) are handled separately by the frozen linear-interpolation "

        "policy (max_gap=5). "

        "Seasonal period: 5 (one trading week). Horizon: 5. "

        "Domain: Financial and Commodity Markets."

    ),

    acquisition_status="deferred_pending_acquisition",

)



EUR_USD_PUB = DatasetSpec(

    dataset_id="EUR_USD",

    display_name="EUR/USD daily exchange rate – noon buying rate (FRED)",

    official_source_name="Federal Reserve Board via FRED",

    official_source_url="https://fred.stlouisfed.org/series/DEXUSEU",

    retrieval_url="https://fred.stlouisfed.org/graph/fredgraph.csv?id=DEXUSEU",

    retrieval_format="csv",

    native_frequency="business_day",

    is_multivariate=False,

    target_variable="DEXUSEU",

    notes=(

        "EUR/USD noon buying rate, FRED series DEXUSEU (from Jan 1999, "

        "~6,500 business-day observations). "

        "Near-random-walk in levels; stationary in log-returns. "

        "Weekends and holidays are structurally absent (NaN in FRED CSV); "

        "dropped during target construction. "

        "Seasonal period: 5. Horizon: 5. "

        "Domain: Financial and Commodity Markets."

    ),

    acquisition_status="deferred_pending_acquisition",

)















APPLIANCES_ENERGY = DatasetSpec(

    dataset_id="Appliances_Energy",

    display_name="UCI Appliances Energy Prediction — Residential Hourly Load (UCI #374)",

    official_source_name="UCI Machine Learning Repository, Dataset #374",

    official_source_url="https://archive.ics.uci.edu/dataset/374/appliances+energy+prediction",

    retrieval_url="https://raw.githubusercontent.com/LuisM78/Appliances-energy-prediction-data/master/energydata_complete.csv",

    retrieval_format="csv",

    native_frequency="hourly",

    is_multivariate=False,

    target_variable="Appliances",

    license_or_terms_url="https://archive.ics.uci.edu/dataset/374/appliances+energy+prediction",

    citation=(

        "Luis M. Candanedo, Veronique Feldheim, Dominique Deramaix, "

        "Data driven prediction models of energy use of appliances in a low-energy house, "

        "Energy and Buildings, Volume 140, 1 April 2017, Pages 81-97, "

        "ISSN 0378-7788, doi:10.1016/j.enbuild.2017.01.083."

    ),

    acquisition_status="acquired_and_validated",

    notes=(

        "ECL replacement dataset. "

        "19,735 10-minute rows spanning 2016-01-11 to 2016-05-27 (~4.5 months). "

        "Target: Appliances column — energy use of household appliances in Wh per "

        "10-minute interval, logged by m-bus energy meters. "

        "Preparation: sum 6 consecutive 10-minute Appliances values per complete "

        "calendar hour (Wh is extensive: sum preserves total hourly energy). "

        "Partial boundary hours excluded deterministically. "

        "Prepared series: 3289 hourly rows, DATE/VALUE format. "

        "Raw file: energydata_complete.csv (11,979,363 bytes). "

        "SHA-256 (raw): 2820bf712ad0275cb18b85a05250926100d8e65ebb9f4d2d016ca91ea152a25d. "

        "SHA-256 (prepared): 94776549d735dda52303ed786c1e1bee84715478e89142be0e32b0e4f85f2981. "

        "Seasonal period: 24 (hourly, daily cycle). Horizon: 24. "

        "Domain: Energy / residential smart-home."

    ),

)















BIKE_SHARING = DatasetSpec(

    dataset_id="Bike_Sharing",

    display_name="UCI Bike Sharing Dataset #275 — Daily Total Rentals",

    official_source_name="UCI Machine Learning Repository, Dataset #275",

    official_source_url="https://archive.ics.uci.edu/dataset/275/bike+sharing+dataset",

    retrieval_url="https://archive.ics.uci.edu/dataset/275/bike+sharing+dataset",

    retrieval_format="csv",

    native_frequency="daily",

    is_multivariate=False,

    target_variable="cnt",

    license_or_terms_url="https://archive.ics.uci.edu/dataset/275",

    citation="Fanaee-T, H., & Gama, J. (2014). Event labeling combining ensemble detectors and background knowledge. Progress in Artificial Intelligence, 2(2-3), 113-127.",

    acquisition_status="acquired_and_validated",

    notes="Dataset. 731 daily rows 2011-01-01 to 2012-12-31. SHA-256: a6bcf826... Sourced via bundle (mirror acquisition noted in provenance).",

)



MAUNA_LOA_CO2 = DatasetSpec(

    dataset_id="Mauna_Loa_CO2",

    display_name="NOAA GML Mauna Loa Monthly CO2 — Official Series",

    official_source_name="NOAA Global Monitoring Laboratory",

    official_source_url="https://gml.noaa.gov/ccgg/trends/",

    retrieval_url="https://gml.noaa.gov/webdata/ccgg/trends/co2/co2_mm_mlo.csv",

    retrieval_format="csv",

    native_frequency="monthly",

    is_multivariate=False,

    target_variable="average",

    license_or_terms_url="https://gml.noaa.gov/ccgg/trends/",

    citation="Dr. Pieter Tans, NOAA/GML and Dr. Ralph Keeling, Scripps Institution of Oceanography.",

    acquisition_status="acquired_and_validated",

    notes="Dataset. 821 monthly rows 1958-03 to 2026-07. SHA-256: eb751e4e... Target: average column (measured mean CO2 ppm).",

)



SILSO_SUNSPOTS = DatasetSpec(

    dataset_id="SILSO_Sunspots",

    display_name="SILSO Monthly Total Sunspot Number V2.0",

    official_source_name="SILSO World Data Center, Royal Observatory of Belgium",

    official_source_url="https://www.sidc.be/SILSO/datafiles",

    retrieval_url="https://www.sidc.be/SILSO/DATA/SN_m_tot_V2.0.csv",

    retrieval_format="csv",

    native_frequency="monthly",

    is_multivariate=False,

    target_variable="monthly_mean_total_sunspot_number",

    license_or_terms_url="https://www.sidc.be/SILSO/datafiles",

    citation="SILSO World Data Center. International Sunspot Number Monthly Bulletin. Royal Observatory of Belgium.",

    acquisition_status="acquired_and_validated",

    notes="Dataset. 3331 rows 1749-01 to 2026-07. SHA-256: a78640e2... Semicolon-delimited, no header. Target=col index 3. License: CC BY-NC 4.0.",

)













EIA_ENERGY_PRODUCTION = DatasetSpec(

    dataset_id="EIA_Energy_Production",

    display_name="EIA Total U.S. Primary Energy Production — Monthly",

    official_source_name="U.S. Energy Information Administration, Monthly Energy Review, Table 1.2",

    official_source_url="https://www.eia.gov/totalenergy/data/monthly/",

    retrieval_url="https://www.eia.gov/totalenergy/data/monthly/",

    retrieval_format="csv",

    native_frequency="monthly",

    is_multivariate=False,

    target_variable="TEPRBUS",

    license_or_terms_url="https://www.eia.gov/totalenergy/data/monthly/",

    citation="U.S. Energy Information Administration, Monthly Energy Review, Table 1.2: Primary Energy Production by Source.",

    acquisition_status="acquired_and_validated",

    notes="Dataset. 640 monthly rows 1973-01 to 2026-04. MSN=TEPRBUS. SHA-256: aefb5efb...",

)



FAO_FOOD_PRICE = DatasetSpec(

    dataset_id="FAO_Food_Price",

    display_name="FAO Food Price Index — Monthly Nominal Overall Index",

    official_source_name="Food and Agriculture Organization of the United Nations",

    official_source_url="https://www.fao.org/world-food-situation/foodpricesindex/en/",

    retrieval_url="https://www.fao.org/world-food-situation/foodpricesindex/en/",

    retrieval_format="xlsx",

    native_frequency="monthly",

    is_multivariate=False,

    target_variable="Food Price Index",

    license_or_terms_url="https://www.fao.org/world-food-situation/foodpricesindex/en/",

    citation="FAO Food Price Index. Food and Agriculture Organization of the United Nations.",

    acquisition_status="acquired_and_validated",

    notes="Dataset. 439 monthly rows 1990-01 to 2026-07. Sheet Indices_Monthly_Nominal. SHA-256: 75f93e73...",

)



KEY_WEST_WATER = DatasetSpec(

    dataset_id="Key_West_Water",

    display_name="NOAA Key West Monthly Mean Water Level, MSL, Metric",

    official_source_name="NOAA CO-OPS, Station 8724580",

    official_source_url="https://api.tidesandcurrents.noaa.gov/api/prod/datagetter",

    retrieval_url="https://api.tidesandcurrents.noaa.gov/api/prod/datagetter",

    retrieval_format="csv",

    native_frequency="monthly",

    is_multivariate=False,

    target_variable="MSL",

    license_or_terms_url="https://tidesandcurrents.noaa.gov/",

    citation="NOAA Center for Operational Oceanographic Products and Services. Station 8724580, Key West, FL.",

    acquisition_status="acquired_and_validated",

    notes="Reserve dataset. 1352 supplied rows 1913-01 to 2026-07. 11 absent calendar months. SHA-256: 939711d0...",

)



PUBLICATION_REGISTRY: dict[str, DatasetSpec] = {

    spec.dataset_id: spec

    for spec in [

        

        CPIAUCSL, INDPRO, WTI, JENA_CLIMATE,

        APPLIANCES_ENERGY, SOLAR_ENERGY, ETTH1, BEIJING_PM25, SP500_PUB, EUR_USD_PUB,

        

        BRENT, UNRATE, NASDAQ, HENRY_HUB, ELECTRICITY_SPOT,

    ]

}







REGISTRY.update(PUBLICATION_REGISTRY)

REGISTRY["Bike_Sharing"] = BIKE_SHARING

REGISTRY["Mauna_Loa_CO2"] = MAUNA_LOA_CO2

REGISTRY["SILSO_Sunspots"] = SILSO_SUNSPOTS

REGISTRY["EIA_Energy_Production"] = EIA_ENERGY_PRODUCTION

REGISTRY["FAO_Food_Price"] = FAO_FOOD_PRICE

REGISTRY["Key_West_Water"] = KEY_WEST_WATER











PUBLICATION_DATASETS: list[str] = [

    "CPIAUCSL",
    "INDPRO",
    "WTI",
    "Jena_Climate",
    "Beijing_PM25",
    "SP500",
    "EUR_USD",
    "Bike_Sharing",
    "EIA_Energy_Production",
    "FAO_Food_Price",

]





def get_dataset_spec(dataset_id: str) -> DatasetSpec:

    if dataset_id not in REGISTRY:

        raise KeyError(

            f"Dataset ID '{dataset_id}' is not in the registry. "

            f"Known IDs: {sorted(REGISTRY.keys())}"

        )

    return REGISTRY[dataset_id]





def datasets_by_status(status: str) -> list:

    """Return dataset_ids whose acquisition_status matches `status`."""

    return [spec.dataset_id for spec in REGISTRY.values() if spec.acquisition_status == status]





def acquisition_status_summary() -> dict:

    """Return a dict of status -> list of dataset_ids, for reporting."""

    summary: dict = {}

    for spec in REGISTRY.values():

        summary.setdefault(spec.acquisition_status, []).append(spec.dataset_id)

    for ids in summary.values():

        ids.sort()

    return summary





__all__ = [

    "DatasetSpec", "REGISTRY", "PUBLICATION_REGISTRY", "PUBLICATION_DATASETS",

    "get_dataset_spec", "datasets_by_status", "acquisition_status_summary",

    "CPIAUCSL", "INDPRO", "WTI", "JENA_CLIMATE",

    "ECL_PUB", "SOLAR_ENERGY", "ETTH1", "BEIJING_PM25", "SP500_PUB", "EUR_USD_PUB",

    "BRENT", "UNRATE", "NASDAQ", "HENRY_HUB", "ELECTRICITY_SPOT",

]



