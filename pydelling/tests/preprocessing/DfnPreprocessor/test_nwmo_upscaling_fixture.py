"""Small real-data integration fixture extracted from the NWMO model."""

from __future__ import annotations

import base64
import io
import lzma
from pathlib import Path
import time

import numpy as np

from pydelling.preprocessing.dfn_preprocessor import SurfaceDfn, intersect_surface_with_mesh, upscale_surface_dfn
from pydelling.preprocessing.mesh_preprocessor import ArrayMesh


ASSETS = Path(__file__).parents[2] / "assets"
GROUP_NAMES = {
    0: "IFZ_FracFace",
    1: "IRU4_FracFace",
    2: "SHF_BH01_305_FracFace",
    3: "SSDFN_FracFace_AllSets_015",
}


def load_archive(name, *, xz=False):
    encoded = (ASSETS / name).read_text().strip()
    data = base64.b64decode(encoded)
    return np.load(io.BytesIO(lzma.decompress(data) if xz else data))


def load_fixture():
    mesh_data = load_archive("nwmo_5x5x5_mesh.npz.b64")
    mesh = ArrayMesh(
        points=mesh_data["points"],
        connectivity=mesh_data["connectivity"],
        cell_types=mesh_data["cell_types"],
        cell_ids=mesh_data["cell_ids"],
        centroids=mesh_data["centroids"],
        volumes=mesh_data["volumes"],
        point_ids=mesh_data["point_ids"],
        material_ids=mesh_data["material_ids"],
        metadata={"fixture": "NWMO logical cells i=62..66, j=80..84, k=101..105"},
    )
    dfn_data = load_archive("nwmo_central_620_triangles.npz.xz.b64", xz=True)
    dfn = SurfaceDfn(
        points=dfn_data["points"],
        triangles=dfn_data["triangles"],
        thickness=dfn_data["thickness"],
        hydraulic_conductivity=dfn_data["hydraulic_conductivity"],
        porosity=dfn_data["porosity"],
        specific_storage=dfn_data["specific_storage"],
        group_ids=dfn_data["group_ids"],
        fracture_element_ids=dfn_data["fracture_element_ids"],
        source_node_ids=dfn_data["source_node_ids"],
        group_names=GROUP_NAMES,
        metadata={"fixture": "310 NWMO fracture faces / 620 triangles"},
    )
    return mesh, dfn, mesh_data["central_cell_ids"]


def logical_oracle(mesh, dfn):
    """Allocate logical face triangles without using geometric clipping."""

    source = dfn.source_node_ids[dfn.triangles] - 1
    k, horizontal = np.divmod(source, 361 * 361)
    j, i = np.divmod(horizontal, 361)
    xyz = dfn.points[dfn.triangles]
    areas = np.linalg.norm(np.cross(xyz[:, 1] - xyz[:, 0], xyz[:, 2] - xyz[:, 0]), axis=1) / 2
    expected = np.zeros(mesh.n_cells)
    id_to_local = {int(cell_id): local for local, cell_id in enumerate(mesh.cell_ids)}
    for triangle_id in range(dfn.n_triangles):
        ranges = [(values[triangle_id].min(), values[triangle_id].max()) for values in (i, j, k)]
        constant = next(axis for axis, (low, high) in enumerate(ranges) if low == high)
        logical = [int(np.floor(values[triangle_id].mean() / 4)) for values in (i, j)] + [int(k[triangle_id].min())]
        coordinate = int(ranges[constant][0])
        if constant < 2 and coordinate % 4:
            candidates = [logical]
        else:
            boundary = coordinate // 4 if constant < 2 else coordinate
            lower = logical.copy()
            upper = logical.copy()
            lower[constant] = boundary - 1
            upper[constant] = boundary
            candidates = [lower, upper]
        local_candidates = []
        for cell_i, cell_j, cell_k in candidates:
            cell_id = cell_k * 8100 + cell_j * 90 + cell_i + 1
            if cell_id in id_to_local:
                local_candidates.append(id_to_local[cell_id])
        for local in local_candidates:
            expected[local] += areas[triangle_id] / len(local_candidates)
    return expected, areas


def test_real_nwmo_fixture_matches_logical_oracle_and_upscales_under_ten_seconds():
    mesh, dfn, central_ids = load_fixture()
    assert mesh.n_cells == 125
    assert dfn.n_triangles == 620
    assert len(dfn.points) == 326
    assert {GROUP_NAMES[int(group)]: int(np.sum(dfn.group_ids == group)) for group in np.unique(dfn.group_ids)} == {
        "IFZ_FracFace": 44,
        "IRU4_FracFace": 74,
        "SHF_BH01_305_FracFace": 316,
        "SSDFN_FracFace_AllSets_015": 186,
    }
    central = np.isin(mesh.cell_ids, central_ids)
    assert central.sum() == 27
    assert dict(zip(*np.unique(mesh.material_ids[central], return_counts=True))) == {1: 12, 2: 6, 5: 6, 6: 3}

    started = time.perf_counter()
    intersections = intersect_surface_with_mesh(dfn, mesh, chunk_size=64)
    oracle_area, source_areas = logical_oracle(mesh, dfn)
    geometric_area = np.zeros(mesh.n_cells)
    np.add.at(geometric_area, intersections.cell_indices, intersections.areas)
    np.testing.assert_allclose(geometric_area, oracle_area, rtol=2.0e-8, atol=1.0e-7)
    np.testing.assert_allclose(intersections.areas.sum(), source_areas.sum(), rtol=2.0e-8)

    porosity_by_material = {1: 0.0043, 2: 0.01, 3: 0.001, 4: 0.001, 5: 0.0043, 6: 0.01}
    matrix_porosity = np.asarray([porosity_by_material[int(value)] for value in mesh.material_ids])
    result = upscale_surface_dfn(
        dfn,
        mesh,
        matrix_porosity=matrix_porosity,
        matrix_intrinsic_permeability=1.0e-12,
        intersections=intersections,
    )
    np.testing.assert_allclose(result.fracture_area, oracle_area, rtol=2.0e-8, atol=1.0e-7)
    assert np.all(result.porosity[central] >= result.matrix_porosity[central])
    assert np.allclose(result.hydraulic_conductivity, result.hydraulic_conductivity.transpose(0, 2, 1))
    assert time.perf_counter() - started < 10.0
