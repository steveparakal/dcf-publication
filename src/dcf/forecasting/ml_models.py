"""
forecasting/ml_models.py

Random Forest, XGBoost, and SVR forecasting model adapters (Coding
Package Section 15, "Machine Learning Models").

These tree/kernel models are not natively sequential, so each adapter
converts the series into a supervised lag-feature regression problem
using the lag set frozen in config (forecasting.models.<name>.lag_features,
currently [1,2,3,4,5,6,7,12] for all three ML models).

IMPORTANT ARCHITECTURAL NOTE (DCF specification / DCF specification
v1.2.0): these lag features are constructed FROM THE RAW TARGET
SERIES ONLY. They are NOT derived from, and do not include, any
characterization measure or Domain Profile component. "Lag-1 value" is
not "Persistence Score" -- the former is a raw input value used for
supervised-regression framing, the latter is a Stage-2 analytical output
that this layer must never consume.

Multi-step forecasting strategy: RECURSIVE. Each model is trained once
per origin to predict one step ahead; to produce a full horizon, the
model's own prior predictions are fed back in as lag features for
subsequent steps. No alternative multi-step strategy is specified in the publication
configuration, so recursive single-step framing is the implementation
default used here.
"""



from __future__ import annotations



import numpy as np

import pandas as pd

from sklearn.ensemble import RandomForestRegressor

from sklearn.preprocessing import StandardScaler

from sklearn.svm import SVR



from dcf.config import get_config

from dcf.forecasting.exception_context import ExternalDependencyError, _raise_if_external_api_error





def _build_lag_feature_matrix(series, lag_features):

    max_lag = max(lag_features)

    values = series.to_numpy()

    n = len(values)



    rows = []

    targets = []

    for i in range(max_lag, n):

        row = [values[i - lag] for lag in lag_features]

        rows.append(row)

        targets.append(values[i])



    return np.array(rows, dtype=float), np.array(targets, dtype=float)





def _recursive_forecast(model, history, lag_features, horizon, scaler=None):

    max_lag = max(lag_features)

    working_history = list(history[-max_lag:]) if len(history) >= max_lag else list(history)

    while len(working_history) < max_lag:

        working_history.insert(0, working_history[0] if working_history else 0.0)



    predictions = []

    for _ in range(horizon):

        row = np.array([[working_history[-lag] for lag in lag_features]], dtype=float)

        if scaler is not None:

            row = scaler.transform(row)

        pred = float(model.predict(row)[0])

        predictions.append(pred)

        working_history.append(pred)



    return np.array(predictions, dtype=float)





def make_random_forest_adapter(config=None):

    cfg = config or get_config(allow_draft=False)

    params = cfg.get("forecasting.models.random_forest", {})

    lag_features = params.get("lag_features", [1, 2, 3, 4, 5, 6, 7, 12])

    seed = cfg.get("reproducibility.global_random_seed", 42)



    def _fit_predict(train, horizon):

        X, y = _build_lag_feature_matrix(train, lag_features)

        if len(X) == 0:

            raise ValueError(

                f"Random Forest: training window (n={len(train)}) is shorter than "

                f"the maximum configured lag ({max(lag_features)}); cannot build "

                "any supervised-regression rows."

            )

        model = RandomForestRegressor(

            n_estimators=params.get("n_estimators", 300),

            max_depth=params.get("max_depth", None),

            min_samples_leaf=params.get("min_samples_leaf", 2),

            n_jobs=params.get("n_jobs", 1),

            random_state=seed,

        )

        try:

            model.fit(X, y)

        except Exception as exc:

            _raise_if_external_api_error("random_forest", exc, "rf.fit")

            raise

        return _recursive_forecast(model, train.to_numpy(), lag_features, horizon)



    return _fit_predict





def make_svr_adapter(config=None):

    cfg = config or get_config(allow_draft=False)

    params = cfg.get("forecasting.models.svr", {})

    lag_features = params.get("lag_features", [1, 2, 3, 4, 5, 6, 7, 12])



    def _fit_predict(train, horizon):

        X, y = _build_lag_feature_matrix(train, lag_features)

        if len(X) == 0:

            raise ValueError(

                f"SVR: training window (n={len(train)}) is shorter than the "

                f"maximum configured lag ({max(lag_features)}); cannot build "

                "any supervised-regression rows."

            )



        scaler = StandardScaler()

        X_scaled = scaler.fit_transform(X)



        model = SVR(

            kernel=params.get("kernel", "rbf"),

            C=params.get("C", 10.0),

            epsilon=params.get("epsilon", 0.1),

            gamma=params.get("gamma", "scale"),

        )

        try:

            model.fit(X_scaled, y)

        except Exception as exc:

            _raise_if_external_api_error("svr", exc, "svr.fit")

            raise

        return _recursive_forecast(model, train.to_numpy(), lag_features, horizon, scaler=scaler)



    return _fit_predict





def make_xgboost_adapter(config=None):

    cfg = config or get_config(allow_draft=False)

    params = cfg.get("forecasting.models.xgboost", {})

    lag_features = params.get("lag_features", [1, 2, 3, 4, 5, 6, 7, 12])

    seed = cfg.get("reproducibility.global_random_seed", 42)



    def _fit_predict(train, horizon):

        try:

            import xgboost as xgb

        except ImportError as exc:

            _raise_if_external_api_error("xgboost", exc, "xgboost.import")

            raise



        X, y = _build_lag_feature_matrix(train, lag_features)

        if len(X) == 0:

            raise ValueError(

                f"XGBoost: training window (n={len(train)}) is shorter than the "

                f"maximum configured lag ({max(lag_features)}); cannot build "

                "any supervised-regression rows."

            )



        model = xgb.XGBRegressor(

            n_estimators=params.get("n_estimators", 300),

            max_depth=params.get("max_depth", 6),

            learning_rate=params.get("learning_rate", 0.05),

            subsample=params.get("subsample", 0.9),

            colsample_bytree=params.get("colsample_bytree", 0.9),

            n_jobs=params.get("n_jobs", 1),

            random_state=seed,

        )

        try:

            model.fit(X, y)

        except Exception as exc:

            _raise_if_external_api_error("xgboost", exc, "xgboost.fit")

            raise

        return _recursive_forecast(model, train.to_numpy(), lag_features, horizon)



    return _fit_predict





__all__ = ["make_random_forest_adapter", "make_svr_adapter", "make_xgboost_adapter"]

