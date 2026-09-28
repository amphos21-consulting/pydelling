import json
import os
import subprocess
import sys

import pytest

from pydelling.monitor.config import Host
from pydelling.monitor.supervisor import Supervisor
from pydelling.tests.monitor import fake_ssh
from pydelling.tests.monitor.conftest import wait_until


def campaign_message(folder, **extra):
    return {
        "t": "campaign",
        "folder": folder,
        "name": folder.rsplit("/", 1)[-1],
        "campaign": {"state": "running"},
        "worker": {"pid": 1, "start": "9"},
        "exit": None,
        "config": {"campaign": "c1", "case": "rc1"},
        "preview": {"study_count": 3},
        "cancel_requested": False,
        "alive": True,
        "mtime": 100.0,
        **extra,
    }


def test_apply_maps_watcher_messages_into_registry(project, registry):
    supervisor = Supervisor(project, registry)
    folder = "/r/campaigns/c1"
    supervisor.apply("local", {"t": "hello", "hostname": "box", "cpus": 8})
    supervisor.apply("local", campaign_message(folder))
    run = registry.find_run("local", folder)
    assert run["origin"] == "discovered" and run["status"] == "running"
    assert run["kind"] == "campaign" and run["preview_json"] == {"study_count": 3}
    supervisor.apply(
        "local",
        {"t": "study", "folder": folder, "name": "a", "status": {"state": "running", "attempt": 1}},
    )
    supervisor.apply(
        "local",
        {
            "t": "event",
            "folder": folder,
            "offset": 0,
            "end": 40,
            "event": {
                "ts": 5.0,
                "type": "study.state",
                "study": "a",
                "state": "failed",
                "error": "x",
            },
        },
    )
    supervisor.apply(
        "local",
        {"t": "log", "folder": folder, "offset": 0, "end": 6, "text": "hello\n", "skipped": 0},
    )
    supervisor.apply(
        "local",
        {
            "t": "progress",
            "folder": folder,
            "study": "a",
            "final_time_s": 10.0,
            "sim_time_s": 5.0,
            "dt_s": 1.0,
            "step": 3,
            "cuts": 0,
            "newton": 4,
            "unit": "s",
            "wall_s": None,
            "points": [[5.0, 1.0, 0]],
        },
    )
    supervisor.apply("local", {"t": "heartbeat", "ts": 1.0, "cpus": 8, "load": [1, 1, 1]})
    run = registry.find_run("local", folder)
    assert run["event_offset"] == 40 and run["log_offset"] == 6 and run["log_tail"] == "hello\n"
    study = registry.studies(run["id"])[0]
    assert study["state"] == "running" and study["progress"] == 0.5
    event = registry.events(run["id"])[-1]
    assert event["source"] == "worker" and event["level"] == "error"
    assert event["message"] == "a: failed — x"
    host = registry.get_host("local")
    assert host["stream_state"] == "connected" and host["heartbeat_json"]["cpus"] == 8
    supervisor.apply(
        "local", campaign_message(folder, alive=False, campaign={"state": "completed"})
    )
    run = registry.find_run("local", folder)
    assert run["status"] == "completed" and run["finished_at"] is not None
    assert registry.events(run["id"])[-1]["event_type"] == "run.status"
    assert registry.events(run["id"])[-1]["source"] == "monitor"


def test_apply_keeps_origin_of_existing_runs(project, registry):
    run_id = registry.ensure_run("macario", "/r/campaigns/c1", name="c1", origin="ui")
    Supervisor(project, registry).apply("macario", campaign_message("/r/campaigns/c1"))
    assert registry.get_run(run_id)["origin"] == "ui"


def test_downloaded_copies_fill_history_until_the_host_syncs(project, registry):
    macario = Host(id="macario", ssh="u@h", root="/r")
    supervisor = Supervisor(project, registry, hosts=[macario])
    snapshot = campaign_message(
        "/local/runs/c1",
        alive=False,
        campaign={"state": "completed"},
        mirror={"remote_folder": "/r/campaigns/c1"},
        download=None,
    )
    supervisor.apply("local", snapshot)
    run = registry.find_run("macario", "/r/campaigns/c1")
    assert run["local_folder"] == "/local/runs/c1" and run["status"] == "completed"
    assert registry.find_run("local", "/local/runs/c1") is None
    study = {"t": "study", "folder": "/local/runs/c1", "name": "a"}
    supervisor.apply("local", {**study, "status": {"state": "completed"}})
    assert registry.studies(run["id"])[0]["state"] == "completed"
    supervisor.apply("macario", campaign_message("/r/campaigns/c1", campaign={"state": "running"}))
    supervisor.apply("local", {**study, "status": {"state": "failed"}})
    assert registry.studies(run["id"])[0]["state"] == "completed", "live host data wins"
    assert registry.get_run(run["id"])["status"] == "running"


def test_downloaded_copy_host_comes_from_download_json(project, registry):
    hosts = [Host(id="a", ssh="u@a", root="/r"), Host(id="b", ssh="u@b", root="/r")]
    supervisor = Supervisor(project, registry, hosts=hosts)
    supervisor.apply(
        "local",
        campaign_message(
            "/l/c9",
            alive=False,
            mirror={"remote_folder": "/r/campaigns/c9"},
            download={"host": "u@b"},
        ),
    )
    assert registry.find_run("b", "/r/campaigns/c9") is not None


def write_campaign(root, name="c1", state="completed"):
    folder = root / name
    folder.mkdir(parents=True)
    (folder / "campaign.json").write_text(json.dumps({"state": state}))
    (folder / "events.jsonl").write_text(json.dumps({"ts": 1.0, "type": "batch.started"}) + "\n")
    (folder / "a").mkdir()
    (folder / "a" / "status.json").write_text(json.dumps({"state": "completed"}))
    (folder / "worker.log").write_text("line\n")
    return folder


def test_supervisor_streams_the_local_host(project, registry):
    folder = write_campaign(project.local_runs)
    supervisor = Supervisor(project, registry, interval=0.1)
    supervisor.start()
    try:
        run = wait_until(lambda: registry.find_run("local", str(folder)))
        wait_until(lambda: registry.get_host("local")["stream_state"] == "connected")
        wait_until(lambda: registry.studies(run["id"]))
        assert (
            supervisor.request(
                "local", {"cmd": "tail", "folder": str(folder), "path": "worker.log"}
            )["text"]
            == "line\n"
        )
        (folder / "b").mkdir()
        (folder / "b" / "status.json").write_text(json.dumps({"state": "running"}))
        wait_until(lambda: len(registry.studies(run["id"])) == 2)
    finally:
        supervisor.stop()
    assert registry.get_host("local")["stream_state"] == "offline"


def test_supervisor_resumes_without_duplicates(project, registry):
    folder = write_campaign(project.local_runs)
    for _ in range(2):
        supervisor = Supervisor(project, registry, interval=0.1)
        supervisor.sync_once("local")
    run = registry.find_run("local", str(folder))
    events = registry.events(run["id"])
    assert [e["event_type"] for e in events if e["source"] == "worker"] == ["batch.started"]
    assert [e["message"] for e in events if e["event_type"] == "run.status"] == [
        "unknown → completed"
    ]
    assert registry.get_run(run["id"])["log_tail"] == "line\n"


@pytest.mark.skipif(os.name == "nt", reason="fake ssh uses POSIX sh")
def test_supervisor_reports_auth_required(project, registry, tmp_path, monkeypatch):
    fake_ssh.install(tmp_path, monkeypatch)
    monkeypatch.setenv("FAKE_SSH_DENY", "1")
    host = Host(id="macario", ssh="u@h", root=str(tmp_path / "remote"))
    supervisor = Supervisor(project, registry, hosts=[host], interval=0.1)
    supervisor.start()
    try:
        wait_until(lambda: registry.get_host("macario")["stream_state"] == "auth_required")
        assert "Permission denied" in registry.get_host("macario")["stream_error"]
    finally:
        supervisor.stop()


@pytest.mark.skipif(os.name == "nt", reason="fake ssh uses POSIX sh")
def test_supervisor_streams_over_ssh(project, registry, tmp_path, monkeypatch):
    fake_ssh.install(tmp_path, monkeypatch)
    folder = write_campaign(tmp_path / "remote" / "campaigns")
    host = Host(id="macario", ssh="u@h", root=str(tmp_path / "remote"))
    supervisor = Supervisor(project, registry, hosts=[host], interval=0.1)
    supervisor.start()
    try:
        run = wait_until(lambda: registry.find_run("macario", str(folder)))
        wait_until(lambda: registry.get_run(run["id"])["status"] == "completed")
        reply = supervisor.request(
            "macario", {"cmd": "tail", "folder": str(folder), "path": "worker.log"}
        )
        assert reply["text"] == "line\n"
    finally:
        supervisor.stop()


def test_maintenance_fails_runs_whose_launcher_died(project, registry):
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()
    run_id = registry.ensure_run("local", "/x/c1", name="c1", status="deploying")
    registry.update_run(run_id, launcher_pid=child.pid)
    Supervisor(project, registry).maintain()
    run = registry.get_run(run_id)
    assert run["status"] == "failed" and run["launch_failed"] == 1
    assert registry.events(run_id)[-1]["event_type"] == "launch.lost"


def test_collected_copy_with_only_download_json_maps_to_remote_run(project, registry):
    supervisor = Supervisor(project, registry, hosts=[Host(id="m", ssh="u@h", root="/r")])
    message = campaign_message(
        "/l/job", alive=False, mirror=None, download={"host": "u@h", "folder": "/r/campaigns/job"}
    )
    supervisor.apply("local", message)
    assert registry.find_run("m", "/r/campaigns/job")["local_folder"] == "/l/job"
    assert registry.find_run("local", "/l/job") is None


def test_discovered_runs_take_their_times_from_the_campaign(project, registry):
    supervisor = Supervisor(project, registry)
    message = campaign_message(
        "/r/campaigns/old",
        alive=False,
        campaign={"state": "completed", "started": 1000.0, "finished": 1600.0},
        worker={"pid": 1, "launched": 990.0},
        exit={"returncode": 0, "finished": 1605.0},
    )
    supervisor.apply("local", message)
    run = registry.find_run("local", "/r/campaigns/old")
    assert run["started_at"] == 990.0 and run["finished_at"] == 1605.0


def test_prepared_only_folders_are_marked_prepared(project, registry):
    supervisor = Supervisor(project, registry)
    message = campaign_message(
        "/l/runs/rc1-smoke", alive=False, campaign=None, worker=None, preview={"study_count": 6}
    )
    supervisor.apply("local", message)
    run = registry.find_run("local", "/l/runs/rc1-smoke")
    assert run["status"] == "prepared" and run["finished_at"] is None


def test_downloaded_copies_mark_the_collect_stage_once(project, registry):
    supervisor = Supervisor(project, registry, hosts=[Host(id="m", ssh="u@h", root="/r")])
    message = campaign_message(
        "/l/c1", alive=False, mirror={"remote_folder": "/r/campaigns/c1"}, download={"host": "u@h"}
    )
    supervisor.apply("local", message)
    supervisor.apply("local", message)
    run = registry.find_run("m", "/r/campaigns/c1")
    collected = [e for e in registry.events(run["id"]) if e["event_type"] == "collect.done"]
    assert len(collected) == 1


def test_cursor_messages_advance_the_stored_mtime(project, registry):
    supervisor = Supervisor(project, registry)
    supervisor.apply("local", campaign_message("/r/campaigns/c1", mtime=10.0))
    supervisor.apply("local", {"t": "cursor", "folder": "/r/campaigns/c1", "mtime": 42.0})
    assert registry.known("local")["/r/campaigns/c1"]["mtime"] == 42.0
