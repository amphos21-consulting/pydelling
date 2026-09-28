"""
Configuration and logging bootstrap for pydelling.

This module loads the project configuration, merges global and local settings
and sets up console logging for the ``pydelling`` logger.

On import, the module looks for a configuration file: the path in the
``PYDELLING_CONFIG`` environment variable, else a ``*config*.yaml`` /
``*config*.yml`` file in the current working directory, else the default
configuration distributed with the package. Global settings are then loaded
and selectively overridden by local values.

Importing pydelling has no side effects outside the ``pydelling`` logger: it
creates no files or folders, leaves the root logger and Python warnings alone,
and only attaches a Rich console handler to ``logging.getLogger("pydelling")``.
Use :func:`configure_logging` (or the ``PYDELLING_LOGGING`` environment
variable: ``package``, ``root`` or ``none``) to change that.

Main responsibilities
---------------------
- load YAML configuration files
- expose the merged configuration through ``config``
- configure console logging for pydelling messages
- expose the package version as ``version``
"""

import logging
import os
from importlib.metadata import PackageNotFoundError, version as package_version
from pathlib import Path
from rich.logging import RichHandler

import yaml
from box import Box

from pydelling.utils.configuration_utils import get_config_path


def read_config(config_file: Path="./local_config.yaml"):
    """
    Read a YAML configuration file and return it as a Box object.

    Parameters
    ----------
    config_file : Path, optional
        Path to the YAML configuration file. By default, ``"./local_config.yaml"``.

    Returns
    -------
    Box
        Configuration content wrapped in a ``Box`` object to allow dot-based
        access to keys.

    Notes
    -----
    The configuration file is parsed using ``yaml.FullLoader``.
    """
    try:
        with open(config_file) as file:
            context = yaml.load(file, Loader=yaml.FullLoader)

        context_as_box = Box(context, default_box=True)

    except:
        # Maybe a generic exception like this one is not recommended, but there are 
        # multiple ways the reading could fail: file not existing, not valid YAML,
        # it is a directory...
        return None

    return context_as_box

LOGGING_MODES = ("package", "root", "none")
_package_logger = logging.getLogger("pydelling")


def _new_console_handler() -> logging.Handler:
    handler = RichHandler(rich_tracebacks=True, show_path=False)
    handler.setFormatter(logging.Formatter("%(message)s", datefmt="[%X]"))
    handler._pydelling_console = True  # marker, so re-imports/reloads never stack handlers
    return handler


def configure_logging(mode: str = "package", level: int = logging.INFO) -> None:
    """Configure console output for pydelling log messages.

    Args:
        mode: ``"package"`` (default) attaches a Rich console handler to the ``pydelling``
            logger only, without propagating to the root logger. ``"root"`` restores the
            pre-1.2.1 behaviour: the root logger gets the Rich handler, so messages from any
            logger (including your scripts) are shown. ``"none"`` removes pydelling's handler
            and lets messages propagate to whatever logging you configure.
        level: level for the configured logger.
    """
    if mode not in LOGGING_MODES:
        raise ValueError(f"Unknown logging mode '{mode}', expected one of {LOGGING_MODES}")
    for logger in (_package_logger, logging.getLogger()):
        for handler in list(logger.handlers):
            if getattr(handler, "_pydelling_console", False):
                logger.removeHandler(handler)
    _package_logger.propagate = True
    _package_logger.setLevel(logging.NOTSET)
    if mode == "none":
        return
    console_handler = _new_console_handler()
    if mode == "package":
        _package_logger.addHandler(console_handler)
        _package_logger.setLevel(level)
        _package_logger.propagate = False
    else:
        root = logging.getLogger()
        root.addHandler(console_handler)
        root.setLevel(level)


def _find_config_file():
    env_config = os.environ.get("PYDELLING_CONFIG")
    if env_config:
        return Path(env_config)
    candidates = sorted(set(Path.cwd().glob("*config*.yaml")) | set(Path.cwd().glob("*config*.yml")))
    candidates = [path for path in candidates if path.is_file()]
    return candidates[0] if candidates else None


used_default_config = False
_config_file = _find_config_file()
config = read_config(config_file=_config_file) if _config_file is not None else None

if config is None:
    # No user file, or it is not valid YAML
    _config_file = get_config_path() / 'local_config.yaml'
    config = read_config(config_file=_config_file)
    used_default_config = True

# Add global configuration
if not config.globals.is_globals_loaded:
    with open(get_config_path() / "global_config.yaml", "r") as yml_file:
        local_yaml_file = yaml.safe_load(yml_file)
        config.globals = local_yaml_file
        config.globals.is_globals_loaded = True

# Allow to override the global configuration with a local file
for key in config:
    if key in config.globals:
        if isinstance(config[key], dict):
            config.globals[key].update(config[key])
        else:
            config.globals[key] = config[key]

# Source checkouts read the version from pyproject.toml; installed packages from metadata.
try:
    with open(Path(__file__).parent.parent.parent / "pyproject.toml", "r") as setup_file:
        version = setup_file.read().split("version = \"")[1].split("\"")[0]
except Exception:
    try:
        version = package_version("pydelling")
    except PackageNotFoundError:
        version = "unknown"

configure_logging(os.environ.get("PYDELLING_LOGGING", "package").lower())

_package_logger.debug(f"Pydelling {version} (config: {_config_file})")
if used_default_config:
    _package_logger.debug('Using default configuration file (not the user defined one)')
