from __future__ import annotations

import csv
import json
import mimetypes
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
PREVIEW_CONTRACT_VERSION = 1
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
    Use when: code needs to compare uploaded asset extensions independent of dot prefix or case.

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
    Use when: asset detection needs a bounded binary sample without loading the full file.

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
    Use when: choosing between text and binary asset handling from a header sample.

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
    Use when: constructing typed handles from runtime context asset entries.
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
        Use when: matching an asset source to a tabular, mesh, image, JSON, text, or binary handle.

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
        Use when: previews and output manifests need a MIME type for an asset.

        Returns:
            str: MIME type, defaulting to application/octet-stream.
        """
        return (
            self.mime_type
            or mimetypes.guess_type(self.file_name)[0]
            or "application/octet-stream"
        )


class BaseAssetHandle:
    """Provide the common runtime contract for any typed user asset.

    Category: asset-handle
    Tags: asset, preview, schema, dataframe, records, text, mesh
    Use when: scripts need a uniform interface before calling format-specific handle methods.
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
        Use when: code needs a bounded byte sample for binary/text checks or preview metadata.

        Returns:
            bytes: header bytes for the source path.
        """
        return self._header if self._header is not None else read_asset_header(self.source.path)

    @property
    def is_binary(self) -> bool:
        return not is_probably_text(self.header)

    def schema(self) -> dict[str, Any]:
        return {"kind": self.kind}

    def preview(self) -> dict[str, Any]:
        return {}

    def preview_sections(self, *, max_rows: int = PREVIEW_ROW_LIMIT, max_bytes: int = HEADER_READ_BYTES) -> list[dict[str, Any]]:
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

    def to_dataframe(self) -> pd.DataFrame:
        """Load this asset as a pandas DataFrame when the format supports rows and columns.

        Category: asset-handle
        Tags: tabular, dataframe, csv, json, records
        Use when: the user needs asset data in DataFrame form for analysis or transformation.

        Returns:
            pd.DataFrame: parsed tabular data.
        """
        raise TypeError(f"{self.__class__.__name__} does not expose a dataframe view.")

    def to_records(self) -> list[dict[str, Any]]:
        """Load this asset as a list of row dictionaries when available.

        Category: asset-handle
        Tags: records, rows, json, tabular
        Use when: scripts need simple Python dictionaries instead of a pandas DataFrame.

        Returns:
            list[dict[str, Any]]: parsed record rows.
        """
        raise TypeError(f"{self.__class__.__name__} does not expose a record view.")

    def to_text(self) -> str:
        """Load this asset as text when the format supports textual content.

        Category: asset-handle
        Tags: text, json, markdown, log
        Use when: the user asks to read, summarize, transform, or inspect textual asset contents.

        Returns:
            str: decoded asset text.
        """
        raise TypeError(f"{self.__class__.__name__} does not expose a text view.")

    def to_igp_reader(self, *, build_mesh: bool = False, output_folder: str | Path | None = None):
        """Open this asset as an iGPReader when it is an iGP/GiD project directory.

        Category: asset-handle
        Tags: igp, gid, mesh, reader, regions, materials
        Use when: scripts need pydelling iGP mesh operations, region access, or VTK export.

        Returns:
            iGPReader: reader configured for the asset directory.
        """
        raise TypeError(f"{self.__class__.__name__} does not expose an iGPReader view.")

    def to_vtk(self, filename: str | Path):
        """Export this asset to a VTK file when the handle supports mesh conversion.

        Category: asset-handle
        Tags: vtk, mesh, export, igp, visualization
        Use when: the user asks to convert an iGP/GiD or mesh asset into VTK for visualization.

        Returns:
            Any: value returned by the concrete exporter.
        """
        raise TypeError(f"{self.__class__.__name__} does not expose a VTK export.")

    def summary_text(self) -> str:
        return f"{self.kind} asset"

    def _flatten_description(self) -> dict[str, Any]:
        return {}

    def describe(self) -> dict[str, Any]:
        """Return schema, preview, loader, and metadata for this asset.

        Category: asset-handle
        Tags: describe, metadata, schema, preview, inventory
        Use when: scripts or MCP tools need a machine-readable summary before selecting an operation.

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
        warnings: list[str] = []
        sections = self.preview_sections(max_rows=max_rows, max_bytes=max_bytes)
        return {
            "version": PREVIEW_CONTRACT_VERSION,
            "asset_kind": self.kind,
            "format": self.source.normalized_extension or "bin",
            "summary": self.summary_text(),
            "sections": sections,
            "warnings": warnings,
            "limits": {"max_rows": max_rows, "max_bytes": max_bytes},
            "computed_at": _utc_now_iso(),
        }

    def to_runtime_dict(self) -> dict[str, Any]:
        """Serialize this handle into the runtime asset metadata contract.

        Category: asset-handle
        Tags: runtime, metadata, context, asset
        Use when: exposing available assets and their typed preview metadata to generated scripts.

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
    Use when: the asset should be read as rows and columns for analysis or transformation.
    """
    kind = "tabular"
    strategy_name = "tabular"

    @cached_property
    def delimiter(self) -> str:
        return _guess_delimiter(self.source.normalized_extension, self.header)

    @cached_property
    def dataframe(self) -> pd.DataFrame:
        return pd.read_csv(self.source.path, sep=self.delimiter)

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
        return pd.read_csv(self.source.path, sep=self.delimiter, nrows=nrows)

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
        if self.eager_metadata_enabled:
            return self.dataframe
        return self.sample_dataframe

    def to_dataframe(self) -> pd.DataFrame:
        """Load this tabular asset as a pandas DataFrame.

        Category: asset-handle
        Tags: tabular, csv, tsv, dataframe, columns
        Use when: the user needs the asset's rows and columns as a DataFrame.

        Returns:
            pd.DataFrame: parsed table with original column names.
        """
        return self.dataframe.copy()

    def to_records(self) -> list[dict[str, Any]]:
        """Load this tabular asset as row dictionaries.

        Category: asset-handle
        Tags: tabular, records, rows, csv, tsv
        Use when: the user needs serializable rows from a delimited table.

        Returns:
            list[dict[str, Any]]: table rows keyed by column name.
        """
        return self.dataframe.fillna("").to_dict(orient="records")

    def schema(self) -> dict[str, Any]:
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

    def preview_sections(self, *, max_rows: int = PREVIEW_ROW_LIMIT, max_bytes: int = HEADER_READ_BYTES) -> list[dict[str, Any]]:
        preview = (
            self.dataframe.head(max_rows)
            if self.eager_metadata_enabled
            else self._read_sample_frame(max_rows)
        )
        total_rows = self.row_count
        return [{
            "kind": "table",
            "title": "Preview",
            "columns": preview.columns.tolist(),
            "rows": preview.fillna("").astype(str).values.tolist(),
            "total_rows": total_rows,
            "shown_rows": int(preview.shape[0]),
            "truncated": total_rows > int(preview.shape[0]),
        }]

    def summary_text(self) -> str:
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


class JsonAssetHandle(BaseAssetHandle):
    """Handle JSON assets as records, DataFrames, text, or structured previews.

    Category: asset-handle
    Tags: json, records, dataframe, text, object, list
    Use when: the asset is JSON and the script needs structured data or formatted text.
    """
    kind = "json"
    strategy_name = "json"

    @cached_property
    def payload(self) -> Any:
        return json.loads(self.source.path.read_text(encoding="utf-8"))

    def to_records(self) -> list[dict[str, Any]]:
        """Load a JSON array of objects as row dictionaries.

        Category: asset-handle
        Tags: json, records, rows, list
        Use when: a JSON payload is a list of objects that should behave like table rows.

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
        Use when: the user wants to analyze or transform JSON records with pandas.

        Returns:
            pd.DataFrame: DataFrame built from top-level JSON objects.
        """
        return pd.DataFrame(self.to_records())

    def to_text(self) -> str:
        """Render the JSON payload as formatted text.

        Category: asset-handle
        Tags: json, text, pretty-print, serialize
        Use when: the user asks to inspect, summarize, or write the JSON as readable text.

        Returns:
            str: indented JSON string.
        """
        return json.dumps(self.payload, indent=2, ensure_ascii=True)

    def schema(self) -> dict[str, Any]:
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
    Use when: the asset should be read as decoded UTF-8 text.
    """
    kind = "text"
    strategy_name = "text"

    @cached_property
    def text(self) -> str:
        return self.source.path.read_text(encoding="utf-8", errors="replace")

    @cached_property
    def lines(self) -> list[str]:
        return self.text.splitlines()

    def to_text(self) -> str:
        """Load this text asset as a string.

        Category: asset-handle
        Tags: text, lines, markdown, log, yaml
        Use when: the user asks to read, summarize, transform, or extract text content.

        Returns:
            str: decoded asset contents.
        """
        return self.text

    def schema(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "rows": len(self.lines),
            "encoding": "utf-8",
        }

    def preview(self) -> dict[str, Any]:
        return {
            "kind": "text",
            "columns": ["line_no", "text"],
            "rows": [[str(index + 1), line] for index, line in enumerate(self.lines[:PREVIEW_LINE_LIMIT])],
            "lines": self.lines[:PREVIEW_LINE_LIMIT],
        }

    def preview_sections(self, *, max_rows: int = PREVIEW_ROW_LIMIT, max_bytes: int = HEADER_READ_BYTES) -> list[dict[str, Any]]:
        lines = self.lines[:max_rows]
        return [{
            "kind": "text",
            "title": "Text",
            "lines": lines,
            "truncated": len(self.lines) > len(lines),
        }]

    def summary_text(self) -> str:
        return f"{len(self.lines)} text lines"

    def _flatten_description(self) -> dict[str, Any]:
        preview = self.preview()
        return {"rows": len(self.lines), "preview_lines": preview["lines"]}


class ImageAssetHandle(BaseAssetHandle):
    """Handle image assets for preview metadata and dimensions.

    Category: asset-handle
    Tags: image, png, jpg, jpeg, gif, dimensions, mime
    Use when: the asset is an image and scripts need MIME type, size, or preview metadata.
    """
    kind = "image"
    strategy_name = "image"

    def schema(self) -> dict[str, Any]:
        dimensions = _image_dimensions(self.source.path, self.source.normalized_extension) or {}
        return {
            "kind": self.kind,
            "mime_type": self.source.guessed_mime_type,
            "bytes": self.source.size_bytes,
            **dimensions,
        }

    def preview(self) -> dict[str, Any]:
        return {
            "kind": "image",
            "mime_type": self.source.guessed_mime_type,
            **self.schema(),
        }

    def preview_sections(self, *, max_rows: int = PREVIEW_ROW_LIMIT, max_bytes: int = HEADER_READ_BYTES) -> list[dict[str, Any]]:
        return [{
            "kind": "image",
            "title": "Image",
            "mime_type": self.source.guessed_mime_type,
            **self.schema(),
        }]

    def summary_text(self) -> str:
        schema = self.schema()
        if schema.get("width") and schema.get("height"):
            return f"{schema['width']} x {schema['height']} image"
        return "image"


class IgpAssetHandle(BaseAssetHandle):
    """Handle iGP/GiD project directories with mesh, region, boundary, and material metadata.

    Category: asset-handle
    Tags: igp, gid, mesh, vtk, regions, boundaries, materials
    Use when: the user asks to inspect, summarize, convert, or visualize an iGP/GiD mesh asset.
    """
    kind = "igp_reader"
    strategy_name = "igp_gid"

    @property
    def is_binary(self) -> bool:
        return False

    @cached_property
    def reader(self):
        return self.to_igp_reader()

    def to_igp_reader(self, *, build_mesh: bool = False, output_folder: str | Path | None = None):
        """Open this iGP/GiD asset with pydelling.readers.iGPReader.

        Category: asset-handle
        Tags: igp, gid, reader, mesh, regions, materials
        Use when: scripts need direct iGPReader methods for mesh conversion, regions, or material access.

        Returns:
            iGPReader: initialized pydelling iGP reader.
        """
        from pydelling.readers.iGPReader import iGPReader

        return iGPReader(
            self.source.path,
            project_name=Path(self.source.file_name).stem,
            build_mesh=build_mesh,
            output_folder=output_folder,
        )

    def to_vtk(self, filename: str | Path):
        """Export this iGP/GiD asset to a VTK mesh file.

        Category: asset-handle
        Tags: igp, gid, vtk, mesh, export, visualization
        Use when: the user asks to convert an iGP/GiD project into VTK for visualization or download.

        Returns:
            Any: value returned by iGPReader.to_vtk.
        """
        reader = self.to_igp_reader(build_mesh=False, output_folder=None)
        return reader.to_vtk(filename)

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

    def _region_summaries(self) -> list[dict[str, Any]]:
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
            "regions": self._region_summaries(),
            "boundaries": self._region_summaries(),
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
                "regions": self._region_summaries(),
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
                    for item in self._region_summaries()
                ],
            },
        ]

    def summary_text(self) -> str:
        return f"{self.reader.n_mesh_elements} iGP elements x {self.reader.n_mesh_nodes} nodes"

    def _flatten_description(self) -> dict[str, Any]:
        schema = self.schema()
        return {
            "points": schema["nodes"],
            "cells": schema["elements"],
            "regions": [item["name"] for item in schema["regions"]],
            "boundaries": [item["name"] for item in schema["boundaries"]],
            "materials": [item["name"] for item in schema["materials"]],
            "capabilities": schema["capabilities"],
        }


class VtkAssetHandle(BaseAssetHandle):
    """Handle VTK-family mesh assets for mesh metadata and visualization previews.

    Category: asset-handle
    Tags: vtk, vtu, vtp, mesh, visualization, cells, points
    Use when: the asset is already a VTK mesh and scripts need mesh metadata or previews.
    """
    kind = "mesh"
    strategy_name = "vtk_mesh"

    @cached_property
    def reader(self):
        from pydelling.readers.vtk_mesh_reader import VTKMeshReader

        return VTKMeshReader(
            str(self.source.path),
            kd_tree=False,
            generate_internal_mesh=False,
        )

    @cached_property
    def meshio_mesh(self):
        try:
            return self.reader.meshio_mesh
        except Exception:
            import meshio

            return meshio.read(self.source.path)

    def schema(self) -> dict[str, Any]:
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
        return [{
            "kind": "mesh",
            "title": "Mesh",
            "metadata": self.schema(),
        }]

    def summary_text(self) -> str:
        schema = self.schema()
        return f"{schema['points']} points x {schema['cells']} cells"

    def _flatten_description(self) -> dict[str, Any]:
        return self.schema()


class StlAssetHandle(BaseAssetHandle):
    """Handle STL mesh assets for geometry summaries and lightweight previews.

    Category: asset-handle
    Tags: stl, mesh, geometry, vertices, faces
    Use when: the asset is an STL mesh and scripts need face, vertex, or bounds metadata.
    """
    kind = "mesh"
    strategy_name = "stl_mesh"

    @cached_property
    def mesh(self):
        return trimesh.load_mesh(self.source.path)

    def schema(self) -> dict[str, Any]:
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
        schema = self.schema()
        return f"{schema['vertices']} vertices x {schema['faces']} faces"

    def _flatten_description(self) -> dict[str, Any]:
        return self.schema()


class Hdf5AssetHandle(BaseAssetHandle):
    """Handle HDF5 assets by listing datasets and small sample previews.

    Category: asset-handle
    Tags: hdf5, h5, datasets, arrays, schema
    Use when: the asset is an HDF5 file and scripts need dataset names, shapes, or samples.
    """
    kind = "hdf5"
    strategy_name = "hdf5"

    @cached_property
    def datasets(self) -> list[dict[str, Any]]:
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
        return {
            "kind": self.kind,
            "datasets": len(self.datasets),
            "fields": self.datasets[:30],
        }

    def preview(self) -> dict[str, Any]:
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
    Use when: no richer asset handle matches and scripts should avoid assuming a text or tabular format.
    """
    kind = "binary"
    strategy_name = "binary"

    def schema(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "bytes": self.source.size_bytes,
            "mime_type": self.source.guessed_mime_type,
        }

    def preview(self) -> dict[str, Any]:
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
        return [{
            "kind": "binary",
            "title": "Binary",
            "columns": ["property", "value"],
            "rows": self.preview()["rows"],
        }]

    def summary_text(self) -> str:
        size = self.source.size_bytes if isinstance(self.source.size_bytes, int) else 0
        return f"{size} binary bytes"


class ErrorAssetHandle(BaseAssetHandle):
    """Represent an asset that failed preview or handle construction.

    Category: asset-handle
    Tags: error, preview, failure, diagnostics
    Use when: surfacing asset inspection failures without crashing the whole asset inventory.
    """
    kind = "error"
    strategy_name = "error"

    def __init__(self, source: AssetSource, error: str, header: bytes | None = None) -> None:
        super().__init__(source, header=header)
        self.error = error

    def preview_sections(self, *, max_rows: int = PREVIEW_ROW_LIMIT, max_bytes: int = HEADER_READ_BYTES) -> list[dict[str, Any]]:
        return [{
            "kind": "error",
            "title": "Preview error",
            "message": self.error,
        }]

    def summary_text(self) -> str:
        return "Preview failed"


def detect_asset_handle_class(source: AssetSource, header: bytes | None = None) -> type[BaseAssetHandle]:
    """Select the typed asset handle class for a source.

    Category: asset-handle
    Tags: detection, asset, handle, mime, extension
    Use when: code needs to choose the best pydelling handle for a runtime asset before loading it.

    Returns:
        type[BaseAssetHandle]: concrete handle class for the source.
    """
    extension = source.normalized_extension
    metadata = source.metadata or {}
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
    if extension == "stl" or prefix.startswith(b"solid "):
        return StlAssetHandle
    if extension in IMAGE_EXTENSIONS or guessed_mime.startswith("image/") or _looks_like_image_header(header):
        return ImageAssetHandle
    if extension == "json" or stripped[:1] in {b"{", b"["}:
        return JsonAssetHandle
    if extension in {"csv", "tsv"} or _looks_like_tabular(header):
        return TabularAssetHandle
    if extension in TEXT_EXTENSIONS or is_probably_text(header):
        return TextAssetHandle
    return BinaryAssetHandle


def load_asset_handle(source: AssetSource, header: bytes | None = None) -> BaseAssetHandle:
    """Build a typed asset handle from an AssetSource.

    Category: asset-handle
    Tags: load, asset, handle, runtime, context
    Use when: scripts need a typed object exposing to_dataframe, to_text, to_vtk, or describe.

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
    Use when: generated scripts receive the execution context JSON and need all available assets.

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
    Use when: code needs quick type, MIME, binary, loader, and text-line metadata for one source.

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
) -> dict[str, Any]:
    """Build the standard preview document for an asset path.

    Category: asset-handle
    Tags: preview, asset, document, table, mesh, image
    Use when: the UI or MCP needs a bounded preview document for a user-uploaded asset.

    Returns:
        dict[str, Any]: preview document with sections, limits, and warnings.
    """
    asset_path = Path(path)
    source = AssetSource(
        reference_name=reference_name,
        file_name=file_name or asset_path.name,
        extension=asset_path.suffix,
        path=asset_path,
        size_bytes=size_bytes if size_bytes is not None else _path_size(asset_path),
        mime_type=mime_type,
        metadata={"max_tabular_eager_bytes": max_tabular_eager_bytes},
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
    Use when: the user asks what assets are available or needs a compact asset catalog.

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
    Use when: the user asks for column names, field types, dataset shapes, or other asset structure.

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
    Use when: the user asks to view sample rows or extracted asset data inline.

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
    Use when: the user asks to visualize or inspect geometry from an iGP, VTK, or STL-like asset.

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
