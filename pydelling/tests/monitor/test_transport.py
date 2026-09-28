import json
import os
import subprocess
import sys

import pytest

from pydelling.monitor.config import Host
from pydelling.monitor.preflight import run_preflight
from pydelling.monitor.transport import (
    classify_ssh_failure,
    make_transport,
    mux_options,
    ssh_options,
)
from pydelling.tests.monitor import fake_ssh

pytestmark = pytest.mark.skipif(os.name == "nt", reason="fake ssh uses POSIX sh")


def ssh_host(tmp_path, **extra):
    return Host(id="remote", transport="ssh", ssh="user@host", root=str(tmp_path / "root"), **extra)


def test_mux_options_are_posix_only_and_respect_overrides(tmp_path):
    (tmp_path / ".ssh").mkdir()
    posix = mux_options([], windows=False, env={}, home=tmp_path)
    assert "ControlMaster=auto" in posix and any("pydelling-%C" in o for o in posix)
    assert mux_options([], windows=True, env={}, home=tmp_path) == []
    assert mux_options([], windows=False, env={"PYDELLING_SSH_MUX": "0"}, home=tmp_path) == []
    custom = ["-o", "ControlPath=/tmp/x"]
    assert mux_options(custom, windows=False, env={}, home=tmp_path) == []
    assert mux_options([], windows=False, env={}, home=tmp_path / "nohome") == []


def test_background_ssh_is_batch_mode_and_quotes_arguments(tmp_path):
    transport = make_transport(ssh_host(tmp_path, ssh_options=["-p", "2222"]))
    argv = transport.argv(["python3", "-c", "print(1)", "/a b/c"])
    assert argv[1:3] == ["-p", "2222"]
    assert "BatchMode=yes" in argv and argv[-2] == "user@host"
    assert argv[-1] == "python3 -c 'print(1)' '/a b/c'"
    interactive = transport.argv(["true"], interactive=True)
    assert "BatchMode=yes" not in interactive
    assert "password" not in " ".join(ssh_options(transport.host)).lower()


@pytest.mark.parametrize(
    ("stderr", "state"),
    [
        ("user@h: Permission denied (publickey,password).", "auth_required"),
        ("ssh: Could not resolve hostname macario: nodename nor servname", "unreachable"),
        ("ssh: connect to host 10.0.0.1 port 22: Operation timed out", "unreachable"),
        ("ssh: connect to host 10.0.0.1 port 22: Connection refused", "unreachable"),
        ("Host key verification failed.", "host_key"),
        ("something else", "error"),
    ],
)
def test_classify_ssh_failure(stderr, state):
    assert classify_ssh_failure(255, stderr)[0] == state


def make_tools(tmp_path):
    uv = tmp_path / "tools" / "uv"
    uv.parent.mkdir()
    uv.write_text("#!/bin/sh\necho 'uv 0.9.0'\n")
    uv.chmod(0o755)
    solver = tmp_path / "tools" / "pflotran"
    solver.write_text("#!/bin/sh\n")
    solver.chmod(0o755)
    database = tmp_path / "tools" / "hanford.dat"
    database.write_text("db")
    return {"uv": str(uv), "executable": str(solver), "database": str(database)}


def test_preflight_on_local_host(tmp_path):
    host = Host(id="local", transport="local", root=str(tmp_path / "runs"), **make_tools(tmp_path))
    seen = []
    result = run_preflight(host, on_check=seen.append)
    statuses = {c["id"]: c["status"] for c in result["checks"]}
    assert result["ok"] and result["state"] == "ok"
    assert statuses["uv"] == statuses["executable"] == statuses["database"] == "ok"
    assert statuses["mpiexec"] == "skip"
    assert [c["id"] for c in seen] == [c["id"] for c in result["checks"]]
    assert (tmp_path / "runs").is_dir()


def test_preflight_reports_missing_solver(tmp_path):
    tools = make_tools(tmp_path)
    tools["executable"] = str(tmp_path / "missing" / "pflotran")
    host = Host(id="local", transport="local", root=str(tmp_path / "runs"), **tools)
    result = run_preflight(host)
    check = next(c for c in result["checks"] if c["id"] == "executable")
    assert not result["ok"] and check["status"] == "fail" and "missing" in check["detail"]


def test_preflight_through_ssh(tmp_path, monkeypatch):
    fake_ssh.install(tmp_path, monkeypatch)
    result = run_preflight(ssh_host(tmp_path, **make_tools(tmp_path)))
    assert result["ok"], result
    assert result["checks"][0]["id"] == "connection"


def test_preflight_auth_failure_is_actionable(tmp_path, monkeypatch):
    fake_ssh.install(tmp_path, monkeypatch)
    monkeypatch.setenv("FAKE_SSH_DENY", "1")
    result = run_preflight(ssh_host(tmp_path))
    assert not result["ok"] and result["state"] == "auth_required"
    assert len(result["checks"]) == 1 and "ssh-key-install" in result["checks"][0]["hint"]


def test_preflight_without_openssh(tmp_path, monkeypatch):
    monkeypatch.setenv("PYDELLING_SSH", str(tmp_path / "no-ssh"))
    result = run_preflight(ssh_host(tmp_path))
    assert not result["ok"] and result["checks"][0]["id"] == "openssh"


def test_watcher_stream_through_ssh(tmp_path, monkeypatch):
    fake_ssh.install(tmp_path, monkeypatch)
    campaign = tmp_path / "root" / "campaigns" / "c1"
    campaign.mkdir(parents=True)
    (campaign / "campaign.json").write_text(json.dumps({"state": "completed"}))
    transport = make_transport(ssh_host(tmp_path))
    process = subprocess.run(
        transport.watcher_argv(),
        input=json.dumps({"roots": [transport.host.campaigns_root], "once": True}) + "\n",
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    messages = [json.loads(line) for line in process.stdout.splitlines()]
    assert [m["name"] for m in messages if m["t"] == "campaign"] == ["c1"]


def test_one_shot_tail_cancel_and_executor(tmp_path, monkeypatch):
    fake_ssh.install(tmp_path, monkeypatch)
    campaign = tmp_path / "root" / "campaigns" / "c1"
    campaign.mkdir(parents=True)
    (campaign / "worker.log").write_text("hello log\n")
    transport = make_transport(ssh_host(tmp_path))
    assert transport.tail(str(campaign), "worker.log") == "hello log\n"
    with pytest.raises(RuntimeError, match="escapes"):
        transport.tail(str(campaign), "../../x")
    transport.cancel(str(campaign))
    assert (campaign / "cancel.request").exists()
    executor = transport.executor()
    assert executor.ssh == os.environ["PYDELLING_SSH"] and "BatchMode=yes" in executor.ssh_options
    assert (
        make_transport(Host(id="local", transport="local", root=str(tmp_path))).executor() is None
    )


def test_local_transport_runs_python3_with_current_interpreter(tmp_path):
    transport = make_transport(Host(id="local", transport="local", root=str(tmp_path)))
    assert transport.argv(["python3", "-c", "x"])[0] == sys.executable
    assert transport.python("import sys; print(sys.argv[1])", "ok").strip() == "ok"


def test_collect_downloads_the_event_log(tmp_path, monkeypatch):
    fake_ssh.install(tmp_path, monkeypatch)
    campaign = tmp_path / "root" / "campaigns" / "c1"
    campaign.mkdir(parents=True)
    (campaign / "events.jsonl").write_text('{"type": "x"}\n')
    (campaign / "secret.key").write_text("no")
    transport = make_transport(ssh_host(tmp_path))
    transport.executor().collect(str(campaign), tmp_path / "local")
    assert (tmp_path / "local" / "events.jsonl").exists()
    assert not (tmp_path / "local" / "secret.key").exists()
