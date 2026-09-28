from __future__ import annotations

import csv
import json
import mimetypes
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import cached_property
from pathlib import Path
from typing import Any

import h5py
import pandas as pd
import trimesh


TEXT_EXTENSIONS = {"csv", "json", "txt", "md", "log", "yaml", "yml", "tsv"}
IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp", "bmp", "tif", "tiff"}
IGP_REQUIRED_FILES = frozenset({"data.mesh", "source.ss", "centroid.dat"})
HEADER_READ_BYTES = 65_536
PREVIEW_ROW_LIMIT = 10
PREVIEW_LINE_LIMIT = 10
TABULAR_EAGER_BYTES = 8_388_608
HDF5_MAGIC = b"\x89HDF\r\n\x1a\n"
PREVIEW_CONTRACT_VERSION = 3
MESH_PREVIEW_CELL_LIMIT = 5_000
MESH_PREVIEW_FACE_LIMIT = 30_000

CELL_TYPE_BY_NODE_COUNT = {
    4: "tetra",
    5: "pyramid",
    6: "wedge",
    8: "hexahedron",
}

FACE_TEMPLATES_BY_NODE_COUNT = {
    4: [[0, 1, 3], [1, 2, 3], [0, 3, 2], [0, 2, 1]],
    5: [[0, 1, 2, 3], [0, 4, 1], [1, 4, 2], [2, 4, 3], [3, 4, 0]],
    6: [[0, 1, 4, 3], [1, 2, 5, 4], [2, 0, 3, 5], [0, 2, 1], [3, 4, 5]],
    8: [[0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7], [0, 3, 2, 1], [4, 5, 6, 7]],
}


def normalize_extension(value: str | None) -> str:
    """Normalize a file extension for asset type detection.

    Category: util
    Tags: extension, mime, detection, asset
    Usage: code needs to compare uploaded asset extensions independent of dot prefix or case.

    Returns:
        str: lower-case extension without a leading dot.
    """
    if not value:
        return ""
    return value.lower().lstrip(".")


def read_asset_header(path: Path, limit: int = HEADER_READ_BYTES) -> bytes:
    """Read the leading bytes used to classify an asset safely.

    Category: util
    Tags: header, bytes, detection, asset
    Usage: asset detection needs a bounded binary sample without loading the full file.

    Returns:
        bytes: at most limit bytes from the file, or empty bytes for directories.
    """
    if path.is_dir():
        return b""
    with path.open("rb") as handle:
        return handle.read(limit)


def _path_size(path: Path) -> int:
    if path.is_dir():
        return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())
    return path.stat().st_size


def is_probably_text(payload: bytes) -> bool:
    """Detect whether a byte payload is likely UTF-8 text.

    Category: util
    Tags: text, binary, detection, encoding
    Usage: choosing between text and binary asset handling from a header sample.

    Returns:
        bool: True when the sample can be treated as text.
    """
    if not payload:
        return True
    if b"\x00" in payload:
        return False
    try:
        payload.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _decode_text(payload: bytes) -> str:
    return payload.decode("utf-8", errors="replace")


def _coerce_preview_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=True)
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value)


def _stringify_mapping(mapping: dict[str, Any]) -> list[list[str]]:
    return [[key, _coerce_preview_value(value)] for key, value in mapping.items()]


def _limit_json_value(value: Any, max_rows: int) -> Any:
    if isinstance(value, dict):
        return {key: _limit_json_value(nested, max_rows) for key, nested in list(value.items())[:max_rows]}
    if isinstance(value, list):
        return [_limit_json_value(item, max_rows) for item in value[:max_rows]]
    return value


def _guess_delimiter(extension: str, header: bytes) -> str:
    if extension == "tsv":
        return "\t"
    if extension == "csv":
        return ","
    sample = _decode_text(header[:4096]).splitlines()
    if not sample:
        return ","
    try:
        dialect = csv.Sniffer().sniff("\n".join(sample[:5]), delimiters=",;\t|")
    except csv.Error:
        dialect = None
    if dialect is not None and dialect.delimiter:
        return dialect.delimiter
    first_line = sample[0]
    counts = {
        ",": first_line.count(","),
        "\t": first_line.count("\t"),
        ";": first_line.count(";"),
        "|": first_line.count("|"),
    }
    delimiter, count = max(counts.items(), key=lambda item: item[1])
    return delimiter if count > 0 else ","


def _delimiter_label(delimiter: str) -> str:
    return {"\t": "tab", ",": "comma", ";": "semicolon", "|": "pipe"}.get(
        delimiter, delimiter
    )


def _looks_like_tabular(header: bytes) -> bool:
    if not is_probably_text(header):
        return False
    lines = [line for line in _decode_text(header[:4096]).splitlines() if line.strip()]
    if len(lines) < 2:
        return False
    for separator in (",", "\t", ";", "|"):
        counts = [line.count(separator) for line in lines[:3]]
        if min(counts) > 0:
            return True
    return False


def _first_non_empty_line(header: bytes) -> str:
    for line in _decode_text(header[:4096]).splitlines():
        if line.strip():
            return line.strip()
    return ""


def _parse_quoted_header_line(line: str) -> list[str]:
    if not line:
        return []
    try:
        return next(csv.reader([line], skipinitialspace=True))
    except csv.Error:
        return []


def _extract_unit(column: str) -> str | None:
    match = re.search(r"\[([^\]]+)\]\s*$", column)
    return match.group(1).strip() if match else None


def _looks_like_pflotran_mass_balance(header: bytes) -> bool:
    if not is_probably_text(header):
        return False
    columns = _parse_quoted_header_line(_first_non_empty_line(header))
    if len(columns) < 4:
        return False
    first = columns[0].strip().strip('"')
    if not first.startswith("Time ["):
        return False
    # PFLOTRAN writes one or two leading timestep columns depending on the
    # active modes: ``dt_tran`` alone, or ``dt_flow`` then ``dt_tran``.
    leading = [str(column).strip().strip('"') for column in columns[1:3]]
    if not any(column.startswith(("dt_tran [", "dt_flow [")) for column in leading):
        return False
    mass_columns = [
        column
        for column in columns[1:]
        if not str(column).strip().strip('"').startswith("dt_")
    ]
    unit_count = sum(1 for column in mass_columns if _extract_unit(str(column)) is not None)
    return unit_count >= 2


def _extract_embedded_unit(column: str) -> str | None:
    """First ``[unit]`` bracket anywhere in the column name.

    Observation columns embed the unit mid-name
    (``Liquid Pressure [Pa] obs1 (231)``), unlike mass-balance columns where
    the unit is the suffix.
    """
    match = re.search(r"\[([^\]]+)\]", column)
    return match.group(1).strip() if match else None


def _looks_like_pflotran_observation(header: bytes) -> bool:
    if not is_probably_text(header):
        return False
    lines = [line for line in _decode_text(header[:4096]).splitlines() if line.strip()]
    if len(lines) < 2:
        return False
    columns = _parse_quoted_header_line(lines[0].strip())
    if len(columns) < 2:
        return False
    first = columns[0].strip().strip('"')
    if not first.startswith("Time ["):
        return False
    if any(
        str(column).strip().strip('"').startswith("dt_") for column in columns[1:3]
    ):
        return False  # that header shape is a PFLOTRAN mass-balance file
    if not any(_extract_embedded_unit(str(column)) for column in columns[1:]):
        return False
    # Data rows are whitespace-separated numerics; a comma-delimited CSV that
    # merely starts with a "Time [...]" column must stay tabular.
    tokens = lines[1].split()
    if len(tokens) < 2:
        return False
    try:
        for token in tokens:
            float(token)
    except ValueError:
        return False
    return True


RASTER_HEADER_KEYS = {
    "ncols",
    "nrows",
    "xllcorner",
    "yllcorner",
    "xllcenter",
    "yllcenter",
    "cellsize",
    "dx",
    "dy",
    "nodata_value",
}
RASTER_EAGER_BYTES = 4 * TABULAR_EAGER_BYTES


def _parse_esri_raster_header(header: bytes) -> tuple[dict[str, float], int]:
    entries: dict[str, float] = {}
    consumed = 0
    for line in _decode_text(header[:4096]).splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0].lower() in RASTER_HEADER_KEYS:
            try:
                entries[parts[0].lower()] = float(parts[1])
            except ValueError:
                break
            consumed += 1
            continue
        if not line.strip() and not entries:
            consumed += 1
            continue
        break
    return entries, consumed


def _looks_like_esri_ascii_raster(header: bytes) -> bool:
    if not is_probably_text(header):
        return False
    entries, _ = _parse_esri_raster_header(header)
    return "ncols" in entries and "nrows" in entries and len(entries) >= 4


def _image_dimensions(path: Path, extension: str) -> dict[str, int] | None:
    try:
        header = read_asset_header(path, limit=64)
        if extension == "png" and header.startswith(b"\x89PNG\r\n\x1a\n"):
            return {
                "width": int.from_bytes(header[16:20], "big"),
                "height": int.from_bytes(header[20:24], "big"),
            }
        if extension in {"jpg", "jpeg"}:
            with path.open("rb") as handle:
                handle.read(2)
                while True:
                    marker_start = handle.read(1)
                    if marker_start != b"\xff":
                        return None
                    marker = handle.read(1)
                    while marker == b"\xff":
                        marker = handle.read(1)
                    length_bytes = handle.read(2)
                    if len(length_bytes) != 2:
                        return None
                    length = int.from_bytes(length_bytes, "big")
                    if marker in {
                        b"\xc0",
                        b"\xc1",
                        b"\xc2",
                        b"\xc3",
                        b"\xc5",
                        b"\xc6",
                        b"\xc7",
                        b"\xc9",
                        b"\xca",
                        b"\xcb",
                        b"\xcd",
                        b"\xce",
                        b"\xcf",
                    }:
                        payload = handle.read(5)
                        if len(payload) != 5:
                            return None
                        return {
                            "height": int.from_bytes(payload[1:3], "big"),
                            "width": int.from_bytes(payload[3:5], "big"),
                        }
                    handle.seek(length - 2, 1)
    except Exception:
        return None
    return None


def _looks_like_image_header(header: bytes) -> bool:
    return (
        header.startswith(b"\x89PNG\r\n\x1a\n")
        or header.startswith(b"\xff\xd8\xff")
        or header.startswith(b"GIF87a")
        or header.startswith(b"GIF89a")
        or header.startswith(b"RIFF") and header[8:12] == b"WEBP"
        or header.startswith(b"BM")
    )


def _is_igp_directory(path: Path) -> bool:
    if not path.is_dir():
        return False
    return all((path / required_file).is_file() for required_file in IGP_REQUIRED_FILES)


@dataclass
class AssetSource:
    """Describe the file path and metadata used to build an asset handle.

    Category: asset-handle
    Tags: asset, source, metadata, file, context
    Usage: constructing typed handles from runtime context asset entries.
    """
    file_name: str
    path: Path
    extension: str = ""
    reference_name: str | None = None
    size_bytes: int | None = None
    mime_type: str | None = None
    metadata: dict[str, Any] | None = None

    @property
    def normalized_extension(self) -> str:
        """Return the source extension normalized for handle detection.

        Category: asset-handle
        Tags: asset, extension, detection
        Usage: matching an asset source to a tabular, mesh, image, JSON, text, or binary handle.

        Returns:
            str: lower-case extension without a leading dot.
        """
        if self.extension:
            return normalize_extension(self.extension)
        return normalize_extension(Path(self.file_name).suffix)

    @property
    def guessed_mime_type(self) -> str:
        """Return the explicit or inferred MIME type for this source.

        Category: asset-handle
        Tags: asset, mime, metadata
        Usage: previews and output manifests need a MIME type for an asset.

        Returns:
            str: MIME type, defaulting to application/octet-stream.
        """
        return (
            self.mime_type
            or mimetypes.guess_type(self.file_name)[0]
            or "application/octet-stream"
        )


@dataclass(frozen=True)
class _VtkCellBlock:
    """Minimal meshio-compatible cell block used for VTK PolyData."""

    type: str
    data: Any


@dataclass(frozen=True)
class _VtkPolyDataMesh:
    """Mesh-shaped representation of a ``.vtp`` document."""

    points: Any
    cells: list[_VtkCellBlock]
    point_data: dict[str, Any]
    cell_data: dict[str, list[Any]]


class BaseAssetHandle:
    """Provide the common runtime contract for any typed user asset.

    Category: asset-handle
    Tags: asset, preview, schema, dataframe, records, text, mesh
    Usage: scripts need a uniform interface before calling format-specific handle methods.
    """
    kind = "binary"
    strategy_name = "binary"

    def __init__(self, source: AssetSource, header: bytes | None = None) -> None:
        self.source = source
        self._header = header

    @cached_property
    def header(self) -> bytes:
        """Load the cached header sample for this asset.

        Category: asset-handle
        Tags: asset, header, detection
        Usage: code needs a bounded byte sample for binary/text checks or preview metadata.

        Returns:
            bytes: header bytes for the source path.
        """
        return self._header if self._header is not None else read_asset_header(self.source.path)

    @property
    def is_binary(self) -> bool:
        """Report whether this asset appears to be binary data.

        Category: asset-handle
        Tags: binary, text, detection, header
        Usage: scripts need to decide whether text-oriented parsing is safe.

        Returns:
            bool: True when the header sample is not probably text.
        """
        return not is_probably_text(self.header)

    def schema(self) -> dict[str, Any]:
        """Return basic schema metadata for this asset handle.

        Category: asset-handle
        Tags: schema, metadata, asset
        Usage: scripts need a lightweight description of asset structure.

        Returns:
            dict[str, Any]: schema metadata for the handle.
        """
        return {"kind": self.kind}

    def preview(self) -> dict[str, Any]:
        """Return a compact data preview for this asset handle.

        Category: asset-handle
        Tags: preview, data, rows, metadata
        Usage: scripts need the smallest available preview payload for an asset.

        Returns:
            dict[str, Any]: preview metadata or sample rows.
        """
        return {}

    def preview_sections(self, *, max_rows: int = PREVIEW_ROW_LIMIT, max_bytes: int = HEADER_READ_BYTES) -> list[dict[str, Any]]:
        """Return UI-ready preview sections for this asset handle.

        Category: asset-handle
        Tags: preview, sections, table, binary, ui
        Usage: pydelling-cloud needs bounded preview sections for display or MCP context.

        Returns:
            list[dict[str, Any]]: preview sections with table, text, mesh, image, or binary content.
        """
        preview = self.preview()
        columns = preview.get("columns")
        rows = preview.get("rows")
        if isinstance(columns, list) and isinstance(rows, list):
            return [{
                "kind": "table",
                "title": "Preview",
                "columns": [str(column) for column in columns],
                "rows": rows[:max_rows],
            }]
        return [{
            "kind": "binary",
            "title": "Preview",
            "columns": ["property", "value"],
            "rows": _stringify_mapping(self.schema()),
        }]

    def preview_metadata(self) -> dict[str, Any]:
        """Return metadata to include in the versioned preview document.

        Category: asset-handle
        Tags: preview, metadata
        Usage: specialized handles can expose UI-facing metadata alongside preview sections.

        Returns:
            dict[str, Any]: preview metadata.
        """
        return {}

    def to_dataframe(self) -> pd.DataFrame:
        """Load this asset as a pandas DataFrame when the format supports rows and columns.

        Category: asset-handle
        Tags: tabular, dataframe, csv, json, records
        Usage: the user needs asset data in DataFrame form for analysis or transformation.

        Returns:
            pd.DataFrame: parsed tabular data.
        """
        raise TypeError(f"{self.__class__.__name__} does not expose a dataframe view.")

    def to_records(self) -> list[dict[str, Any]]:
        """Load this asset as a list of row dictionaries when available.

        Category: asset-handle
        Tags: records, rows, json, tabular
        Usage: scripts need simple Python dictionaries instead of a pandas DataFrame.

        Returns:
            list[dict[str, Any]]: parsed record rows.
        """
        raise TypeError(f"{self.__class__.__name__} does not expose a record view.")

    def to_text(self) -> str:
        """Load this asset as text when the format supports textual content.

        Category: asset-handle
        Tags: text, json, markdown, log
        Usage: the user asks to read, summarize, transform, or inspect textual asset contents.

        Returns:
            str: decoded asset text.
        """
        raise TypeError(f"{self.__class__.__name__} does not expose a text view.")

    def to_igp_reader(self, *, build_mesh: bool = False, output_folder: str | Path | None = None):
        """Open this asset as an iGPReader when it is an iGP/GiD project directory.

        Category: asset-handle
        Tags: igp, gid, mesh, reader, regions, materials
        Usage: scripts need pydelling iGP mesh operations, region access, or VTK export.

        Returns:
            iGPReader: reader configured for the asset directory.
        """
        raise TypeError(f"{self.__class__.__name__} does not expose an iGPReader view.")

    def to_vtk(self, filename: str | Path):
        """Export this asset to a VTK file when the handle supports mesh conversion.

        Category: asset-handle
        Tags: vtk, mesh, export, igp, visualization
        Usage: the user asks to convert an iGP/GiD or mesh asset into VTK for visualization.

        Returns:
            Any: value returned by the concrete exporter.
        """
        raise TypeError(f"{self.__class__.__name__} does not expose a VTK export.")

    def summary_text(self) -> str:
        """Return a short human-readable summary for this asset.

        Category: asset-handle
        Tags: summary, inventory, asset
        Usage: building asset inventories or compact loader descriptions.

        Returns:
            str: one-line summary of the asset.
        """
        return f"{self.kind} asset"

    def _flatten_description(self) -> dict[str, Any]:
        return {}

    def preview_warnings(self) -> list[str]:
        """Return non-fatal warnings to surface in the preview document.

        Category: asset-handle
        Tags: preview, warnings, diagnostics
        Usage: specialized handles report skipped or partially-read content without failing the preview.

        Returns:
            list[str]: human-readable warning messages (empty by default).
        """
        return []

    def describe(self) -> dict[str, Any]:
        """Return schema, preview, loader, and metadata for this asset.

        Category: asset-handle
        Tags: describe, metadata, schema, preview, inventory
        Usage: scripts or MCP tools need a machine-readable summary before selecting an operation.

        Returns:
            dict[str, Any]: structured description of the typed asset.
        """
        schema = self.schema()
        preview = self.preview()
        payload: dict[str, Any] = {
            "format": self.source.normalized_extension or "bin",
            "asset_kind": self.kind,
            "strategy": self.strategy_name,
            "mime_type": self.source.guessed_mime_type,
            "size_bytes": self.source.size_bytes,
            "binary": self.is_binary,
            "schema": schema,
            "preview": preview,
            "preview_document": self.preview_document(),
            "loader": {
                "class_name": self.__class__.__name__,
                "kind": self.kind,
                "strategy": self.strategy_name,
            },
        }
        payload.update(self._flatten_description())
        return payload

    def preview_document(
        self,
        *,
        max_rows: int = PREVIEW_ROW_LIMIT,
        max_bytes: int = HEADER_READ_BYTES,
    ) -> dict[str, Any]:
        """Build the versioned preview document for this asset.

        Category: asset-handle
        Tags: preview, document, sections, limits, metadata
        Usage: pydelling-cloud needs the standard preview contract for an asset.

        Returns:
            dict[str, Any]: versioned preview document with sections and limits.
        """
        warnings: list[str] = list(self.preview_warnings())
        sections = self.preview_sections(max_rows=max_rows, max_bytes=max_bytes)
        document = {
            "version": PREVIEW_CONTRACT_VERSION,
            "asset_kind": self.kind,
            "format": self.source.normalized_extension or "bin",
            "summary": self.summary_text(),
            "sections": sections,
            "warnings": warnings,
            "limits": {"max_rows": max_rows, "max_bytes": max_bytes},
            "computed_at": _utc_now_iso(),
        }
        metadata = self.preview_metadata()
        if metadata:
            document["metadata"] = metadata
        return document

    def to_runtime_dict(self) -> dict[str, Any]:
        """Serialize this handle into the runtime asset metadata contract.

        Category: asset-handle
        Tags: runtime, metadata, context, asset
        Usage: exposing available assets and their typed preview metadata to generated scripts.

        Returns:
            dict[str, Any]: runtime-safe asset descriptor.
        """
        metadata = self.describe()
        return {
            "reference_name": self.source.reference_name,
            "file_name": self.source.file_name,
            "extension": self.source.normalized_extension,
            "path": str(self.source.path),
            "size_bytes": self.source.size_bytes,
            "mime_type": self.source.guessed_mime_type,
            "metadata": metadata,
        }


class TabularAssetHandle(BaseAssetHandle):
    """Handle CSV, TSV, and delimiter-detected tabular assets.

    Category: asset-handle
    Tags: tabular, csv, tsv, dataframe, records, columns
    Usage: the asset should be read as rows and columns for analysis or transformation.
    """
    kind = "tabular"
    strategy_name = "tabular"

    @cached_property
    def delimiter(self) -> str:
        """Detect the delimiter used by this tabular asset.

        Category: asset-handle
        Tags: tabular, delimiter, csv, tsv
        Usage: parsing a delimited table with the correct separator.

        Returns:
            str: detected delimiter character.
        """
        return _guess_delimiter(self.source.normalized_extension, self.header)

    @cached_property
    def dataframe(self) -> pd.DataFrame:
        """Load and cache this tabular asset as a pandas DataFrame.

        Category: asset-handle
        Tags: tabular, dataframe, csv, tsv
        Usage: repeated tabular operations should avoid reparsing the file.

        Returns:
            pd.DataFrame: parsed tabular data.
        """
        return pd.read_csv(self.source.path, sep=self.delimiter)

    @cached_property
    def max_eager_bytes(self) -> int:
        """Return the byte limit for eager full-table metadata loading.

        Category: asset-handle
        Tags: tabular, performance, metadata, limit
        Usage: deciding whether to load the full table or only a sample for metadata.

        Returns:
            int: configured or default eager-loading byte threshold.
        """
        metadata = self.source.metadata or {}
        configured = metadata.get("max_tabular_eager_bytes")
        if isinstance(configured, int) and configured > 0:
            return configured
        return TABULAR_EAGER_BYTES

    @cached_property
    def eager_metadata_enabled(self) -> bool:
        """Report whether the full table can be loaded for metadata.

        Category: asset-handle
        Tags: tabular, performance, metadata, eager
        Usage: scripts need row counts and dtypes without overloading large files.

        Returns:
            bool: True when full-table metadata loading is allowed.
        """
        return self.source.size_bytes is None or self.source.size_bytes <= self.max_eager_bytes

    def _read_sample_frame(self, nrows: int = PREVIEW_ROW_LIMIT) -> pd.DataFrame:
        return pd.read_csv(self.source.path, sep=self.delimiter, nrows=nrows)

    @cached_property
    def sample_dataframe(self) -> pd.DataFrame:
        """Load a bounded sample of the tabular asset.

        Category: asset-handle
        Tags: tabular, sample, dataframe, preview
        Usage: previewing a large table without loading every row.

        Returns:
            pd.DataFrame: sample rows from the table.
        """
        return self._read_sample_frame(PREVIEW_ROW_LIMIT)

    @cached_property
    def row_count(self) -> int:
        """Return the number of data rows in the tabular asset.

        Category: asset-handle
        Tags: tabular, rows, count, metadata
        Usage: summaries or schema output need a row count.

        Returns:
            int: number of table rows.
        """
        if self.eager_metadata_enabled:
            return int(self.dataframe.shape[0])
        with self.source.path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
            return max(sum(1 for _ in handle) - 1, 0)

    def _metadata_frame(self) -> pd.DataFrame:
        if self.eager_metadata_enabled:
            return self.dataframe
        return self.sample_dataframe

    @cached_property
    def spatial_csv_metadata(self) -> dict[str, Any] | None:
        metadata = self.source.metadata or {}
        spatial = metadata.get("spatial_csv")
        return spatial if isinstance(spatial, dict) else None

    def to_dataframe(self) -> pd.DataFrame:
        """Load this tabular asset as a pandas DataFrame.

        Category: asset-handle
        Tags: tabular, csv, tsv, dataframe, columns
        Usage: the user needs the asset's rows and columns as a DataFrame.

        Returns:
            pd.DataFrame: parsed table with original column names.
        """
        return self.dataframe.copy()

    def to_records(self) -> list[dict[str, Any]]:
        """Load this tabular asset as row dictionaries.

        Category: asset-handle
        Tags: tabular, records, rows, csv, tsv
        Usage: the user needs serializable rows from a delimited table.

        Returns:
            list[dict[str, Any]]: table rows keyed by column name.
        """
        return self.dataframe.fillna("").to_dict(orient="records")

    def schema(self) -> dict[str, Any]:
        """Return row, column, delimiter, and field metadata for this table.

        Category: asset-handle
        Tags: tabular, schema, columns, dtype, delimiter
        Usage: scripts need table structure before selecting columns or transformations.

        Returns:
            dict[str, Any]: tabular schema metadata.
        """
        frame = self._metadata_frame()
        return {
            "kind": self.kind,
            "rows": self.row_count,
            "columns": int(frame.shape[1]),
            "delimiter": self.delimiter,
            "delimiter_label": _delimiter_label(self.delimiter),
            "fields": [
                {"name": column, "dtype": str(dtype)}
                for column, dtype in zip(frame.columns.tolist(), frame.dtypes.tolist(), strict=False)
            ],
        }

    def preview(self) -> dict[str, Any]:
        """Return a bounded row preview for this table.

        Category: asset-handle
        Tags: tabular, preview, rows, columns
        Usage: the user asks to inspect sample rows from a table.

        Returns:
            dict[str, Any]: table preview with columns and rows.
        """
        preview = (
            self.dataframe.head(PREVIEW_ROW_LIMIT)
            if self.eager_metadata_enabled
            else self.sample_dataframe
        )
        return {
            "kind": "table",
            "columns": preview.columns.tolist(),
            "rows": preview.fillna("").astype(str).values.tolist(),
        }

    def preview_metadata(self) -> dict[str, Any]:
        if self.spatial_csv_metadata is None:
            return {}
        return {"spatial_csv": self.spatial_csv_metadata}

    def _numeric_values(self, frame: pd.DataFrame, column: str) -> pd.Series | None:
        if column not in frame.columns:
            return None
        values = pd.to_numeric(frame[column], errors="coerce")
        return values if values.notna().any() else None

    @staticmethod
    def _float_list(values: pd.Series) -> list[float | None]:
        return [float(value) if pd.notna(value) else None for value in values.tolist()]

    def _scatter_section(self, frame: pd.DataFrame, *, total_rows: int) -> dict[str, Any] | None:
        spatial = self.spatial_csv_metadata
        if not spatial or spatial.get("status") != "completed" or not spatial.get("is_spatial"):
            return None

        x_column = spatial.get("x_column")
        y_column = spatial.get("y_column")
        z_column = spatial.get("z_column")
        if not isinstance(x_column, str):
            return None

        x_values = self._numeric_values(frame, x_column)
        if x_values is None:
            return None

        y_values = self._numeric_values(frame, y_column) if isinstance(y_column, str) else None
        z_values = self._numeric_values(frame, z_column) if isinstance(z_column, str) else None
        dimensions = 3 if y_values is not None and z_values is not None else 2 if y_values is not None else 1

        valid_mask = x_values.notna()
        if dimensions >= 2:
            valid_mask &= y_values.notna()
        if dimensions == 3:
            valid_mask &= z_values.notna()
        if not valid_mask.any():
            return None

        coordinate_columns = {
            column
            for column in (x_column, y_column if dimensions >= 2 else None, z_column if dimensions == 3 else None)
            if isinstance(column, str)
        }
        coordinates: dict[str, dict[str, Any]] = {
            "x": {"column": x_column, "values": self._float_list(x_values[valid_mask])},
        }
        if dimensions >= 2 and isinstance(y_column, str) and y_values is not None:
            coordinates["y"] = {"column": y_column, "values": self._float_list(y_values[valid_mask])}
        if dimensions == 3 and isinstance(z_column, str) and z_values is not None:
            coordinates["z"] = {"column": z_column, "values": self._float_list(z_values[valid_mask])}

        numeric_value_columns: list[str] = []
        numeric_value_map: dict[str, pd.Series] = {}
        for column in frame.columns.tolist():
            column_name = str(column)
            if column_name in coordinate_columns:
                continue
            values = self._numeric_values(frame, column_name)
            if values is not None:
                numeric_value_columns.append(column_name)
                numeric_value_map[column_name] = values

        ai_order = [
            column
            for column in spatial.get("value_columns", [])
            if isinstance(column, str) and column in numeric_value_map
        ]
        ordered_value_columns = [
            *dict.fromkeys([*ai_order, *numeric_value_columns]).keys()
        ]
        value_columns = [
            {
                "name": column,
                "values": self._float_list(numeric_value_map[column][valid_mask]),
            }
            for column in ordered_value_columns
        ]

        default_value_column = spatial.get("default_value_column")
        if default_value_column not in ordered_value_columns:
            default_value_column = ordered_value_columns[0] if ordered_value_columns else None

        return {
            "kind": "scatter",
            "title": f"{dimensions}D scatter preview",
            "dimensions": dimensions,
            "coordinates": coordinates,
            "value_columns": value_columns,
            "default_value_column": default_value_column,
            "confidence": spatial.get("confidence"),
            "total_rows": total_rows,
            "shown_rows": len(coordinates["x"]["values"]),
            "truncated": total_rows > int(frame.shape[0]),
        }

    def preview_sections(self, *, max_rows: int = PREVIEW_ROW_LIMIT, max_bytes: int = HEADER_READ_BYTES) -> list[dict[str, Any]]:
        """Return a table preview section for this tabular asset.

        Category: asset-handle
        Tags: tabular, preview, section, rows, columns
        Usage: the UI or MCP context needs sample rows plus truncation metadata.

        Returns:
            list[dict[str, Any]]: one table preview section.
        """
        preview = (
            self.dataframe.head(max_rows)
            if self.eager_metadata_enabled
            else self._read_sample_frame(max_rows)
        )
        total_rows = self.row_count
        sections: list[dict[str, Any]] = []
        scatter = self._scatter_section(preview, total_rows=total_rows)
        if scatter is not None:
            sections.append(scatter)
        sections.append({
            "kind": "table",
            "title": "Preview",
            "columns": preview.columns.tolist(),
            "rows": preview.fillna("").astype(str).values.tolist(),
            "total_rows": total_rows,
            "shown_rows": int(preview.shape[0]),
            "truncated": total_rows > int(preview.shape[0]),
        })
        return sections

    def summary_text(self) -> str:
        """Return row-by-column dimensions for this table.

        Category: asset-handle
        Tags: tabular, summary, rows, columns
        Usage: inventory output needs a compact table summary.

        Returns:
            str: table dimensions.
        """
        schema = self.schema()
        return f"{schema['rows']} rows x {schema['columns']} columns"

    def _flatten_description(self) -> dict[str, Any]:
        preview = self.preview()
        schema = self.schema()
        return {
            "rows": schema["rows"],
            "columns": schema["columns"],
            "column_names": preview["columns"],
            "preview_rows": preview["rows"],
            "shape": [schema["rows"], schema["columns"]],
        }


class PflotranMassBalanceAssetHandle(BaseAssetHandle):
    """Handle PFLOTRAN mass-balance files with quoted headers and numeric rows.

    Category: asset-handle
    Tags: pflotran, mass-balance, dataframe, plotly, preview
    Usage: the asset is a PFLOTRAN ``*-mas.dat`` style table and needs time-series mass or rate plots.
    """
    kind = "pflotran_mass_balance"
    strategy_name = "pflotran_mass_balance"
    DEFAULT_VISIBLE_TRACE_COUNT = 12

    @cached_property
    def columns(self) -> list[str]:
        """Return PFLOTRAN mass-balance columns parsed from the first line.

        Category: asset-handle
        Tags: pflotran, mass-balance, columns, header
        Usage: the file body is whitespace-delimited but column names are comma-separated and quoted.

        Returns:
            list[str]: column names exactly as written by PFLOTRAN.
        """
        columns = _parse_quoted_header_line(_first_non_empty_line(self.header))
        return [str(column).strip() for column in columns]

    @property
    def time_column(self) -> str:
        return self.columns[0]

    @cached_property
    def timestep_columns(self) -> list[str]:
        """Leading ``dt_*`` timestep columns (``dt_flow`` and/or ``dt_tran``).

        Category: asset-handle
        Tags: pflotran, mass-balance, timestep, columns
        Usage: PFLOTRAN writes one or two timestep columns depending on the active modes.

        Returns:
            list[str]: contiguous leading timestep column names after Time.
        """
        found: list[str] = []
        for column in self.columns[1:]:
            if column.strip().strip('"').startswith("dt_"):
                found.append(column)
            else:
                break
        return found or [self.columns[1]]

    @property
    def timestep_column(self) -> str:
        return self.timestep_columns[0]

    @cached_property
    def max_eager_bytes(self) -> int:
        metadata = self.source.metadata or {}
        configured = metadata.get("max_tabular_eager_bytes")
        if isinstance(configured, int) and configured > 0:
            return configured
        return TABULAR_EAGER_BYTES

    @cached_property
    def eager_metadata_enabled(self) -> bool:
        return self.source.size_bytes is None or self.source.size_bytes <= self.max_eager_bytes

    def _read_sample_frame(self, nrows: int = PREVIEW_ROW_LIMIT) -> pd.DataFrame:
        return pd.read_csv(
            self.source.path,
            skiprows=1,
            header=None,
            names=self.columns,
            sep=r"\s+",
            engine="python",
            nrows=nrows,
        )

    @cached_property
    def dataframe(self) -> pd.DataFrame:
        return pd.read_csv(
            self.source.path,
            skiprows=1,
            header=None,
            names=self.columns,
            sep=r"\s+",
            engine="python",
        )

    @cached_property
    def sample_dataframe(self) -> pd.DataFrame:
        return self._read_sample_frame(PREVIEW_ROW_LIMIT)

    @cached_property
    def row_count(self) -> int:
        if self.eager_metadata_enabled:
            return int(self.dataframe.shape[0])
        with self.source.path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
            return max(sum(1 for _ in handle) - 1, 0)

    def _metadata_frame(self) -> pd.DataFrame:
        return self.dataframe if self.eager_metadata_enabled else self.sample_dataframe

    def _mass_columns(self) -> list[str]:
        return self.columns[1 + len(self.timestep_columns):]

    def _column_group(self, column: str) -> str:
        stem = re.sub(r"\s*\[[^\]]+\]\s*$", "", column).strip()
        return stem.split(maxsplit=1)[0] if stem else column

    def _column_label(self, column: str) -> str:
        stem = re.sub(r"\s*\[[^\]]+\]\s*$", "", column).strip()
        parts = stem.split(maxsplit=1)
        return parts[1] if len(parts) > 1 else stem

    @cached_property
    def column_metadata(self) -> list[dict[str, str | None]]:
        return [
            {
                "name": column,
                "group": self._column_group(column),
                "label": self._column_label(column),
                "unit": _extract_unit(column),
            }
            for column in self._mass_columns()
        ]

    @cached_property
    def grouped_columns(self) -> dict[str, list[str]]:
        groups: dict[str, list[str]] = {}
        for item in self.column_metadata:
            group = str(item["group"] or "Ungrouped")
            groups.setdefault(group, []).append(str(item["name"]))
        return groups

    @cached_property
    def unit_columns(self) -> dict[str, list[str]]:
        groups: dict[str, list[str]] = {}
        for item in self.column_metadata:
            unit = str(item["unit"] or "unitless")
            groups.setdefault(unit, []).append(str(item["name"]))
        return groups

    def to_dataframe(self) -> pd.DataFrame:
        """Load this PFLOTRAN mass-balance file as a pandas DataFrame.

        Category: asset-handle
        Tags: pflotran, mass-balance, dataframe
        Usage: scripts need the parsed PFLOTRAN mass-balance table with original column names.

        Returns:
            pd.DataFrame: parsed mass-balance table.
        """
        return self.dataframe.copy()

    def to_records(self) -> list[dict[str, Any]]:
        """Load this PFLOTRAN mass-balance file as row dictionaries.

        Category: asset-handle
        Tags: pflotran, mass-balance, records
        Usage: scripts need serializable rows from a PFLOTRAN mass-balance file.

        Returns:
            list[dict[str, Any]]: table rows keyed by original column name.
        """
        return self.dataframe.fillna("").to_dict(orient="records")

    def schema(self) -> dict[str, Any]:
        """Return PFLOTRAN mass-balance table metadata.

        Category: asset-handle
        Tags: pflotran, mass-balance, schema, units, groups
        Usage: scripts need time column, units, and group names before plotting or selecting columns.

        Returns:
            dict[str, Any]: PFLOTRAN mass-balance schema metadata.
        """
        frame = self._metadata_frame()
        return {
            "kind": self.kind,
            "rows": self.row_count,
            "columns": int(len(self.columns)),
            "time_column": self.time_column,
            "time_unit": _extract_unit(self.time_column),
            "timestep_column": self.timestep_column,
            "timestep_unit": _extract_unit(self.timestep_column),
            "units": list(self.unit_columns.keys()),
            "groups": {group: len(columns) for group, columns in self.grouped_columns.items()},
            "unit_groups": {unit: len(columns) for unit, columns in self.unit_columns.items()},
            "fields": [
                {"name": column, "dtype": str(dtype)}
                for column, dtype in zip(frame.columns.tolist(), frame.dtypes.tolist(), strict=False)
            ],
            "mass_balance_fields": self.column_metadata,
        }

    def preview(self) -> dict[str, Any]:
        preview = (
            self.dataframe.head(PREVIEW_ROW_LIMIT)
            if self.eager_metadata_enabled
            else self.sample_dataframe
        )
        return {
            "kind": "table",
            "columns": preview.columns.tolist(),
            "rows": preview.fillna("").astype(str).values.tolist(),
        }

    @staticmethod
    def _float_list(values: pd.Series) -> list[float | None]:
        return [float(value) if pd.notna(value) else None for value in values.tolist()]

    def _ordered_visible_columns(self, columns: list[str]) -> set[str]:
        ordered = sorted(
            columns,
            key=lambda column: (
                0 if self._column_group(column).lower() == "global" else 1,
                self.columns.index(column),
            ),
        )
        return set(ordered[:self.DEFAULT_VISIBLE_TRACE_COUNT])

    def _plotly_section(
        self,
        *,
        title: str,
        frame: pd.DataFrame,
        y_columns: list[str],
        y_title: str,
        total_rows: int,
    ) -> dict[str, Any] | None:
        if not y_columns:
            return None
        x_values = self._float_list(pd.to_numeric(frame[self.time_column], errors="coerce"))
        visible_columns = self._ordered_visible_columns(y_columns)
        traces: list[dict[str, Any]] = []
        for column in y_columns:
            values = self._float_list(pd.to_numeric(frame[column], errors="coerce"))
            trace: dict[str, Any] = {
                "type": "scatter",
                "mode": "lines",
                "name": self._column_label(column),
                "x": x_values,
                "y": values,
                "hovertemplate": f"{self.time_column}: %{{x}}<br>{column}: %{{y:.6g}}<extra></extra>",
            }
            if column not in visible_columns:
                trace["visible"] = "legendonly"
            traces.append(trace)
        return {
            "kind": "plotly",
            "title": title,
            "figure": {
                "data": traces,
                "layout": {
                    "margin": {"l": 64, "r": 22, "t": 14, "b": 48},
                    "paper_bgcolor": "transparent",
                    "plot_bgcolor": "transparent",
                    "xaxis": {"title": self.time_column, "zeroline": False},
                    "yaxis": {"title": y_title, "zeroline": False},
                    "legend": {"orientation": "h", "y": -0.24},
                    "hovermode": "x unified",
                },
            },
            "total_rows": total_rows,
            "shown_rows": int(frame.shape[0]),
            "truncated": total_rows > int(frame.shape[0]),
        }

    def _group_summary_section(self) -> dict[str, Any]:
        rows = []
        for unit, columns in self.unit_columns.items():
            counts = Counter(self._column_group(column) for column in columns)
            rows.extend(
                [group, unit, count]
                for group, count in sorted(counts.items(), key=lambda item: item[0].lower())
            )
        return {
            "kind": "table",
            "title": "Mass-balance groups",
            "columns": ["group", "unit", "columns"],
            "rows": rows,
        }

    def preview_sections(self, *, max_rows: int = PREVIEW_ROW_LIMIT, max_bytes: int = HEADER_READ_BYTES) -> list[dict[str, Any]]:
        """Return Plotly and table sections for a PFLOTRAN mass-balance file.

        Category: asset-handle
        Tags: pflotran, mass-balance, preview, plotly, table
        Usage: pydelling-cloud needs grouped time-series plots plus bounded raw rows.

        Returns:
            list[dict[str, Any]]: Plotly charts, group summary, and table preview sections.
        """
        frame = (
            self.dataframe.head(max_rows)
            if self.eager_metadata_enabled
            else self._read_sample_frame(max_rows)
        )
        total_rows = self.row_count
        sections: list[dict[str, Any]] = []
        timestep_section = self._plotly_section(
            title="Timestep size",
            frame=frame,
            y_columns=self.timestep_columns,
            y_title=self.timestep_column,
            total_rows=total_rows,
        )
        if timestep_section is not None:
            sections.append(timestep_section)
        for unit, columns in self.unit_columns.items():
            unit_section = self._plotly_section(
                title=f"Mass balance ({unit})",
                frame=frame,
                y_columns=columns,
                y_title=unit,
                total_rows=total_rows,
            )
            if unit_section is not None:
                sections.append(unit_section)
        preview = frame.fillna("").astype(str)
        return [
            *sections,
            self._group_summary_section(),
            {
                "kind": "table",
                "title": "Data preview",
                "columns": preview.columns.tolist(),
                "rows": preview.values.tolist(),
                "total_rows": total_rows,
                "shown_rows": int(frame.shape[0]),
                "truncated": total_rows > int(frame.shape[0]),
            },
        ]

    def preview_metadata(self) -> dict[str, Any]:
        schema = self.schema()
        return {
            "time_column": schema["time_column"],
            "time_unit": schema["time_unit"],
            "timestep_column": schema["timestep_column"],
            "units": schema["units"],
            "groups": schema["groups"],
        }

    def summary_text(self) -> str:
        schema = self.schema()
        units = ", ".join(schema["units"])
        return f"{schema['rows']} PFLOTRAN mass-balance rows x {schema['columns']} columns ({units})"

    def _flatten_description(self) -> dict[str, Any]:
        preview = self.preview()
        schema = self.schema()
        return {
            "rows": schema["rows"],
            "columns": schema["columns"],
            "column_names": preview["columns"],
            "preview_rows": preview["rows"],
            "shape": [schema["rows"], schema["columns"]],
            "time_column": schema["time_column"],
            "units": schema["units"],
            "groups": schema["groups"],
        }


class PflotranObservationAssetHandle(PflotranMassBalanceAssetHandle):
    """Handle PFLOTRAN observation-point time series (``*-obs-N.tec``).

    Category: asset-handle
    Tags: pflotran, observation, tec, time-series, plotly, dataframe
    Usage: the asset is a PFLOTRAN OBSERVATION output file and needs per-point time-series plots.
    """
    kind = "pflotran_observation"
    strategy_name = "pflotran_observation"

    _POINT_RE = re.compile(r"(\S+)\s*\(\d+\)")

    def _mass_columns(self) -> list[str]:
        # Observation files have no ``dt_tran`` column: everything after Time is data.
        return self.columns[1:]

    def _column_group(self, column: str) -> str:
        match = self._POINT_RE.search(column)
        if match:
            return match.group(1)
        stem = re.split(r"\s*\[[^\]]+\]", column, maxsplit=1)[0].strip()
        return stem.split(maxsplit=1)[0] if stem else column

    def _column_label(self, column: str) -> str:
        variable = re.split(r"\s*\[[^\]]+\]", column, maxsplit=1)[0].strip() or column
        match = self._POINT_RE.search(column)
        return f"{variable} · {match.group(1)}" if match else variable

    @cached_property
    def column_metadata(self) -> list[dict[str, str | None]]:
        return [
            {
                "name": column,
                "group": self._column_group(column),
                "label": self._column_label(column),
                "unit": _extract_embedded_unit(column),
            }
            for column in self._mass_columns()
        ]

    def schema(self) -> dict[str, Any]:
        """Return PFLOTRAN observation table metadata.

        Category: asset-handle
        Tags: pflotran, observation, schema, units, points
        Usage: scripts need the time column, units, and observation-point names before plotting.

        Returns:
            dict[str, Any]: PFLOTRAN observation schema metadata.
        """
        schema = super().schema()
        schema["kind"] = self.kind
        schema.pop("timestep_column", None)
        schema.pop("timestep_unit", None)
        schema["observation_points"] = sorted(self.grouped_columns.keys())
        return schema

    def _group_summary_section(self) -> dict[str, Any]:
        rows = []
        for unit, columns in self.unit_columns.items():
            counts = Counter(self._column_group(column) for column in columns)
            rows.extend(
                [group, unit, count]
                for group, count in sorted(counts.items(), key=lambda item: item[0].lower())
            )
        return {
            "kind": "table",
            "title": "Observation points",
            "columns": ["point", "unit", "columns"],
            "rows": rows,
        }

    def preview_sections(self, *, max_rows: int = PREVIEW_ROW_LIMIT, max_bytes: int = HEADER_READ_BYTES) -> list[dict[str, Any]]:
        """Return Plotly and table sections for a PFLOTRAN observation file.

        Category: asset-handle
        Tags: pflotran, observation, preview, plotly, table
        Usage: pydelling-cloud needs per-unit time-series plots plus bounded raw rows.

        Returns:
            list[dict[str, Any]]: Plotly charts, point summary, and table preview sections.
        """
        frame = (
            self.dataframe.head(max_rows)
            if self.eager_metadata_enabled
            else self._read_sample_frame(max_rows)
        )
        total_rows = self.row_count
        sections: list[dict[str, Any]] = []
        for unit, columns in self.unit_columns.items():
            unit_section = self._plotly_section(
                title=f"Observations ({unit})",
                frame=frame,
                y_columns=columns,
                y_title=unit,
                total_rows=total_rows,
            )
            if unit_section is not None:
                sections.append(unit_section)
        preview = frame.fillna("").astype(str)
        return [
            *sections,
            self._group_summary_section(),
            {
                "kind": "table",
                "title": "Data preview",
                "columns": preview.columns.tolist(),
                "rows": preview.values.tolist(),
                "total_rows": total_rows,
                "shown_rows": int(frame.shape[0]),
                "truncated": total_rows > int(frame.shape[0]),
            },
        ]

    def preview_metadata(self) -> dict[str, Any]:
        schema = self.schema()
        return {
            "time_column": schema["time_column"],
            "time_unit": schema["time_unit"],
            "units": schema["units"],
            "groups": schema["groups"],
            "observation_points": schema["observation_points"],
        }

    def summary_text(self) -> str:
        schema = self.schema()
        units = ", ".join(schema["units"])
        points = len(schema["observation_points"])
        return (
            f"{schema['rows']} PFLOTRAN observation rows x {schema['columns']} columns "
            f"· {points} point(s) ({units})"
        )


class RasterAssetHandle(BaseAssetHandle):
    """Handle Esri ASCII grid rasters (.asc) with header metadata and cell values.

    Category: asset-handle
    Tags: raster, asc, esri, grid, elevation, preview
    Usage: the asset is an ASCII raster grid (ncols/nrows header) such as a surface elevation map.
    """
    kind = "raster"
    strategy_name = "esri_ascii_raster"

    @cached_property
    def _header_info(self) -> tuple[dict[str, float], int]:
        return _parse_esri_raster_header(self.header)

    @property
    def grid_header(self) -> dict[str, float]:
        """Return the parsed Esri ASCII raster header entries.

        Category: asset-handle
        Tags: raster, header, metadata, grid
        Usage: scripts need grid dimensions, origin, cell size, or nodata value before loading cells.

        Returns:
            dict[str, float]: lower-cased header key/value pairs.
        """
        return self._header_info[0]

    @property
    def ncols(self) -> int:
        return int(self.grid_header.get("ncols", 0))

    @property
    def nrows(self) -> int:
        return int(self.grid_header.get("nrows", 0))

    @property
    def cell_size(self) -> tuple[float, float]:
        header = self.grid_header
        cellsize = header.get("cellsize")
        dx = header.get("dx", cellsize)
        dy = header.get("dy", cellsize)
        return (abs(dx) if dx else 0.0, abs(dy) if dy else 0.0)

    @property
    def origin(self) -> tuple[float, float]:
        header = self.grid_header
        dx, dy = self.cell_size
        if "xllcenter" in header or "yllcenter" in header:
            return (
                header.get("xllcenter", header.get("xllcorner", 0.0)) - dx / 2,
                header.get("yllcenter", header.get("yllcorner", 0.0)) - dy / 2,
            )
        return (header.get("xllcorner", 0.0), header.get("yllcorner", 0.0))

    @property
    def nodata_value(self) -> float | None:
        return self.grid_header.get("nodata_value")

    @cached_property
    def eager_stats_enabled(self) -> bool:
        return self.source.size_bytes is None or self.source.size_bytes <= RASTER_EAGER_BYTES

    @cached_property
    def grid(self) -> pd.DataFrame:
        """Load the raster cell values as a DataFrame with nodata masked to NaN.

        Category: asset-handle
        Tags: raster, grid, dataframe, nodata
        Usage: scripts need the full 2D cell-value matrix of an ASCII raster.

        Returns:
            pd.DataFrame: nrows x ncols cell values, top row first.
        """
        _, skiprows = self._header_info
        frame = pd.read_csv(
            self.source.path,
            skiprows=skiprows,
            header=None,
            sep=r"\s+",
            engine="python",
        )
        nodata = self.nodata_value
        if nodata is not None:
            frame = frame.mask(frame == nodata)
        return frame

    def to_dataframe(self) -> pd.DataFrame:
        """Load this ASCII raster as a DataFrame of cell values.

        Category: asset-handle
        Tags: raster, asc, dataframe, grid
        Usage: scripts need raster cells for interpolation, statistics, or surface building.

        Returns:
            pd.DataFrame: nrows x ncols cell values with nodata as NaN.
        """
        return self.grid.copy()

    def _value_stats(self) -> dict[str, Any]:
        values = self.grid.to_numpy().ravel()
        finite = values[pd.notna(values)]
        stats: dict[str, Any] = {"nodata_cells": int(values.size - finite.size)}
        if finite.size:
            stats.update(
                min=float(finite.min()),
                max=float(finite.max()),
                mean=float(finite.mean()),
            )
        return stats

    def schema(self) -> dict[str, Any]:
        """Return raster grid metadata: dimensions, extent, cell size, and value range.

        Category: asset-handle
        Tags: raster, schema, extent, cellsize, nodata
        Usage: scripts need raster geometry and value range before processing cells.

        Returns:
            dict[str, Any]: raster schema metadata.
        """
        dx, dy = self.cell_size
        x0, y0 = self.origin
        schema: dict[str, Any] = {
            "kind": self.kind,
            "rows": self.nrows,
            "columns": self.ncols,
            "cell_size": [dx, dy],
            "extent": {
                "xmin": x0,
                "xmax": x0 + dx * self.ncols,
                "ymin": y0,
                "ymax": y0 + dy * self.nrows,
            },
            "nodata_value": self.nodata_value,
        }
        if self.eager_stats_enabled:
            schema["values"] = self._value_stats()
        return schema

    def _stats_rows(self, schema: dict[str, Any]) -> list[list[str]]:
        extent = schema["extent"]
        rows = [
            ["grid size", f"{schema['rows']} rows x {schema['columns']} cols"],
            ["cell size", f"{schema['cell_size'][0]:.6g} x {schema['cell_size'][1]:.6g}"],
            ["x extent", f"{extent['xmin']:.6g} to {extent['xmax']:.6g}"],
            ["y extent", f"{extent['ymin']:.6g} to {extent['ymax']:.6g}"],
        ]
        if schema.get("nodata_value") is not None:
            rows.append(["nodata value", f"{schema['nodata_value']:.6g}"])
        values = schema.get("values") or {}
        if "min" in values:
            rows.append(["value range", f"{values['min']:.6g} to {values['max']:.6g} (mean {values['mean']:.6g})"])
        if values.get("nodata_cells"):
            rows.append(["nodata cells", str(values["nodata_cells"])])
        return rows

    def preview(self) -> dict[str, Any]:
        """Return raster header and value statistics as a key/value table preview.

        Category: asset-handle
        Tags: raster, preview, stats, table
        Usage: the user inspects an ASCII raster asset without loading the full grid in the UI.

        Returns:
            dict[str, Any]: property/value table preview.
        """
        rows = self._stats_rows(self.schema())
        return {
            "kind": "table",
            "columns": ["property", "value"],
            "rows": rows,
        }

    def preview_sections(self, *, max_rows: int = PREVIEW_ROW_LIMIT, max_bytes: int = HEADER_READ_BYTES) -> list[dict[str, Any]]:
        """Return a raster viewer marker section plus a grid summary table.

        Category: asset-handle
        Tags: raster, preview, section, heatmap
        Usage: pydelling-cloud renders the 2D raster heatmap client-side and shows grid metadata.

        Returns:
            list[dict[str, Any]]: raster viewer and summary table sections.
        """
        schema = self.schema()
        return [
            {
                "kind": "raster",
                "title": "2D raster preview",
                "metadata": {
                    "rows": schema["rows"],
                    "columns": schema["columns"],
                    "cell_size": schema["cell_size"],
                    "extent": schema["extent"],
                    "nodata_value": schema["nodata_value"],
                    **(schema.get("values") or {}),
                },
            },
            {
                "kind": "table",
                "title": "Raster summary",
                "columns": ["property", "value"],
                "rows": self._stats_rows(schema),
            },
        ]

    def preview_metadata(self) -> dict[str, Any]:
        schema = self.schema()
        return {
            "rows": schema["rows"],
            "columns": schema["columns"],
            "cell_size": schema["cell_size"],
            "extent": schema["extent"],
            "nodata_value": schema["nodata_value"],
        }

    def summary_text(self) -> str:
        schema = self.schema()
        values = schema.get("values") or {}
        value_range = (
            f", values {values['min']:.6g} to {values['max']:.6g}" if "min" in values else ""
        )
        return f"{schema['rows']} x {schema['columns']} ASCII raster grid{value_range}"

    def _flatten_description(self) -> dict[str, Any]:
        schema = self.schema()
        return {
            "rows": schema["rows"],
            "columns": schema["columns"],
            "shape": [schema["rows"], schema["columns"]],
            "cell_size": schema["cell_size"],
            "extent": schema["extent"],
            "nodata_value": schema["nodata_value"],
            "values": schema.get("values") or {},
        }


class JsonAssetHandle(BaseAssetHandle):
    """Handle JSON assets as records, DataFrames, text, or structured previews.

    Category: asset-handle
    Tags: json, records, dataframe, text, object, list
    Usage: the asset is JSON and the script needs structured data or formatted text.
    """
    kind = "json"
    strategy_name = "json"

    @cached_property
    def payload(self) -> Any:
        """Load and cache the JSON payload from disk.

        Category: asset-handle
        Tags: json, payload, load, cache
        Usage: scripts need the parsed JSON object, list, or scalar.

        Returns:
            Any: parsed JSON payload.
        """
        return json.loads(self.source.path.read_text(encoding="utf-8"))

    def to_records(self) -> list[dict[str, Any]]:
        """Load a JSON array of objects as row dictionaries.

        Category: asset-handle
        Tags: json, records, rows, list
        Usage: a JSON payload is a list of objects that should behave like table rows.

        Returns:
            list[dict[str, Any]]: JSON objects from the top-level list.
        """
        if isinstance(self.payload, list) and all(isinstance(item, dict) for item in self.payload):
            return list(self.payload)
        raise TypeError("JSON payload is not a list of objects.")

    def to_dataframe(self) -> pd.DataFrame:
        """Load a JSON records payload as a pandas DataFrame.

        Category: asset-handle
        Tags: json, dataframe, records, table
        Usage: the user wants to analyze or transform JSON records with pandas.

        Returns:
            pd.DataFrame: DataFrame built from top-level JSON objects.
        """
        return pd.DataFrame(self.to_records())

    def to_text(self) -> str:
        """Render the JSON payload as formatted text.

        Category: asset-handle
        Tags: json, text, pretty-print, serialize
        Usage: the user asks to inspect, summarize, or write the JSON as readable text.

        Returns:
            str: indented JSON string.
        """
        return json.dumps(self.payload, indent=2, ensure_ascii=True)

    def schema(self) -> dict[str, Any]:
        """Return structural metadata for the JSON payload.

        Category: asset-handle
        Tags: json, schema, records, object, fields
        Usage: scripts need to know whether JSON is records, object, list, or scalar.

        Returns:
            dict[str, Any]: JSON schema metadata.
        """
        payload = self.payload
        if isinstance(payload, list):
            sample = payload[:PREVIEW_ROW_LIMIT]
            if sample and all(isinstance(item, dict) for item in sample):
                frame = pd.DataFrame(sample)
                all_columns = list(dict.fromkeys(key for item in payload if isinstance(item, dict) for key in item.keys()))
                return {
                    "kind": "json_records",
                    "top_level_type": "list",
                    "rows": len(payload),
                    "columns": len(all_columns),
                    "fields": [
                        {"name": column, "dtype": str(frame[column].dtype) if column in frame else "unknown"}
                        for column in all_columns
                    ],
                }
            value_types = sorted({type(item).__name__ for item in sample}) if sample else []
            return {
                "kind": "json_list",
                "top_level_type": "list",
                "rows": len(payload),
                "value_types": value_types,
            }
        if isinstance(payload, dict):
            return {
                "kind": "json_object",
                "top_level_type": "dict",
                "keys": list(payload.keys())[:50],
                "fields": [
                    {"name": key, "dtype": type(value).__name__}
                    for key, value in list(payload.items())[:50]
                ],
            }
        return {"kind": "json_scalar", "top_level_type": type(payload).__name__}

    def preview(self) -> dict[str, Any]:
        """Return a bounded preview of the JSON payload.

        Category: asset-handle
        Tags: json, preview, records, object, list
        Usage: the user asks to inspect JSON contents in table or key-value form.

        Returns:
            dict[str, Any]: JSON preview payload.
        """
        payload = self.payload
        schema = self.schema()
        if schema["kind"] == "json_records":
            frame = self.to_dataframe().head(PREVIEW_ROW_LIMIT)
            return {
                "kind": "table",
                "columns": frame.columns.tolist(),
                "rows": frame.fillna("").astype(str).values.tolist(),
            }
        if isinstance(payload, dict):
            return {
                "kind": "mapping",
                "columns": ["key", "value"],
                "rows": _stringify_mapping(dict(list(payload.items())[:PREVIEW_ROW_LIMIT])),
            }
        if isinstance(payload, list):
            return {
                "kind": "list",
                "columns": ["index", "value"],
                "rows": [
                    [str(index), _coerce_preview_value(value)]
                    for index, value in enumerate(payload[:PREVIEW_ROW_LIMIT])
                ],
            }
        return {
            "kind": "scalar",
            "columns": ["value"],
            "rows": [[_coerce_preview_value(payload)]],
        }

    def preview_sections(self, *, max_rows: int = PREVIEW_ROW_LIMIT, max_bytes: int = HEADER_READ_BYTES) -> list[dict[str, Any]]:
        """Return JSON and optional table preview sections.

        Category: asset-handle
        Tags: json, preview, section, records, table
        Usage: pydelling-cloud needs both raw JSON context and tabular record samples.

        Returns:
            list[dict[str, Any]]: JSON preview sections.
        """
        if self.schema()["kind"] == "json_records":
            frame = self.to_dataframe().head(max_rows)
            sections = [{
                "kind": "table",
                "title": "Preview",
                "columns": frame.columns.tolist(),
                "rows": frame.fillna("").astype(str).values.tolist(),
                "total_rows": len(self.payload),
                "shown_rows": int(frame.shape[0]),
                "truncated": len(self.payload) > int(frame.shape[0]),
            }]
        else:
            sections = super().preview_sections(max_rows=max_rows, max_bytes=max_bytes)
        return [
            {
                "kind": "json",
                "title": "JSON",
                "value": _limit_json_value(self.payload, max_rows),
                "truncated": json.dumps(self.payload, ensure_ascii=True) != json.dumps(_limit_json_value(self.payload, max_rows), ensure_ascii=True),
            },
            *sections,
        ]

    def summary_text(self) -> str:
        """Return a short summary of the JSON payload shape.

        Category: asset-handle
        Tags: json, summary, records, keys
        Usage: inventory output needs compact JSON metadata.

        Returns:
            str: one-line JSON summary.
        """
        schema = self.schema()
        if schema["kind"] == "json_records":
            return f"{schema['rows']} JSON records"
        if schema["kind"] == "json_object":
            return f"{len(schema.get('keys', []))} JSON keys"
        return f"JSON {schema['top_level_type']}"

    def _flatten_description(self) -> dict[str, Any]:
        preview = self.preview()
        schema = self.schema()
        payload: dict[str, Any] = {"top_level_type": schema.get("top_level_type")}
        if schema["kind"] == "json_records":
            payload.update(
                {
                    "rows": schema["rows"],
                    "columns": schema["columns"],
                    "column_names": preview["columns"],
                    "preview_rows": preview["rows"],
                }
            )
        elif "keys" in schema:
            payload["keys"] = schema["keys"]
        return payload


class TextAssetHandle(BaseAssetHandle):
    """Handle plain text, Markdown, logs, YAML, and other text-like assets.

    Category: asset-handle
    Tags: text, markdown, log, yaml, lines
    Usage: the asset should be read as decoded UTF-8 text.
    """
    kind = "text"
    strategy_name = "text"

    @cached_property
    def text(self) -> str:
        """Load and cache the asset as decoded UTF-8 text.

        Category: asset-handle
        Tags: text, load, utf-8, cache
        Usage: scripts need the full decoded text content.

        Returns:
            str: decoded text.
        """
        return self.source.path.read_text(encoding="utf-8", errors="replace")

    @cached_property
    def lines(self) -> list[str]:
        """Split the decoded text into lines.

        Category: asset-handle
        Tags: text, lines, split
        Usage: previews or scripts need line-oriented text processing.

        Returns:
            list[str]: decoded text lines.
        """
        return self.text.splitlines()

    def to_text(self) -> str:
        """Load this text asset as a string.

        Category: asset-handle
        Tags: text, lines, markdown, log, yaml
        Usage: the user asks to read, summarize, transform, or extract text content.

        Returns:
            str: decoded asset contents.
        """
        return self.text

    def schema(self) -> dict[str, Any]:
        """Return line count and encoding metadata for this text asset.

        Category: asset-handle
        Tags: text, schema, rows, encoding
        Usage: scripts need text size metadata before processing.

        Returns:
            dict[str, Any]: text schema metadata.
        """
        return {
            "kind": self.kind,
            "rows": len(self.lines),
            "encoding": "utf-8",
        }

    def preview(self) -> dict[str, Any]:
        """Return the first lines of this text asset as a table preview.

        Category: asset-handle
        Tags: text, preview, lines, table
        Usage: the user asks to inspect a text file without reading all lines in the UI.

        Returns:
            dict[str, Any]: line-numbered text preview.
        """
        return {
            "kind": "text",
            "columns": ["line_no", "text"],
            "rows": [[str(index + 1), line] for index, line in enumerate(self.lines[:PREVIEW_LINE_LIMIT])],
            "lines": self.lines[:PREVIEW_LINE_LIMIT],
        }

    def preview_sections(self, *, max_rows: int = PREVIEW_ROW_LIMIT, max_bytes: int = HEADER_READ_BYTES) -> list[dict[str, Any]]:
        """Return a bounded text preview section.

        Category: asset-handle
        Tags: text, preview, section, lines
        Usage: pydelling-cloud needs display-ready text lines with truncation status.

        Returns:
            list[dict[str, Any]]: one text preview section.
        """
        lines = self.lines[:max_rows]
        return [{
            "kind": "text",
            "title": "Text",
            "lines": lines,
            "truncated": len(self.lines) > len(lines),
        }]

    def summary_text(self) -> str:
        """Return the number of text lines in the asset.

        Category: asset-handle
        Tags: text, summary, lines
        Usage: inventory output needs compact text metadata.

        Returns:
            str: line-count summary.
        """
        return f"{len(self.lines)} text lines"

    def _flatten_description(self) -> dict[str, Any]:
        preview = self.preview()
        return {"rows": len(self.lines), "preview_lines": preview["lines"]}


class ImageAssetHandle(BaseAssetHandle):
    """Handle image assets for preview metadata and dimensions.

    Category: asset-handle
    Tags: image, png, jpg, jpeg, gif, dimensions, mime
    Usage: the asset is an image and scripts need MIME type, size, or preview metadata.
    """
    kind = "image"
    strategy_name = "image"

    def schema(self) -> dict[str, Any]:
        """Return MIME, size, and dimension metadata for this image.

        Category: asset-handle
        Tags: image, schema, dimensions, mime
        Usage: scripts need image metadata without decoding the full image.

        Returns:
            dict[str, Any]: image schema metadata.
        """
        dimensions = _image_dimensions(self.source.path, self.source.normalized_extension) or {}
        return {
            "kind": self.kind,
            "mime_type": self.source.guessed_mime_type,
            "bytes": self.source.size_bytes,
            **dimensions,
        }

    def preview(self) -> dict[str, Any]:
        """Return image preview metadata.

        Category: asset-handle
        Tags: image, preview, mime, dimensions
        Usage: pydelling-cloud needs to identify the asset as an image preview.

        Returns:
            dict[str, Any]: image preview metadata.
        """
        return {
            "kind": "image",
            "mime_type": self.source.guessed_mime_type,
            **self.schema(),
        }

    def preview_sections(self, *, max_rows: int = PREVIEW_ROW_LIMIT, max_bytes: int = HEADER_READ_BYTES) -> list[dict[str, Any]]:
        """Return an image preview section.

        Category: asset-handle
        Tags: image, preview, section, mime
        Usage: the UI needs display metadata for an image asset.

        Returns:
            list[dict[str, Any]]: one image preview section.
        """
        return [{
            "kind": "image",
            "title": "Image",
            "mime_type": self.source.guessed_mime_type,
            **self.schema(),
        }]

    def summary_text(self) -> str:
        """Return image dimensions when available.

        Category: asset-handle
        Tags: image, summary, dimensions
        Usage: inventory output needs compact image metadata.

        Returns:
            str: image dimension summary or generic image text.
        """
        schema = self.schema()
        if schema.get("width") and schema.get("height"):
            return f"{schema['width']} x {schema['height']} image"
        return "image"


class IgpAssetHandle(BaseAssetHandle):
    """Handle iGP/GiD project directories with mesh, region, boundary, and material metadata.

    Category: asset-handle
    Tags: igp, gid, mesh, vtk, regions, boundaries, materials
    Usage: the user asks to inspect, summarize, convert, or visualize an iGP/GiD mesh asset.
    """
    kind = "igp_reader"
    strategy_name = "igp_gid"

    @property
    def is_binary(self) -> bool:
        """Report that iGP/GiD project directories are not binary blobs.

        Category: asset-handle
        Tags: igp, gid, directory, binary
        Usage: preview logic needs text/binary behavior for directory-backed meshes.

        Returns:
            bool: always False.
        """
        return False

    @cached_property
    def reader(self):
        """Load and cache the iGPReader for this project directory.

        Category: asset-handle
        Tags: igp, gid, reader, cache
        Usage: multiple schema, preview, or export operations need the same iGPReader.

        Returns:
            iGPReader: cached reader for the iGP/GiD project.
        """
        return self.to_igp_reader()

    def to_igp_reader(self, *, build_mesh: bool = False, output_folder: str | Path | None = None):
        """Open this iGP/GiD asset with pydelling.readers.iGPReader.

        Category: asset-handle
        Tags: igp, gid, reader, mesh, regions, materials
        Usage: scripts need direct iGPReader methods for mesh conversion, regions, or material access.

        Returns:
            iGPReader: initialized pydelling iGP reader.
        """
        from pydelling.readers import iGPReader

        return iGPReader(
            self.source.path,
            project_name=Path(self.source.file_name).stem,
            build_mesh=build_mesh,
            output_folder=output_folder,
        )

    def to_vtk(self, filename: str | Path, cell_data=None):
        """Export this iGP/GiD asset to a VTK mesh file, optionally with per-cell data arrays.

        Category: asset-handle
        Tags: igp, gid, vtk, mesh, export, visualization, cell data
        Usage: the user asks to convert an iGP/GiD project into VTK for visualization or download. cell_data maps array names to per-element values in original element order.

        Returns:
            Any: value returned by iGPReader.to_vtk.
        """
        reader = self.to_igp_reader(build_mesh=False, output_folder=None)
        return reader.to_vtk(filename, cell_data=cell_data)

    def _node_bounds(self) -> list[list[float]]:
        nodes = self.reader.nodes
        return [
            [float(nodes[:, 0].min()), float(nodes[:, 1].min()), float(nodes[:, 2].min())],
            [float(nodes[:, 0].max()), float(nodes[:, 1].max()), float(nodes[:, 2].max())],
        ]

    def _centroid_bounds(self) -> list[list[float]]:
        centroids = self.reader.centroids
        return [
            [float(centroids[:, 0].min()), float(centroids[:, 1].min()), float(centroids[:, 2].min())],
            [float(centroids[:, 0].max()), float(centroids[:, 1].max()), float(centroids[:, 2].max())],
        ]

    @cached_property
    def region_summaries(self) -> list[dict[str, Any]]:
        """Summaries of the GiD/iGP surface regions, computed once per handle.

        Category: asset-handle
        Tags: igp, gid, regions, boundaries, summary
        Usage: scripts need per-region face/node/cell counts; iGP surface regions double as the boundary face sets.

        Returns:
            list[dict[str, Any]]: one ``{name, faces, nodes, cells}`` entry per region.
        """
        summaries: list[dict[str, Any]] = []
        for name, info in self.reader.region_dict.items():
            node_ids = sorted({int(node_id) for face in info.get("elements", []) for node_id in face})
            summaries.append(
                {
                    "name": name,
                    "faces": int(info.get("length") or len(info.get("elements", []))),
                    "nodes": len(node_ids),
                    "cells": int(len(info.get("centroid_id", []))),
                }
            )
        return summaries

    def _region_summaries(self) -> list[dict[str, Any]]:
        return self.region_summaries

    def _material_summaries(self) -> list[dict[str, Any]]:
        summaries: list[dict[str, Any]] = []
        for name, element_ids in self.reader.material_dict.items():
            try:
                count = int(len(element_ids))
            except TypeError:
                count = 0
            summaries.append({"name": str(name), "cells": count})
        return summaries

    def schema(self) -> dict[str, Any]:
        """Return mesh, region, boundary, and material metadata for this iGP asset.

        Category: asset-handle
        Tags: igp, gid, mesh, schema, regions, materials
        Usage: scripts need to understand iGP mesh structure before export or visualization.

        Returns:
            dict[str, Any]: iGP mesh schema metadata.
        """
        element_counts = Counter(len(nodes) for nodes in self.reader.element_nodes)
        cell_types = {
            CELL_TYPE_BY_NODE_COUNT.get(node_count, f"{node_count}_node_cell"): count
            for node_count, count in sorted(element_counts.items())
        }
        return {
            "kind": self.kind,
            "format": "gid",
            "storage_type": "directory",
            "elements": int(self.reader.n_mesh_elements),
            "nodes": int(self.reader.n_mesh_nodes),
            "centroids": int(len(self.reader.centroids)),
            "cell_types": cell_types,
            "bounds": {
                "nodes": self._node_bounds(),
                "centroids": self._centroid_bounds(),
            },
            # GiD/iGP surface regions ARE the boundary face sets; both keys
            # expose the same summaries (kept for API compatibility).
            "regions": self.region_summaries,
            "boundaries": self.region_summaries,
            "materials": self._material_summaries(),
            "capabilities": [
                "schema",
                "mesh_visualization",
                "regions",
                "boundaries",
                "materials",
                "element_selection",
                "to_igp_reader",
                "to_vtk",
            ],
        }

    def _material_by_cell(self) -> list[str | None]:
        values: list[str | None] = [None] * int(self.reader.n_mesh_elements)
        for material, element_ids in self.reader.material_dict.items():
            for raw_id in element_ids:
                cell_id = int(raw_id) - 1
                if 0 <= cell_id < len(values):
                    values[cell_id] = str(material)
        return values

    def _boundary_by_surface_face(self, surface_faces: list[list[int]]) -> list[str | None]:
        boundary_by_key: dict[tuple[int, ...], str] = {}
        for name, info in self.reader.region_dict.items():
            for face in info.get("elements", []):
                key = tuple(sorted(int(node_id) for node_id in face))
                boundary_by_key[key] = name
        return [boundary_by_key.get(tuple(sorted(face))) for face in surface_faces]

    def _cell_faces(self, cell_nodes: list[int]) -> list[list[int]]:
        templates = FACE_TEMPLATES_BY_NODE_COUNT.get(len(cell_nodes), [])
        return [[int(cell_nodes[index]) for index in template] for template in templates]

    def _mesh_payload(self) -> dict[str, Any]:
        element_nodes = [list(map(int, nodes)) for nodes in self.reader.element_nodes]
        total_cells = len(element_nodes)
        cell_limit = min(total_cells, MESH_PREVIEW_CELL_LIMIT)
        all_faces: list[list[int]] = []
        all_face_cell_ids: list[int] = []
        face_owner: dict[tuple[int, ...], dict[str, Any]] = {}
        hidden_surface_keys: set[tuple[int, ...]] = set()

        for cell_id, cell_nodes in enumerate(element_nodes[:cell_limit]):
            for face in self._cell_faces(cell_nodes):
                if len(all_faces) < MESH_PREVIEW_FACE_LIMIT:
                    all_faces.append(face)
                    all_face_cell_ids.append(cell_id)
                key = tuple(sorted(face))
                if key in face_owner:
                    hidden_surface_keys.add(key)
                else:
                    face_owner[key] = {"face": face, "cell_id": cell_id}

        surface_entries = [
            entry for key, entry in face_owner.items()
            if key not in hidden_surface_keys
        ][:MESH_PREVIEW_FACE_LIMIT]
        surface_faces = [entry["face"] for entry in surface_entries]
        face_cell_ids = [int(entry["cell_id"]) for entry in surface_entries]
        cell_types = [
            CELL_TYPE_BY_NODE_COUNT.get(len(nodes), f"{len(nodes)}_node_cell")
            for nodes in element_nodes[:cell_limit]
        ]
        cell_materials = self._material_by_cell()[:cell_limit]
        boundary_names = self._boundary_by_surface_face(surface_faces)
        surface_group_counts = {
            "boundaries": dict(Counter(name or "Interior" for name in boundary_names)),
            "materials": dict(Counter(cell_materials[cell_id] or "Unassigned" for cell_id in face_cell_ids)),
            "cell_types": dict(Counter(cell_types[cell_id] for cell_id in face_cell_ids)),
        }
        all_group_counts = {
            "materials": dict(Counter(cell_materials[cell_id] or "Unassigned" for cell_id in all_face_cell_ids)),
            "cell_types": dict(Counter(cell_types[cell_id] for cell_id in all_face_cell_ids)),
        }

        return {
            "kind": "polydata_faces",
            "points": self.reader.nodes.astype(float).tolist(),
            "faces": surface_faces,
            "face_cell_ids": face_cell_ids,
            "face_boundary_names": boundary_names,
            "all_faces": all_faces,
            "all_face_cell_ids": all_face_cell_ids,
            "cell_types": cell_types,
            "cell_materials": cell_materials,
            "cell_centroids": self.reader.centroids[:cell_limit].astype(float).tolist(),
            "bounds": {
                "points": self._node_bounds(),
                "centroids": self._centroid_bounds(),
            },
            "counts": {
                "points": int(self.reader.n_mesh_nodes),
                "cells": total_cells,
                "surface_faces": len(surface_faces),
                "all_faces": len(all_faces),
                "regions": len(self.reader.region_dict),
                "materials": len(self.reader.material_dict),
            },
            "groups": {
                "surface": surface_group_counts,
                "all": all_group_counts,
                "regions": self.region_summaries,
                "materials": self._material_summaries(),
            },
            "truncated": total_cells > cell_limit or len(all_faces) >= MESH_PREVIEW_FACE_LIMIT,
            "limits": {
                "max_cells": MESH_PREVIEW_CELL_LIMIT,
                "max_faces": MESH_PREVIEW_FACE_LIMIT,
            },
            "selection": {
                "face_cell_ids": "original zero-based iGP element ids",
                "cell_centroids": "zero-based iGP element centroids",
            },
        }

    def preview_sections(self, *, max_rows: int = PREVIEW_ROW_LIMIT, max_bytes: int = HEADER_READ_BYTES) -> list[dict[str, Any]]:
        """Return mesh and region preview sections for this iGP asset.

        Category: asset-handle
        Tags: igp, gid, mesh, preview, regions, boundaries
        Usage: pydelling-cloud needs display-ready mesh geometry and region tables.

        Returns:
            list[dict[str, Any]]: mesh and table preview sections.
        """
        return [
            {
                "kind": "mesh",
                "title": "iGP mesh",
                "metadata": self.schema(),
                "mesh": self._mesh_payload(),
            },
            {
                "kind": "table",
                "title": "Regions and boundaries",
                "columns": ["name", "faces", "cells", "nodes"],
                "rows": [
                    [item["name"], item["faces"], item["cells"], item["nodes"]]
                    for item in self.region_summaries
                ],
            },
        ]

    def summary_text(self) -> str:
        """Return element and node counts for this iGP mesh.

        Category: asset-handle
        Tags: igp, gid, mesh, summary, nodes, elements
        Usage: inventory output needs compact iGP mesh dimensions.

        Returns:
            str: element-by-node summary.
        """
        return f"{self.reader.n_mesh_elements} iGP elements x {self.reader.n_mesh_nodes} nodes"

    def _flatten_description(self) -> dict[str, Any]:
        # "regions"/"boundaries"/"materials" carry the same {name, ...} summaries
        # as schema(); flattening them to bare names here used to make
        # describe()["regions"] and schema["regions"] two different shapes under
        # one key, so callers iterating describe() hit AttributeError on .get().
        # Bare names stay available under the explicit *_names keys.
        schema = self.schema()
        return {
            "points": schema["nodes"],
            "cells": schema["elements"],
            "regions": schema["regions"],
            "boundaries": schema["boundaries"],
            "materials": schema["materials"],
            "region_names": [item["name"] for item in schema["regions"]],
            "boundary_names": [item["name"] for item in schema["boundaries"]],
            "material_names": [item["name"] for item in schema["materials"]],
            "capabilities": schema["capabilities"],
        }


class VtkAssetHandle(BaseAssetHandle):
    """Handle VTK-family mesh assets for mesh metadata and visualization previews.

    Category: asset-handle
    Tags: vtk, vtu, vtp, mesh, visualization, cells, points
    Usage: the asset is already a VTK mesh and scripts need mesh metadata or previews.
    """
    kind = "mesh"
    strategy_name = "vtk_mesh"

    @cached_property
    def reader(self):
        """Load the pydelling VTKMeshReader for this VTK asset.

        Category: asset-handle
        Tags: vtk, mesh, reader, cache
        Usage: scripts need pydelling reader access to a VTK-family mesh file.

        Returns:
            VTKMeshReader: pydelling VTK mesh reader.
        """
        from pydelling.readers.vtk_mesh_reader import VTKMeshReader

        return VTKMeshReader(
            str(self.source.path),
            kd_tree=False,
            generate_internal_mesh=False,
        )

    @cached_property
    def meshio_mesh(self):
        """Load this VTK-family asset as a meshio mesh.

        Category: asset-handle
        Tags: vtk, meshio, mesh, load
        Usage: scripts need points, cells, or mesh data arrays from a VTK-family file.

        Returns:
            Any: meshio-compatible mesh object.
        """
        if self.source.path.suffix.lower() == ".vtp":
            return self._read_vtp()
        try:
            return self.reader.meshio_mesh
        except Exception:
            import meshio

            return meshio.read(self.source.path)

    def _read_vtp(self) -> _VtkPolyDataMesh:
        """Read XML PolyData without importing the compatibility ``vtk`` package."""
        import numpy as np
        from vtkmodules.util.numpy_support import vtk_to_numpy
        from vtkmodules.vtkIOXML import vtkXMLPolyDataReader

        reader = vtkXMLPolyDataReader()
        reader.SetFileName(str(self.source.path))
        reader.Update()
        poly_data = reader.GetOutput()
        if poly_data is None:
            raise ValueError(f"Unable to read VTK PolyData asset: {self.source.path}")

        vtk_points = poly_data.GetPoints()
        points = (
            vtk_to_numpy(vtk_points.GetData()).copy()
            if vtk_points is not None
            else np.empty((0, 3), dtype=float)
        )

        grouped_cells: dict[tuple[str, int], list[list[int]]] = {}
        grouped_indices: dict[tuple[str, int], list[int]] = {}
        for cell_index in range(poly_data.GetNumberOfCells()):
            cell = poly_data.GetCell(cell_index)
            point_ids = [
                int(cell.GetPointId(index))
                for index in range(cell.GetNumberOfPoints())
            ]
            cell_type = self._poly_data_cell_type(
                int(cell.GetCellType()),
                len(point_ids),
            )
            key = (cell_type, len(point_ids))
            grouped_cells.setdefault(key, []).append(point_ids)
            grouped_indices.setdefault(key, []).append(cell_index)

        cells = [
            _VtkCellBlock(cell_type, np.asarray(values, dtype=np.int64))
            for (cell_type, _), values in grouped_cells.items()
        ]

        point_data = self._vtk_data_arrays(poly_data.GetPointData(), vtk_to_numpy)
        raw_cell_data = self._vtk_data_arrays(poly_data.GetCellData(), vtk_to_numpy)
        cell_data = {
            name: [values[grouped_indices[key]] for key in grouped_cells]
            for name, values in raw_cell_data.items()
        }
        return _VtkPolyDataMesh(
            points=points,
            cells=cells,
            point_data=point_data,
            cell_data=cell_data,
        )

    @staticmethod
    def _vtk_data_arrays(attributes: Any, converter: Any) -> dict[str, Any]:
        arrays: dict[str, Any] = {}
        if attributes is None:
            return arrays
        for index in range(attributes.GetNumberOfArrays()):
            array = attributes.GetAbstractArray(index)
            name = array.GetName() if array is not None else None
            if array is None or not name:
                continue
            try:
                arrays[str(name)] = converter(array).copy()
            except (AttributeError, TypeError):
                continue
        return arrays

    @staticmethod
    def _poly_data_cell_type(vtk_type: int, point_count: int) -> str:
        fixed_types = {
            1: "vertex",
            3: "line",
            5: "triangle",
            8: "quad",
            9: "quad",
        }
        if vtk_type in fixed_types:
            return fixed_types[vtk_type]
        if vtk_type == 4:
            return f"line{point_count}"
        if vtk_type == 6:
            return f"triangle_strip{point_count}"
        if vtk_type == 7:
            return f"polygon{point_count}"
        if vtk_type == 2:
            return f"poly_vertex{point_count}"
        return f"vtk_cell_{vtk_type}_{point_count}"

    def schema(self) -> dict[str, Any]:
        """Return point, cell, and variable metadata for this VTK mesh.

        Category: asset-handle
        Tags: vtk, mesh, schema, points, cells, variables
        Usage: scripts need VTK mesh structure before selecting fields or visualization paths.

        Returns:
            dict[str, Any]: VTK mesh schema metadata.
        """
        mesh = self.meshio_mesh
        cells = sum(len(block.data) for block in mesh.cells)
        return {
            "kind": self.kind,
            "points": int(len(mesh.points)),
            "cells": int(cells),
            "point_variables": list(getattr(mesh, "point_data", {}).keys()),
            "cell_variables": list(getattr(mesh, "cell_data", {}).keys()),
        }

    def preview_sections(self, *, max_rows: int = PREVIEW_ROW_LIMIT, max_bytes: int = HEADER_READ_BYTES) -> list[dict[str, Any]]:
        """Return a mesh metadata preview section for this VTK asset.

        Category: asset-handle
        Tags: vtk, mesh, preview, section
        Usage: pydelling-cloud needs display-ready metadata for an existing VTK mesh.

        Returns:
            list[dict[str, Any]]: one mesh preview section.
        """
        return [{
            "kind": "mesh",
            "title": "Mesh",
            "metadata": self.schema(),
        }]

    def summary_text(self) -> str:
        """Return point and cell counts for this VTK mesh.

        Category: asset-handle
        Tags: vtk, mesh, summary, points, cells
        Usage: inventory output needs compact VTK mesh dimensions.

        Returns:
            str: point-by-cell summary.
        """
        schema = self.schema()
        return f"{schema['points']} points x {schema['cells']} cells"

    def _flatten_description(self) -> dict[str, Any]:
        return self.schema()


class StlAssetHandle(BaseAssetHandle):
    """Handle STL mesh assets for geometry summaries and lightweight previews.

    Category: asset-handle
    Tags: stl, mesh, geometry, vertices, faces
    Usage: the asset is an STL mesh and scripts need face, vertex, or bounds metadata.
    """
    kind = "mesh"
    strategy_name = "stl_mesh"

    @cached_property
    def mesh(self):
        """Load and cache the STL mesh with trimesh.

        Category: asset-handle
        Tags: stl, mesh, trimesh, load
        Usage: scripts need vertices, faces, or bounds from an STL file.

        Returns:
            Any: trimesh mesh object.
        """
        return trimesh.load_mesh(self.source.path)

    def schema(self) -> dict[str, Any]:
        """Return vertices, faces, and bounds for this STL mesh.

        Category: asset-handle
        Tags: stl, mesh, schema, vertices, faces, bounds
        Usage: scripts need STL geometry metadata.

        Returns:
            dict[str, Any]: STL mesh schema metadata.
        """
        return {
            "kind": self.kind,
            "vertices": int(len(self.mesh.vertices)),
            "faces": int(len(self.mesh.faces)),
            "bounds": self.mesh.bounds.tolist(),
        }

    def _decimated_geometry(self, max_faces: int = 1200) -> dict[str, Any] | None:
        faces = self.mesh.faces[:max_faces]
        if len(faces) == 0:
            return None
        vertex_ids = sorted({int(vertex_id) for face in faces for vertex_id in face})
        remap = {vertex_id: index for index, vertex_id in enumerate(vertex_ids)}
        vertices = self.mesh.vertices[vertex_ids].tolist()
        remapped_faces = [[remap[int(vertex_id)] for vertex_id in face] for face in faces]
        return {
            "vertices": vertices,
            "faces": remapped_faces,
            "truncated": len(self.mesh.faces) > len(faces),
        }

    def preview_sections(self, *, max_rows: int = PREVIEW_ROW_LIMIT, max_bytes: int = HEADER_READ_BYTES) -> list[dict[str, Any]]:
        """Return a mesh preview section for this STL asset.

        Category: asset-handle
        Tags: stl, mesh, preview, geometry, section
        Usage: pydelling-cloud needs decimated STL geometry for visualization.

        Returns:
            list[dict[str, Any]]: one mesh preview section.
        """
        section: dict[str, Any] = {
            "kind": "mesh",
            "title": "Mesh",
            "metadata": self.schema(),
        }
        geometry = self._decimated_geometry()
        if geometry is not None:
            section["geometry"] = geometry
        return [section]

    def summary_text(self) -> str:
        """Return vertex and face counts for this STL mesh.

        Category: asset-handle
        Tags: stl, mesh, summary, vertices, faces
        Usage: inventory output needs compact STL mesh dimensions.

        Returns:
            str: vertex-by-face summary.
        """
        schema = self.schema()
        return f"{schema['vertices']} vertices x {schema['faces']} faces"

    def _flatten_description(self) -> dict[str, Any]:
        return self.schema()


class Hdf5AssetHandle(BaseAssetHandle):
    """Handle HDF5 assets by listing datasets and small sample previews.

    Category: asset-handle
    Tags: hdf5, h5, datasets, arrays, schema
    Usage: the asset is an HDF5 file and scripts need dataset names, shapes, or samples.
    """
    kind = "hdf5"
    strategy_name = "hdf5"

    @cached_property
    def datasets(self) -> list[dict[str, Any]]:
        """List datasets contained in this HDF5 file.

        Category: asset-handle
        Tags: hdf5, datasets, schema, shape, dtype
        Usage: scripts need dataset names, shapes, and dtypes before reading HDF5 content.

        Returns:
            list[dict[str, Any]]: dataset metadata entries.
        """
        datasets: list[dict[str, Any]] = []
        with h5py.File(self.source.path, "r") as handle:
            def collect(name: str, obj: Any) -> None:
                if isinstance(obj, h5py.Dataset):
                    datasets.append(
                        {
                            "name": name,
                            "shape": list(obj.shape),
                            "dtype": str(obj.dtype),
                        }
                    )

            handle.visititems(collect)
        return datasets

    def schema(self) -> dict[str, Any]:
        """Return dataset count and field metadata for this HDF5 asset.

        Category: asset-handle
        Tags: hdf5, schema, datasets, fields
        Usage: scripts need an overview of HDF5 structure.

        Returns:
            dict[str, Any]: HDF5 schema metadata.
        """
        return {
            "kind": self.kind,
            "datasets": len(self.datasets),
            "fields": self.datasets[:30],
        }

    def preview(self) -> dict[str, Any]:
        """Return a table preview of HDF5 datasets.

        Category: asset-handle
        Tags: hdf5, preview, datasets, table
        Usage: the user asks to inspect available datasets in an HDF5 file.

        Returns:
            dict[str, Any]: dataset table preview.
        """
        return {
            "kind": "table",
            "columns": ["dataset", "shape", "dtype"],
            "rows": [
                [item["name"], json.dumps(item["shape"]), item["dtype"]]
                for item in self.datasets[:PREVIEW_ROW_LIMIT]
            ],
        }

    def _sample_dataset(self, dataset_name: str, max_rows: int) -> dict[str, Any] | None:
        try:
            with h5py.File(self.source.path, "r") as handle:
                dataset = handle[dataset_name]
                if not isinstance(dataset, h5py.Dataset):
                    return None
                if dataset.shape == ():
                    value = dataset[()]
                    return {"name": dataset_name, "columns": ["value"], "rows": [[_coerce_preview_value(value)]]}
                if len(dataset.shape) == 1:
                    values = dataset[:max_rows]
                    return {
                        "name": dataset_name,
                        "columns": ["index", "value"],
                        "rows": [[index, _coerce_preview_value(value)] for index, value in enumerate(values)],
                    }
                if len(dataset.shape) == 2:
                    values = dataset[:max_rows, : min(dataset.shape[1], 12)]
                    return {
                        "name": dataset_name,
                        "columns": [str(index) for index in range(values.shape[1])],
                        "rows": [[_coerce_preview_value(value) for value in row] for row in values],
                    }
        except Exception:
            return None
        return None

    def preview_sections(self, *, max_rows: int = PREVIEW_ROW_LIMIT, max_bytes: int = HEADER_READ_BYTES) -> list[dict[str, Any]]:
        """Return dataset and sample preview sections for this HDF5 asset.

        Category: asset-handle
        Tags: hdf5, preview, sections, datasets, samples
        Usage: pydelling-cloud needs dataset listings and small array samples.

        Returns:
            list[dict[str, Any]]: HDF5 preview sections.
        """
        sections: list[dict[str, Any]] = [{
            "kind": "hdf5",
            "title": "Datasets",
            "datasets": self.datasets[:50],
            "truncated": len(self.datasets) > 50,
        }]
        for dataset in self.datasets[:3]:
            sample = self._sample_dataset(dataset["name"], max_rows=max_rows)
            if sample is not None:
                sections.append({
                    "kind": "table",
                    "title": f"{dataset['name']} sample",
                    "columns": sample["columns"],
                    "rows": sample["rows"],
                })
        return sections

    def summary_text(self) -> str:
        """Return the number of datasets in this HDF5 file.

        Category: asset-handle
        Tags: hdf5, summary, datasets
        Usage: inventory output needs compact HDF5 metadata.

        Returns:
            str: dataset-count summary.
        """
        return f"{len(self.datasets)} HDF5 datasets"

    def _flatten_description(self) -> dict[str, Any]:
        return {
            "datasets": len(self.datasets),
            "dataset_names": [item["name"] for item in self.datasets[:30]],
        }


class BinaryAssetHandle(BaseAssetHandle):
    """Handle unknown binary assets with safe header and MIME metadata.

    Category: asset-handle
    Tags: binary, bytes, mime, unknown, header
    Usage: no richer asset handle matches and scripts should avoid assuming a text or tabular format.
    """
    kind = "binary"
    strategy_name = "binary"

    def schema(self) -> dict[str, Any]:
        """Return byte size and MIME metadata for this binary asset.

        Category: asset-handle
        Tags: binary, schema, bytes, mime
        Usage: scripts need safe metadata for an otherwise unknown binary file.

        Returns:
            dict[str, Any]: binary schema metadata.
        """
        return {
            "kind": self.kind,
            "bytes": self.source.size_bytes,
            "mime_type": self.source.guessed_mime_type,
        }

    def preview(self) -> dict[str, Any]:
        """Return safe binary preview metadata.

        Category: asset-handle
        Tags: binary, preview, bytes, mime, header
        Usage: the user needs to inspect binary file metadata without decoding file contents.

        Returns:
            dict[str, Any]: binary preview table payload.
        """
        return {
            "kind": "mapping",
            "columns": ["property", "value"],
            "rows": [
                ["mime_type", self.source.guessed_mime_type],
                ["bytes", _coerce_preview_value(self.source.size_bytes)],
                ["header_hex", self.header[:24].hex(" ")],
            ],
        }

    def preview_sections(self, *, max_rows: int = PREVIEW_ROW_LIMIT, max_bytes: int = HEADER_READ_BYTES) -> list[dict[str, Any]]:
        """Return a binary metadata preview section.

        Category: asset-handle
        Tags: binary, preview, section, header
        Usage: pydelling-cloud needs display-ready metadata for an unknown binary asset.

        Returns:
            list[dict[str, Any]]: one binary preview section.
        """
        return [{
            "kind": "binary",
            "title": "Binary",
            "columns": ["property", "value"],
            "rows": self.preview()["rows"],
        }]

    def summary_text(self) -> str:
        """Return the byte size summary for this binary asset.

        Category: asset-handle
        Tags: binary, summary, bytes
        Usage: inventory output needs compact binary metadata.

        Returns:
            str: binary byte-size summary.
        """
        size = self.source.size_bytes if isinstance(self.source.size_bytes, int) else 0
        return f"{size} binary bytes"


class ErrorAssetHandle(BaseAssetHandle):
    """Represent an asset that failed preview or handle construction.

    Category: asset-handle
    Tags: error, preview, failure, diagnostics
    Usage: surfacing asset inspection failures without crashing the whole asset inventory.
    """
    kind = "error"
    strategy_name = "error"

    def __init__(self, source: AssetSource, error: str, header: bytes | None = None) -> None:
        super().__init__(source, header=header)
        self.error = error

    def preview_sections(self, *, max_rows: int = PREVIEW_ROW_LIMIT, max_bytes: int = HEADER_READ_BYTES) -> list[dict[str, Any]]:
        """Return an error preview section for a failed asset.

        Category: asset-handle
        Tags: error, preview, diagnostics, section
        Usage: pydelling-cloud needs to show why an asset preview failed.

        Returns:
            list[dict[str, Any]]: one error preview section.
        """
        return [{
            "kind": "error",
            "title": "Preview error",
            "message": self.error,
        }]

    def summary_text(self) -> str:
        """Return a summary for a failed preview.

        Category: asset-handle
        Tags: error, summary, preview
        Usage: inventory output needs a compact failure status.

        Returns:
            str: preview failure summary.
        """
        return "Preview failed"


def detect_asset_handle_class(source: AssetSource, header: bytes | None = None) -> type[BaseAssetHandle]:
    """Select the typed asset handle class for a source.

    Category: asset-handle
    Tags: detection, asset, handle, mime, extension
    Usage: code needs to choose the best pydelling handle for a runtime asset before loading it.

    Returns:
        type[BaseAssetHandle]: concrete handle class for the source.
    """
    extension = source.normalized_extension
    metadata = source.metadata or {}
    # PFLOTRAN nested children carry an explicit ``pflotran_role`` (and results
    # assets an ``asset_kind``); honor those before any content sniffing.
    if metadata.get("pflotran_role") or metadata.get("asset_kind") == "pflotran_results":
        from pydelling.assets.pflotran_handlers import pflotran_handle_for_role

        pflotran_class = pflotran_handle_for_role(metadata.get("pflotran_role"), metadata)
        if pflotran_class is not None:
            return pflotran_class
    if (
        metadata.get("storage_type") == "directory"
        or source.path.is_dir()
        or extension == "gid"
    ) and (metadata.get("directory_kind") == "igp_gid" or extension == "gid" or _is_igp_directory(source.path)):
        return IgpAssetHandle

    header = header if header is not None else read_asset_header(source.path)
    stripped = header.lstrip()
    prefix = header[:1024]
    guessed_mime = source.guessed_mime_type

    if header.startswith(HDF5_MAGIC) or extension in {"h5", "hdf5"}:
        return Hdf5AssetHandle
    if extension in {"vtk", "vtu", "vtp"} or prefix.startswith(b"# vtk DataFile") or b"<VTKFile" in prefix:
        return VtkAssetHandle
    if extension in {"xmf", "xdmf"} or b"<Xdmf" in prefix:
        # Lazy import: pflotran_handlers imports this module.
        from pydelling.assets.pflotran_handlers import PflotranXdmfAssetHandle

        return PflotranXdmfAssetHandle
    if extension == "stl" or prefix.startswith(b"solid "):
        return StlAssetHandle
    if extension in IMAGE_EXTENSIONS or guessed_mime.startswith("image/") or _looks_like_image_header(header):
        return ImageAssetHandle
    if extension == "json" or stripped[:1] in {b"{", b"["}:
        return JsonAssetHandle
    if _looks_like_esri_ascii_raster(header):
        return RasterAssetHandle
    if _looks_like_pflotran_mass_balance(header):
        return PflotranMassBalanceAssetHandle
    if _looks_like_pflotran_observation(header):
        return PflotranObservationAssetHandle
    if extension in {"csv", "tsv"} or _looks_like_tabular(header):
        return TabularAssetHandle
    if extension in TEXT_EXTENSIONS or is_probably_text(header):
        return TextAssetHandle
    return BinaryAssetHandle


def load_asset_handle(source: AssetSource, header: bytes | None = None) -> BaseAssetHandle:
    """Build a typed asset handle from an AssetSource.

    Category: asset-handle
    Tags: load, asset, handle, runtime, context
    Usage: scripts need a typed object exposing to_dataframe, to_text, to_vtk, or describe.

    Returns:
        BaseAssetHandle: concrete asset handle for the source.
    """
    asset_class = detect_asset_handle_class(source, header=header)
    return asset_class(source, header=header)


def load_asset_handles_from_context(
    items: dict[str, Any] | list[dict[str, Any]] | None,
) -> list[BaseAssetHandle]:
    """Load typed asset handles from runtime context asset entries.

    Category: asset-handle
    Tags: runtime, context, assets, handles, load
    Usage: generated scripts receive the execution context JSON and need all available assets.

    Returns:
        list[BaseAssetHandle]: typed handles for valid context assets.
    """
    if isinstance(items, dict):
        nested_items = items.get("assets")
        items = nested_items if isinstance(nested_items, list) else []
    if items is None:
        return []

    handles: list[BaseAssetHandle] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        path_value = item.get("path")
        file_name = item.get("file_name")
        if not isinstance(path_value, str) or not isinstance(file_name, str):
            continue
        source = AssetSource(
            reference_name=item.get("reference_name"),
            file_name=file_name,
            extension=str(item.get("extension") or ""),
            path=Path(path_value),
            size_bytes=item.get("size_bytes"),
            mime_type=item.get("mime_type"),
            metadata=item.get("metadata") if isinstance(item.get("metadata"), dict) else None,
        )
        handles.append(load_asset_handle(source))
    return handles


def inspect_asset_source(source: AssetSource, header: bytes | None = None) -> dict[str, Any]:
    """Inspect one asset source without building a full preview document.

    Category: asset-handle
    Tags: inspect, asset, metadata, preview, loader
    Usage: code needs quick type, MIME, binary, loader, and text-line metadata for one source.

    Returns:
        dict[str, Any]: compact inspection payload.
    """
    handle = load_asset_handle(source, header=header)
    preview_lines: list[str] = []
    if not handle.is_binary:
        preview_lines = _decode_text(handle.header[:HEADER_READ_BYTES]).splitlines()[:PREVIEW_LINE_LIMIT]
    return {
        "format": source.normalized_extension or "bin",
        "asset_kind": handle.kind,
        "strategy": handle.strategy_name,
        "mime_type": source.guessed_mime_type,
        "size_bytes": source.size_bytes,
        "binary": handle.is_binary,
        "loader": {
            "class_name": handle.__class__.__name__,
            "kind": handle.kind,
            "strategy": handle.strategy_name,
        },
        "preview_lines": preview_lines,
    }


def build_asset_preview(
    path: str | Path,
    *,
    file_name: str | None = None,
    reference_name: str | None = None,
    max_rows: int = PREVIEW_ROW_LIMIT,
    max_bytes: int = HEADER_READ_BYTES,
    max_tabular_eager_bytes: int = TABULAR_EAGER_BYTES,
    mime_type: str | None = None,
    size_bytes: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the standard preview document for an asset path.

    Category: asset-handle
    Tags: preview, asset, document, table, mesh, image
    Usage: the UI or MCP needs a bounded preview document for a user-uploaded asset.

    Returns:
        dict[str, Any]: preview document with sections, limits, and warnings.
    """
    asset_path = Path(path)
    source_metadata = dict(metadata or {})
    source_metadata["max_tabular_eager_bytes"] = max_tabular_eager_bytes
    source = AssetSource(
        reference_name=reference_name,
        file_name=file_name or asset_path.name,
        extension=asset_path.suffix,
        path=asset_path,
        size_bytes=size_bytes if size_bytes is not None else _path_size(asset_path),
        mime_type=mime_type,
        metadata=source_metadata,
    )
    try:
        handle = load_asset_handle(source)
        return handle.preview_document(max_rows=max_rows, max_bytes=max_bytes)
    except Exception as exc:
        return {
            "version": PREVIEW_CONTRACT_VERSION,
            "asset_kind": "error",
            "format": source.normalized_extension or "bin",
            "summary": "Preview failed",
            "sections": [{
                "kind": "error",
                "title": "Preview error",
                "message": str(exc),
            }],
            "warnings": [str(exc)],
            "limits": {"max_rows": max_rows, "max_bytes": max_bytes},
            "computed_at": _utc_now_iso(),
        }


def build_asset_inventory_output(handles: list[BaseAssetHandle]) -> dict[str, Any]:
    """Build a table output listing all available asset handles.

    Category: asset-handle
    Tags: inventory, assets, table, summary, output
    Usage: the user asks what assets are available or needs a compact asset catalog.

    Returns:
        dict[str, Any]: table output payload for available assets.
    """
    rows = [
        [
            handle.source.reference_name or handle.source.file_name,
            handle.source.file_name,
            handle.kind,
            handle.summary_text(),
        ]
        for handle in handles
    ]
    return {
        "kind": "table",
        "title": "Available assets",
        "columns": ["asset", "file_name", "kind", "summary"],
        "rows": rows,
        "export_name": "available_assets.csv",
    }


def build_asset_schema_output(handle: BaseAssetHandle) -> dict[str, Any]:
    """Build a table output describing an asset schema.

    Category: asset-handle
    Tags: schema, fields, columns, datasets, table, output
    Usage: the user asks for column names, field types, dataset shapes, or other asset structure.

    Returns:
        dict[str, Any]: table output payload for schema metadata.
    """
    schema = handle.schema()
    if schema.get("fields"):
        fields = schema["fields"]
        if fields and isinstance(fields[0], dict) and {"name", "dtype"} <= set(fields[0]):
            rows = [[item["name"], item["dtype"]] for item in fields]
            return {
                "kind": "table",
                "title": f"{handle.source.file_name} · schema",
                "columns": ["field", "dtype"],
                "rows": rows,
                "export_name": f"{handle.source.reference_name or 'asset'}_schema.csv",
            }
        rows = [[_coerce_preview_value(item.get("name")), _coerce_preview_value(item.get("shape")), _coerce_preview_value(item.get("dtype"))] for item in fields if isinstance(item, dict)]
        return {
            "kind": "table",
            "title": f"{handle.source.file_name} · schema",
            "columns": ["name", "shape", "dtype"],
            "rows": rows,
            "export_name": f"{handle.source.reference_name or 'asset'}_schema.csv",
        }
    return {
        "kind": "table",
        "title": f"{handle.source.file_name} · schema",
        "columns": ["property", "value"],
        "rows": _stringify_mapping(schema),
        "export_name": f"{handle.source.reference_name or 'asset'}_schema.csv",
    }


def build_asset_data_output(handle: BaseAssetHandle) -> dict[str, Any]:
    """Build a table output from an asset preview.

    Category: asset-handle
    Tags: data, preview, rows, columns, table, output
    Usage: the user asks to view sample rows or extracted asset data inline.

    Returns:
        dict[str, Any]: table output payload for preview data.
    """
    preview = handle.preview()
    columns = preview.get("columns")
    rows = preview.get("rows")
    if isinstance(columns, list) and isinstance(rows, list):
        return {
            "kind": "table",
            "title": f"{handle.source.file_name} · data preview",
            "columns": [str(column) for column in columns],
            "rows": rows,
            "export_name": f"{handle.source.reference_name or 'asset'}_preview.csv",
        }
    return {
        "kind": "table",
        "title": f"{handle.source.file_name} · data preview",
        "columns": ["property", "value"],
        "rows": _stringify_mapping(preview),
        "export_name": f"{handle.source.reference_name or 'asset'}_preview.csv",
    }


def build_asset_mesh_output(handle: BaseAssetHandle) -> dict[str, Any]:
    """Build a mesh output from a mesh-capable asset handle.

    Category: asset-handle
    Tags: mesh, vtk, igp, visualization, output
    Usage: the user asks to visualize or inspect geometry from an iGP, VTK, or STL-like asset.

    Returns:
        dict[str, Any]: mesh output payload with geometry and metadata.
    """
    sections = handle.preview_sections(max_rows=PREVIEW_ROW_LIMIT)
    for section in sections:
        if section.get("kind") != "mesh":
            continue
        mesh = section.get("mesh") or section.get("geometry")
        if not isinstance(mesh, dict):
            continue
        return {
            "kind": "mesh",
            "title": section.get("title") or f"{handle.source.file_name} · mesh",
            "mesh": mesh,
            "metadata": section.get("metadata") or handle.schema(),
        }
    raise TypeError(f"{handle.__class__.__name__} does not expose a mesh visualization.")
