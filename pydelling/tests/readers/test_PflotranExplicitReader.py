from __future__ import annotations

from pathlib import Path

from pydelling.readers.iGPReader.io import (
    read_boundary_connections,
    read_material_ids,
)


def test_read_material_ids(tmp_path: Path) -> None:
    mat = tmp_path / "Rock.mat"
    mat.write_text("\n".join(str(i) for i in [5, 1, 9, 3]) + "\n")
    summary = read_material_ids(mat)
    assert summary["count"] == 4
    assert summary["min"] == 1
    assert summary["max"] == 9
    assert summary["ids"].tolist() == [5, 1, 9, 3]


def test_read_empty_material(tmp_path: Path) -> None:
    mat = tmp_path / "empty.mat"
    mat.write_text("")
    summary = read_material_ids(mat)
    assert summary["count"] == 0
    assert summary["min"] is None
    assert summary["max"] is None


def test_read_boundary_connections(tmp_path: Path) -> None:
    ex = tmp_path / "top.ex"
    ex.write_text(
        "CONNECTIONS 3\n"
        "101 0.0 0.0 1.0 2.0\n"
        "102 1.0 0.0 1.0 3.0\n"
        "103 2.0 5.0 1.0 5.0\n"
    )
    summary = read_boundary_connections(ex)
    assert summary["declared_count"] == 3
    assert summary["face_count"] == 3
    assert summary["total_area"] == 10.0
    assert summary["area_min"] == 2.0
    assert summary["area_max"] == 5.0
    assert summary["bbox"]["min"] == [0.0, 0.0, 1.0]
    assert summary["bbox"]["max"] == [2.0, 5.0, 1.0]
    assert summary["element_ids"].tolist() == [101, 102, 103]


def test_declared_count_may_differ_from_rows(tmp_path: Path) -> None:
    # A truncated file: header claims more faces than are present.
    ex = tmp_path / "partial.ex"
    ex.write_text("CONNECTIONS 10\n1 0.0 0.0 0.0 1.0\n")
    summary = read_boundary_connections(ex)
    assert summary["declared_count"] == 10
    assert summary["face_count"] == 1
