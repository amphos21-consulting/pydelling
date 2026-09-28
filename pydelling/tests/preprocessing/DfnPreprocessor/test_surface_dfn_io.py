from pathlib import Path

import numpy as np
import pytest

from pydelling.preprocessing.dfn_preprocessor import DfnPreprocessor, validate_hgs_directory


MESH = """CELLS 1
1 0.5 0.5 0.5 1.0
CONNECTIONS 0
ELEMENTS 1
H 1 2 4 3 5 6 8 7
VERTICES 8
0 0 0
1 0 0
0 1 0
1 1 0
0 0 1
1 0 1
0 1 1
1 1 1
"""


def hgs(element_offset=0):
    return f"""Number of fracture elements
2
FracElem_ID ElemNode1 ElemNode2 ElemNode3 Thickness Hydraulic_Conductivity Porosity Specific_Storage
{element_offset + 1} 1 2 4 0.1 2.0 0.5 1e-6
{element_offset + 2} 1 4 3 0.1 2.0 0.5 1e-6
"""


def test_hgs_physical_policy_pair_validation_and_vtk_round_trip(tmp_path: Path):
    mesh_path = tmp_path / "mesh.mesh"
    mesh_path.write_text(MESH)
    (tmp_path / "IFZ_FracFace_aperture.hgs").write_text(hgs())
    (tmp_path / "IFZ_FracFace_0.1.hgs").write_text(hgs().replace(" 0.5 ", " 0.1 "))
    (tmp_path / "SSDFN_FracFace_AllSets_015_aperture.hgs").write_text(hgs(10))
    (tmp_path / "SSDFN_FracFace_Set1_015_aperture.hgs").write_text(hgs(20))
    dfn = DfnPreprocessor.from_hgs_directory(
        tmp_path, companion_mesh=mesh_path, variant="aperture", groups="physical", refinement=1
    )
    surface = dfn.surface_networks[0]
    assert surface.n_triangles == 4
    assert len(surface.group_names) == 2
    assert np.all(surface.effective_aperture == 0.05)
    vtk = surface.write_vtk(tmp_path / "surface.vtu")
    restored = DfnPreprocessor.from_surface_vtk(vtk, groups="physical").surface_networks[0]
    assert restored.n_triangles == 4
    np.testing.assert_allclose(restored.plane_transmissivity, surface.plane_transmissivity)
    report = validate_hgs_directory(tmp_path)
    assert report["variants_checked"] == 1
    assert report["ssdfn_subset_triangles"] == 2


def test_legacy_polydata_surface_vtk_is_supported(tmp_path: Path):
    pytest.importorskip("vtk", reason="legacy POLYDATA requires the cloud extra")
    path = tmp_path / "surface.vtk"
    path.write_text(
        """# vtk DataFile Version 3.0
surface
ASCII
DATASET POLYDATA
FIELD FieldData 1
dfn_id_0__test_group 1 1 int
0
POINTS 3 double
0 0 0
1 0 0
0 1 0
POLYGONS 1 4
3 0 1 2
CELL_DATA 1
SCALARS dfn_id int 1
LOOKUP_TABLE default
0
FIELD FieldData 5
thickness 1 1 double
0.1
hydraulic_conductivity 1 1 double
2.0
porosity 1 1 double
0.25
specific_storage 1 1 double
3e-6
fracture_element_id 1 1 int
7
"""
    )
    restored = DfnPreprocessor.from_surface_vtk(path, groups="all").surface_networks[0]
    assert restored.n_triangles == 1
    assert restored.group_names == {0: "test_group"}
    assert restored.fracture_element_ids[0] == 7
    assert restored.effective_aperture[0] == pytest.approx(0.025)


def test_legacy_polydata_reports_missing_optional_dependency(tmp_path: Path, monkeypatch):
    import sys
    from pydelling.preprocessing.dfn_preprocessor.surface_dfn import SurfaceDfnError

    monkeypatch.setitem(sys.modules, "vtk", None)
    path = tmp_path / "surface.vtk"
    path.write_text("# vtk DataFile Version 3.0\nsurface\nASCII\nDATASET POLYDATA\n")
    with pytest.raises(SurfaceDfnError, match="cloud"):
        DfnPreprocessor.from_surface_vtk(path)
