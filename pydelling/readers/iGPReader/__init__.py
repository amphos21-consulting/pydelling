"""iGP reader namespace with a lazy public class export."""

from __future__ import annotations

from importlib import import_module
from typing import Any


def __getattr__(name: str) -> Any:
    if name != "iGPReader":
        raise AttributeError(name)
    value = import_module("pydelling.readers.iGPReader.io.igp_reader").iGPReader
    globals()[name] = value
    return value


__all__ = ["iGPReader"]
