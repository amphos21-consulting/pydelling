import json

import meshio
import numpy as np
import pytest

from pydelling.preprocessing import DfnPreprocessor, MeshPreprocessor
from pydelling.preprocessing.dfn_preprocessor import (
    DfnUpscaler,
    resolve_hydraulic_properties,
)


def cube_mesh(node_offset=0, cell_id=0):
    points = np.asarray(
        [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
         [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]], dtype=float
    )
    mesh = MeshPreprocessor()
    mesh.add_hexahedra(np.arange(8) + node_offset, points)
    mesh.elements[0].local_id = cell_id
    return mesh


def central_fracture_dfn():
    dfn = DfnPreprocessor()
    dfn.add_fracture(
        polygon=np.asarray([[0.5, 0, 0], [0.5, 1, 0], [0.5, 1, 1], [0.5, 0, 1]]),
        aperture=0.1,
        transmissivity=0.02,
        storativity=2.0e-6,
    )
    return dfn


def test_object_adapters_preserve_ids_and_triangulate_concave_polygon():
    mesh = cube_mesh(node_offset=10, cell_id=42)
    compact = mesh.to_array_mesh()
    np.testing.assert_array_equal(compact.point_ids, np.arange(10, 18))
    np.testing.assert_array_equal(compact.cell_ids, [42])
    assert compact.connectivity.min() == 0
    assert compact.connectivity.max() == 7

    dfn = DfnPreprocessor()
    polygon = np.asarray(
        [[0.5, 0, 0], [0.5, 1, 0], [0.5, 1, 1], [0.5, 0.5, 0.5], [0.5, 0, 1]],
        dtype=float,
    )
    dfn.add_fracture(polygon=polygon, aperture=0.01, transmissivity=1.0e-4)
    surface = dfn.to_surface_dfn()
    xyz = surface.points[surface.triangles]
    area = 0.5 * np.linalg.norm(
        np.cross(xyz[:, 1] - xyz[:, 0], xyz[:, 2] - xyz[:, 0]), axis=1
    ).sum()
    assert area == pytest.approx(0.75)
    assert set(surface.source_kinds) == {"fracture"}


def test_hydraulic_resolver_cubic_law_and_explicit_precedence():
    dfn = DfnPreprocessor()
    dfn.add_fracture(
        polygon=np.asarray([[0, 0, 0], [1, 0, 0], [0, 1, 0]]),
        aperture=2.0e-4,
    )
    inferred = resolve_hydraulic_properties(dfn[0])
    expected = 997.16 * 9.80665 * (2.0e-4) ** 3 / (12 * 8.9e-4)
    assert inferred.transmissivity == pytest.approx(expected)
    assert inferred.provenance["transmissivity"] == "cubic_law"

    dfn[0]._transmissivity = expected * 2
    explicit = resolve_hydraulic_properties(dfn[0])
    assert explicit.transmissivity == pytest.approx(expected * 2)
    assert explicit.provenance["transmissivity"] == "explicit"
    assert explicit.warnings


def test_default_bulk_engine_is_indexed_lazy_and_queryable():
    dfn = central_fracture_dfn()
    mesh = cube_mesh()
    upscaler = DfnUpscaler(dfn, mesh)
    assert not mesh.elements[0].associated_fractures
    result = upscaler.upscale(
        matrix_porosity=0.2,
        matrix_intrinsic_permeability=1.0e-12,
        matrix_specific_storage=1.0e-6,
        keep_intersections="auto",
    )
    assert result.metadata["intersection_engine"] == "indexed"
    assert result.fracture_area[0] == pytest.approx(1.0)
    assert result.porosity[0] == pytest.approx(0.28)
    assert result.specific_storage[0] == pytest.approx(1.1e-6)
    view = upscaler.intersections_for(dfn[0])
    assert len(view) == 2
    assert view.areas.sum() == pytest.approx(1.0)
    assert upscaler.intersection_index.for_pair(dfn[0], mesh.elements[0]).areas.sum() == pytest.approx(1.0)
    assert not mesh.elements[0].associated_fractures

    upscaler.materialize_legacy_intersections(fractures=[dfn[0]])
    assert mesh.elements[0].associated_fractures[0]["area"] == pytest.approx(1.0)
    assert dfn[0].intersection_dictionary[0] == pytest.approx(1.0)
    upscaler.materialize_legacy_intersections(fractures=[0])
    assert mesh.elements[0].associated_fractures[0]["area"] == pytest.approx(1.0)
    assert upscaler.intersection_index.for_cell(mesh.elements[0]).areas.sum() == pytest.approx(1.0)


def test_object_and_direct_array_workflows_match():
    dfn = central_fracture_dfn()
    mesh = cube_mesh()
    object_result = DfnUpscaler(dfn, mesh).upscale(
        matrix_porosity=0.2,
        matrix_intrinsic_permeability=1.0e-12,
        matrix_specific_storage=1.0e-6,
        keep_intersections=False,
    )
    array_dfn = DfnPreprocessor()
    array_dfn.add_surface_network(dfn.to_surface_dfn())
    array_result = DfnUpscaler(array_dfn, mesh.to_array_mesh()).upscale(
        matrix_porosity=0.2,
        matrix_intrinsic_permeability=1.0e-12,
        matrix_specific_storage=1.0e-6,
    )
    np.testing.assert_allclose(object_result.porosity, array_result.porosity)
    np.testing.assert_allclose(object_result.specific_storage, array_result.specific_storage)
    np.testing.assert_allclose(object_result.hydraulic_conductivity, array_result.hydraulic_conductivity)


def test_faults_join_the_same_surface_with_provenance():
    dfn = central_fracture_dfn()
    fault_mesh = meshio.Mesh(
        points=np.asarray([[0, 0.5, 0], [1, 0.5, 0], [1, 0.5, 1], [0, 0.5, 1]], dtype=float),
        cells=[("triangle", np.asarray([[0, 1, 2], [0, 2, 3]]))],
    )
    dfn.add_fault(mesh=fault_mesh, aperture=0.02, hydraulic_aperture=1.0e-4, storativity=3.0e-6)
    surface = dfn.to_surface_dfn()
    assert set(surface.source_kinds) == {"fracture", "fault"}
    assert {surface.group_names[int(value)] for value in np.unique(surface.group_ids)} == {"fractures", "faults"}
    assert all(json.loads(value)["transmissivity"] in {"explicit", "cubic_law"} for value in surface.property_origins)


def test_storage_is_written_to_hdf5(tmp_path):
    result = DfnUpscaler(central_fracture_dfn(), cube_mesh()).upscale(
        matrix_porosity=0.2,
        matrix_intrinsic_permeability=1.0e-12,
        matrix_specific_storage=1.0e-6,
    )
    path = result.to_pflotran_hdf5(tmp_path / "hybrid.h5")
    import h5py
    with h5py.File(path) as handle:
        np.testing.assert_allclose(handle["Specific Storage"][:], result.specific_storage)
        np.testing.assert_allclose(handle["QA/specific_storage"][:], result.specific_storage)


def test_overlapping_physical_thickness_keeps_fracture_storage_and_clamps_matrix():
    dfn = DfnPreprocessor()
    polygon = np.asarray([[0.5, 0, 0], [0.5, 1, 0], [0.5, 1, 1], [0.5, 0, 1]])
    for _ in range(2):
        dfn.add_fracture(
            polygon=polygon,
            aperture=0.75,
            porosity=0.1,
            transmissivity=0.02,
            storativity=2.0e-6,
        )
    result = DfnUpscaler(dfn, cube_mesh()).upscale(
        matrix_porosity=0.2,
        matrix_intrinsic_permeability=1.0e-12,
        matrix_specific_storage=1.0e-6,
        keep_intersections=False,
    )
    assert result.dfn_specific_storage[0] == pytest.approx(3.0e-6)
    assert result.specific_storage[0] == pytest.approx(3.0e-6)
    assert result.metadata["physical_fraction_clipped_cells"] == 1


def test_adapter_caches_detect_direct_geometry_and_property_changes():
    dfn = central_fracture_dfn()
    first_surface = dfn.to_surface_dfn()
    assert dfn.to_surface_dfn() is first_surface
    dfn[0].aperture = 0.2
    second_surface = dfn.to_surface_dfn()
    assert second_surface is not first_surface
    np.testing.assert_allclose(second_surface.thickness, 0.2)

    mesh = cube_mesh()
    first_mesh = mesh.to_array_mesh()
    assert mesh.to_array_mesh() is first_mesh
    mesh.elements[0].coords[:, 0] *= 2
    second_mesh = mesh.to_array_mesh()
    assert second_mesh is not first_mesh
    assert second_mesh.volumes[0] == pytest.approx(2.0)


def test_invalid_polygon_is_rejected_and_legacy_wrappers_default_to_indexed():
    dfn = DfnPreprocessor()
    dfn.add_fracture(
        polygon=np.asarray([[0.5, 0, 0], [0.5, 1, 1], [0.5, 0, 1], [0.5, 1, 0]]),
        aperture=0.1,
        transmissivity=0.02,
    )
    with pytest.raises(ValueError, match="self-intersecting"):
        dfn.to_surface_dfn()

    upscaler = DfnUpscaler(central_fracture_dfn(), cube_mesh())
    porosity = upscaler.upscale_mesh_porosity(matrix_porosity=0.2, truncate=False)
    assert porosity[0] == pytest.approx(0.28)
    assert upscaler.upscaling_result.metadata["intersection_engine"] == "indexed"
