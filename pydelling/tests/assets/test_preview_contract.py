from __future__ import annotations

from pathlib import Path

import h5py
import meshio
import numpy as np
import pytest

from pydelling.assets import PREVIEW_CONTRACT_VERSION, build_asset_preview
from pydelling.preprocessing import DfnPreprocessor
from pydelling.readers import PflotranReader


TEST_DATA = Path(__file__).resolve().parents[1] / "test_data"
CONTRACT_KEYS = {
    "version",
    "asset_kind",
    "format",
    "summary",
    "sections",
    "warnings",
    "limits",
    "computed_at",
}


def _assert_contract(document: dict, *, expected_kind: str) -> None:
    assert CONTRACT_KEYS <= set(document)
    assert set(document) <= CONTRACT_KEYS | {"metadata"}
    assert document["version"] == PREVIEW_CONTRACT_VERSION == 3
    assert document["asset_kind"] == expected_kind
    assert isinstance(document["sections"], list)
    assert document["sections"]
    assert all("kind" in section and "title" in section for section in document["sections"])
    assert document["limits"] == {"max_rows": 3, "max_bytes": 4096}


@pytest.mark.parametrize(
    ("relative_path", "expected_kind"),
    [
        ("centroid_reader_data.csv", "tabular"),
        ("top_surface.asc", "raster"),
        ("test_fault.stl", "mesh"),
        ("test_implicit_to_explicit.gid", "igp_reader"),
    ],
)
def test_existing_asset_golden_contract(relative_path: str, expected_kind: str):
    document = build_asset_preview(
        TEST_DATA / relative_path,
        max_rows=3,
        max_bytes=4096,
    )

    _assert_contract(document, expected_kind=expected_kind)


def test_hdf5_golden_contract(tmp_path: Path):
    path = tmp_path / "sample.h5"
    with h5py.File(path, "w") as handle:
        handle.create_dataset("values", data=np.arange(6).reshape(2, 3))

    document = build_asset_preview(path, max_rows=3, max_bytes=4096)

    _assert_contract(document, expected_kind="hdf5")


@pytest.mark.parametrize("extension", ["vtk", "vtu"])
def test_vtk_family_golden_contract(tmp_path: Path, extension: str):
    path = tmp_path / f"mesh.{extension}"
    meshio.Mesh(
        points=np.asarray(
            [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
        ),
        cells=[("triangle", np.asarray([[0, 1, 2]]))],
    ).write(path)

    document = build_asset_preview(path, max_rows=3, max_bytes=4096)

    _assert_contract(document, expected_kind="mesh")


def test_vtp_golden_contract(tmp_path: Path):
    pytest.importorskip("vtkmodules")
    from vtkmodules.vtkCommonCore import vtkPoints
    from vtkmodules.vtkCommonDataModel import vtkCellArray, vtkPolyData, vtkTriangle
    from vtkmodules.vtkIOXML import vtkXMLPolyDataWriter

    points = vtkPoints()
    points.InsertNextPoint(0.0, 0.0, 0.0)
    points.InsertNextPoint(1.0, 0.0, 0.0)
    points.InsertNextPoint(0.0, 1.0, 0.0)
    triangle = vtkTriangle()
    for index in range(3):
        triangle.GetPointIds().SetId(index, index)
    polygons = vtkCellArray()
    polygons.InsertNextCell(triangle)
    poly_data = vtkPolyData()
    poly_data.SetPoints(points)
    poly_data.SetPolys(polygons)

    path = tmp_path / "mesh.vtp"
    writer = vtkXMLPolyDataWriter()
    writer.SetFileName(str(path))
    writer.SetInputData(poly_data)
    assert writer.Write() == 1

    document = build_asset_preview(path, max_rows=3, max_bytes=4096)

    _assert_contract(document, expected_kind="mesh")
    assert document["sections"][0]["metadata"]["points"] == 3
    assert document["sections"][0]["metadata"]["cells"] == 1


def test_legacy_public_imports_remain_available():
    from pydelling.readers import iGPReader

    assert PflotranReader.__name__ == "PflotranReader"
    assert iGPReader.__name__ == "iGPReader"
    assert DfnPreprocessor.__name__ == "DfnPreprocessor"


def test_igp_describe_regions_match_schema_regions():
    """describe() and schema() must agree on the shape of "regions".

    They used to disagree — describe() flattened them to bare names — so callers
    iterating describe()["regions"] and reading per-region counts crashed.
    """
    from pydelling.assets.handlers import AssetSource, load_asset_handle

    root = TEST_DATA / "test_implicit_to_explicit.gid"
    handle = load_asset_handle(
        AssetSource(file_name=root.name, path=root, extension="gid")
    )
    description = handle.describe()

    assert description["regions"] == description["schema"]["regions"]
    assert description["boundaries"] == description["schema"]["boundaries"]
    assert description["regions"] == handle.region_summaries
    assert all(region["faces"] > 0 for region in description["regions"])
    assert description["region_names"] == [
        region["name"] for region in description["regions"]
    ]
