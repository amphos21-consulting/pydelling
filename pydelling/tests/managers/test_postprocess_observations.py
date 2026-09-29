"""``ObservationPoints``: PFLOTRAN observation files as one long table."""

from pathlib import Path

import pytest

from pydelling.managers import PflotranStudy
from pydelling.managers.postprocess import ObservationPoints, PostprocessCallback
from pydelling.managers.postprocess.observations import parse_header, read_observation_files

DECK = """SUBSURFACE
REGION obs_mid
  COORDINATE 5.d0 0.5d0 0.5d0
END
REGION outlet
  COORDINATE 9.975d0 0.5d0 0.5d0
END
OBSERVATION
  REGION obs_mid
END
OBSERVATION
  REGION outlet
END
END_SUBSURFACE
"""


def write_obs(path: Path, header: list[str], rows: list[list[str]]) -> None:
    lines = [",".join(f' "{column}"' for column in header)]
    lines += ["".join(f" {value:>14}" for value in row) for row in rows]
    path.write_text("\n".join(lines) + "\n")


@pytest.fixture
def run(tmp_path: Path) -> Path:
    """A finished run with two MPI ranks, one observation point each."""
    write_obs(
        tmp_path / "model-obs-0.pft",
        [
            "Time [d]",
            "Total_Tracer_c [M] obs_mid (100) (5.0000E+00 5.0000E-01 5.0000E-01)",
            "Liquid Saturation obs_mid (100) (5.0000E+00 5.0000E-01 5.0000E-01)",
        ],
        [["0.000000E+00", "1.000000-100", "1.000000E+00"], ["1.000000E+00", "2.500000E-01", "1.0"]],
    )
    write_obs(
        tmp_path / "model-obs-1.pft",
        ["Time [d]", "4-Total_Tracer_c [M] outlet (200) (9.9750E+00 5.0000E-01 5.0000E-01)"],
        [["0.000000E+00", "0.000000E+00"], ["1.000000E+00", "5.000000E-02"]],
    )
    return tmp_path


def test_headers_give_variable_unit_point_cell_and_coordinates():
    assert parse_header("Total_Tracer_c [M] obs_mid (100) (5.0E+00 5.0E-01 5.0E-01)") == {
        "variable": "Total_Tracer_c",
        "unit": "M",
        "point": "obs_mid",
        "cell": 100,
        "x": 5.0,
        "y": 0.5,
        "z": 0.5,
    }
    assert parse_header("Liquid Saturation obs (3) (1 2 3)")["variable"] == "Liquid Saturation"
    assert parse_header("Liquid Saturation obs (3) (1 2 3)")["unit"] is None
    assert parse_header("12-qlx [m/d] obs (3) (1 2 3)")["variable"] == "qlx"
    assert parse_header("Integral flux") == {"variable": "Integral flux", "unit": None,
                                             "point": None, "cell": None,
                                             "x": None, "y": None, "z": None}


def test_ranks_are_merged_into_one_long_table_in_seconds(run):
    frame = read_observation_files(run)
    assert list(frame.columns) == ["time_s", "point", "cell", "x", "y", "z", "variable", "unit",
                                   "value"]
    assert len(frame) == 2 * 3
    outlet = frame[frame.point == "outlet"]
    assert outlet.time_s.tolist() == [0.0, 86400.0]
    assert outlet.value.tolist() == [0.0, 0.05]
    tiny = frame[(frame.point == "obs_mid") & (frame.variable == "Total_Tracer_c")]
    assert tiny.value.iloc[0] == pytest.approx(1e-100)


def test_variables_and_points_can_be_filtered_with_globs(run, tmp_path):
    study = PflotranStudy.__new__(PflotranStudy)
    frame = ObservationPoints(variables="Total_*", points=["out*"]).process(run, study)
    assert set(frame.point) == {"outlet"} and set(frame.variable) == {"Total_Tracer_c"}


def test_a_missing_variable_or_point_is_an_error(run):
    study = PflotranStudy.__new__(PflotranStudy)
    with pytest.raises(ValueError, match="No observation matches variables"):
        ObservationPoints(variables="Total_Nope").process(run, study)


def test_validation_requires_observation_points(tmp_path):
    deck = tmp_path / "deck.in"
    deck.write_text(DECK)
    study = PflotranStudy(str(deck), study_name="with")
    ObservationPoints(points=["outlet"]).validate(study)
    with pytest.raises(ValueError, match="no observation point matches"):
        ObservationPoints(points=["inlet"]).validate(study)
    deck.write_text("SUBSURFACE\nEND_SUBSURFACE\n")
    with pytest.raises(ValueError, match="no OBSERVATION cards"):
        ObservationPoints().validate(PflotranStudy(str(deck), study_name="without"))


def test_a_run_without_observation_files_is_an_error(tmp_path):
    with pytest.raises(ValueError, match="No PFLOTRAN observation files"):
        read_observation_files(tmp_path)


def test_spec_round_trip():
    callback = ObservationPoints(variables=["Total_*"], points="outlet", name="obs")
    rebuilt = PostprocessCallback.from_spec(callback.spec())
    assert rebuilt.options() == {"variables": ["Total_*"], "points": ["outlet"], "name": "obs"}
