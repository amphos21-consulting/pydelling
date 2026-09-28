from __future__ import annotations

from pathlib import Path

from pydelling.assets import AssetSource, load_asset_handle
from pydelling.assets.handlers import (
    PflotranMassBalanceAssetHandle,
    PflotranObservationAssetHandle,
)

OBS_TEXT = (
    '"Time [y]","Liquid Pressure [Pa] well1 (12) (0.5 0.5 0.5)",'
    '"Liquid Pressure [Pa] well2 (44) (1.5 0.5 0.5)",'
    '"Total TracerT [M] well1 (12) (0.5 0.5 0.5)"\n'
    "  0.00000000E+00  1.01325000E+05  1.01330000E+05  1.00000000E-08\n"
    "  1.00000000E+00  1.01425000E+05  1.01435000E+05  2.00000000E-08\n"
)

MAS_TEXT = (
    '"Time [y]","dt_flow [y]","dt_tran [y]","Global Water Mass [kg]",'
    '"Global TracerT [mol]"\n'
    "  1.0E-01  7.4E-04  7.4E-04  7.0E+11  3.4E+10\n"
    "  2.0E-01  7.4E-04  7.4E-04  7.1E+11  3.5E+10\n"
)


def _source(path: Path) -> AssetSource:
    return AssetSource(
        file_name=path.name,
        path=path,
        extension=path.suffix.lstrip("."),
        size_bytes=path.stat().st_size,
    )


def test_observation_tec_detection_is_content_based(tmp_path: Path):
    tec = tmp_path / "case-obs-0.tec"
    tec.write_text(OBS_TEXT)
    assert isinstance(load_asset_handle(_source(tec)), PflotranObservationAssetHandle)

    # Same content under a different extension still detects.
    dat = tmp_path / "points.dat"
    dat.write_text(OBS_TEXT)
    assert isinstance(load_asset_handle(_source(dat)), PflotranObservationAssetHandle)


def test_mass_balance_header_still_wins_over_observation(tmp_path: Path):
    mas = tmp_path / "case-mas.dat"
    mas.write_text(MAS_TEXT)
    handle = load_asset_handle(_source(mas))
    assert isinstance(handle, PflotranMassBalanceAssetHandle)
    assert not isinstance(handle, PflotranObservationAssetHandle)
    # dt_flow + dt_tran are both timestep columns, not mass traces.
    assert handle.timestep_columns == ["dt_flow [y]", "dt_tran [y]"]
    assert handle._mass_columns() == [
        "Global Water Mass [kg]",
        "Global TracerT [mol]",
    ]


def test_comma_delimited_csv_is_not_misdetected(tmp_path: Path):
    csv_file = tmp_path / "series.csv"
    csv_file.write_text('"Time [y]","Value [m]"\n0.0,1.0\n1.0,2.0\n')
    handle = load_asset_handle(_source(csv_file))
    assert not isinstance(handle, PflotranObservationAssetHandle)


def test_observation_preview_plots_per_unit_and_to_dataframe(tmp_path: Path):
    tec = tmp_path / "case-obs-0.tec"
    tec.write_text(OBS_TEXT)
    handle = load_asset_handle(_source(tec))

    schema = handle.schema()
    assert schema["kind"] == "pflotran_observation"
    assert schema["observation_points"] == ["well1", "well2"]
    assert schema["units"] == ["Pa", "M"]
    assert "timestep_column" not in schema

    document = handle.preview_document()
    plotly_sections = [
        section for section in document["sections"] if section["kind"] == "plotly"
    ]
    assert [section["title"] for section in plotly_sections] == [
        "Observations (Pa)",
        "Observations (M)",
    ]
    assert [trace["name"] for trace in plotly_sections[0]["figure"]["data"]] == [
        "Liquid Pressure · well1",
        "Liquid Pressure · well2",
    ]
    point_table = next(
        section
        for section in document["sections"]
        if section.get("title") == "Observation points"
    )
    assert point_table["columns"] == ["point", "unit", "columns"]

    frame = handle.to_dataframe()
    assert frame.shape == (2, 4)
    assert frame.iloc[1]["Time [y]"] == 1.0
