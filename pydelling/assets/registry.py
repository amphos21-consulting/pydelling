from __future__ import annotations

from pathlib import Path
from typing import Any

from .handlers import (
    HEADER_READ_BYTES,
    PREVIEW_ROW_LIMIT,
    AssetSource,
    BaseAssetHandle,
    build_asset_preview,
    detect_asset_handle_class,
    load_asset_handle,
)

from .contracts import PreviewDocument


class DefaultPreviewHandler:
    """Adapter exposing the stable preview-handler integration contract."""

    def detect(self, source: AssetSource, header: bytes | None = None) -> bool:
        detect_asset_handle_class(source, header=header)
        return True

    def load(self, source: AssetSource, header: bytes | None = None) -> BaseAssetHandle:
        return load_asset_handle(source, header=header)

    def build_preview(
        self,
        path: str | Path,
        *,
        file_name: str | None = None,
        reference_name: str | None = None,
        max_rows: int = PREVIEW_ROW_LIMIT,
        max_bytes: int = HEADER_READ_BYTES,
        mime_type: str | None = None,
        size_bytes: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> PreviewDocument:
        return build_asset_preview(
            path,
            file_name=file_name,
            reference_name=reference_name,
            max_rows=max_rows,
            max_bytes=max_bytes,
            mime_type=mime_type,
            size_bytes=size_bytes,
            metadata=metadata,
        )


DEFAULT_PREVIEW_HANDLER = DefaultPreviewHandler()


def get_asset_handler(
    source: AssetSource, header: bytes | None = None
) -> BaseAssetHandle:
    return DEFAULT_PREVIEW_HANDLER.load(source, header=header)


__all__ = ["DEFAULT_PREVIEW_HANDLER", "DefaultPreviewHandler", "get_asset_handler"]
