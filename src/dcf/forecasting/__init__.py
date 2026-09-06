"""
dcf.forecasting

The Forecasting Layer (DCF specification): model adapters,
rolling-origin execution harness, and the configurable model registry.
"""



from dcf.forecasting._base import (

    ForecastingModelError,

    ModelForecastResult,

    OriginForecastResult,

    run_rolling_origin_forecast,

)

from dcf.forecasting.registry import build_model_registry



__all__ = [

    "ForecastingModelError",

    "ModelForecastResult",

    "OriginForecastResult",

    "run_rolling_origin_forecast",

    "build_model_registry",

]

