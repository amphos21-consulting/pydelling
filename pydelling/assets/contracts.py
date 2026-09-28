from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, Protocol, TypedDict, runtime_checkable

from .handlers import AssetSource


class PreviewSection(TypedDict, total=False):
    kind: Literal[
        "table",
        "text",
        "mesh",
        "image",
        "binary",
        "error",
        "heatmap",
        "plotly",
        "hdf5",
        "thermodynamic_database",
    ]
    title: str
    columns: list[str]
    rows: list[list[Any]]
    lines: list[str]
    mesh: dict[str, Any]
    metadata: dict[str, Any]
    message: str


class _PreviewDocumentRequired(TypedDict):
    version: int
    asset_kind: str
    format: str
    summary: str
    sections: list[PreviewSection]
    warnings: list[str]
    limits: dict[str, int]
    computed_at: str


class PreviewDocument(_PreviewDocumentRequired, total=False):
    metadata: dict[str, Any]


@runtime_checkable
class AssetHandle(Protocol):
    source: AssetSource
    kind: str
    strategy_name: str

    def schema(self) -> dict[str, Any]: ...

    def preview(self) -> dict[str, Any]: ...

    def preview_document(self, *, max_rows: int, max_bytes: int) -> PreviewDocument: ...

    def summary_text(self) -> str: ...


@runtime_checkable
class PreviewHandler(Protocol):
    def detect(self, source: AssetSource, header: bytes | None = None) -> bool: ...

    def load(self, source: AssetSource, header: bytes | None = None) -> AssetHandle: ...

    def build_preview(
        self,
        path: str | Path,
        *,
        file_name: str | None = None,
        reference_name: str | None = None,
        max_rows: int = 10,
        max_bytes: int = 65_536,
        mime_type: str | None = None,
        size_bytes: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> PreviewDocument: ...


__all__ = [
    "AssetHandle",
    "AssetSource",
    "PreviewDocument",
    "PreviewHandler",
    "PreviewSection",
]
