"""Tutorial 2 — samplers, sensitivity cases and a manager.

1. Describe the uncertain parameters once (``ParameterSpace``).
2. Pick a sampler: ``LHS``, ``Sobol``, ``Random``, ``Grid``, ``Table`` or your own.
3. ``manager.add_studies(sampler, parameters, template)`` draws the samples and adds one
   study per sample. The same sampler on another template is a sensitivity case.
4. Select, inspect and write the studies; run them with ``run_batch``.

    python tutorial_02_samplers_and_sensitivity.py
"""

from pathlib import Path

import numpy as np
from pydelling.managers import (
    LHS,
    Grid,
    ParameterSpace,
    PflotranManager,
    PflotranStudy,
    Sampler,
    Table,
)
from scipy.stats import qmc

TEMPLATE = Path(__file__).with_name("column_template.in")
OUTPUT = Path("studies/tutorial-02")

# 1. Parameters in physical units. Every sample is checked against these ranges.
parameters = ParameterSpace(
    {
        "K": {"bounds": [1e-6, 1e-3], "scale": "log", "units": "m/s"},
        "porosity": {"bounds": [0.1, 0.5], "units": "1"},
    }
)


# One sample -> the values of the template placeholders (<<PERM>>, <<PHI>>).
def to_pflotran(sample: dict[str, float]) -> dict[str, float]:
    return {"PERM": sample["K"] * 1e-3 / (1000 * 9.81), "PHI": sample["porosity"]}


# The template, with the card edits shared by every study.
base = PflotranStudy(str(TEMPLATE), variable_delimiters=("<<", ">>"))
base["TIME/FINAL_TIME"] = [200, "d"]


# 2. Samplers. Your own method is a subclass with one method: n points in the unit cube,
#    one column per parameter; they are mapped through each range and scale for you.
class Halton(Sampler):
    def points(self, dimension: int) -> np.ndarray:
        return qmc.Halton(dimension, seed=self.seed).random(self.n)


# 3. One line per set of studies: sampler, parameters, template.
manager = PflotranManager()
manager.add_studies(LHS(n=8, seed=42), parameters, base, variables=to_pflotran)
manager.add_studies(
    Grid(levels={"K": [1e-5, 1e-4], "porosity": [0.2, 0.4]}), parameters, base, to_pflotran
)
manager.add_studies(Halton(n=8, seed=1), parameters, base, variables=to_pflotran)
manual = Table([{"K": 1e-5, "porosity": 0.2}, {"K": 1e-4, "porosity": 0.3}], name="manual")
manager.add_studies(manual, parameters, base, variables=to_pflotran)

# A sensitivity case: the same sampler (same samples) on another template.
high_dispersion = base.copy()
high_dispersion["MATERIAL_PROPERTY soil/LONGITUDINAL_DISPERSIVITY"] = 2.0
manager.add_studies(
    LHS(n=8, seed=42),
    parameters,
    high_dispersion,
    variables=to_pflotran,
    name="lhs-dispersion",
    metadata={"case": "dispersion"},
)
print(f"{len(manager.studies)} studies: {list(manager.designs)}")

# 4. Every study keeps where it came from; select works on any of those fields.
print(list(manager.select(case="dispersion").studies)[:3])
record = manager.records()[0]
print({key: record[key] for key in ("study_id", "design", "method", "seed", "K")})

# Write the inputs and the samples (replay them later with Table("...csv")).
for name, study in manager.studies.items():
    study.to_file(OUTPUT / name)
for name, samples in manager.designs.items():
    samples.to_csv(OUTPUT / f"samples-{name}.csv")
replay = Table(OUTPUT / "samples-lhs.csv").sample(parameters)
assert replay.samples.equals(manager.designs["lhs"].samples)
print(f"Wrote {len(manager.studies)} studies to {OUTPUT}")

# To run them (needs PFLOTRAN), with durable status, validation and resume:
#
#   from pydelling.managers import LocalExecutor
#   requirements = manager.requirements(["Total_Tracer [M]"])  # times read from each deck
#   result = manager.run_batch(LocalExecutor(executable="pflotran", workers=4),
#                              OUTPUT, requirements)
#   manager.select(case="dispersion").run_batch(...)   # or only one case
