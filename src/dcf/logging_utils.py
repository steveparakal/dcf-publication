"""
logging_utils.py

Four-stream logging architecture required by DCF specification.

Streams
-------
1. Execution Log   — pipeline-level progress: stage entry/exit, dataset
                      processed, timing. One line per significant event.
2. Experiment Log   — scientific record of what was run: dataset IDs,
                      experiment ID, parameters used, models run. This is
                      the log a reviewer would want to audit.
3. Error Log        — failures, exceptions, and recoverable warnings.
                      Per DCF design: failures are reported,
                      never silently swallowed, and do not halt processing
                      of remaining datasets/models unless explicitly fatal.
4. Config Log       — every configuration value actually used during a run,
                      including frozen publication defaults and any
                      runtime overrides. Supports reproducibility audits.

Each logger writes to its own file under `logs/`, named with the date and
stream, and to the console at a reduced verbosity. All loggers attach the
Experiment ID (when available) to every record so cross-stream correlation
is possible.

This module deliberately does not import anything from the rest of the
`dcf` package, so it can be imported first, before configuration is loaded.
"""



from __future__ import annotations



import sys

from pathlib import Path

from typing import Optional



from loguru import logger as _loguru_logger











LOG_DIR = Path(__file__).resolve().parents[2] / "logs"



EXECUTION_LOG_PATH = LOG_DIR / "execution.log"

EXPERIMENT_LOG_PATH = LOG_DIR / "experiment.log"

ERROR_LOG_PATH = LOG_DIR / "error.log"

CONFIG_LOG_PATH = LOG_DIR / "config.log"



_LOG_FORMAT = (

    "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | "

    "exp_id={extra[experiment_id]} | {name}:{function}:{line} | {message}"

)



_initialized = False





def _default_extra() -> dict:

    return {"experiment_id": "UNSET"}





def init_logging(experiment_id: Optional[str] = None, console_level: str = "INFO") -> None:

    """
    Initialize the four logging sinks. Safe to call multiple times;
    only the first call configures sinks, subsequent calls update the
    bound experiment_id context.

    Parameters
    ----------
    experiment_id:
        The active Experiment ID (see experiment_manifest.py, DCF specification
        / DCF specification-29). If not yet known (e.g. during very early
        v1.2.0 scaffolding), pass None and it will display as "UNSET".
    console_level:
        Minimum level echoed to stderr console. File sinks always capture
        DEBUG and above.
    """

    global _initialized

    LOG_DIR.mkdir(parents=True, exist_ok=True)



    if not _initialized:

        _loguru_logger.remove()  



        

        _loguru_logger.add(

            sys.stderr,

            level=console_level,

            format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",

            colorize=True,

        )



        

        _loguru_logger.add(

            EXECUTION_LOG_PATH,

            level="DEBUG",

            format=_LOG_FORMAT,

            filter=lambda record: record["extra"].get("stream") == "execution",

            rotation="10 MB",

            retention="60 days",

            enqueue=True,

        )



        

        _loguru_logger.add(

            EXPERIMENT_LOG_PATH,

            level="DEBUG",

            format=_LOG_FORMAT,

            filter=lambda record: record["extra"].get("stream") == "experiment",

            rotation="10 MB",

            retention="365 days",  

            enqueue=True,

        )



        

        _loguru_logger.add(

            ERROR_LOG_PATH,

            level="WARNING",

            format=_LOG_FORMAT,

            filter=lambda record: record["extra"].get("stream") == "error",

            rotation="10 MB",

            retention="365 days",

            enqueue=True,

        )



        

        _loguru_logger.add(

            CONFIG_LOG_PATH,

            level="DEBUG",

            format=_LOG_FORMAT,

            filter=lambda record: record["extra"].get("stream") == "config",

            rotation="10 MB",

            retention="365 days",

            enqueue=True,

        )



        _initialized = True



    _loguru_logger.configure(extra={"experiment_id": experiment_id or "UNSET"})





def _bound(stream: str):

    if not _initialized:

        init_logging()

    return _loguru_logger.bind(stream=stream)





def get_execution_logger():

    """Logger for pipeline-level progress events (stage entry/exit, timing)."""

    return _bound("execution")





def get_experiment_logger():

    """Logger for the scientific record of what was run (datasets, params, models)."""

    return _bound("experiment")





def get_error_logger():

    """Logger for failures, exceptions, and recoverable warnings."""

    return _bound("error")





def get_config_logger():

    """Logger for configuration values actually used during a run."""

    return _bound("config")





__all__ = [

    "init_logging",

    "get_execution_logger",

    "get_experiment_logger",

    "get_error_logger",

    "get_config_logger",

    "LOG_DIR",

    "EXECUTION_LOG_PATH",

    "EXPERIMENT_LOG_PATH",

    "ERROR_LOG_PATH",

    "CONFIG_LOG_PATH",

]

