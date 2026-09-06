"""
exception_context.py  —  DCF v1.2.0 structured exception transport

Provides the ExternalDependencyError exception and the private
_raise_if_external_api_error() boundary factory, used at reviewed
external-dependency call sites in the forecasting adapters.

Design constraints:
  - _raise_if_external_api_error is PRIVATE (underscore prefix).
  - It is not exported in __all__ and must not be imported as a public API.
  - ExternalDependencyError.classification must come from the closed set.
  - AttributeError at an adapter boundary always -> failed (not technically_unevaluable).
  - Broad generic TypeError/AttributeError classification is prohibited.
  - technically_unevaluable is reserved for the structured ExternalDependencyError
    path only; ordinary numerical/convergence/data/model failures remain failed.

Reviewed external-boundary call sites (12 total across adapters):
  - statistical_models.py: ARIMA pm.auto_arima(), ARIMA predict(),
    SARIMA pm.auto_arima(), SARIMA predict(), ETS fit(), ETS predict()
  - ml_models.py: RF fit(), RF predict(), XGB fit(), XGB predict(), SVR fit(), SVR predict()
  - dl_models.py: LSTM forward(), GRU forward(), TCN forward()
  (DL adapters use torch; their forward() calls share one reviewed boundary)
"""



from __future__ import annotations



__all__ = ["ExternalDependencyError"]





_VALID_CLASSIFICATIONS = frozenset({

    "import_error",

    "api_signature_change",

    "configuration_error",

    "data_contract_violation",

    "schema_error",

    "external_package_error",

})





class ExternalDependencyError(Exception):

    """
    Raised at reviewed external-dependency boundaries when a structured
    classification is available.

    classification must be one of the closed set in _VALID_CLASSIFICATIONS.
    Not raised for ordinary numerical, convergence, or model failures
    (those propagate as standard exceptions -> failed status).
    """



    def __init__(self, classification: str, detail: str = "", boundary_id: str = ""):

        if classification not in _VALID_CLASSIFICATIONS:

            raise ValueError(

                f"ExternalDependencyError: unknown classification '{classification}'. "

                f"Must be one of {sorted(_VALID_CLASSIFICATIONS)}"

            )

        self.classification = classification

        self.detail = detail

        self.boundary_id = boundary_id

        super().__init__(f"{classification}: {detail} [boundary={boundary_id}]")





def _raise_if_external_api_error(model_id: str, exc: Exception, boundary_id: str) -> None:

    """
    PRIVATE boundary factory. Inspects exc and raises ExternalDependencyError
    if the failure pattern matches a known external-API structural failure.

    Rules:
      - AttributeError at an external boundary: always -> failed, NOT
        technically_unevaluable. Do not classify AttributeError as
        ExternalDependencyError.
      - ImportError / ModuleNotFoundError: -> ExternalDependencyError("import_error")
      - TypeError matching known API-signature patterns: ->
        ExternalDependencyError("api_signature_change")
      - All other exceptions: re-raise as-is (not wrapped).

    The caller (adapter) wraps its external call in try/except and calls
    this function in the except block. If this function does not raise,
    the caller should re-raise the original exception.
    """

    

    if isinstance(exc, AttributeError):

        return  



    

    if isinstance(exc, (ImportError, ModuleNotFoundError)):

        raise ExternalDependencyError(

            "import_error",

            f"model={model_id}: {exc}",

            boundary_id=boundary_id,

        ) from exc



    

    

    if isinstance(exc, TypeError):

        msg = str(exc).lower()

        if any(kw in msg for kw in ("force_all_finite", "unexpected keyword", "got an unexpected")):

            raise ExternalDependencyError(

                "api_signature_change",

                f"model={model_id}: API signature incompatibility: {exc}",

                boundary_id=boundary_id,

            ) from exc



    

    return

