# Configuration

The `pydelling.config` package manages project configuration and logging setup.

When imported, it loads a local configuration file, merges it with the global
project configuration, initializes the logging system, creates the log
directory if needed, and exposes the resulting settings through the `config`
object.

## Package contents

The `config` package is responsible for managing configuration and logging in `pydelling`.

It includes the following files:

- `__init__.py`: handles configuration loading and merging, initializes logging, and exposes the `config` object.
- `global_config.yaml`: defines shared default values for the project.
- `local_config.yaml`: defines local overrides or execution-specific parameters.
- `logger_config.yaml`: provides the base logging configuration.
- `conda_env.yaml`: defines a Conda environment for reproducibility, although it appears to reflect a machine-specific or legacy setup.

## Important note

Importing `pydelling.config` triggers configuration loading and logging
initialization automatically.

## Configuration loading

The package first searches for a user-defined configuration file in the current
working directory using the pattern `*config*`. If no matching file is found,
it falls back to the default `local_config.yaml` distributed with the package.

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

Logging is initialized using `logger_config.yaml`. This file defines the base
logging configuration, including message formats, output handlers, and root
logger behaviour.

The initial configuration includes:

- a console handler for standard output
- a file handler that writes logs to `logs/info.log`

After loading this file, the logging setup is further customized in
`pydelling.config.__init__`, where the root handlers are replaced with a
`RichHandler` to improve console output.

The package also captures Python warnings through the logging system.

## Files

### `__init__.py`

This module is responsible for:

- loading configuration files
- merging global and local settings
- creating the logs directory
- initializing logging
- capturing warnings
- displaying a startup message with the current package version

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

### `logger_config.yaml`

This file defines the base logging configuration for `pydelling`.

It specifies:

- message formatters
- console and file handlers
- output log levels
- root logger settings

The file handler writes logs to `logs/info.log`, and the current configuration
uses write mode, so the log file is overwritten at the beginning of each run.

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