"""Read the tables of a downloaded run (CSV and parquet) so the dashboard can show them.

Only ``.csv`` and ``.parquet`` files inside the run's local folder are served, and only a
page of rows at a time, so a multi-million-row profile never travels whole to the browser.
Parquet needs ``pyarrow``; without it those files are not listed.
"""

import csv
import math
import sys
from collections import OrderedDict
from pathlib import Path

csv.field_size_limit(min(sys.maxsize, 2**31 - 1))

try:
    import pyarrow.parquet as pq
except ImportError:  # pragma: no cover - pyarrow is a dependency of the projects using it
    pq = None

SUFFIXES = frozenset({".csv", ".parquet"} if pq else {".csv"})
MAX_PAGE = 500
DEFAULT_PAGE = 100
# Study folders hold per-study copies of the merged tables and the solver inputs.
SKIP_DIRS = frozenset(
    {"attempts", "processed", "prepared", "input_files", "inputs", "__pycache__"}
)
_TOTALS: OrderedDict[tuple, int] = OrderedDict()
_TOTALS_KEPT = 64


def list_tables(base: str | Path, *, max_depth: int = 2) -> list[dict]:
    """Table files (CSV, parquet) of a run folder, top level first.

    Args:
        base: Local run folder.
        max_depth: Sub-folder levels searched (``postprocess/x.csv`` is depth 1).

    Returns:
        list[dict]: ``{"path", "name", "size"}`` per file, ``path`` relative and POSIX;
        ``manifest.csv`` first (the small overview), then top-level files, then sub-folders.
    """
    base = Path(base)
    if not base.is_dir():
        return []
    found = []

    def walk(folder: Path, depth: int) -> None:
        for entry in sorted(folder.iterdir(), key=lambda p: (p.is_dir(), p.name)):
            if entry.is_symlink():
                continue
            if entry.is_dir():
                if depth < max_depth and entry.name not in SKIP_DIRS:
                    walk(entry, depth + 1)
            elif entry.suffix in SUFFIXES:
                relative = entry.relative_to(base).as_posix()
                found.append({"path": relative, "name": entry.name, "size": entry.stat().st_size})

    walk(base, 0)
    found.sort(key=lambda t: (t["path"] != "manifest.csv", t["path"].count("/"), t["path"]))
    return found


def resolve_table(base: str | Path, relative: str) -> Path:
    """The table file ``relative`` inside ``base``, refusing anything else.

    Args:
        base: Local run folder.
        relative: POSIX path relative to ``base``.

    Returns:
        Path: The file.

    Raises:
        ValueError: If the path escapes ``base``, is a link, or is not an existing table.
    """
    base = Path(base).resolve()
    if not isinstance(relative, str) or "\\" in relative or Path(relative).is_absolute():
        raise ValueError("Ruta de tabla no válida")
    path = base / relative
    if (
        ".." in Path(relative).parts
        or path.suffix not in SUFFIXES
        or path.is_symlink()
        or not path.resolve().is_relative_to(base)
        or not path.is_file()
    ):
        raise ValueError(f"{relative} no es una tabla de este run")
    return path


def _total(path: Path) -> int:
    stat = path.stat()
    key = (str(path), stat.st_mtime_ns, stat.st_size)
    if key in _TOTALS:
        _TOTALS.move_to_end(key)
        return _TOTALS[key]
    with path.open(newline="", errors="replace") as stream:
        reader = csv.reader(stream)
        next(reader, None)
        total = sum(1 for _ in reader)
    _TOTALS[key] = total
    while len(_TOTALS) > _TOTALS_KEPT:
        _TOTALS.popitem(last=False)
    return total


def _cell(value: object) -> str:
    """Text of one parquet value, as it would read in a CSV (empty for missing)."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    return str(value)


def _parquet_rows(table) -> list[list[str]]:
    return [[_cell(row[name]) for name in table.column_names] for row in table.to_pylist()]


def _read_parquet(path: Path, offset: int, limit: int, needle: str) -> dict:
    parquet = pq.ParquetFile(path)
    columns = list(parquet.schema_arrow.names)
    rows: list[list[str]] = []
    if needle:
        matched = 0
        for batch in parquet.iter_batches(batch_size=20000):
            for row in _parquet_rows(batch):
                if any(needle in cell.lower() for cell in row):
                    if offset <= matched < offset + limit:
                        rows.append(row)
                    matched += 1
        return {"columns": columns, "rows": rows, "total": matched}
    start = 0
    for group in range(parquet.num_row_groups):
        count = parquet.metadata.row_group(group).num_rows
        if start + count > offset and start < offset + limit:
            low, high = max(offset - start, 0), min(offset + limit - start, count)
            rows += _parquet_rows(parquet.read_row_group(group).slice(low, high - low))
        start += count
        if start >= offset + limit:
            break
    return {"columns": columns, "rows": rows, "total": parquet.metadata.num_rows}


def read_table(
    base: str | Path,
    relative: str,
    *,
    offset: int = 0,
    limit: int = DEFAULT_PAGE,
    query: str = "",
) -> dict:
    """One page of a CSV or parquet table.

    Args:
        base: Local run folder.
        relative: Table path relative to ``base``.
        offset: First row of the page (0-based, after the header).
        limit: Rows in the page, at most :data:`MAX_PAGE`.
        query: Keep only rows containing this text in any cell (case-insensitive).

    Returns:
        dict: ``path``, ``size``, ``columns``, ``rows`` (lists of text; CSV as written,
        parquet values as ``str``), ``offset``, ``limit`` and ``total`` (rows in the file,
        or matching ``query``).

    Raises:
        ValueError: If the path is not a table of this run.
    """
    path = resolve_table(base, relative)
    offset = max(0, int(offset))
    limit = min(MAX_PAGE, max(1, int(limit)))
    needle = (query or "").strip().lower()
    if path.suffix == ".parquet":
        page = _read_parquet(path, offset, limit, needle)
        return {
            "path": relative,
            "size": path.stat().st_size,
            "offset": offset,
            "limit": limit,
            **page,
        }
    with path.open(newline="", errors="replace") as stream:
        reader = csv.reader(stream)
        columns = next(reader, [])
        rows: list[list[str]] = []
        if needle:
            matched = 0
            for row in reader:
                if any(needle in cell.lower() for cell in row):
                    if offset <= matched < offset + limit:
                        rows.append(row)
                    matched += 1
            total = matched
        else:
            total = _total(path)
            for index, row in enumerate(reader):
                if index >= offset + limit:
                    break
                if index >= offset:
                    rows.append(row)
    return {
        "path": relative,
        "size": path.stat().st_size,
        "columns": columns,
        "rows": rows,
        "offset": offset,
        "limit": limit,
        "total": total,
    }
