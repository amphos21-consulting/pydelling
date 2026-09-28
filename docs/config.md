# Configuration

The `pydelling.config` package manages project configuration and logging setup.

When imported, it loads a local configuration file, merges it with the global
project configuration, attaches a console handler to the `pydelling` logger and
exposes the resulting settings through the `config` object. It creates no files
or folders and does not touch the root logger or Python warnings.

## Package contents

The `config` package is responsible for managing configuration and logging in `pydelling`.

It includes the following files:

- `__init__.py`: handles configuration loading and merging, configures pydelling's console logging, and exposes the `config` object.
- `global_config.yaml`: defines shared default values for the project.
- `local_config.yaml`: defines local overrides or execution-specific parameters.
- `conda_env.yaml`: defines a Conda environment for reproducibility, although it appears to reflect a machine-specific or legacy setup.

## Important note

Importing `pydelling.config` triggers configuration loading and attaches a
console handler to the `pydelling` logger automatically.

## Configuration loading

The package uses, in order:

1. the file named by the `PYDELLING_CONFIG` environment variable;
2. the first (alphabetically) `*config*.yaml` / `*config*.yml` file in the current working directory;
3. the default `local_config.yaml` distributed with the package.

A file that cannot be read as YAML falls back to the default configuration.

The configuration is loaded from YAML and stored as a `Box` object, which
allows dot-style access to configuration values.

## Global and local configuration

The configuration system combines two main YAML files:

- `global_config.yaml`, which defines shared default values
- `local_config.yaml`, which defines local overrides and execution-specific settings

In general:

- use `global_config.yaml` for shared project defaults
- use `local_config.yaml` for user-specific or machine-specific changes

If a key defined in the local configuration also exists in the global
configuration, the local value overrides the global one.

## Logging setup

pydelling modules log through `logging.getLogger(__name__)`, i.e. children of the
`pydelling` logger. On import, that logger gets a Rich console handler at `INFO`
level and does not propagate to the root logger. Nothing else is configured:
no log files, no root handlers, no warning capture.

Change this with `configure_logging` or the `PYDELLING_LOGGING` environment
variable (read at import):

```python
from pydelling.config import configure_logging

configure_logging("package")        # default: Rich console output for pydelling only
configure_logging("root")           # pre-1.2.1 behaviour: Rich handler on the root logger
configure_logging("none")           # no pydelling handler; messages propagate to your logging setup
configure_logging("package", level=logging.DEBUG)
```

## Files

### `__init__.py`

This module is responsible for:

- loading configuration files
- merging global and local settings
- configuring console logging for the `pydelling` logger (`configure_logging`)
- exposing the package version as `version`

It also exposes the merged configuration through the `config` object.

### `global_config.yaml`

This file stores the shared default configuration for `pydelling`.

It includes project-wide settings such as:

- element mappings
- writer mappings
- verbosity defaults
- physical constants
- constitutive law parameters
- supported file formats for web applications
- default manager options

This file should contain values intended to be shared across the project.

### `local_config.yaml`

This file stores local configuration values used to customize the behaviour of
`pydelling` for a specific user, machine, or execution context.

It is used to override shared defaults and define settings such as:

- working folder
- verbosity
- numerical tolerance
- module-specific parameters

This is the right place for settings that may change between users or runs.

### `conda_env.yaml`

This file defines a Conda environment for `pydelling`, including the Python
version and a pinned set of dependencies.

Its purpose is to help reproduce a specific software setup for development or
execution.

This file also includes a machine-specific `prefix` path, so it should be
understood as an environment definition rather than a portable configuration
file for all users.

## Summary

The `config` package centralizes project configuration and logging behaviour.

Its main purpose is to keep shared defaults, local customizations, and logging
settings organized in a single place, while making the project easier to run
and maintain across different environments.