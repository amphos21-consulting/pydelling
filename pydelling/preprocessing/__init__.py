"""Public preprocessing namespace with backwards-compatible lazy exports."""

from __future__ import annotations

from importlib import import_module
from typing import Any


_LAZY_EXPORTS = {
    "BasePreprocessing": (
        "pydelling.preprocessing.base_preprocessing",
        "BasePreprocessing",
    ),
    "ClosedStlGenerator": (
        "pydelling.preprocessing.closed_stl_generator",
        "ClosedStlGenerator",
    ),
    "DfnPreprocessor": ("pydelling.preprocessing.dfn_preprocessor", "DfnPreprocessor"),
    "DfnUpscaler": ("pydelling.preprocessing.dfn_preprocessor", "DfnUpscaler"),
    "SurfaceDfn": ("pydelling.preprocessing.dfn_preprocessor", "SurfaceDfn"),
    "UpscalingResult": ("pydelling.preprocessing.dfn_preprocessor", "UpscalingResult"),
    "ArrayMesh": ("pydelling.preprocessing.mesh_preprocessor", "ArrayMesh"),
    "MeshPreprocessor": (
        "pydelling.preprocessing.mesh_preprocessor",
        "MeshPreprocessor",
    ),
}


def __getattr__(name: str) -> Any:
    try:
        module_name, attribute = _LAZY_EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc
    value = getattr(import_module(module_name), attribute)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted({*globals(), *_LAZY_EXPORTS})


__all__ = [
    "base_preprocessing",
    "closed_stl_generator",
    "dfn_preprocessor",
    "mesh_preprocessor",
    *_LAZY_EXPORTS,
]
