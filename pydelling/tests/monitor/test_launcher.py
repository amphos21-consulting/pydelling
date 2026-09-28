import json
import subprocess
import sys
from pathlib import Path

import pytest

from pydelling.monitor.launcher import (
    cancel_run,
    collect_run,
    launch_entry,
    launch_script,
    spawn_detached,
)
from pydelling.monitor.reporter import Reporter
from pydelling.monitor.supervisor import Supervisor
from pydelling.monitor.watcher_script import process_alive
from pydelling.tests.monitor.conftest import wait_until


def test_spawn_detached_survives_and_logs(tmp_path):
    log = tmp_path / "logs" / "x.log"
    pid = spawn_detached([sys.executable, "-c", "print('detached')"], tmp_path, log)
    wait_until(lambda: log.exists() and "detached" in log.read_text())
    wait_until(lambda: process_alive({"pid": pid}) is False)


def test_launch_entry_spawns_the_declared_command(project, registry):
    run_id = launch_entry(project, registry, "campaign", "cases/alpha.yaml", origin="ui")
    launched = wait_until(
        lambda: (
            (project.root / "launched.json").exists()
            and json.loads((project.root / "launched.json").read_text())
        )
    )
    assert launched["argv"] == ["fake_cli.py", "run", "cases/alpha.yaml"]
    assert launched["origin"] == "ui"
    run = registry.get_run(run_id)
    assert run["remote_folder"] == str(project.local_runs / "alpha")
    assert run["entry_path"] == "cases/alpha.yaml" and run["origin"] == "ui"
    assert run["launcher_pid"] == launched["pid"] and run["status"] == "queued"
    assert run["preview_json"] == {"study_count": 2}
    assert registry.events(run_id)[-1]["event_type"] == "launch.queued"
    again = launch_entry(project, registry, "campaign", "cases/alpha.yaml", action="resume")
    assert again == run_id


@pytest.mark.parametrize("path", ["../pyproject.toml", "fake_cli.py", "cases/missing.yaml"])
def test_launch_entry_rejects_undeclared_paths(project, registry, path):
    with pytest.raises(ValueError):
        launch_entry(project, registry, "campaign", path)
    assert not (project.root / "launched.json").exists()
    assert registry.list_runs() == []


def test_launch_script_locally_records_exit_and_log(project, registry):
    run_id = launch_entry(project, registry, "script", "scripts/job.py", args=["0"], spawn=False)
    launch_script(project, registry, run_id)
    run = registry.get_run(run_id)
    folder = Path(run["remote_folder"])
    wait_until(lambda: (folder / "worker-exit.json").exists())
    Supervisor(project, registry).sync_once("local")
    run = registry.get_run(run_id)
    assert run["status"] == "completed" and run["exit_code"] == 0
    assert "hello from job 0" in run["log_tail"]
    types = [e["event_type"] for e in registry.events(run_id)]
    assert types[:3] == ["launch.queued", "launch.requested", "preflight.started"]
    assert "preflight.check" in types and "worker.started" in types


def test_launch_script_failure_is_failed(project, registry):
    run_id = launch_entry(project, registry, "script", "scripts/job.py", args=["3"], spawn=False)
    launch_script(project, registry, run_id)
    folder = Path(registry.get_run(run_id)["remote_folder"])
    wait_until(lambda: (folder / "worker-exit.json").exists())
    Supervisor(project, registry).sync_once("local")
    run = registry.get_run(run_id)
    assert run["status"] == "failed" and run["exit_code"] == 3


def test_reporter_is_disabled_inside_workers(project, monkeypatch):
    monkeypatch.setenv("PYDELLING_RUNS_WORKER", "1")
    assert Reporter.open(project.root, host_id="local", remote_folder="/x", name="x") is None


def test_reporter_records_stages_and_failures(project, registry):
    reporter = Reporter.open(
        project.root, host_id="local", remote_folder="/x/c", name="c", entry_path="cases/a.yaml"
    )
    reporter.begin("run")
    with reporter.stage("deploy", status="deploying"):
        reporter.on_event("deploy.hashed", files=3)
    with pytest.raises(RuntimeError), reporter.stage("start", status="starting"):
        raise RuntimeError("boom")
    reporter.fail("boom")
    run = registry.get_run(reporter.run_id)
    assert run["status"] == "failed" and run["launch_failed"] == 1 and run["error"] == "boom"
    types = [e["event_type"] for e in registry.events(reporter.run_id)]
    assert types == [
        "launch.requested",
        "deploy.started",
        "deploy.hashed",
        "deploy.done",
        "start.started",
        "start.failed",
        "launch.failed",
    ]
    assert registry.get_run(reporter.run_id)["origin"] == "cli"


def test_cancel_during_client_phase_stops_the_launcher(project, registry):
    sleeper = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    run_id = registry.ensure_run("local", str(project.local_runs / "c1"), name="c1")
    registry.update_run(run_id, status="deploying", launcher_pid=sleeper.pid)
    cancel_run(project, registry, run_id)
    assert sleeper.wait(timeout=10) != 0
    run = registry.get_run(run_id)
    assert run["status"] == "cancelled"


def test_cancel_running_local_run_requests_cooperative_stop(project, registry):
    folder = project.local_runs / "c1"
    folder.mkdir(parents=True)
    run_id = registry.ensure_run("local", str(folder), name="c1", status="running")
    registry.update_run(run_id, worker_alive=1)
    cancel_run(project, registry, run_id)
    assert (folder / "cancel.request").exists()
    assert registry.get_run(run_id)["status"] == "cancelling"


def test_collect_refuses_while_worker_alive(project, registry):
    run_id = registry.ensure_run("macario", "/r/campaigns/c1", name="c1", status="running")
    registry.update_run(run_id, worker_alive=1)
    with pytest.raises(ValueError, match="sigue"):
        collect_run(project, registry, run_id)


def test_a_new_launch_restarts_the_clock(project, registry):
    reporter = Reporter.open(project.root, host_id="local", remote_folder="/x/c", name="c")
    reporter.begin("run")
    reporter.status("running")
    registry.update_run(reporter.run_id, started_at=1.0, status="failed")
    reporter.begin("resume")
    run = registry.get_run(reporter.run_id)
    assert run["started_at"] is None and run["finished_at"] is None
    reporter.status("preflight")
    assert registry.get_run(reporter.run_id)["started_at"] > 1.0
