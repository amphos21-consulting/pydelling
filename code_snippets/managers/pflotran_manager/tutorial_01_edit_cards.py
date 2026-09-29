"""Tutorial 1 — edit a PFLOTRAN deck like a dict.

A ``PflotranStudy`` maps *card paths* to values. A path is ``/``-separated selectors,
``KEYWORD`` or ``KEYWORD name``: the first is a top-level card (``GRID``, ``TIME``,
``REGION west``…), the rest are direct children. Run from any folder:

    python tutorial_01_edit_cards.py
"""

from pathlib import Path

from pydelling.managers import CardNotFound, PflotranStudy

TEMPLATE = Path(__file__).with_name("column_template.in")

study = PflotranStudy(str(TEMPLATE), study_name="longer-column", variable_delimiters=("<<", ">>"))

# 1. Read: string tokens, exactly as written in the deck.
print(study["GRID/NXYZ"])  # ['100', '1', '1']
print(study["MATERIAL_PROPERTY soil/LONGITUDINAL_DISPERSIVITY"])  # ['0.5d0']
print(study["GRID/BOUNDS"])  # a block gives its rows
print(study["OUTPUT/TIMES"])  # repeated cards give one row each

# 2. Change values. Indentation and comments are kept.
study["MATERIAL_PROPERTY soil/LONGITUDINAL_DISPERSIVITY"] = 1.0
study["TIME/FINAL_TIME"] = [200, "d"]

# 3. Rewrite blocks of rows (coordinates, bounds) in place: a 20 m column.
length = 20.0
study.update(
    {
        "GRID/NXYZ": [200, 1, 1],
        "GRID/BOUNDS": [[0, 0, 0], [length, 1, 1]],
        "REGION all/COORDINATES": [[0, 0, 0], [length, 1, 1]],
        "REGION east/COORDINATES": [[length, 0, 0], [length, 1, 1]],
        "FLOW_CONDITION inlet/LIQUID_PRESSURE": [101325 + 1000 * 9.81 * length, "Pa"],
    }
)

# 4. Repeated cards: a list of rows becomes one card per row.
times = list(range(20, 201, 20))
study["OUTPUT/TIMES"] = [["d", *times[:5]], ["d", *times[5:]]]

# 5. Add and remove. A missing card is appended to its block; None (or del) removes.
study["TIME/INITIAL_TIMESTEP_SIZE"] = [1, "s"]
study["OUTPUT/MASS_BALANCE"] = None
assert "OUTPUT/MASS_BALANCE" not in study

# 6. Mistakes are loud and point to the right path.
try:
    study["MATERIAL_PROPERTY soil/PERM_ISO"] = 1e-12  # PERM_ISO lives in PERMEABILITY
except CardNotFound as error:
    print(error)  # ... found at: MATERIAL_PROPERTY soil/PERMEABILITY/PERM_ISO

# 7. Placeholders are filled at render time; write the study folder.
study.set_variables(PERM=1e-11, PHI=0.3)
study.to_file(Path("studies") / study.name)
print(f"Wrote {Path('studies') / study.name / TEMPLATE.name}")
