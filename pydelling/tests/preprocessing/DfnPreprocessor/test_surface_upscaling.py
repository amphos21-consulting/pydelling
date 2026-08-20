from __future__ import annotations

from pathlib import Path

import h5py
import meshio
import numpy as np
import pytest

from pydelling.preprocessing.dfn_preprocessor import (
    DfnPreprocessor,
    DfnUpscaler,
    Fault,
    Fracture,
    SurfaceDfn,
    intersect_surface_with_mesh,
    upscale_surface_dfn,
)
from pydelling.preprocessing.mesh_preprocessor import ArrayMesh, MeshPreprocessor


def array_mesh(points, connectivity, code, *, cell_id=1, volume=1.0):
    points = np.asarray(points, dtype=float)
    connectivity = np.asarray(connectivity, dtype=np.int64)
    padded = np.full((1, 8), -1, dtype=np.int64)
    padded[0, : len(connectivity)] = connectivity
    return ArrayMesh(
        points=points,
        connectivity=padded,
        cell_types=np.asarray([code]),
        cell_ids=np.asarray([cell_id]),
        centroids=np.asarray([points[connectivity].mean(axis=0)]),
        volumes=np.asarray([volume]),
    )


def surface(
    points,
    *,
    thickness=0.1,
    conductivity=2.0,
    porosity=0.5,
    specific_storage=1.0e-6,
    group=0,
):
    points = np.asarray(points, dtype=float)
    return SurfaceDfn(
        points=points,
        triangles=np.asarray([[0, 1, 2]]),
        thickness=np.asarray([thickness]),
        hydraulic_conductivity=np.asarray([conductivity]),
        porosity=np.asarray([porosity]),
        specific_storage=np.asarray([specific_storage]),
        group_ids=np.asarray([group]),
        fracture_element_ids=np.asarray([42]),
        group_names={group: "test"},
    )


CELL_CASES = (
    (
        "T",
        [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]],
        [0, 1, 2, 3],
        [[0.1, 0.1, 0.1], [0.3, 0.1, 0.1], [0.1, 0.3, 0.1]],
    ),
    (
        "H",
        [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]],
        list(range(8)),
        [[0.2, 0.2, 0.5], [0.8, 0.2, 0.5], [0.2, 0.8, 0.5]],
    ),
    (
        "W",
        [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1], [1, 0, 1], [0, 1, 1]],
        list(range(6)),
        [[0.1, 0.1, 0.5], [0.5, 0.1, 0.5], [0.1, 0.5, 0.5]],
    ),
    (
        "P",
        [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0.5, 0.5, 1]],
        list(range(5)),
        [[0.3, 0.3, 0.25], [0.7, 0.3, 0.25], [0.3, 0.7, 0.25]],
    ),
)


@pytest.mark.parametrize("code,points,connectivity,triangle", CELL_CASES)
def test_full_triangle_containment_for_supported_cells(code, points, connectivity, triangle):
    mesh = array_mesh(points, connectivity, code)
    dfn = surface(triangle)
    intersections = intersect_surface_with_mesh(dfn, mesh)
    expected = np.linalg.norm(np.cross(dfn.points[1] - dfn.points[0], dfn.points[2] - dfn.points[0])) / 2
    np.testing.assert_allclose(intersections.areas, [expected], rtol=1.0e-12)


def test_intersection_is_rotation_invariant():
    code, points, connectivity, triangle = CELL_CASES[1]
    angle = np.deg2rad(37.0)
    rotation = np.asarray(
        [[np.cos(angle), -np.sin(angle), 0], [np.sin(angle), np.cos(angle), 0], [0, 0, 1]]
    )
    mesh = array_mesh(np.asarray(points) @ rotation.T, connectivity, code)
    dfn = surface(np.asarray(triangle) @ rotation.T)
    expected = np.linalg.norm(np.cross(dfn.points[1] - dfn.points[0], dfn.points[2] - dfn.points[0])) / 2
    np.testing.assert_allclose(intersect_surface_with_mesh(dfn, mesh).areas, [expected])


def test_no_intersection_returns_empty_table():
    code, points, connectivity, _ = CELL_CASES[1]
    mesh = array_mesh(points, connectivity, code)
    result = intersect_surface_with_mesh(surface([[2, 2, 2], [3, 2, 2], [2, 3, 2]]), mesh)
    assert result.areas.size == 0


def test_parallel_shared_array_intersection_matches_serial():
    code, points, connectivity, triangle = CELL_CASES[1]
    mesh = array_mesh(points, connectivity, code)
    points = np.asarray(triangle + [[0.3, 0.3, 0.7], [0.7, 0.3, 0.7], [0.3, 0.7, 0.7]])
    dfn = SurfaceDfn(
        points=points,
        triangles=np.asarray([[0, 1, 2], [3, 4, 5]]),
        thickness=np.full(2, 0.1),
        hydraulic_conductivity=np.full(2, 2.0),
        porosity=np.full(2, 0.5),
        specific_storage=np.full(2, 1.0e-6),
        group_ids=np.zeros(2, dtype=int),
        fracture_element_ids=np.arange(2),
    )
    serial = intersect_surface_with_mesh(dfn, mesh, chunk_size=1)
    parallel = intersect_surface_with_mesh(dfn, mesh, chunk_size=1, workers=2)
    np.testing.assert_array_equal(parallel.triangle_indices, serial.triangle_indices)
    np.testing.assert_array_equal(parallel.cell_indices, serial.cell_indices)
    np.testing.assert_allclose(parallel.areas, serial.areas)


def test_shared_face_area_is_split_conservatively():
    points = np.asarray(
        [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1],
         [2, 0, 0], [2, 1, 0], [2, 0, 1], [2, 1, 1]],
        dtype=float,
    )
    connectivity = np.asarray(
        [[0, 1, 2, 3, 4, 5, 6, 7], [1, 8, 9, 2, 5, 10, 11, 6]], dtype=np.int64
    )
    mesh = ArrayMesh(
        points, connectivity, np.asarray(["H", "H"]), np.asarray([10, 11]),
        np.asarray([[0.5, 0.5, 0.5], [1.5, 0.5, 0.5]]), np.ones(2),
    )
    dfn = surface([[1, 0.2, 0.2], [1, 0.8, 0.2], [1, 0.2, 0.8]])
    result = intersect_surface_with_mesh(dfn, mesh)
    np.testing.assert_allclose(result.areas, [0.09, 0.09], atol=1.0e-12)
    assert result.areas.sum() == pytest.approx(0.18)


def test_upscaling_equations_tensor_units_and_idempotence():
    code, points, connectivity, triangle = CELL_CASES[1]
    mesh = array_mesh(points, connectivity, code, volume=1.0)
    dfn = surface(triangle, thickness=0.1, conductivity=2.0, porosity=0.5)
    intersections = intersect_surface_with_mesh(dfn, mesh)
    first = upscale_surface_dfn(
        dfn,
        mesh,
        matrix_porosity=0.1,
        matrix_intrinsic_permeability=1.0e-12,
        intersections=intersections,
    )
    second = upscale_surface_dfn(
        dfn,
        mesh,
        matrix_porosity=np.asarray([0.1]),
        matrix_intrinsic_permeability=np.asarray([1.0e-12]),
        intersections=intersections,
    )
    area = intersections.areas[0]
    expected_dfn_phi = area * 0.1 * 0.5
    assert first.dfn_porosity[0] == pytest.approx(expected_dfn_phi)
    assert first.porosity[0] == pytest.approx(0.1 * (1 - expected_dfn_phi) + expected_dfn_phi)
    np.testing.assert_allclose(first.hydraulic_conductivity, first.hydraulic_conductivity.transpose(0, 2, 1))
    assert np.all(np.diagonal(first.hydraulic_conductivity, axis1=1, axis2=2) >= 0)
    conversion = 997.16 * 9.80665 / 8.9e-4
    np.testing.assert_allclose(first.intrinsic_permeability * conversion, first.hydraulic_conductivity)
    np.testing.assert_allclose(first.porosity, second.porosity)
    np.testing.assert_allclose(first.intrinsic_permeability, second.intrinsic_permeability)


def test_additive_combination_preserves_matrix_and_adds_dfn_increments():
    code, points, connectivity, triangle = CELL_CASES[1]
    mesh = array_mesh(points, connectivity, code, volume=1.0)
    dfn = surface(
        triangle,
        thickness=0.1,
        conductivity=2.0,
        porosity=0.5,
        specific_storage=3.0,
    )
    intersections = intersect_surface_with_mesh(dfn, mesh)
    result = upscale_surface_dfn(
        dfn,
        mesh,
        matrix_porosity=0.1,
        matrix_intrinsic_permeability=1.0e-12,
        matrix_specific_storage=4.0e-7,
        intersections=intersections,
        combination_mode="additive",
    )

    assert result.porosity[0] == pytest.approx(
        result.matrix_porosity[0] + result.dfn_porosity[0]
    )
    assert result.specific_storage[0] == pytest.approx(
        result.matrix_specific_storage[0] + result.dfn_specific_storage[0]
    )
    np.testing.assert_allclose(
        result.intrinsic_permeability,
        result.matrix_intrinsic_permeability + result.dfn_intrinsic_permeability,
    )
    assert result.metadata["combination_mode"] == "additive"


def test_vtk_and_hdf5_round_trip(tmp_path: Path):
    code, points, connectivity, triangle = CELL_CASES[1]
    mesh = array_mesh(points, connectivity, code, cell_id=73)
    result = upscale_surface_dfn(
        surface(triangle), mesh, matrix_porosity=0.1, matrix_intrinsic_permeability=1.0e-12
    )
    vtk_path = result.to_vtk(tmp_path / "qa.vtu")
    h5_path = result.to_pflotran_hdf5(tmp_path / "properties.h5")
    vtk = meshio.read(vtk_path)
    assert {"porosity", "permeability_xx", "hydraulic_conductivity_xz"} <= set(vtk.cell_data)
    with h5py.File(h5_path) as data:
        assert data["Cell Ids"][:].tolist() == [73]
        assert set(("Porosity", "PermeabilityX", "PermeabilityXY", "PermeabilityXZ", "PermeabilityY", "PermeabilityYZ", "PermeabilityZ")) <= set(data)
        assert data.attrs["density_kg_m3"] == pytest.approx(997.16)


def test_new_api_through_dfn_upscaler():
    code, points, connectivity, triangle = CELL_CASES[1]
    mesh = array_mesh(points, connectivity, code)
    dfn = DfnPreprocessor()
    dfn.add_surface_network(surface(triangle))
    result = DfnUpscaler(dfn, mesh).upscale(
        matrix_porosity=0.2, matrix_intrinsic_permeability=1.0e-12
    )
    assert result.matrix_porosity.tolist() == [0.2]


def test_arbitrary_polygon_fracture_and_instance_caches():
    triangle = Fracture(
        polygon=np.asarray([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=float),
        aperture=0.01,
        transmissivity=2.5,
        storativity=3.5,
    )
    pentagon = Fracture(
        polygon=np.asarray([[0, 0, 1], [1, 0, 1], [1.5, 0.5, 1], [0.5, 1.5, 1], [-0.5, 0.5, 1]]),
        aperture=0.02,
    )
    assert len(triangle.corner_segments) == 3
    assert len(pentagon.corner_lines) == 5
    assert triangle.area == pytest.approx(0.5)
    assert triangle.transmissivity == 2.5
    assert triangle.storativity == 3.5
    assert triangle.plane is not pentagon.plane
    old_centroid = triangle.plane.p.copy()
    triangle.shift(2, 0, 0)
    assert not np.array_equal(triangle.plane.p, old_centroid)


def test_fault_mesh_only_and_distance_remainder(monkeypatch):
    fault = Fault(
        mesh=meshio.Mesh(
            np.asarray([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=float),
            [("triangle", np.asarray([[0, 1, 2]]))],
        )
    )
    calls = []

    def signed_distance(_mesh, values):
        calls.append(len(values))
        return values[:, 2]

    monkeypatch.setattr("pydelling.preprocessing.dfn_preprocessor.fault.proximity.signed_distance", signed_distance)
    points = np.zeros((2501, 3))
    assert fault.distance(points, n_max=1000).shape == (2501,)
    assert calls == [1000, 1000, 501]


def test_mesh_preprocessor_state_isolation_and_non_contiguous_node_ids():
    first = MeshPreprocessor()
    second = MeshPreprocessor()
    first.add_tetrahedra(
        np.asarray([10, 20, 30, 40]),
        np.asarray([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=float),
    )
    first.add_cell_data("value", np.asarray([4.0]))
    first.convert_mesh_to_meshio()
    assert first.meshio_mesh.points.shape == (4, 3)
    assert not second.cell_data
    first.centroids
    first.add_tetrahedra(
        np.asarray([50, 60, 70, 80]),
        np.asarray([[2, 0, 0], [3, 0, 0], [2, 1, 0], [2, 0, 1]], dtype=float),
    )
    assert len(first.centroids) == 2
