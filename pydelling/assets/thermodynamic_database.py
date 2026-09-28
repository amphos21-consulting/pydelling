"""Tolerant parser for PFLOTRAN thermodynamic database files."""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any


SECTION_NAMES = (
    "primary_aqueous",
    "secondary_aqueous",
    "gases",
    "minerals",
    "surface_complexes",
)


def _number(value: str) -> float | None:
    try:
        return float(value.replace("d", "e").replace("D", "E"))
    except (TypeError, ValueError):
        return None


def _tokens(line: str) -> list[str]:
    lexer = shlex.shlex(line, posix=True)
    lexer.whitespace_split = True
    lexer.commenters = "#"
    return list(lexer)


@dataclass(frozen=True)
class ThermodynamicDatabase:
    temperatures: list[float]
    sections: dict[str, list[dict[str, Any]]]
    warnings: list[str]

    @property
    def counts(self) -> dict[str, int]:
        return {name: len(self.sections.get(name, [])) for name in SECTION_NAMES}


def _parse_temperature(tokens: list[str]) -> list[float]:
    if not tokens or tokens[0].lower() != "temperature points":
        return []
    count = int(_number(tokens[1]) or 0) if len(tokens) > 1 else 0
    values = [_number(token) for token in tokens[2 : 2 + count]]
    return [value for value in values if value is not None]


def _parse_record(
    tokens: list[str], section: str, temperatures: list[float]
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "name": tokens[0],
        "section": section,
        "reaction": [],
        "log_k": [],
        "properties": {},
        "reference": None,
    }
    if section == "primary_aqueous":
        values = [_number(token) for token in tokens[1:4]]
        for key, value in zip(("ion_size", "charge", "molecular_weight"), values):
            record["properties"][key] = value
        if len(tokens) > 4:
            record["reference"] = " ".join(tokens[4:])
        return record

    cursor = 1
    if section == "minerals":
        record["properties"]["molar_volume"] = (
            _number(tokens[cursor]) if cursor < len(tokens) else None
        )
        cursor += 1

    component_count = int(_number(tokens[cursor]) or 0) if cursor < len(tokens) else 0
    cursor += 1
    reaction: list[dict[str, Any]] = []
    for _ in range(max(component_count, 0)):
        if cursor + 1 >= len(tokens):
            break
        coefficient = _number(tokens[cursor])
        species = tokens[cursor + 1]
        reaction.append({"coefficient": coefficient, "species": species})
        cursor += 2
    record["reaction"] = reaction

    log_k_count = min(len(temperatures), 8)
    log_k: list[float | None] = []
    for token in tokens[cursor : cursor + log_k_count]:
        log_k.append(_number(token))
    record["log_k"] = log_k
    cursor += log_k_count

    trailing = tokens[cursor:]
    numeric: list[float] = []
    reference: list[str] = []
    for token in trailing:
        value = _number(token)
        if value is not None and not reference:
            numeric.append(value)
        else:
            reference.append(token)
    if section == "minerals":
        if numeric:
            record["properties"]["molecular_weight"] = numeric[-1]
    else:
        keys = ("ion_size", "charge", "molecular_weight")
        for key, value in zip(keys, numeric[-3:]):
            record["properties"][key] = value
    if reference:
        record["reference"] = " ".join(reference)
    return record


def parse_thermodynamic_database(path: str | Path) -> ThermodynamicDatabase:
    """Parse a PFLOTRAN database while retaining valid records around bad rows."""
    source = Path(path)
    temperatures: list[float] = []
    sections = {name: [] for name in SECTION_NAMES}
    warnings: list[str] = []
    section_index = 0

    with source.open("r", encoding="utf-8", errors="replace") as handle:
        for line_number, raw in enumerate(handle, 1):
            stripped = raw.strip()
            if not stripped or stripped.startswith("#"):
                continue
            try:
                tokens = _tokens(raw)
            except ValueError as exc:
                warnings.append(f"line {line_number}: {exc}")
                continue
            if not tokens:
                continue
            if not temperatures and tokens[0].lower() == "temperature points":
                temperatures = _parse_temperature(tokens)
                if not temperatures:
                    warnings.append(f"line {line_number}: invalid temperature header")
                continue
            if tokens[0].lower() == "null":
                section_index += 1
                continue
            section = SECTION_NAMES[min(section_index, len(SECTION_NAMES) - 1)]
            try:
                sections[section].append(_parse_record(tokens, section, temperatures))
            except (IndexError, TypeError, ValueError) as exc:
                warnings.append(f"line {line_number}: {exc}")

    return ThermodynamicDatabase(temperatures, sections, warnings)


@lru_cache(maxsize=16)
def _cached_database(path: str, size: int, modified_ns: int) -> ThermodynamicDatabase:
    del size, modified_ns
    return parse_thermodynamic_database(path)


def load_thermodynamic_database(path: str | Path) -> ThermodynamicDatabase:
    source = Path(path)
    stat = source.stat()
    return _cached_database(str(source), stat.st_size, stat.st_mtime_ns)


def search_thermodynamic_database(
    database: ThermodynamicDatabase,
    *,
    section: str | None = None,
    query: str = "",
    offset: int = 0,
    limit: int = 50,
) -> dict[str, Any]:
    names = [section] if section in SECTION_NAMES else list(SECTION_NAMES)
    records = [record for name in names for record in database.sections.get(name, [])]
    needle = query.strip().casefold()
    if needle:
        records = [
            record
            for record in records
            if needle in str(record.get("name") or "").casefold()
            or needle in str(record.get("reference") or "").casefold()
            or any(
                needle in str(term.get("species") or "").casefold()
                for term in record.get("reaction") or []
            )
        ]
    total = len(records)
    return {
        "temperatures": database.temperatures,
        "counts": database.counts,
        "section": section,
        "query": query,
        "offset": offset,
        "limit": limit,
        "total": total,
        "items": records[offset : offset + limit],
        "warnings": database.warnings[:20],
    }


__all__ = [
    "SECTION_NAMES",
    "ThermodynamicDatabase",
    "load_thermodynamic_database",
    "parse_thermodynamic_database",
    "search_thermodynamic_database",
]
