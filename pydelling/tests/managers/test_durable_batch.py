import os
import sys

import h5py
import pytest

from pydelling.managers import LocalExecutor, PflotranManager, PflotranStudy
from pydelling.managers.batch import campaign_lock, check_outputs
from pydelling.readers import PflotranReader


@pytest.fixture
def solver(tmp_path):
    if os.name == "nt":
        pytest.skip("Fake executable uses POSIX shebang; Windows is an SSH client")
    path = tmp_path / "fake-solver"
    path.write_text(
        f"#!{sys.executable}\n"
        + """import os,time,h5py,numpy as np
+mode=os.environ.get('FAKE_MODE','ok')
+if mode=='timeout': time.sleep(20)
+if mode=='fail': raise SystemExit(7)
+with h5py.File('result.h5','w') as f:
+ c=f.create_group('Coordinates')
+ for axis,values in [('X',[0,1,2]),('Y',[0,1]),('Z',[0,1])]: c[axis+' [m]']=values
+ g=f.create_group('Time:  1.00000E+00 d' if mode!='incomplete' else 'Time:  1.00000E+00 s')
+ g['Total_Tracer_c [M]']=np.zeros((2,1,1))
+""".replace("\n+", "\n")
    )
    path.chmod(0o755)
    return str(path)


def setup_manager(tmp_path):
    deck = tmp_path / "template.in"
    deck.write_text("SIMULATION\nEND\nSUBSURFACE\nEND_SUBSURFACE\n")
    manager = PflotranManager()
    for name in ["a", "b"]:
        manager.add_study(PflotranStudy(str(deck), study_name=name))
    requirements = {
        n: {"expected_times": [86400.0], "required_variables": ["Total_Tracer_c [M]"]}
        for n in manager.studies
    }
    return manager, requirements


def test_resume_and_corrupted_output(tmp_path, solver):
    manager, requirements = setup_manager(tmp_path)
    executor = LocalExecutor(solver, workers=2)
    folder = tmp_path / "runs"
    result = manager.run_batch(executor, folder, requirements)
    assert result.successful
    assert manager.run_batch(executor, folder, requirements).states == result.states
    (folder / "a/attempts/0001/result.h5").unlink()
    repeated = manager.run_batch(executor, folder, requirements)
    assert repeated.states["a"]["attempt"] == 2
    assert repeated.states["b"]["attempt"] == 1
    assert (folder / "a/attempts/0001/status.json").exists()
    with pytest.raises(ValueError, match="Incompatible"):
        manager.run_batch(executor, folder, requirements, provenance={"changed": True})


@pytest.mark.parametrize("mode", ["fail", "incomplete", "timeout"])
def test_detect_failures(tmp_path, solver, mode):
    manager, requirements = setup_manager(tmp_path)
    executor = LocalExecutor(
        solver, timeout=0.1 if mode == "timeout" else 10, env={"FAKE_MODE": mode}
    )
    result = manager.run_batch(executor, tmp_path / "runs", requirements)
    assert not result.successful
    assert all(s["state"] == "failed" for s in result.states.values())


def test_lock(tmp_path):
    with (
        campaign_lock(tmp_path),
        pytest.raises(RuntimeError, match="already running"),
        campaign_lock(tmp_path),
    ):
        pass


def test_reader_time_centers_and_close(tmp_path):
    path = tmp_path / "result.h5"
    with h5py.File(path, "w") as f:
        coordinates = f.create_group("Coordinates")
        coordinates["X [m]"] = [0.0, 1.0, 3.0]
        coordinates["Y [m]"] = [0.0, 1.0]
        coordinates["Z [m]"] = [0.0, 1.0]
        f.create_group("Time:  2.00000E+00 d")["Total_Tracer_c [M]"] = [[[1]], [[2]]]
    with PflotranReader(path, variables=["Total_Tracer_c [M]"]) as reader:
        assert reader.times_seconds == [172800.0]
        assert reader.cell_centers["x[m]"].tolist() == [0.5, 2.0]
    assert not reader.data.id.valid
    check_outputs(tmp_path, [172800], ["Total_Tracer_c [M]"])
