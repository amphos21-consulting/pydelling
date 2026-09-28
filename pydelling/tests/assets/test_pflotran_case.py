from __future__ import annotations

from collections import Counter
from pathlib import Path

import h5py
import numpy as np

from pydelling.assets import detect_pflotran_case

DECK = """
SIMULATION
  SIMULATION_TYPE SUBSURFACE
  PROCESS_MODELS
    SUBSURFACE_FLOW flow
      MODE RICHARDS
    /
  /
END

SUBSURFACE

DATASET top_pressure_bc
  FILENAME ./input_files/top_pressure_bc.h5
  HDF5_DATASET_NAME top_pressure_bc_dataset
END

DATASET east_pressure_bc
  FILENAME ./input_files/east_pressure_bc.h5
  HDF5_DATASET_NAME east_pressure_bc_dataset
END

CHEMISTRY
  PRIMARY_SPECIES
    TracerT
  /
  DATABASE ./hanford.dat
END

GRID
  TYPE unstructured_explicit ./input_files/mesh.mesh
END

MATERIAL_PROPERTY Rock
  ID 7
  POROSITY 4.3d-3
  TORTUOSITY 0.3d0
  PERMEABILITY
    PERM_ISO 1.d-15
  /
END

REGION Rock
  FILE ./input_files/Rock.mat
END

REGION top
  FILE ./input_files/top.ex
END

BOUNDARY_CONDITION top
  REGION top
END

STRATA
  REGION Rock
  MATERIAL Rock
END

END_SUBSURFACE
"""


def _h5(path: Path) -> None:
    with h5py.File(path, "w") as handle:
        handle.create_dataset("Data", data=np.ones((2, 2), dtype="f8"))


def _build_case(root: Path, *, missing_mesh: bool = False, stray: bool = False) -> Path:
    inputs = root / "input_files"
    inputs.mkdir(parents=True, exist_ok=True)
    (root / "input_case.in").write_text(DECK)
    if not missing_mesh:
        (inputs / "mesh.mesh").write_text("CELLS 2\n1 0 0 0 1\n2 1 0 0 1\n")
    (inputs / "Rock.mat").write_text("1\n2\n")
    (inputs / "top.ex").write_text("CONNECTIONS 1\n1 0 0 1 0.5\n")
    _h5(inputs / "top_pressure_bc.h5")
    _h5(inputs / "east_pressure_bc.h5")
    (root / "hanford.dat").write_text("# db\n")
    (root / "input_case-000.h5").write_text("snap")
    (root / "input_case-000.xmf").write_text("<Xdmf/>")
    (root / "input_case-domain.h5").write_text("dom")
    (root / "input_case-mas.dat").write_text("Time Mass\n0 1\n")
    (root / "input_case-obs-0.tec").write_text(
        '"Time [y]","Liquid Pressure [Pa] well1 (12)"\n0.0 101325.0\n'
    )
    (root / "input_case.out").write_text("log\n")
    if stray:
        (root / "leftover.txt").write_text("not referenced\n")
    return root


def test_detect_roles_and_all_datasets(tmp_path: Path) -> None:
    model = detect_pflotran_case(_build_case(tmp_path / "case"))
    assert model is not None
    counts = Counter(c.role for c in model.components)
    # Both DATASET blocks are found, including the first one that PflotranStudy's
    # get_datasets drops.
    assert counts["bc_dataset_h5"] == 2
    assert counts["mesh"] == 1
    assert counts["material_ids"] == 1
    assert counts["boundary_ex"] == 1
    assert counts["restart"] == 0
    assert counts["geochem_db"] == 1
    assert counts["output_snapshot"] == 1
    assert counts["output_xmf"] == 1
    assert counts["observation"] == 1
    assert counts["mass_balance"] == 1
    assert counts["log"] == 1
    assert counts["domain_h5"] == 1
    observation = next(c for c in model.components if c.role == "observation")
    assert observation.detail == {"rank": 0}
    material = next(c for c in model.components if c.role == "material_ids")
    assert material.detail["material"] == "Rock"
    assert material.detail["material_id"] == 7
    assert material.detail["material_properties"] == {
        "POROSITY": 4.3e-3,
        "TORTUOSITY": 0.3,
        "PERM_ISO": 1.0e-15,
    }
    assert model.summary["modes"] == ["RICHARDS"]
    assert [group["key"] for group in model.summary["asset_groups"]] == [
        "case",
        "domain",
        "materials",
        "boundary_conditions",
        "chemistry",
        "results",
    ]
    boundary_group = next(
        group
        for group in model.summary["asset_groups"]
        if group["key"] == "boundary_conditions"
    )
    assert boundary_group["count"] == 3
    assert boundary_group["roles"] == ["boundary_ex", "bc_dataset_h5"]
    assert model.warnings == []


def test_unreferenced_file_is_flagged(tmp_path: Path) -> None:
    model = detect_pflotran_case(_build_case(tmp_path / "case", stray=True))
    assert model is not None
    stray = [c for c in model.components if c.relative_path == "leftover.txt"]
    assert stray and stray[0].role == "other"
    assert any("not referenced" in w for w in model.warnings)


def test_missing_referenced_file_is_flagged(tmp_path: Path) -> None:
    model = detect_pflotran_case(_build_case(tmp_path / "case", missing_mesh=True))
    assert model is not None
    assert not [c for c in model.components if c.role == "mesh"]
    assert any("mesh.mesh" in w for w in model.warnings)


def test_non_case_folder_returns_none(tmp_path: Path) -> None:
    (tmp_path / "notes.txt").write_text("hello")
    assert detect_pflotran_case(tmp_path) is None


def test_structured_single_file_output_is_a_snapshot(tmp_path: Path) -> None:
    root = _build_case(tmp_path / "case")
    (root / "input_case.h5").write_text("structured output stand-in")
    model = detect_pflotran_case(root)
    assert model is not None
    single = next(
        c for c in model.components if c.relative_path == "input_case.h5"
    )
    assert single.role == "output_snapshot"
    assert single.detail == {"single_file": True}
