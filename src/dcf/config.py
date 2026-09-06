"""
config.py

Configuration loader for the Domain Characterization Framework.

Loads `configs/version1_defaults.yaml` (or an explicitly supplied path),
validates the file is not still in draft status once v1.2.0+ work begins,
and exposes a single `Config` object used throughout the pipeline.

Design intent (per DCF design. This module is the single point of access to those values so that
every module reads the same frozen specification.

Usage
-----
    from dcf.config import get_config

    cfg = get_config()
    seed = cfg.get("reproducibility.global_random_seed")
    pelt_penalty = cfg.get("characterization.structural_change.pelt_penalty")

Dotted-path access (`cfg.get("a.b.c")`) is supported for convenience;
the raw dict is also available via `cfg.raw`.
"""



from __future__ import annotations



import copy

import threading

from pathlib import Path

from typing import Any, Optional



import yaml



PROJECT_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_CONFIG_PATH = PROJECT_ROOT / "configs" / "version1_defaults.yaml"



_ALLOWED_DRAFT_STATUSES = {"DRAFT_PENDING_APPROVAL"}

_APPROVED_STATUSES = {"FROZEN_APPROVED"}





class ConfigError(Exception):

    """Raised for configuration loading or validation failures."""





class Config:

    """
    Immutable-by-convention wrapper around the loaded configuration dict.

    The dict is deep-copied on load so that callers mutating a returned
    sub-dict cannot accidentally corrupt the shared configuration object.
    """



    def __init__(self, data: dict, source_path: Path):

        self._data = data

        self._source_path = source_path



    @property

    def raw(self) -> dict:

        """Deep copy of the full configuration dict."""

        return copy.deepcopy(self._data)



    @property

    def source_path(self) -> Path:

        return self._source_path



    @property

    def version(self) -> str:

        return self._data.get("version", "UNKNOWN")



    @property

    def status(self) -> str:

        return self._data.get("status", "UNKNOWN")



    @property

    def is_approved(self) -> bool:

        return self.status in _APPROVED_STATUSES



    def get(self, dotted_path: str, default: Any = None) -> Any:

        """
        Retrieve a value by dotted path, e.g. "stl.default_periods_by_frequency.monthly".

        Returns `default` if any segment of the path is missing, rather
        than raising — callers that require a value to exist should
        check explicitly or use `require`.
        """

        node: Any = self._data

        for segment in dotted_path.split("."):

            if isinstance(node, dict) and segment in node:

                node = node[segment]

            else:

                return default

        return copy.deepcopy(node)



    def require(self, dotted_path: str) -> Any:

        """Like `get`, but raises ConfigError if the path is not present."""

        _MISSING = object()

        value = self.get(dotted_path, default=_MISSING)

        if value is _MISSING:

            raise ConfigError(

                f"Required configuration path '{dotted_path}' is missing from "

                f"{self._source_path}."

            )

        return value



    def __repr__(self) -> str:

        return f"<Config version={self.version!r} status={self.status!r} source={self._source_path}>"





_lock = threading.Lock()

_config_singleton: Optional[Config] = None





def load_config(path: Optional[Path] = None, allow_draft: bool = True) -> Config:

    """
    Load configuration from `path` (default: configs/version1_defaults.yaml).

    Parameters
    ----------
    path:
        Explicit path to a YAML config file. Defaults to the publication
        defaults file shipped with the project.
    allow_draft:
        If False, raises ConfigError when the loaded file's `status` field
        is not an approved status. Set this to False from v1.2.0 onward
        once the defaults file has been reviewed and approved, so that
        accidental use of an un-approved draft configuration is caught
        immediately rather than silently producing results under
        unapproved assumptions.

    Returns
    -------
    Config
        Wrapped configuration object. Does not mutate the module-level
        singleton; use `get_config()` for that.
    """

    config_path = Path(path) if path is not None else DEFAULT_CONFIG_PATH



    if not config_path.exists():

        raise ConfigError(f"Configuration file not found: {config_path}")



    with open(config_path, "r") as f:

        data = yaml.safe_load(f)



    if not isinstance(data, dict):

        raise ConfigError(f"Configuration file {config_path} did not parse to a mapping.")



    status = data.get("status", "UNKNOWN")

    if status not in _ALLOWED_DRAFT_STATUSES and status not in _APPROVED_STATUSES:

        raise ConfigError(

            f"Configuration file {config_path} has unrecognized status '{status}'. "

            f"Expected one of {_ALLOWED_DRAFT_STATUSES | _APPROVED_STATUSES}."

        )



    if not allow_draft and status in _ALLOWED_DRAFT_STATUSES:

        raise ConfigError(

            f"Configuration file {config_path} is still status='{status}'. "

            "It must be reviewed and its status updated to an approved value "

            "(e.g. 'FROZEN_APPROVED') before v1.2.0 (data preparation) or any "

            "later phase may proceed. Refusing to load a draft configuration "

            "for non-draft use."

        )



    return Config(data=data, source_path=config_path)





def get_config(path: Optional[Path] = None, allow_draft: bool = True, force_reload: bool = False) -> Config:

    """
    Return the process-wide Config singleton, loading it on first call.

    Subsequent calls return the cached instance unless `force_reload=True`
    or a different `path` is supplied (in which case the singleton is
    replaced — primarily useful for tests).
    """

    global _config_singleton

    with _lock:

        if (

            _config_singleton is None

            or force_reload

            or (path is not None and Path(path) != _config_singleton.source_path)

        ):

            _config_singleton = load_config(path=path, allow_draft=allow_draft)

        return _config_singleton





def reset_config_singleton() -> None:

    """Clear the cached singleton. Intended for use in tests only."""

    global _config_singleton

    with _lock:

        _config_singleton = None





__all__ = [

    "Config",

    "ConfigError",

    "load_config",

    "get_config",

    "reset_config_singleton",

    "DEFAULT_CONFIG_PATH",

    "PROJECT_ROOT",

]

