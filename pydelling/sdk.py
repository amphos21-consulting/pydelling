from __future__ import annotations

from pydelling_cloud_backend.runtime_sdk import (
    RuntimeContext,
    load_context as _load_context,
    load_asset_handles_from_context as _load_asset_handles_from_context,
    make_output_manifest_item as _make_output_manifest_item,
    write_outputs_manifest as _write_outputs_manifest,
)
from pydelling.preview import build_asset_preview


def load_context(context_json):
    """Load the execution context JSON into a RuntimeContext.

    Category: runtime
    Tags: runtime, context, assets, load, sdk
    Usage: generated scripts need the compatibility pydelling.sdk entry point to access user assets.

    Returns:
        RuntimeContext: context object exposing get_asset and list_assets.
    """
    return _load_context(context_json)


def load_asset_handles_from_context(items):
    """Load typed pydelling asset handles from runtime context items.

    Category: runtime
    Tags: runtime, context, assets, handles, sdk
    Usage: generated scripts need all available assets as typed handles.

    Returns:
        list: typed asset handles built from context entries.
    """
    return _load_asset_handles_from_context(items)


def make_output_manifest_item(
    path,
    *,
    kind="artifact",
    title=None,
    mime_type=None,
    download_path=None,
    download_mime_type=None,
):
    """Create one outputs_manifest.json item for a generated file.

    Category: runtime
    Tags: runtime, output, manifest, artifact, table
    Usage: scripts need to publish an artifact or table output back to pydelling-cloud.

    Returns:
        dict: manifest item with path, kind, title, and MIME type.
    """
    return _make_output_manifest_item(
        path,
        kind=kind,
        title=title,
        mime_type=mime_type,
        download_path=download_path,
        download_mime_type=download_mime_type,
    )


def write_outputs_manifest(output_dir, items):
    """Write outputs_manifest.json for generated script outputs.

    Category: runtime
    Tags: runtime, output, manifest, write, sdk
    Usage: scripts have finished creating output files and need pydelling-cloud to display them.

    Returns:
        Path: path to the written outputs manifest.
    """
    return _write_outputs_manifest(output_dir, items)

__all__ = [
    "RuntimeContext",
    "load_context",
    "load_asset_handles_from_context",
    "build_asset_preview",
    "make_output_manifest_item",
    "write_outputs_manifest",
]
