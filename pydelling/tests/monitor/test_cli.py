import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from pydelling.managers.batch import request_cancel
from pydelling.monitor.demo import create_demo_project, run_campaign
from pydelling.tests.monitor.conftest import wait_until


def cli(project, *args, check=True):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pydelling.monitor",
            args[0],
            "--project",
            str(project.root),
            *args[1:],
        ],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=project.root,
        check=False,
    )
    if check:
        assert result.returncode == 0, result.stdout + result.stderr
    return result


COMMANDS = (
    "ui",
    "demo",
    "list",
    "show",
    "hosts",
    "preflight",
    "launch",
    "cancel",
    "collect",
    "sync",
    "connect",
    "ssh-key-install",
)


@pytest.mark.skipif(os.name == "nt" or not shutil.which("ssh"), reason="requires POSIX SSH")
def test_connect_master_accepts_background_sessions(tmp_path, monkeypatch):
    from pydelling.monitor import __main__ as monitor_cli

    host = SimpleNamespace(id="remote", transport="ssh", ssh="user@localhost", ssh_options=[])
    monkeypatch.setattr(
        monitor_cli, "load_project", lambda root: SimpleNamespace(host=lambda _: host)
    )
    monkeypatch.setattr(monitor_cli, "open_registry", lambda project: None)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    calls = []
    real_run = subprocess.run

    def capture(argv, **kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 1 if "check" in argv else 0)

    monkeypatch.setattr(subprocess, "run", capture)
    assert monitor_cli.main(["connect", "remote"]) == 0
    # Ask OpenSSH to resolve the generated configuration without opening a connection.
    result = real_run(
        [calls[-1][0], "-G", "-F", os.devnull, *calls[-1][1:]],
        capture_output=True,
        text=True,
        check=True,
    )
    config = dict(line.split(" ", 1) for line in result.stdout.splitlines())
    assert config["controlmaster"] == "true", result.stdout


def test_help_lists_commands():
    out = subprocess.run(
        [sys.executable, "-m", "pydelling.monitor", "--help"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    for command in COMMANDS:
        assert command in out


def test_hosts_preflight_and_list(project, registry):
    assert "local" in cli(project, "hosts").stdout
    result = cli(project, "preflight", "local")
    assert "Carpeta de trabajo" in result.stdout and "✓" in result.stdout
    registry.ensure_run("local", str(project.local_runs / "old"), name="old", status="completed")
    listing = cli(project, "list").stdout
    assert "old" in listing and "Completado" in listing


def test_launch_script_sync_and_show(project, registry):
    result = cli(project, "launch", "script", "scripts/job.py", "--host", "local", "--", "0")
    run_id = result.stdout.strip().splitlines()[-1].split()[-1]
    folder = Path(registry.get_run(run_id)["remote_folder"])
    wait_until(lambda: (folder / "worker-exit.json").exists())
    cli(project, "sync", "local")
    shown = cli(project, "show", run_id).stdout
    assert "Completado" in shown and "hello from job 0" in shown


def test_launch_rejects_undeclared_path(project):
    result = cli(project, "launch", "script", "scripts/missing.py", check=False)
    assert result.returncode == 2 and "not declared" in result.stderr


def test_unknown_host_exit_code(project):
    result = cli(project, "preflight", "nope", check=False)
    assert result.returncode == 2


def test_simulated_campaign_outcomes(tmp_path):
    assert run_campaign(tmp_path / "ok", studies=3, workers=2, duration=0.05) == "completed"
    failed = tmp_path / "bad"
    assert (
        run_campaign(failed, studies=3, workers=3, duration=0.05, fail=("pilot-000001",))
        == "failed"
    )
    assert json.loads((failed / "worker-exit.json").read_text())["returncode"] == 1
    cancelled = tmp_path / "cancel"
    thread = threading.Thread(
        target=lambda: run_campaign(cancelled, studies=6, workers=2, duration=3.0)
    )
    thread.start()
    wait_until(lambda: (cancelled / "events.jsonl").exists())
    time.sleep(0.3)
    request_cancel(cancelled)
    thread.join(timeout=20)
    assert json.loads((cancelled / "campaign.json").read_text())["state"] == "cancelled"


def test_demo_project_is_self_contained(tmp_path):
    root, live = create_demo_project(tmp_path / "demo", live_duration=1.0)
    assert (root / "pyproject.toml").exists()
    live.join(timeout=30)
    states = {
        p.name: json.loads((p / "campaign.json").read_text())["state"]
        for p in (root / "runs").iterdir()
        if p.is_dir()
    }
    assert states == {
        "rc1-demo-verificacion": "completed",
        "rc1-demo-barrido": "failed",
        "rc1-demo-en-vivo": "completed",
    }


def test_cleanup_cli_requires_confirmation(project, registry):
    run = registry.ensure_run("local", str(project.local_runs / "old"), status="completed")
    assert cli(project, "delete", run, check=False).returncode == 2
    assert registry.get_run(run)
    cli(project, "delete", run, "--yes")
    assert registry.get_run(run) is None
    registry.ensure_run("local", str(project.local_runs / "other"), status="completed")
    assert cli(project, "clear-history", check=False).returncode == 2
    cli(project, "clear-history", "--yes")
    assert registry.kpis()["total"] == 0


def test_cleanup_cli_reports_preserved_files(project, registry):
    outside = project.root / "external"
    outside.mkdir()
    registry.ensure_run("local", str(outside), status="completed")
    result = cli(project, "clear-history", "--yes", "--files")
    assert "Archivos conservados [local]" in result.stdout
    assert str(outside) in result.stdout
    assert outside.exists() and registry.kpis()["total"] == 0
