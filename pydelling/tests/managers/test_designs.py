"""Named sample designs and building studies from them with a manager."""

import numpy as np
import pandas as pd
import pytest
from scipy.stats import qmc

from pydelling.managers import (
    LHS,
    Grid,
    ParameterSpace,
    PflotranManager,
    PflotranStudy,
    Random,
    Sampler,
    Sobol,
    Table,
)

SPACE = {
    "K": {"bounds": [1e-6, 1e-3], "scale": "log"},
    "phi": {"bounds": [0.1, 0.5]},
    "alpha": {"fixed": 1.0},
}
TEMPLATE = """\
SUBSURFACE
MATERIAL_PROPERTY soil
  POROSITY <<PHI>>
  PERMEABILITY
    PERM_ISO <<PERM>>
  /
END
TIME
  FINAL_TIME 1.d0 y
END
OUTPUT
  TIMES y 1.
END
END_SUBSURFACE
"""


@pytest.fixture
def template(tmp_path):
    path = tmp_path / "template.in"
    path.write_text(TEMPLATE)
    return PflotranStudy(str(path), study_name="template", variable_delimiters=("<<", ">>"))


# ---------------------------------------------------------------- samplers
def test_sampler_gives_a_named_reproducible_design():
    design = LHS(n=4, seed=42).sample(SPACE)
    assert (design.name, design.method, design.seed, len(design)) == ("lhs", "lhs", 42, 4)
    again = LHS(n=4, seed=42, name="pilot").sample(ParameterSpace(SPACE))
    assert again.name == "pilot"
    pd.testing.assert_frame_equal(design.samples, again.samples)
    rows = list(design)
    assert set(rows[0]) == {"K", "phi", "alpha"} and all(r["alpha"] == 1.0 for r in rows)


def test_samplers_are_interchangeable():
    for sampler in (
        Random(n=4),
        LHS(n=4),
        Sobol(n=4),
        Grid(levels={"K": [1e-5, 1e-4], "phi": [0.2, 0.3]}),
    ):
        design = sampler.sample(SPACE)
        assert len(design) == 4 and design.method == type(sampler).__name__.lower()


def test_lhs_and_sobol_pass_scipy_options():
    a = LHS(n=8, seed=1, scramble=False).sample(SPACE).samples
    b = LHS(n=8, seed=1).sample(SPACE).samples
    assert not a.equals(b)
    assert len(Sobol(n=8, scramble=False).sample(SPACE)) == 8


def test_table_replays_records_frames_and_csv(tmp_path):
    design = Random(n=3, seed=1).sample(SPACE)
    design.to_csv(tmp_path / "pilot.csv")
    for source in (
        list(design),
        design.samples,
        tmp_path / "pilot.csv",
        str(tmp_path / "pilot.csv"),
    ):
        replay = Table(source, name="replay").sample(SPACE)
        pd.testing.assert_frame_equal(replay.samples, design.samples, check_exact=True)
        assert (replay.name, replay.method, replay.seed) == ("replay", "table", None)


def test_table_is_validated_against_the_space():
    with pytest.raises(ValueError, match="outside"):
        Table([{"K": 1.0, "phi": 0.2, "alpha": 1.0}]).sample(SPACE)


@pytest.mark.parametrize("name", ["a b", "../x", "a/b"])
def test_unsafe_names_are_rejected(name):
    with pytest.raises(ValueError, match="name"):
        LHS(n=1, name=name).sample(SPACE)


class Halton(Sampler):
    """A custom method: only points() is needed."""

    def __init__(self, n, seed=0, name=None, scramble=True):
        super().__init__(n, seed, name)
        self.scramble = scramble

    def points(self, dimension):
        return qmc.Halton(dimension, seed=self.seed, scramble=self.scramble).random(self.n)


def test_a_custom_sampler_is_a_small_subclass():
    design = Halton(n=8, seed=3).sample(SPACE)
    assert (design.name, design.method, design.seed, len(design)) == ("halton", "halton", 3, 8)
    # Unit-cube points are mapped through each range and scale; fixed values stay fixed.
    assert design.samples.K.between(1e-6, 1e-3).all() and (design.samples.alpha == 1.0).all()
    pd.testing.assert_frame_equal(design.samples, Halton(n=8, seed=3).sample(SPACE).samples)
    assert not Halton(n=8, scramble=False).sample(SPACE).samples.equals(design.samples)


def test_custom_sampler_output_is_checked():
    class Outside(Sampler):
        def points(self, dimension):
            return np.full((self.n, dimension), 2.0)

    with pytest.raises(ValueError, match="unit cube"):
        Outside(n=2).sample(SPACE)
    with pytest.raises(NotImplementedError):
        Sampler(n=2).sample(SPACE)


# ---------------------------------------------------------------- manager
def to_placeholders(sample):
    return {"PERM": sample["K"] * 1.02e-7, "PHI": sample["phi"]}


def test_add_studies_builds_one_study_per_sample(template):
    manager = PflotranManager()
    studies = manager.add_studies(
        LHS(n=3, seed=7, name="pilot"),
        SPACE,
        template,
        variables=to_placeholders,
        metadata={"kind": "training"},
    )
    assert [s.name for s in studies] == ["pilot-000000", "pilot-000001", "pilot-000002"]
    assert list(manager.studies) == [s.name for s in studies]
    design = manager.designs["pilot"]  # the samples drawn, kept for tables and CSVs
    assert (design.method, design.seed, len(design)) == ("lhs", 7, 3)
    first = studies[0].metadata
    assert list(first)[:4] == ["kind", "design", "method", "seed"]
    assert first["kind"] == "training" and first["phi"] == first["PHI"]
    assert f"POROSITY {first['phi']}" in studies[0].render()
    assert template.jinja_settings == {}  # the template is never modified


def test_zero_samples_add_nothing(template):
    manager = PflotranManager()
    assert manager.add_studies(LHS(n=0), SPACE, template, variables=to_placeholders) == []
    assert not manager.studies and not manager.designs


def test_samples_are_the_variables_by_default(template):
    manager = PflotranManager()
    manager.add_studies(
        Table([{"PERM": 1e-12, "PHI": 0.2}, {"PERM": 1e-12, "PHI": 0.3}]),
        {"PERM": {"fixed": 1e-12}, "PHI": {"values": [0.2, 0.3]}},
        template,
    )
    assert ["POROSITY 0.3" in s.render() for s in manager.studies.values()] == [False, True]


def test_sensitivity_cases_reuse_the_sampler(template):
    """Same sampler and seed on two variants of the template: the same samples twice."""
    long_run = template.copy()
    long_run["TIME/FINAL_TIME"] = [10, "y"]
    sampler = LHS(n=2, seed=1)
    manager = PflotranManager()
    manager.add_studies(sampler, SPACE, template, to_placeholders, metadata={"case": "base"})
    manager.add_studies(
        sampler, SPACE, long_run, to_placeholders, name="lhs-long", metadata={"case": "long"}
    )
    assert list(manager.studies) == [
        "lhs-000000",
        "lhs-000001",
        "lhs-long-000000",
        "lhs-long-000001",
    ]
    assert manager.designs["lhs"].samples.equals(manager.designs["lhs-long"].samples)
    long = manager.select(case="long")
    assert all("FINAL_TIME 10 y" in s.render() for s in long.studies.values())


def test_duplicate_names_are_rejected(template):
    manager = PflotranManager()
    manager.add_studies(LHS(n=1), SPACE, template, to_placeholders)
    with pytest.raises(ValueError, match="lhs"):
        manager.add_studies(LHS(n=1), SPACE, template, to_placeholders)


def test_select_and_records(template):
    manager = PflotranManager()
    benchmark = template.copy("benchmark")
    benchmark.set_variables(PERM=1e-12, PHI=0.3)
    benchmark.metadata = {"kind": "verification"}
    manager.add_study(benchmark)
    twins = Table([{"K": 1e-4, "phi": 0.3, "alpha": 1.0}] * 2, name="twins")
    manager.add_studies(twins, SPACE, template, to_placeholders, metadata={"kind": "training"})

    training = manager.select(kind="training")
    assert isinstance(training, PflotranManager)
    assert list(training.studies) == ["twins-000000", "twins-000001"]
    assert list(training.designs) == ["twins"]
    assert list(manager.select(kind="verification").studies) == ["benchmark"]
    assert manager.studies["twins-000001"].idx == 2  # selecting never renumbers the original

    records = manager.records()
    assert [r["study_id"] for r in records] == ["benchmark", "twins-000000", "twins-000001"]
    keys = list(records[1])
    assert keys[0] == "study_id" and keys[-1] == "simulation_id"
    # Identical inputs share a simulation id, whatever sampler produced them.
    assert records[1]["simulation_id"] == records[2]["simulation_id"]
    assert records[0]["simulation_id"] != records[1]["simulation_id"]


def test_requirements_come_from_the_decks(template):
    template["TIME/FINAL_TIME"] = [2, "d"]
    template.set_output_times([3600, 86400, 172800])
    manager = PflotranManager()
    manager.add_studies(LHS(n=2), SPACE, template, to_placeholders)
    requirements = manager.requirements(["Total_Tracer [M]"])
    assert requirements == {
        name: {
            "expected_times": [3600.0, 86400.0, 172800.0],
            "required_variables": ["Total_Tracer [M]"],
        }
        for name in ("lhs-000000", "lhs-000001")
    }
