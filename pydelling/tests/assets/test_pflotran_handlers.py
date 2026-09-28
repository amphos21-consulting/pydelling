from __future__ import annotations

from pathlib import Path

import h5py
import numpy as np

from pydelling.assets import AssetSource, load_asset_handle
from pydelling.assets.pflotran_handlers import (
    PflotranDomainAssetHandle,
    PflotranResultsAssetHandle,
    decode_domain_cells,
)


def _source(path: Path, role: str, **metadata) -> AssetSource:
    return AssetSource(
        file_name=path.name,
        path=path,
        extension=path.suffix.lstrip("."),
        size_bytes=path.stat().st_size if path.is_file() else None,
        metadata={"pflotran_role": role, **metadata},
    )


def test_decode_uniform_hex():
    cells = np.array([9, 0, 1, 2, 3, 4, 5, 6, 7, 9, 8, 9, 10, 11, 12, 13, 14, 15])
    blocks = decode_domain_cells(cells)
    assert set(blocks) == {"hexahedron"}
    assert blocks["hexahedron"].shape == (2, 8)


def test_decode_mixed_topology():
    # one tetra (code 6, 4 nodes) then one hex (code 9, 8 nodes)
    cells = np.array([6, 0, 1, 2, 3, 9, 0, 1, 2, 3, 4, 5, 6, 7])
    blocks = decode_domain_cells(cells)
    assert set(blocks) == {"tetra", "hexahedron"}
    assert blocks["tetra"].shape == (1, 4)
    assert blocks["hexahedron"].shape == (1, 8)


def _write_domain(path: Path) -> None:
    with h5py.File(path, "w") as handle:
        domain = handle.create_group("Domain")
        domain.create_dataset("Vertices", data=np.random.rand(8, 3))
        domain.create_dataset(
            "Cells", data=np.array([9, 0, 1, 2, 3, 4, 5, 6, 7], dtype=np.int64)
        )


def test_domain_handle_describe_and_to_vtk(tmp_path: Path):
    import meshio

    domain = tmp_path / "input_case-domain.h5"
    _write_domain(domain)
    handle = load_asset_handle(_source(domain, "domain_h5"))
    assert isinstance(handle, PflotranDomainAssetHandle)
    schema = handle.schema()
    assert schema["n_vertices"] == 8
    assert schema["n_cells"] == 1
    assert schema["cell_types"] == {"hexahedron": 1}

    out = tmp_path / "domain.vtk"
    handle.to_vtk(out)
    mesh = meshio.read(out)
    assert mesh.points.shape == (8, 3)
    assert sum(len(block.data) for block in mesh.cells) == 1


def test_material_and_boundary_handles(tmp_path: Path):
    mat = tmp_path / "Rock.mat"
    mat.write_text("1\n2\n3\n4\n")
    handle = load_asset_handle(_source(mat, "material_ids"))
    assert handle.schema()["count"] == 4

    ex = tmp_path / "top.ex"
    ex.write_text("CONNECTIONS 2\n1 0 0 1 2.0\n2 1 0 1 3.0\n")
    handle = load_asset_handle(_source(ex, "boundary_ex"))
    assert handle.schema()["face_count"] == 2
    assert handle.schema()["total_area"] == 5.0


def test_bc_dataset_handle(tmp_path: Path):
    bc = tmp_path / "top_pressure_bc.h5"
    with h5py.File(bc, "w") as handle:
        group = handle.create_group("top_pressure_bc_dataset")
        group.create_dataset("Data", data=np.ones((4, 4, 1)) * 5.0)
        group.create_dataset("Times", data=np.array([0.0, 1.0]))
    handle = load_asset_handle(_source(bc, "bc_dataset_h5"))
    schema = handle.schema()
    assert schema["group"] == "top_pressure_bc_dataset"
    assert schema["data_shape"] == [4, 4, 1]
    assert schema["n_times"] == 2


def _write_structured_snapshot(
    path: Path, *, index: int, time: float, pressures: np.ndarray
) -> None:
    """A PFLOTRAN structured HDF5 snapshot: Coordinates + one Time group."""
    with h5py.File(path, "w") as handle:
        coords = handle.create_group("Coordinates")
        coords.create_dataset("X [m]", data=np.array([0.0, 1.0, 2.0, 3.0]))
        coords.create_dataset("Y [m]", data=np.array([0.0, 1.0, 2.0]))
        coords.create_dataset("Z [m]", data=np.array([0.0, 1.0]))
        group = handle.create_group(f"{index} Time {time:.5E} y")
        group.create_dataset("Liquid_Pressure", data=pressures)
        group.create_dataset("Temperature", data=np.zeros_like(pressures))


def test_results_handle_enumerates_and_reads_field(tmp_path: Path):
    for i, t in enumerate((0.0, 10.0)):
        _write_structured_snapshot(
            tmp_path / f"case-{i:03d}.h5",
            index=i,
            time=t,
            pressures=np.arange(6, dtype=float) + i * 100,
        )
    results = tmp_path / "case.h5"  # stem "case" drives the snapshot glob
    handle = load_asset_handle(_source(results, "pflotran_results"))
    assert isinstance(handle, PflotranResultsAssetHandle)

    info = handle.results_info
    assert info["n_timesteps"] == 2
    assert info["times"] == [0.0, 10.0]
    assert "Liquid_Pressure" in info["variables"]

    field = handle.read_field(1, "Liquid_Pressure")
    assert field["time"] == 10.0
    assert field["values"].tolist() == (np.arange(6, dtype=float) + 100).tolist()
    assert field["coordinates"]["x"].tolist() == [0.0, 1.0, 2.0, 3.0]

    # Default variable + bounds errors.
    assert handle.read_field(0)["variable"] == "Liquid_Pressure"
    try:
        handle.read_field(5)
    except IndexError:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected IndexError for out-of-range time_index")


def test_results_handle_prefers_concentration_fields_by_default(tmp_path: Path):
    snapshot = tmp_path / "chemistry-000.h5"
    with h5py.File(snapshot, "w") as handle:
        group = handle.create_group("0 Time 0.00000E+00 y")
        group.create_dataset("Liquid Density [kg_m^3]", data=np.ones(1))
        group.create_dataset("Aqueous Concentration [M]", data=np.ones(1))
        group.create_dataset("Total Tracer [M]", data=np.ones(1))
        group.create_dataset("pH", data=np.ones(1))

    handle = load_asset_handle(_source(tmp_path / "chemistry.h5", "pflotran_results"))
    assert handle.read_field(0)["variable"] == "Aqueous Concentration [M]"


def test_results_handle_prefers_tracer_over_other_molar_fields(tmp_path: Path):
    snapshot = tmp_path / "tracer-000.h5"
    with h5py.File(snapshot, "w") as handle:
        group = handle.create_group("0 Time 0.00000E+00 y")
        group.create_dataset("Liquid Density [kg_m^3]", data=np.ones(1))
        group.create_dataset("Sodium [M]", data=np.ones(1))
        group.create_dataset("Total Tracer [M]", data=np.ones(1))
        group.create_dataset("pH", data=np.ones(1))

    handle = load_asset_handle(_source(tmp_path / "tracer.h5", "pflotran_results"))
    assert handle.read_field(0)["variable"] == "Total Tracer [M]"


def test_results_handle_prefers_molar_fields_over_ph(tmp_path: Path):
    snapshot = tmp_path / "molar-000.h5"
    with h5py.File(snapshot, "w") as handle:
        group = handle.create_group("0 Time 0.00000E+00 y")
        group.create_dataset("Liquid Density [kg_m^3]", data=np.ones(1))
        group.create_dataset("Sodium [M]", data=np.ones(1))
        group.create_dataset("pH", data=np.ones(1))

    handle = load_asset_handle(_source(tmp_path / "molar.h5", "pflotran_results"))
    assert handle.read_field(0)["variable"] == "Sodium [M]"


def test_results_handle_uses_ph_when_no_molar_field_is_available(tmp_path: Path):
    snapshot = tmp_path / "acid-base-000.h5"
    with h5py.File(snapshot, "w") as handle:
        group = handle.create_group("0 Time 0.00000E+00 y")
        group.create_dataset("Liquid Density [kg_m^3]", data=np.ones(1))
        group.create_dataset("pH", data=np.ones(1))

    handle = load_asset_handle(_source(tmp_path / "acid-base.h5", "pflotran_results"))
    assert handle.read_field(0)["variable"] == "pH"


def test_input_handle(tmp_path: Path):
    deck = tmp_path / "input_case.in"
    deck.write_text(
        "SIMULATION\n  SIMULATION_TYPE SUBSURFACE\n/\n"
        "GRID\n  TYPE unstructured_explicit ./m.mesh\nEND\n"
        "MATERIAL_PROPERTY Rock\n  ID 1\nEND\n"
        "TIME\n  FINAL_TIME 100 y\nEND\n"
    )
    handle = load_asset_handle(_source(deck, "input_file"))
    schema = handle.schema()
    assert schema["grid_type"] == "unstructured_explicit"
    assert schema["n_materials"] == 1
    assert schema["final_time"] == 100.0


def _write_xmf(
    path: Path,
    *,
    snapshot_name: str = "case-001.h5",
    domain_name: str = "case-domain.h5",
) -> None:
    path.write_text(
        f"""<?xml version="1.0" ?>
<!DOCTYPE Xdmf SYSTEM "Xdmf.dtd" []>
<Xdmf>
\t<Domain>
\t<Grid Name="Mesh">
\t\t<Time Value = "1.00000E-01" />
\t\t<Topology Type="Mixed" NumberOfElements="2" >
\t\t\t<DataItem Format="HDF" DataType="Int" Dimensions="18">
\t\t\t\t {domain_name}:/Domain/Cells
\t\t\t</DataItem>
\t\t</Topology>
\t\t<Geometry GeometryType="XYZ">
\t\t\t<DataItem Format="HDF" Dimensions="16 3">
\t\t\t\t {domain_name}:/Domain/Vertices
\t\t\t</DataItem>
\t\t</Geometry>
\t\t<Attribute Name="Liquid Pressure [Pa]" AttributeType="Scalar"  Center="Cell">
\t\t\t<DataItem Dimensions="2 1" Format="HDF">
\t\t\t\t{snapshot_name}:/   1 Time  1.00000E-01 y/Liquid Pressure [Pa]
\t\t\t</DataItem>
\t\t</Attribute>
\t\t<Attribute Name="Material ID" AttributeType="Scalar"  Center="Cell">
\t\t\t<DataItem Dimensions="2 1" Format="HDF">
\t\t\t\t{snapshot_name}:/   1 Time  1.00000E-01 y/Material ID
\t\t\t</DataItem>
\t\t</Attribute>
\t</Grid>
\t</Domain>
</Xdmf>"""
    )


def test_xdmf_handle_parses_grid_attributes_and_h5_references(tmp_path: Path):
    from pydelling.assets.pflotran_handlers import PflotranXdmfAssetHandle

    xmf = tmp_path / "case-001.xmf"
    _write_xmf(xmf)
    handle = load_asset_handle(_source(xmf, "output_xmf"))
    assert isinstance(handle, PflotranXdmfAssetHandle)

    schema = handle.schema()
    assert schema["n_cells"] == 2
    assert schema["time"] == 0.1
    assert schema["time_unit"] == "y"
    assert schema["topology_type"] == "Mixed"
    assert schema["geometry_type"] == "XYZ"
    assert schema["n_attributes"] == 2
    assert schema["snapshot_file"] == "case-001.h5"
    assert schema["domain_file"] == "case-domain.h5"

    document = handle.preview_document()
    assert document["warnings"] == []
    assert [section["kind"] for section in document["sections"]] == [
        "table",
        "table",
        "table",
    ]
    attribute_names = [row[0] for row in document["sections"][1]["rows"]]
    assert attribute_names == ["Liquid Pressure [Pa]", "Material ID"]

    flattened = handle._flatten_description()["xdmf"]
    assert flattened["snapshot_file"] == "case-001.h5"
    assert flattened["domain_file"] == "case-domain.h5"
    assert flattened["attributes"] == ["Liquid Pressure [Pa]", "Material ID"]


def test_xdmf_handle_tolerates_malformed_xml(tmp_path: Path):
    xmf = tmp_path / "broken-001.xmf"
    xmf.write_text("<Xdmf><Grid unclosed")
    handle = load_asset_handle(_source(xmf, "output_xmf"))
    document = handle.preview_document()
    assert document["warnings"]
    assert handle.schema()["snapshot_file"] is None


def _write_restart(path: Path) -> None:
    with h5py.File(path, "w") as handle:
        checkpoint = handle.create_group("Checkpoint")
        checkpoint.create_dataset("Revision Number", data=np.array([1], dtype=np.int32))
        flow = checkpoint.create_group("PMCSubsurfaceFlow")
        stepper = flow.create_group("Timestepper")
        stepper.create_dataset("Time", data=np.array([3.15576e7]))
        stepper.create_dataset("Dt", data=np.array([1000.0]))
        stepper.create_dataset("Prev_dt", data=np.array([900.0]))
        stepper.create_dataset("Num_steps", data=np.array([42], dtype=np.int32))
        stepper.create_dataset(
            "Cumulative_newton_iterations", data=np.array([120], dtype=np.int32)
        )
        stepper.create_dataset(
            "Cumulative_linear_iterations", data=np.array([950], dtype=np.int32)
        )
        stepper.create_dataset(
            "Cumulative_time_step_cuts", data=np.array([2], dtype=np.int32)
        )
        variables = flow.create_group("flow")
        variables.create_dataset("Porosity", data=np.ones(6))
        variables.create_dataset("Primary_Variables", data=np.zeros(6))


def test_restart_handle_reports_checkpoint_times_and_variables(tmp_path: Path):
    from pydelling.assets.pflotran_handlers import PflotranRestartAssetHandle

    restart = tmp_path / "case-restart.h5"
    _write_restart(restart)
    handle = load_asset_handle(_source(restart, "restart"))
    assert isinstance(handle, PflotranRestartAssetHandle)

    schema = handle.schema()
    assert schema["revision"] == 1
    assert schema["n_process_models"] == 1
    assert schema["process_models"] == ["PMCSubsurfaceFlow"]
    assert schema["time_seconds"] == 3.15576e7

    document = handle.preview_document()
    assert document["warnings"] == []
    kinds = [section["kind"] for section in document["sections"]]
    assert kinds == ["table", "hdf5"]
    model = handle.preview_metadata()["pflotran_restart"]["process_models"][0]
    assert model["num_steps"] == 42
    assert model["n_variables"] == 2
    assert "t=3.156e+07 s" in handle.summary_text()


def test_restart_handle_warns_on_non_checkpoint_h5(tmp_path: Path):
    plain = tmp_path / "not-a-restart.h5"
    with h5py.File(plain, "w") as handle:
        handle.create_dataset("Data", data=np.ones((2, 2)))
    handle = load_asset_handle(_source(plain, "restart"))
    document = handle.preview_document()
    assert any("Checkpoint" in warning for warning in document["warnings"])
    assert handle.schema()["n_process_models"] == 0


def test_results_handle_surfaces_unreadable_snapshots(tmp_path: Path):
    _write_structured_snapshot(
        tmp_path / "case-000.h5", index=0, time=0.0, pressures=np.arange(6, dtype=float)
    )
    (tmp_path / "case-001.h5").write_text("this is not an HDF5 file")
    handle = load_asset_handle(_source(tmp_path / "case.h5", "pflotran_results"))

    info = handle.results_info
    assert info["n_timesteps"] == 1
    assert len(info["skipped"]) == 1
    assert info["skipped"][0]["file"] == "case-001.h5"

    document = handle.preview_document()
    assert any("case-001.h5" in warning for warning in document["warnings"])
    warning_sections = [
        section for section in document["sections"] if section.get("title") == "Warnings"
    ]
    assert warning_sections and "case-001.h5" in warning_sections[0]["lines"][0]
    assert "1 unreadable" in handle.summary_text()


def test_pflotran_handle_for_role_maps_new_roles():
    from pydelling.assets.pflotran_handlers import (
        PflotranRestartAssetHandle,
        PflotranXdmfAssetHandle,
        pflotran_handle_for_role,
    )
    from pydelling.assets.handlers import PflotranObservationAssetHandle

    assert pflotran_handle_for_role("output_xmf", {}) is PflotranXdmfAssetHandle
    assert pflotran_handle_for_role("restart", {}) is PflotranRestartAssetHandle
    assert pflotran_handle_for_role("observation", {}) is PflotranObservationAssetHandle


def _write_structured_single_file(path: Path) -> None:
    """Structured-grid output: one file, all timesteps, plus Coordinates."""
    with h5py.File(path, "w") as handle:
        coords = handle.create_group("Coordinates")
        coords.create_dataset("X [m]", data=np.linspace(0.0, 4.0, 5))
        coords.create_dataset("Y [m]", data=np.array([0.0, 1.0]))
        coords.create_dataset("Z [m]", data=np.array([0.0, 1.0]))
        handle.create_group("Provenance")
        # Deliberately exponent-misordered names: alphabetical order would put
        # 5.18400E+03 before 8.64000E+02.
        for time in (0.0, 8.64000e2, 5.18400e3):
            group = handle.create_group(f"Time:  {time:.5E} s")
            group.create_dataset(
                "Liquid_Pressure [Pa]", data=np.full((4, 1, 1), 1.0e5 + time)
            )
            group.create_dataset("Material_ID", data=np.ones((4, 1, 1), dtype="i4"))


def test_results_handle_reads_structured_single_file(tmp_path: Path):
    single = tmp_path / "infiltration1d.h5"
    _write_structured_single_file(single)
    handle = load_asset_handle(_source(single, "output_snapshot", single_file=True))
    assert isinstance(handle, PflotranResultsAssetHandle)

    info = handle.results_info
    assert info["n_timesteps"] == 3
    assert info["times"] == [0.0, 864.0, 5184.0]  # chronological, not alphabetical
    assert info["timesteps"][0]["time_unit"] == "s"
    assert "Liquid_Pressure [Pa]" in info["variables"]

    field = handle.read_field(2, "Liquid_Pressure [Pa]")
    assert field["time"] == 5184.0
    assert field["values"].tolist() == [1.0e5 + 5184.0] * 4
    assert field["coordinates"]["x"].tolist() == [0.0, 1.0, 2.0, 3.0, 4.0]

    # Per-file snapshots still enumerate exactly as before.
    _write_structured_snapshot(
        tmp_path / "case-000.h5", index=0, time=0.0, pressures=np.arange(6, dtype=float)
    )
    multi = load_asset_handle(_source(tmp_path / "case.h5", "pflotran_results"))
    assert multi.results_info["n_timesteps"] == 1
