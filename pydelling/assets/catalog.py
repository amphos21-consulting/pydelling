from __future__ import annotations

import json
from functools import lru_cache
from importlib.resources import files
from typing import Any


API_CATALOG_VERSION = 1


@lru_cache(maxsize=1)
def get_api_catalog() -> dict[str, Any]:
    catalog_path = files("pydelling.assets").joinpath("api_catalog.json")
    if not catalog_path.is_file():
        raise RuntimeError(
            "The Pydelling API catalog is missing. Reinstall Pydelling from a complete distribution."
        )
    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != API_CATALOG_VERSION:
        raise RuntimeError("Unsupported Pydelling API catalog version.")
    return payload


__all__ = ["API_CATALOG_VERSION", "get_api_catalog"]
