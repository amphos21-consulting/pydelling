"""Optional SSH integrations loaded only when the HPC extra is used."""

from __future__ import annotations

from importlib import import_module
from typing import Any


_LAZY_EXPORTS = {
    "BaseSsh": ("pydelling.managers.ssh.base_ssh", "BaseSsh"),
    "JurecaSsh": ("pydelling.managers.ssh.jureca_ssh", "JurecaSsh"),
    "LumiSsh": ("pydelling.managers.ssh.lumi_ssh", "LumiSsh"),
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


__all__ = list(_LAZY_EXPORTS)
