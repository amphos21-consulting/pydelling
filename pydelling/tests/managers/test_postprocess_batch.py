"""Post-processing callbacks inside durable batches: state, events and cheap resume."""

import json
import os
import sys
from pathlib import Path

import pandas as pd
import pytest

from pydelling.managers import LocalExecutor, PflotranManager, PflotranStudy
from pydelling.managers.batch import study_identity
from pydelling.managers.postprocess import (
    Cell,
    Domain,
    ExtractHDF5,
    PostprocessCallback,
)

REQUIREMENT = {"expected_times": [86400.0], "required_variables": ["Total_Tracer_c [M]"]}


class Flaky(PostprocessCallback):
    """Fails while ``flag`` exists; a stand-in for a buggy or unlucky callback."""

    def __init__(self, flag: str, name: str = "flaky") -> None:
        self.flag = flag
        self.name = name

    def options(self) -> dict:
        return {"flag": self.flag, "name": self.name}

    def process(self, workdir: Path, study: PflotranStudy) -> pd.DataFrame:
        if Path(self.flag).exists():
            raise RuntimeError("flag present")
        return pd.DataFrame({"ok": [True]})


@pytest.fixture
def solver(tmp_path: Path) -> str:
    """Fake PFLOTRAN: 3 x 1 x 1 cells, tracer = cell id; counts its runs."""
    if os.name == "nt":
        pytest.skip("Fake executable uses POSIX shebang; Windows is an SSH client")
    path = tmp_path / "fake-solver"
    runs = tmp_path / "solver-runs.txt"
    path.write_text(
        f"#!{sys.executable}\n"
        + f"""import h5py, numpy as np
open({str(runs)!r}, "a").write("run\\n")
with h5py.File("result.h5", "w") as f:
    c = f.create_group("Coordinates")
    c["X [m]"] = [0.0, 1.0, 2.0, 3.0]
    c["Y [m]"] = [0.0, 1.0]
    c["Z [m]"] = [0.0, 1.0]
    f.create_group("Time:  1.00000E+00 d")["Total_Tracer_c [M]"] = np.arange(1.0, 4.0).reshape(3, 1, 1)
"""
    )
    path.chmod(0o755)
    return str(path)


def solver_runs(tmp_path: Path) -> int:
    runs = tmp_path / "solver-runs.txt"
    return len(runs.read_text().splitlines()) if runs.exists() else 0


def make_manager(tmp_path: Path, *callbacks: PostprocessCallback) -> PflotranManager:
    deck = tmp_path / "template.in"
    deck.write_text("SIMULATION\nEND\nSUBSURFACE\nEND_SUBSURFACE\n")
    manager = PflotranManager()
    study = PflotranStudy(str(deck), study_name="a")
    study.add_postprocess(*callbacks)
    manager.add_study(study)
    return manager


def events(folder: Path, kind: str) -> list[dict]:
    lines = (folder / "events.jsonl").read_text().splitlines()
    return [e for e in map(json.loads, lines) if e["type"] == kind]


def test_callbacks_run_after_the_solver_and_are_recorded(tmp_path, solver):
    extract = ExtractHDF5("Total_*", {"last": Cell(x=3.0), "sum": Domain("sum")})
    manager = make_manager(tmp_path, extract)
    folder = tmp_path / "runs"
    result = manager.run_batch(LocalExecutor(solver), folder, {"a": REQUIREMENT})
    assert result.successful
    state = result.states["a"]
    assert state["solver_completed"] and state["postprocess_attempts"] == 1
    record = state["postprocess"]["extractions"]
    assert record["state"] == "completed" and record["rows"] == 2
    table = pd.read_parquet(folder / "a" / state["workdir"] / record["file"])
    assert table.set_index("selection").value.to_dict() == {"last": 3.0, "sum": 6.0}
    [event] = events(folder, "study.postprocess")
    assert event["name"] == "extractions" and event["state"] == "completed"
    # Completed and unchanged: a resume runs nothing.
    again = manager.run_batch(LocalExecutor(solver), folder, {"a": REQUIREMENT})
    assert again.states == result.states and solver_runs(tmp_path) == 1


def test_a_failed_callback_fails_the_study_and_resume_only_reruns_callbacks(tmp_path, solver):
    flag = tmp_path / "broken"
    flag.write_text("")
    manager = make_manager(tmp_path, Flaky(str(flag)))
    folder = tmp_path / "runs"
    failed = manager.run_batch(LocalExecutor(solver), folder, {"a": REQUIREMENT})
    state = failed.states["a"]
    assert state["state"] == "failed" and state["solver_completed"]
    assert state["error"] == "postprocess flaky: RuntimeError: flag present"
    assert "RuntimeError" in (folder / "a" / state["workdir"] / "postprocess.log").read_text()
    assert events(folder, "study.postprocess")[0]["error"] == "RuntimeError: flag present"

    flag.unlink()
    resumed = manager.run_batch(LocalExecutor(solver), folder, {"a": REQUIREMENT})
    state = resumed.states["a"]
    assert state["state"] == "completed" and "error" not in state
    assert state["attempt"] == 1 and state["postprocess_attempts"] == 2
    assert solver_runs(tmp_path) == 1  # PFLOTRAN did not run again
    assert json.loads((folder / "a/status.json").read_text())["state"] == "completed"
    assert events(folder, "batch.started")[-1]["postprocess_only"] == 1


def test_changed_processed_tables_are_rebuilt(tmp_path, solver):
    manager = make_manager(tmp_path, ExtractHDF5("Total_*", {"c": Cell(id=1)}))
    folder = tmp_path / "runs"
    state = manager.run_batch(LocalExecutor(solver), folder, {"a": REQUIREMENT}).states["a"]
    table = folder / "a" / state["workdir"] / "processed/extractions.parquet"
    pd.DataFrame({"tampered": [1]}).to_parquet(table, index=False)
    again = manager.run_batch(LocalExecutor(solver), folder, {"a": REQUIREMENT}).states["a"]
    assert again["postprocess_attempts"] == 2 and solver_runs(tmp_path) == 1
    assert pd.read_parquet(table).value.tolist() == [1.0]


def test_missing_solver_outputs_rerun_the_solver(tmp_path, solver):
    manager = make_manager(tmp_path, ExtractHDF5("Total_*", {"c": Cell(id=1)}))
    folder = tmp_path / "runs"
    manager.run_batch(LocalExecutor(solver), folder, {"a": REQUIREMENT})
    (folder / "a/result.h5").unlink()
    again = manager.run_batch(LocalExecutor(solver), folder, {"a": REQUIREMENT}).states["a"]
    assert again["attempt"] == 2 and again["state"] == "completed"
    assert solver_runs(tmp_path) == 2


def test_studies_without_callbacks_keep_their_identity(tmp_path):
    deck = tmp_path / "template.in"
    deck.write_text("SUBSURFACE\nEND_SUBSURFACE\n")
    study = PflotranStudy(str(deck), study_name="a")
    assert set(study_identity(study)) == {"deck", "files"}
    study.add_postprocess(ExtractHDF5("Total_*", {"c": Cell(id=1)}))
    assert study_identity(study)["postprocess"][0]["options"]["name"] == "extractions"


def test_invalid_callbacks_stop_the_batch_before_running(tmp_path, solver):
    deck = tmp_path / "template.in"
    deck.write_text("SUBSURFACE\nEND_SUBSURFACE\n")
    manager = PflotranManager()
    study = PflotranStudy(str(deck), study_name="a")
    from pydelling.managers.postprocess import ObservationPoints

    study.add_postprocess(ObservationPoints())
    manager.add_study(study)
    with pytest.raises(ValueError, match="a: observations: .* no OBSERVATION cards"):
        manager.run_batch(LocalExecutor(solver), tmp_path / "runs", {"a": REQUIREMENT})
    assert solver_runs(tmp_path) == 0


def test_the_generic_worker_rebuilds_callbacks_from_specs(tmp_path, solver, monkeypatch):
    from pydelling.managers import batch_worker

    inputs = tmp_path / "inputs"
    (inputs / "a").mkdir(parents=True)
    (inputs / "a/model.in").write_text("SIMULATION\nEND\nSUBSURFACE\nEND_SUBSURFACE\n")
    callback = ExtractHDF5("Total_*", {"c": Cell(id=2)})
    job = {
        "studies": [{"name": "a", "input": "model.in", "auxiliary": [],
                     "postprocess": [callback.spec()]}],
        "inputs": str(inputs),
        "requirements": {"a": REQUIREMENT},
        "executor": {"executable": solver},
        "provenance": None,
        "resume": True,
        "batch_name": "batch",
    }
    (tmp_path / "job.json").write_text(json.dumps(job))
    folder = tmp_path / "remote"
    monkeypatch.setattr(sys, "argv", ["worker", str(tmp_path / "job.json"), str(folder)])
    batch_worker.main()
    state = json.loads((folder / "a/status.json").read_text())
    assert state["state"] == "completed" and state["postprocess"]["extractions"]["rows"] == 1
