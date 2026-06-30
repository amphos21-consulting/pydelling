"""Lightweight package entrypoint for the vendored pydelling workspace member.

The cloud app only needs explicit submodules such as ``pydelling.readers``.
Avoid importing the entire dependency graph at package import time because the
upstream package eagerly loads optional configuration and COMSOL integrations.
"""

__all__ = [
    "interpolation",
    "preprocessing",
    "readers",
    "sdk",
    "utils",
    "writers",
]
