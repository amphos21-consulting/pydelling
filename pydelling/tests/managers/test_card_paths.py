"""Dict-like card-path editing of PFLOTRAN studies (``study['GRID/NXYZ'] = ...``)."""

import pytest

from pydelling.managers import CardNotFound, PflotranDeck, PflotranStudy

DECK = """\
SIMULATION
  SIMULATION_TYPE SUBSURFACE
END

SUBSURFACE

GRID
  TYPE STRUCTURED
  NXYZ 10 1 1
  BOUNDS
    0.d0 0.d0 0.d0
    10.d0 1.d0 1.d0
  /
END

MATERIAL_PROPERTY soil
  ID 1
  POROSITY 0.25  # measured
  PERMEABILITY
    PERM_ISO 1.d-12
  /
END

REGION all
  COORDINATES
    0.d0 0.d0 0.d0
    10.d0 1.d0 1.d0
  /
END

REGION west
  FACE WEST
  COORDINATES
    0.d0 0.d0 0.d0
    0.d0 1.d0 1.d0
  /
END

FLOW_CONDITION initial
  TYPE
    LIQUID_PRESSURE HYDROSTATIC
  /
  LIQUID_PRESSURE 101325 Pa
END

CHEMISTRY
  PRIMARY_SPECIES
    Tracer
  /
  OUTPUT
    TOTAL
  /
END

STRATA
  REGION all
  MATERIAL soil
END

TIME
  FINAL_TIME 1.d0 y
END

OUTPUT
  TIMES d 1. 2.
  TIMES d 3. 4.
  FORMAT HDF5
END

END_SUBSURFACE
"""


@pytest.fixture
def study(tmp_path):
    path = tmp_path / "deck.in"
    path.write_text(DECK)
    return PflotranStudy(str(path), study_name="deck")


def deck(study):
    parsed = PflotranDeck(study.raw_text)
    assert parsed.warnings == []
    return parsed


# ---------------------------------------------------------------- reading
def test_read_values(study):
    assert study["GRID/NXYZ"] == ["10", "1", "1"]
    assert study["MATERIAL_PROPERTY soil/PERMEABILITY/PERM_ISO"] == ["1.d-12"]
    assert study["time/final_time"] == ["1.d0", "y"]  # case-insensitive


def test_read_rows_of_blocks_and_repeated_cards(study):
    assert study["GRID/BOUNDS"] == [["0.d0", "0.d0", "0.d0"], ["10.d0", "1.d0", "1.d0"]]
    assert study["OUTPUT/TIMES"] == [["d", "1.", "2."], ["d", "3.", "4."]]


def test_first_selector_is_top_level_and_later_ones_direct_children(study):
    # CHEMISTRY/OUTPUT is nested; the subsurface OUTPUT is the top-level one.
    assert study["OUTPUT/FORMAT"] == ["HDF5"]
    assert study["CHEMISTRY/OUTPUT/TOTAL"] == []
    # The direct child, not TYPE/LIQUID_PRESSURE.
    assert study["FLOW_CONDITION initial/LIQUID_PRESSURE"] == ["101325", "Pa"]
    # A REGION reference inside STRATA is not a top-level REGION block.
    assert study["REGION all/COORDINATES"][1] == ["10.d0", "1.d0", "1.d0"]


def test_contains(study):
    assert "GRID/BOUNDS" in study
    assert "GRID/DXYZ" not in study
    assert "REGION east/COORDINATES" not in study


def test_missing_path_suggests_full_paths(study):
    with pytest.raises(CardNotFound, match="MATERIAL_PROPERTY soil/PERMEABILITY/PERM_ISO"):
        study["PERM_ISO"]
    with pytest.raises(KeyError):
        study["GRID/DXYZ"]


def test_ambiguous_block_must_be_named(study):
    with pytest.raises(CardNotFound, match="REGION all.*REGION west"):
        study["REGION/COORDINATES"]


# ---------------------------------------------------------------- writing
def test_set_values_keeps_indentation_and_comment(study):
    study["MATERIAL_PROPERTY soil/POROSITY"] = 0.3
    study["TIME/FINAL_TIME"] = [1000, "d"]
    assert "  POROSITY 0.3  # measured" in study.raw_text.splitlines()
    assert study["TIME/FINAL_TIME"] == ["1000", "d"]
    deck(study)


def test_set_block_rows_in_place(study):
    study["GRID/BOUNDS"] = [[0, 0, 0], [20.0, 2, 3]]
    study["REGION west/COORDINATES"] = [(0, 0, 0), (0, 2, 3)]
    assert study["GRID/BOUNDS"] == [["0", "0", "0"], ["20.0", "2", "3"]]
    assert study["REGION west/COORDINATES"] == [["0", "0", "0"], ["0", "2", "3"]]
    lines = study.raw_text.splitlines()
    bounds = lines.index("  BOUNDS")
    assert lines[bounds + 1 : bounds + 4] == ["    0 0 0", "    20.0 2 3", "  /"]
    assert study["GRID/NXYZ"] == ["10", "1", "1"]
    deck(study)


def test_rows_replace_all_repeated_cards(study):
    study["OUTPUT/TIMES"] = [["s", 1, 2], ["s", 3], ["s", 4.5]]
    assert study["OUTPUT/TIMES"] == [["s", "1", "2"], ["s", "3"], ["s", "4.5"]]
    assert study["OUTPUT/FORMAT"] == ["HDF5"]
    assert study["CHEMISTRY/OUTPUT/TOTAL"] == []
    deck(study)


def test_single_value_on_repeated_cards_is_ambiguous(study):
    with pytest.raises(ValueError, match="2 cards"):
        study["OUTPUT/TIMES"] = ["s", 1]


def test_flat_values_on_a_block_are_rejected(study):
    with pytest.raises(ValueError, match="rows"):
        study["GRID/BOUNDS"] = [0, 0, 0]


def test_missing_card_is_appended_to_its_block(study):
    study["TIME/MAXIMUM_TIMESTEP_SIZE"] = [1e5, "s"]
    assert study["TIME/MAXIMUM_TIMESTEP_SIZE"] == ["100000.0", "s"]
    assert study.raw_text.splitlines()[study.get_card("TIME").end_line - 1] == (
        "  MAXIMUM_TIMESTEP_SIZE 100000.0 s"
    )
    deck(study)


def test_missing_card_needs_an_existing_parent(study):
    with pytest.raises(CardNotFound):
        study["REGION east/FACE"] = "EAST"


def test_misplaced_card_is_not_appended(study):
    """A keyword that exists deeper is a wrong path, not a new card."""
    with pytest.raises(CardNotFound, match="MATERIAL_PROPERTY soil/PERMEABILITY/PERM_ISO"):
        study["MATERIAL_PROPERTY soil/PERM_ISO"] = 1e-11
    with pytest.raises(
        CardNotFound, match="found at: MATERIAL_PROPERTY soil/PERMEABILITY/PERM_ISO"
    ):
        study["PERM_ISO"] = 1e-11
    assert study["MATERIAL_PROPERTY soil/PERMEABILITY/PERM_ISO"] == ["1.d-12"]


def test_missing_card_with_rows_is_rejected(study):
    with pytest.raises(ValueError, match="does not exist"):
        study["GRID/ORIGIN"] = [[0, 0, 0]]


def test_strings_pass_through(study):
    study["CHEMISTRY/PRIMARY_SPECIES/Tracer"] = []
    study["TIME/FINAL_TIME"] = "5.d0 y"
    assert study["TIME/FINAL_TIME"] == ["5.d0", "y"]


# ---------------------------------------------------------------- removing
def test_delete_card_block_and_repeats(study):
    del study["GRID/BOUNDS"]
    del study["OUTPUT/TIMES"]
    assert "GRID/BOUNDS" not in study and "OUTPUT/TIMES" not in study
    assert study["GRID/NXYZ"] == ["10", "1", "1"]
    deck(study)
    with pytest.raises(KeyError):
        del study["GRID/BOUNDS"]


def test_none_removes_and_is_idempotent(study):
    study["MATERIAL_PROPERTY soil/POROSITY"] = None
    study["MATERIAL_PROPERTY soil/POROSITY"] = None
    assert "MATERIAL_PROPERTY soil/POROSITY" not in study


# ---------------------------------------------------------------- batches & copies
def test_update_applies_in_order(study):
    study.update(
        {
            "GRID/NXYZ": [200, 1, 1],
            "GRID/BOUNDS": [[0, 0, 0], [5, 1, 1]],
            "OUTPUT/TIMES": [["y", 1, 2]],
            "OUTPUT/FORMAT": None,
            "OUTPUT/MASS_BALANCE": [],
        }
    )
    assert study["GRID/NXYZ"] == ["200", "1", "1"]
    assert study["OUTPUT/TIMES"] == ["y", "1", "2"]  # a single card reads as its arguments
    assert "OUTPUT/FORMAT" not in study
    assert study["OUTPUT/MASS_BALANCE"] == []
    deck(study)


def test_edits_on_copies_are_independent(study):
    case = study.copy("case")
    case["GRID/NXYZ"] = [5, 1, 1]
    assert study["GRID/NXYZ"] == ["10", "1", "1"]
    assert case["GRID/NXYZ"] == ["5", "1", "1"]


def test_template_placeholders_survive_edits(tmp_path):
    path = tmp_path / "template.in"
    path.write_text(DECK.replace("POROSITY 0.25", "POROSITY <<PHI>>"))
    template = PflotranStudy(str(path), variable_delimiters=("<<", ">>"))
    template["GRID/NXYZ"] = [20, 1, 1]
    template.set_variables(PHI=0.4)
    assert "POROSITY 0.4" in template.render()


# ---------------------------------------------------------------- output times
def test_output_times_are_read_in_seconds(study):
    assert study.output_times() == [86400.0, 172800.0, 259200.0, 345600.0]
    assert study.output_times(unit="d") == [1.0, 2.0, 3.0, 4.0]


def test_set_output_times_wraps_long_lists(study):
    times = [float(t) for t in range(1, 24)]
    study.set_output_times(times)
    rows = study["OUTPUT/TIMES"]
    assert [len(row) - 1 for row in rows] == [10, 10, 3]
    assert {row[0] for row in rows} == {"s"}
    assert study.output_times() == times
    study.set_output_times([0.5, 1.5], unit="y")
    assert study["OUTPUT/TIMES"] == ["y", "0.5", "1.5"]
    assert study.output_times(unit="y") == [0.5, 1.5]
    deck(study)


def test_output_times_are_sorted_and_unique(study):
    with pytest.raises(ValueError, match="increasing"):
        study.set_output_times([2.0, 1.0])
    with pytest.raises(ValueError, match="unit"):
        study.set_output_times([1.0], unit="fortnight")
