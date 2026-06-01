"""
Configuration and logging bootstrap for pydelling.

This module loads the project configuration, merges global and local settings,
initializes the logging system, creates the log directory if needed, and
displays a startup message with the current package version.

On import, the module looks for a user-defined configuration file in the
current working directory. If none is found, it falls back to the default
local configuration distributed with the package. Global settings are then
loaded and selectively overridden by local values.

Main responsibilities
---------------------
- load YAML configuration files
- expose the merged configuration through ``config``
- initialize the logging system
- capture Python warnings
- report the current package version at startup
"""

import logging.config
import os
from pathlib import Path
from importlib.metadata import PackageNotFoundError, version as package_version
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

    with open(config_file) as file:
        context = yaml.load(file, Loader=yaml.FullLoader)
    return Box(context, default_box=True)


_config_file = list(Path.cwd().glob("*config*"))
if not _config_file:
    _config_file = [get_config_path() / 'local_config.yaml']
    logging.warning('Using default configuration file (not the user defined one)')
assert len(_config_file) >= 1, "Please provide a configuration file that has a '*config.yaml' name structure"
config = read_config(config_file=_config_file[0])

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

os.makedirs(config.path.logs if config.path.logs else Path().cwd() / "logs", exist_ok=True)
with open(Path(__file__).parent / "logger_config.yaml", "r") as ymlfile:
    log_config = yaml.safe_load(ymlfile)
logging.config.dictConfig(log_config)

for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)
logging.basicConfig(level=logging.INFO, format="%(message)s", datefmt="[%X]", handlers=[RichHandler(rich_tracebacks=True, show_path=False)])

# # Fix logging issue caused by streamlit
# loggers = [handler for handler in logging.root.handlers if isinstance(handler, logging.StreamHandler)]
# strange_logger = loggers[-1]
# strange_logger.setLevel(logging.ERROR)

# Capture warnings
logging.captureWarnings(True)
logging.getLogger("py.warnings").setLevel(logging.ERROR)

# Add welcome message, get the version from the setup.py file
try:
    with open(Path(__file__).parent.parent.parent / "pyproject.toml", "r") as setup_file:
        setup_file = setup_file.read()
        version = setup_file.split("version = \"")[1].split("\"")[0]
except Exception:
    try:
        version = package_version("pydelling")
    except PackageNotFoundError:
        version = "unknown"
logging.info(f"-----------------------------------")
logging.info(f"[blue bold]Welcome to Pydelling {version}", extra={"markup": True})
logging.info(f"-----------------------------------")



