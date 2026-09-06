"""
forecasting/registry.py

The Forecasting Model Registry (DCF specification, "Model
Registry"): a configurable mapping from model name to adapter factory.
"Additional forecasting models may be added through the model registry
without modifying the framework architecture" -- this module is exactly
that extension point.

Every entry's enabled/disabled state and hyperparameters come from the
frozen config (forecasting.models.<name>), never hardcoded here.
"""



from __future__ import annotations



from dcf.config import get_config

from dcf.forecasting.baselines import drift_fit_predict, make_seasonal_naive_adapter, naive_fit_predict

from dcf.forecasting.dl_models import make_gru_adapter, make_lstm_adapter, make_tcn_adapter

from dcf.forecasting.ml_models import make_random_forest_adapter, make_svr_adapter, make_xgboost_adapter

from dcf.forecasting.statistical_models import make_arima_adapter, make_ets_adapter, make_sarima_adapter





def build_model_registry(frequency_key, dataset_id="", config=None):

    """
    Build the full registry of {model_name: {...}} for one dataset's
    frequency, including only models enabled in config. The Domain
    Profile is never passed to or accessible from any factory here --
    per DCF specification / DCF design, this function's
    signature has no parameter for one, by design.
    """

    cfg = config or get_config(allow_draft=False)

    models_cfg = cfg.get("forecasting.models", {})



    registry = {}



    if models_cfg.get("naive", {}).get("enabled", True):

        registry["naive"] = {"fit_predict": naive_fit_predict, "selected_order_holder": None}



    if models_cfg.get("seasonal_naive", {}).get("enabled", True):

        registry["seasonal_naive"] = {

            "fit_predict": make_seasonal_naive_adapter(frequency_key, config=cfg),

            "selected_order_holder": None,

        }



    if models_cfg.get("drift", {}).get("enabled", True):

        registry["drift"] = {"fit_predict": drift_fit_predict, "selected_order_holder": None}



    if models_cfg.get("arima", {}).get("enabled", True):

        fn, holder = make_arima_adapter(dataset_id=dataset_id, config=cfg)

        registry["arima"] = {"fit_predict": fn, "selected_order_holder": holder}



    if models_cfg.get("sarima", {}).get("enabled", True):

        fn, holder = make_sarima_adapter(frequency_key, dataset_id=dataset_id, config=cfg)

        registry["sarima"] = {"fit_predict": fn, "selected_order_holder": holder}



    if models_cfg.get("ets", {}).get("enabled", True):

        fn, holder = make_ets_adapter(frequency_key, dataset_id=dataset_id, config=cfg)

        registry["ets"] = {"fit_predict": fn, "selected_order_holder": holder}



    if models_cfg.get("random_forest", {}).get("enabled", True):

        registry["random_forest"] = {

            "fit_predict": make_random_forest_adapter(config=cfg),

            "selected_order_holder": None,

        }



    if models_cfg.get("xgboost", {}).get("enabled", True):

        registry["xgboost"] = {

            "fit_predict": make_xgboost_adapter(config=cfg),

            "selected_order_holder": None,

        }



    if models_cfg.get("svr", {}).get("enabled", True):

        registry["svr"] = {"fit_predict": make_svr_adapter(config=cfg), "selected_order_holder": None}



    if models_cfg.get("lstm", {}).get("enabled", True):

        registry["lstm"] = {"fit_predict": make_lstm_adapter(config=cfg), "selected_order_holder": None}



    if models_cfg.get("gru", {}).get("enabled", True):

        registry["gru"] = {"fit_predict": make_gru_adapter(config=cfg), "selected_order_holder": None}



    if models_cfg.get("tcn", {}).get("enabled", True):

        registry["tcn"] = {"fit_predict": make_tcn_adapter(config=cfg), "selected_order_holder": None}



    return registry





__all__ = ["build_model_registry"]

