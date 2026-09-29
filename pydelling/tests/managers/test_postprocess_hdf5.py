"""``ExtractHDF5``: time series of cells and regions from PFLOTRAN snapshots."""

from pathlib import Path

import h5py
import numpy as np
import pandas as pd
import pytest

from pydelling.managers import PflotranStudy
from pydelling.managers.postprocess import (
    Cell,
    CellGeometry,
    Cells,
    Domain,
    ExtractHDF5,
    PostprocessCallback,
    Region,
    Selection,
)
from pydelling.managers.postprocess.selections import aggregate

# 4 x 2 x 1 cells of 1 x 1 x 2 m; natural ids run along x first.
DECK = """SUBSURFACE
GRID
  TYPE STRUCTURED
  NXYZ 4 2 1
  BOUNDS
    0.d0 0.d0 0.d0
    4.d0 2.d0 2.D0
  END
END
REGION all
  COORDINATES
    0.d0 0.d0 0.d0
    4.d0 2.d0 2.d0
  END
END
REGION west
  COORDINATES
    0.d0 0.d0 0.d0
    0.d0 2.d0 2.d0
  END
END
REGION right_half
  COORDINATES
    2.d0 0.d0 0.d0
    4.d0 2.d0 2.d0
  END
END
REGION probe
  COORDINATE 2.6d0 1.5d0 1.d0
END
REGION corner
  BLOCK 4 4 2 2 1 1
END
REGION listed
  FILE input_files/listed.txt
END
END_SUBSURFACE
"""


def natural_to_array(values: np.ndarray, shape: tuple[int, int, int]) -> np.ndarray:
    """PFLOTRAN stores structured snapshots as (nx, ny, nz) arrays."""
    return np.asarray(values, dtype=float).reshape(shape, order="F")


@pytest.fixture
def study(tmp_path: Path) -> PflotranStudy:
    deck = tmp_path / "deck.in"
    deck.write_text(DECK)
    listed = tmp_path / "listed.txt"
    listed.write_text("CELL_IDS 2\n1\n8\n")
    study = PflotranStudy(str(deck), study_name="s")
    study.add_input_file(listed)
    return study


@pytest.fixture
def run(tmp_path: Path) -> Path:
    """Two snapshots in two files; the tracer equals the cell id times the time in days."""
    work = tmp_path / "work"
    work.mkdir()
    ids = np.arange(1, 9)
    for index, day in enumerate([1.0, 2.0]):
        with h5py.File(work / f"pflotran-{index:03d}.h5", "w") as out:
            coordinates = out.create_group("Coordinates")
            coordinates["X [m]"] = [0.0, 1.0, 2.0, 3.0, 4.0]
            coordinates["Y [m]"] = [0.0, 1.0, 2.0]
            coordinates["Z [m]"] = [0.0, 2.0]
            group = out.create_group(f"Time:  {day:.5E} d")
            group["Total_Tracer [M]"] = natural_to_array(ids * day, (4, 2, 1))
            group["Liquid Pressure [Pa]"] = natural_to_array(ids * 0 + 1e5, (4, 2, 1))
    (work / "input_files").mkdir()
    (work / "input_files/listed.txt").write_text("CELL_IDS 2\n1\n8\n")
    return work


def geometry() -> CellGeometry:
    return CellGeometry.structured([0, 1, 2, 3, 4], [0, 1, 2], [0, 2])


# ---------------------------------------------------------------- geometry


def test_structured_geometry_from_the_hdf5_and_from_the_deck(run, study):
    from_h5 = CellGeometry.from_hdf5(run / "pflotran-000.h5")
    from_deck = CellGeometry.from_deck(study)
    for grid in (from_h5, from_deck):
        assert grid.shape == (4, 2, 1)
        assert grid.centers[0].tolist() == [0.5, 0.5, 1.0]
        assert grid.centers[4].tolist() == [0.5, 1.5, 1.0]  # x runs first
        assert grid.volumes.tolist() == [2.0] * 8
        assert [b.tolist() for b in grid.bounds] == [[0, 0, 0], [4, 2, 2]]


def test_dxyz_with_repeats_and_an_origin(tmp_path):
    deck = tmp_path / "deck.in"
    deck.write_text(
        "SUBSURFACE\nGRID\n  TYPE STRUCTURED\n  NXYZ 3 1 1\n  ORIGIN 10.d0 0.d0 0.d0\n"
        "  DXYZ\n    2*1.d0 2.0\n    1.\n    1.\n  END\nEND\nEND_SUBSURFACE\n"
    )
    grid = CellGeometry.from_deck(PflotranStudy(str(deck)))
    assert grid.centers[:, 0].tolist() == [10.5, 11.5, 13.0]
    assert grid.volumes.tolist() == [1.0, 1.0, 2.0]


def test_placeholders_defer_the_geometry_to_the_run(tmp_path):
    deck = tmp_path / "deck.in"
    deck.write_text("SUBSURFACE\nGRID\n  TYPE STRUCTURED\n  NXYZ <<NX>> 1 1\nEND\nEND_SUBSURFACE\n")
    assert CellGeometry.from_deck(PflotranStudy(str(deck))) is None


def test_explicit_unstructured_geometry_from_the_uge_file(tmp_path):
    mesh = tmp_path / "mesh.uge"
    mesh.write_text("CELLS 2\n2 1.5 0.5 0.5 1.0\n1 0.5 0.5 0.5 2.0\nCONNECTIONS 1\n1 2 1 .5 .5 1\n")
    deck = tmp_path / "deck.in"
    deck.write_text("SUBSURFACE\nGRID\n  TYPE UNSTRUCTURED_EXPLICIT mesh.uge\nEND\nEND_SUBSURFACE\n")
    study = PflotranStudy(str(deck))
    study.add_input_file(mesh)
    grid = CellGeometry.from_deck(study)
    assert grid.centers[:, 0].tolist() == [0.5, 1.5]
    assert grid.volumes.tolist() == [2.0, 1.0]
    assert grid.shape is None and grid.lower is None


def test_implicit_unstructured_geometry_from_the_domain(tmp_path):
    cube = [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]]
    tet = [[2, 0, 0], [3, 0, 0], [2, 1, 0], [2, 0, 1]]
    path = tmp_path / "out.h5"
    with h5py.File(path, "w") as out:
        out["Domain/Vertices"] = np.array(cube + tet, dtype=float)
        out["Domain/Cells"] = np.array([9, 0, 1, 2, 3, 4, 5, 6, 7, 6, 8, 9, 10, 11])
    grid = CellGeometry.from_hdf5(path)
    assert grid.volumes == pytest.approx([1.0, 1 / 6])
    assert grid.centers[0].tolist() == [0.5, 0.5, 0.5]
    assert grid.centers[1].tolist() == pytest.approx([2.25, 0.25, 0.25])


# ---------------------------------------------------------------- selections


def test_a_cell_by_point_id_or_index(study):
    grid = geometry()
    assert Cell(x=2.6, y=1.5, z=1).cells(grid, study, None).tolist() == [7]
    assert Cell(x=3.9).cells(grid, study, None).tolist() == [4]  # y and z ignored
    assert Cell(id=5).cells(grid, study, None).tolist() == [5]
    assert Cell(index=(2, 2, 1)).cells(grid, study, None).tolist() == [6]
    assert Cell(id=5).cells(None, study, None).tolist() == [5]  # no geometry needed
    with pytest.raises(ValueError, match="outside the grid"):
        Cell(x=4.5).cells(grid, study, None)
    with pytest.raises(ValueError, match="id 9 is not a cell"):
        Cell(id=9).cells(grid, study, None)
    with pytest.raises(ValueError, match="exactly one of"):
        Cell(x=1.0, id=1)


def test_regions_from_the_deck(study):
    grid = geometry()
    assert Region("all", aggregate="mean").cells(grid, study, None).tolist() == list(range(1, 9))
    assert Region("west", aggregate="mean").cells(grid, study, None).tolist() == [1, 5]
    assert Region("right_half", aggregate="sum").cells(grid, study, None).tolist() == [3, 4, 7, 8]
    assert Region("probe", aggregate="max").cells(grid, study, None).tolist() == [7]
    assert Region("corner", aggregate="max").cells(grid, study, None).tolist() == [8]
    assert Region("listed", aggregate="max").cells(grid, study, None).tolist() == [1, 8]
    with pytest.raises(ValueError, match="No REGION 'nowhere'"):
        Region("nowhere", aggregate="mean").cells(grid, study, None)


def test_boxes_cells_and_the_whole_domain(study):
    grid = geometry()
    box = Region(box=[[0.5, 0, 0], [1.5, 1, 2]], aggregate="mean")
    assert box.cells(grid, study, None).tolist() == [1, 2]
    assert Cells(ids=[3, 1]).cells(grid, study, None).tolist() == [3, 1]
    assert Cells(points=[[0.1, 0.1, 0.1], [3.9, 1.9, 1.9]]).cells(grid, study, None).tolist() == [
        1,
        8,
    ]
    assert Domain("max").cells(grid, study, None).tolist() == list(range(1, 9))
    with pytest.raises(ValueError, match="selects no cell"):
        Region(box=[[5, 5, 5], [6, 6, 6]], aggregate="mean").cells(grid, study, None)


def test_regions_need_an_aggregate():
    with pytest.raises(ValueError, match="needs an aggregate"):
        Region("all")
    with pytest.raises(ValueError, match="Unknown aggregate 'median'"):
        Domain("median")


def test_unstructured_boxes_use_cell_centers():
    grid = CellGeometry(centers=np.array([[0.5, 0, 0], [1.5, 0, 0]]), volumes=np.ones(2))
    assert Region(box=[[0, -1, -1], [1, 1, 1]], aggregate="mean").cells(grid, None, None).tolist() == [1]


def spread(values: np.ndarray, volumes: np.ndarray | None) -> float:
    """A custom aggregate: ``f(values, volumes) -> float``."""
    return float(values.max() - values.min())


def test_aggregates():
    values, volumes = np.array([1.0, 3.0]), np.array([1.0, 3.0])
    assert aggregate("mean", values, volumes) == 2.0
    assert aggregate("volume_mean", values, volumes) == 2.5
    assert aggregate("sum", values, volumes) == 4.0
    assert aggregate("integral", values, volumes) == 10.0
    assert aggregate("min", values, volumes) == 1.0
    assert aggregate("max", values, volumes) == 3.0
    assert aggregate(spread, values, volumes) == 2.0
    with pytest.raises(ValueError, match="needs cell volumes"):
        aggregate("integral", values, None)


class EvenCells(Selection):
    """A custom selection: every even natural id."""

    def cells(self, geometry, study, workdir):
        return np.arange(2, len(geometry.centers) + 1, 2)


# ---------------------------------------------------------------- extraction


def test_extract_cells_and_regions_over_time(run, study):
    callback = ExtractHDF5(
        "Total_*",
        {
            "probe": Cell(x=2.6, y=1.5, z=1),
            "pair": Cells(ids=[1, 8]),
            "left": Region(box=[[0, 0, 0], [2, 2, 2]], aggregate="volume_mean"),
            "total": Domain("integral"),
            "even": EvenCells(aggregate="sum"),
        },
    )
    callback.validate(study)
    frame = callback.process(run, study)
    assert list(frame.columns) == [
        "time_s", "selection", "variable", "unit", "cell", "value", "aggregate", "n_cells",
        "volume",
    ]
    assert set(frame.variable) == {"Total_Tracer"} and set(frame.unit) == {"M"}
    day2 = frame[frame.time_s == 2 * 86400.0].set_index(["selection", "cell"], drop=False)
    assert day2.loc[("probe", 7), "value"] == 14.0
    pair = frame[(frame.selection == "pair") & (frame.time_s == 86400.0)]
    assert pair.cell.tolist() == [1, 8] and pair.value.tolist() == [1.0, 8.0]
    left = frame[(frame.selection == "left") & (frame.time_s == 86400.0)].iloc[0]
    assert left.value == 3.5 and left.n_cells == 4 and left.volume == 8.0
    assert left["aggregate"] == "volume_mean" and pd.isna(left.cell)
    total = frame[(frame.selection == "total") & (frame.time_s == 86400.0)].iloc[0]
    assert total.value == 2.0 * 36
    even = frame[(frame.selection == "even") & (frame.time_s == 86400.0)].iloc[0]
    assert even.value == 2 + 4 + 6 + 8
    assert sorted(frame.time_s.unique()) == [86400.0, 172800.0]


def test_times_filter_and_missing_times(run, study):
    frame = ExtractHDF5("Liquid Pressure [Pa]", {"c": Cell(id=1)}, times=[172800]).process(
        run, study
    )
    assert frame.time_s.tolist() == [172800.0] and frame.value.tolist() == [1e5]
    with pytest.raises(ValueError, match="No snapshot at 3600"):
        ExtractHDF5("Total_*", {"c": Cell(id=1)}, times=[3600]).process(run, study)
    with pytest.raises(ValueError, match="No HDF5 variable matches"):
        ExtractHDF5("Nope*", {"c": Cell(id=1)}).process(run, study)


def test_the_same_time_in_two_files_is_an_error(run, study):
    with h5py.File(run / "pflotran-000.h5") as source, h5py.File(run / "copy.h5", "w") as copy:
        source.copy("Coordinates", copy)
        source.copy(next(k for k in source if k.startswith("Time:")), copy)
    with pytest.raises(ValueError, match="twice"):
        ExtractHDF5("Total_*", {"c": Cell(id=1)}).process(run, study)


def test_validation_before_the_run(study):
    ExtractHDF5("Total_*", {"west": Region("west", aggregate="mean")}).validate(study)
    with pytest.raises(ValueError, match="No REGION 'east'"):
        ExtractHDF5("Total_*", {"e": Region("east", aggregate="mean")}).validate(study)
    with pytest.raises(ValueError, match="outside the grid"):
        ExtractHDF5("Total_*", {"far": Cell(x=100.0)}).validate(study)
    with pytest.raises(ValueError, match="at least one selection"):
        ExtractHDF5("Total_*", {})


def test_spec_round_trip():
    callback = ExtractHDF5(
        ["Total_*"],
        {"c": Cell(x=1.0), "r": Region("all", aggregate=spread), "d": Domain("max")},
        times=[1.0],
        name="ex",
    )
    spec = callback.spec()
    assert spec["options"]["selections"]["r"]["options"]["aggregate"] == f"{__name__}:spread"
    rebuilt = PostprocessCallback.from_spec(spec)
    assert rebuilt.spec() == spec
    assert rebuilt.selections["r"].aggregate is spread
