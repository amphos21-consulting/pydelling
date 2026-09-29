"""Monitoring contract of durable batches: event log, cooperative cancel, worker exit."""

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from pydelling.managers import LocalExecutor, PflotranManager, PflotranStudy, SSHExecutor
from pydelling.managers.batch import (
    CANCEL_FILE,
    EVENTS_FILE,
    append_event,
    cancel_requested,
    request_cancel,
)


@pytest.fixture
def solver(tmp_path):
    if os.name == "nt":
        pytest.skip("Fake executable uses POSIX shebang; Windows is an SSH client")
    path = tmp_path / "fake-solver"
    path.write_text(
        f"#!{sys.executable}\n"
        + """import os,time,pathlib,h5py,numpy as np
+pathlib.Path(os.environ['FAKE_MARKER']).joinpath(str(os.getpid())).write_text('ran')
+if os.environ.get('FAKE_MODE')=='sleep': time.sleep(30)
+with h5py.File('result.h5','w') as f:
+ c=f.create_group('Coordinates')
+ for axis,values in [('X',[0,1,2]),('Y',[0,1]),('Z',[0,1])]: c[axis+' [m]']=values
+ g=f.create_group('Time:  1.00000E+00 d')
+ g['Total_Tracer_c [M]']=np.zeros((2,1,1))
+""".replace("\n+", "\n")
    )
    path.chmod(0o755)
    return str(path)


def batch(tmp_path, solver, **env):
    marker = tmp_path / "marker"
    marker.mkdir(exist_ok=True)
    deck = tmp_path / "template.in"
    deck.write_text("SIMULATION\nEND\nSUBSURFACE\nEND_SUBSURFACE\n")
    manager = PflotranManager()
    for name in ["a", "b"]:
        manager.add_study(PflotranStudy(str(deck), study_name=name))
    requirements = {
        n: {"expected_times": [86400.0], "required_variables": ["Total_Tracer_c [M]"]}
        for n in manager.studies
    }
    executor = LocalExecutor(solver, workers=2, env={"FAKE_MARKER": str(marker), **env})
    return manager, executor, requirements, marker


def read_events(folder):
    path = Path(folder) / EVENTS_FILE
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_batch_appends_study_and_batch_events(tmp_path, solver):
    manager, executor, requirements, _ = batch(tmp_path, solver)
    folder = tmp_path / "campaign"
    assert manager.run_batch(executor, folder, requirements, batch_name="training").successful
    events = read_events(folder)
    types = [e["type"] for e in events]
    assert types[0] == "batch.started" and types[-1] == "batch.finished"
    assert events[0]["batch"] == "training" and events[0]["pending"] == 2
    assert events[0]["workers"] == 2
    assert events[-1]["counts"] == {"completed": 2}
    states = sorted((e["study"], e["state"]) for e in events if e["type"] == "study.state")
    assert states == [("a", "completed"), ("a", "running"), ("b", "completed"), ("b", "running")]
    assert all(isinstance(e["ts"], float) for e in events)


def test_cancel_before_start_never_launches_the_solver(tmp_path, solver):
    manager, executor, requirements, marker = batch(tmp_path, solver)
    folder = tmp_path / "campaign"
    request_cancel(folder, origin="test")
    result = manager.run_batch(executor, folder, requirements)
    assert {s["state"] for s in result.states.values()} == {"interrupted"}
    assert not list(marker.iterdir())
    assert "cancel.requested" in [e["type"] for e in read_events(folder)]


def test_cancel_while_running_kills_the_solver(tmp_path, solver):
    manager, executor, requirements, marker = batch(tmp_path, solver, FAKE_MODE="sleep")
    folder = tmp_path / "campaign"
    result = {}
    worker = threading.Thread(
        target=lambda: result.update(r=manager.run_batch(executor, folder, requirements))
    )
    started = time.monotonic()
    worker.start()
    deadline = time.monotonic() + 10
    while len(list(marker.iterdir())) < 2 and time.monotonic() < deadline:
        time.sleep(0.05)
    request_cancel(folder)
    worker.join(timeout=10)
    assert not worker.is_alive()
    assert time.monotonic() - started < 10
    assert {s["state"] for s in result["r"].states.values()} == {"interrupted"}


def test_request_cancel_is_idempotent(tmp_path):
    assert not cancel_requested(tmp_path)
    request_cancel(tmp_path)
    first = (tmp_path / CANCEL_FILE).read_text()
    request_cancel(tmp_path)
    assert cancel_requested(tmp_path)
    assert (tmp_path / CANCEL_FILE).read_text() == first
    assert [e["type"] for e in read_events(tmp_path)] == ["cancel.requested"]


def test_append_event_is_one_json_line_per_call_under_threads(tmp_path):
    threads = [
        threading.Thread(target=lambda i=i: append_event(tmp_path, "x", i=i, blob="y" * 5000))
        for i in range(20)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(e["i"] for e in read_events(tmp_path)) == list(range(20))


def local_python(root):
    """Run SSHExecutor remote snippets locally, mapping the fake remote root."""

    def run(code, *args):
        return subprocess.run(
            [sys.executable, "-c", code, *[a.replace("/remote", str(root)) for a in args]],
            check=True,
            capture_output=True,
            text=True,
        ).stdout

    return run


def test_launch_worker_records_exit_code_and_worker_marker(tmp_path):
    executor = SSHExecutor("user@host", "/remote")
    folder = tmp_path / "campaigns" / "job"
    folder.mkdir(parents=True)
    (folder / CANCEL_FILE).write_text("{}")
    probe = tmp_path / "env.txt"
    argv = [
        sys.executable,
        "-c",
        (
            f"import os,pathlib; pathlib.Path({str(probe)!r}).write_text("
            "os.environ['PYDELLING_RUNS_WORKER']+os.environ['PYDELLING_RUN_FOLDER']); "
            "raise SystemExit(3)"
        ),
    ]
    if not hasattr(os, "fork"):
        pytest.skip("Remote launcher targets POSIX hosts")
    with patch.object(executor, "python", side_effect=local_python(tmp_path)):
        state = executor.launch_worker(str(tmp_path), "/remote/campaigns/job", argv)
    assert state["pid"] > 0
    exit_file = folder / "worker-exit.json"
    deadline = time.monotonic() + 10
    while not exit_file.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    assert json.loads(exit_file.read_text())["returncode"] == 3
    # The worker learns the folder the monitor watches, so its output lands there.
    assert probe.read_text() == "1" + str(tmp_path / "campaigns" / "job")
    assert not (folder / CANCEL_FILE).exists(), "a new launch clears stale cancel requests"


def test_deploy_and_start_report_stages(tmp_path):
    (tmp_path / "source.py").write_text("print(1)\n")
    executor = SSHExecutor("user@host", "/home/user/runs", transfer="tar")
    seen = []
    with (
        patch.object(executor, "command"),
        patch.object(executor, "python"),
        patch.object(executor, "_upload"),
    ):
        executor.deploy(tmp_path, [Path("source.py")], on_event=lambda t, **p: seen.append(t))
    assert seen == ["deploy.hashed", "deploy.uploaded", "deploy.verified", "deploy.synced"]
    with (
        patch.object(executor, "command"),
        patch.object(executor, "python"),
        patch.object(executor, "launch_worker", return_value={"pid": 7, "start": "1"}),
    ):
        executor.start("/r", {"a": 1}, "c1", on_event=lambda t, **p: seen.append((t, p)))
    assert seen[-1] == ("worker.started", {"pid": 7})


def test_ssh_binary_is_configurable():
    executor = SSHExecutor("user@host", "/runs", ssh="/opt/fake-ssh")
    with patch("subprocess.run") as run:
        executor.command(["true"])
    assert run.call_args.args[0][0] == "/opt/fake-ssh"


def test_remote_cancel_writes_request(tmp_path):
    executor = SSHExecutor("user@host", "/remote")
    (tmp_path / "campaigns" / "c1").mkdir(parents=True)
    with patch.object(executor, "python", side_effect=local_python(tmp_path)):
        executor.cancel("/remote/campaigns/c1")
    assert cancel_requested(tmp_path / "campaigns" / "c1")
    assert read_events(tmp_path / "campaigns" / "c1")[0]["type"] == "cancel.requested"


def test_status_reports_worker_exit(tmp_path):
    executor = SSHExecutor("user@host", "/remote")
    folder = tmp_path / "campaigns" / "c1"
    folder.mkdir(parents=True)
    (folder / "worker-exit.json").write_text(json.dumps({"returncode": 2}))
    with patch.object(executor, "python", side_effect=local_python(tmp_path)):
        status = executor.status("/remote/campaigns/c1")
    assert status["worker-exit.json"]["returncode"] == 2


def test_batch_worker_marks_cancelled_campaign(tmp_path, solver, monkeypatch):
    from pydelling.managers import batch_worker

    inputs = tmp_path / "inputs"
    (inputs / "a").mkdir(parents=True)
    (inputs / "a" / "a.in").write_text("SIMULATION\nEND\nSUBSURFACE\nEND_SUBSURFACE\n")
    job = {
        "inputs": str(inputs),
        "studies": [{"name": "a", "input": "a.in", "auxiliary": []}],
        "requirements": {
            "a": {"expected_times": [86400.0], "required_variables": ["Total_Tracer_c [M]"]}
        },
        "executor": {"executable": solver, "env": {"FAKE_MARKER": str(tmp_path)}},
        "provenance": None,
        "resume": True,
        "batch_name": "batch",
    }
    (tmp_path / "job.json").write_text(json.dumps(job))
    folder = tmp_path / "campaign"
    request_cancel(folder)
    monkeypatch.setattr(sys, "argv", ["batch_worker", str(tmp_path / "job.json"), str(folder)])
    batch_worker.main()
    assert json.loads((folder / "campaign.json").read_text())["state"] == "cancelled"
