"""The remote watcher is executed exactly as on a host: ``python -c <source>``."""

import ast
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from pydelling.managers.batch import campaign_lock
from pydelling.monitor import watcher_script
from pydelling.monitor.watcher_script import (
    final_time_seconds,
    lock_held,
    parse_progress,
    process_alive,
)

FIXTURE = Path(__file__).with_name("pflotran_rc1_stdout.txt")
SOURCE = Path(watcher_script.__file__).read_text()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def make_campaign(root, name="c1", *, running=True):
    folder = root / name
    write_json(folder / "campaign.json", {"state": "running" if running else "completed"})
    write_json(folder / "config.json", {"campaign": name, "case": "rc1", "big": "x" * 5000})
    write_json(folder / "worker.json", {"pid": os.getpid(), "start": None})
    work = folder / "a" / "attempts" / "0001"
    work.mkdir(parents=True)
    (work / "model.in").write_text("TIME\n  FINAL_TIME 1.d5 s # end\nEND\n")
    (work / "stdout.log").write_text(
        " Step      1 Time=  1.00000E+00 Dt=  1.00000E+00 [s] conv_reason: 2\n"
        "  newton =   1 [       1] linear =     1 [         1] cuts =  0 [   0]\n"
    )
    write_json(
        folder / "a" / "status.json",
        {
            "state": "running",
            "attempt": 1,
            "workdir": "attempts/0001",
            "command": ["pflotran", "-pflotranin", "model.in"],
        },
    )
    write_json(folder / "b" / "status.json", {"state": "pending"})
    lines = [{"ts": 1.0, "type": "batch.started"}, {"ts": 2.0, "type": "study.state"}]
    (folder / "events.jsonl").write_text("".join(json.dumps(x) + "\n" for x in lines))
    (folder / "worker.log").write_text("worker says hi\n")
    return folder


class Stream:
    """A watcher subprocess with an NDJSON reader thread."""

    def __init__(self, init):
        self.process = subprocess.Popen(
            [sys.executable, "-u", "-c", SOURCE],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.messages = []
        self.process.stdin.write(json.dumps(init) + "\n")
        self.process.stdin.flush()
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self):
        for line in self.process.stdout:
            self.messages.append(json.loads(line))

    def send(self, command):
        self.process.stdin.write(json.dumps(command) + "\n")
        self.process.stdin.flush()

    def wait_for(self, predicate, timeout=10):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            found = [m for m in list(self.messages) if predicate(m)]
            if found:
                return found[-1]
            time.sleep(0.02)
        raise AssertionError(f"Timed out; got {[m['t'] for m in self.messages]}")

    def close(self):
        self.process.stdin.close()
        assert self.process.wait(timeout=10) == 0, self.process.stderr.read()


def run_once(init):
    result = subprocess.run(
        [sys.executable, "-u", "-c", SOURCE],
        input=json.dumps({**init, "once": True}) + "\n",
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    return [json.loads(line) for line in result.stdout.splitlines()]


def test_parse_progress_on_real_rc1_output():
    state = {}
    points = parse_progress(FIXTURE.read_text().splitlines(), state)
    assert state["step"] == 951
    assert state["sim_time_s"] == pytest.approx(8.64e7)
    assert state["dt_s"] == pytest.approx(2e4)
    assert state["newton_by"] == {"RICHARDS FLOW": 944, "REACTIVE TRANSPORT": 988}
    assert state["newton"] == 944 + 988
    assert state["cuts"] == 0
    assert state["wall_s"] == pytest.approx(0.43836)
    times = [p[0] for p in points]
    assert times == sorted(set(times)), "coupled FLOW/TRAN steps must not duplicate points"


def test_parse_progress_units_and_cut_markers():
    state = {}
    lines = [
        "== REACTIVE TRANSPORT ======",
        " Step      1 Time=  1.00000D+00 Dt=  1.00000E+00 [d] conv_reason: 2",
        "  newton =   3 [       3] linear =     1 [         1] cuts =  2 [   2]",
        " Step      2 Time=  5.00000E-01 Dt=  1.00000E-01 [y] conv_reason: 2",
        "  newton =   1 [       4] linear =     1 [         2] cuts =  0 [   2]",
    ]
    points = parse_progress(lines, state)
    assert points[0][:2] == [86400.0, 86400.0]
    assert points[1][0] == pytest.approx(0.5 * 31557600)
    assert state["cuts"] == 2 and state["unit"] == "y"
    assert parse_progress(["garbage", ""], state) == []


def test_final_time_seconds():
    assert final_time_seconds("TIME\n  FINAL_TIME 1000 d\nEND") == 86400000
    assert final_time_seconds("  FINAL_TIME 1.d5 s # comment") == 1e5
    assert final_time_seconds("# FINAL_TIME 3 y\n  FINAL_TIME 2 y") == 2 * 31557600
    assert final_time_seconds("TIME\nEND") is None


def test_liveness_helpers(tmp_path):
    assert process_alive({"pid": os.getpid()}) is True
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()
    assert process_alive({"pid": child.pid}) is False
    assert process_alive({}) is None
    assert lock_held(tmp_path) is False
    with campaign_lock(tmp_path):
        assert lock_held(tmp_path) is True
    assert lock_held(tmp_path) is False


def test_snapshot_reports_campaign_studies_events_log_and_progress(tmp_path):
    folder = make_campaign(tmp_path)
    messages = run_once({"roots": [str(tmp_path)]})
    kinds = [m["t"] for m in messages]
    assert kinds[0] == "hello"
    campaign = next(m for m in messages if m["t"] == "campaign")
    assert campaign["folder"] == str(folder) and campaign["name"] == "c1"
    assert campaign["alive"] is True and campaign["campaign"]["state"] == "running"
    assert campaign["config"] == {"campaign": "c1", "case": "rc1"}
    studies = {m["name"]: m["status"]["state"] for m in messages if m["t"] == "study"}
    assert studies == {"a": "running", "b": "pending"}
    events = [m for m in messages if m["t"] == "event"]
    assert [e["event"]["type"] for e in events] == ["batch.started", "study.state"]
    assert events[1]["offset"] == len(json.dumps({"ts": 1.0, "type": "batch.started"})) + 1
    assert next(m for m in messages if m["t"] == "log")["text"] == "worker says hi\n"
    progress = next(m for m in messages if m["t"] == "progress")
    assert progress["study"] == "a"
    assert progress["final_time_s"] == 1e5 and progress["sim_time_s"] == 1.0
    assert progress["points"] == [[1.0, 1.0, 0]]
    heartbeat = next(m for m in messages if m["t"] == "heartbeat")
    assert heartbeat["cpus"] >= 1 and heartbeat["disk_total"] > 0


def test_known_state_suppresses_replay(tmp_path):
    folder = make_campaign(tmp_path)
    known = {
        str(folder): {
            "mtime": time.time() + 60,
            "event_offset": (folder / "events.jsonl").stat().st_size,
            "log_offset": (folder / "worker.log").stat().st_size,
        }
    }
    kinds = [m["t"] for m in run_once({"roots": [str(tmp_path)], "known": known})]
    assert "campaign" in kinds
    assert not {"study", "event", "log"} & set(kinds)


def test_live_changes_are_streamed(tmp_path):
    folder = make_campaign(tmp_path)
    stream = Stream({"roots": [str(tmp_path)], "interval": 0.1})
    try:
        stream.wait_for(lambda m: m["t"] == "progress")
        with (folder / "events.jsonl").open("a") as log:
            log.write(json.dumps({"ts": 3.0, "type": "cancel.requested"}) + "\n")
        stream.wait_for(lambda m: m["t"] == "event" and m["event"]["type"] == "cancel.requested")
        with (folder / "a/attempts/0001/stdout.log").open("a") as out:
            out.write(" Step      2 Time=  5.00000E+04 Dt=  4.00000E+04 [s] conv_reason: 2\n")
        live = stream.wait_for(lambda m: m["t"] == "progress" and m["sim_time_s"] == 5e4)
        assert live["points"] == [[5e4, 4e4, 0]]
        time.sleep(0.05)
        write_json(folder / "a" / "status.json", {"state": "completed", "workdir": "attempts/0001"})
        stream.wait_for(lambda m: m["t"] == "study" and m["status"]["state"] == "completed")
        (folder / "late").mkdir()
        write_json(folder / "late" / "status.json", {"state": "pending"})
        stream.wait_for(lambda m: m["t"] == "study" and m["name"] == "late")
        make_campaign(tmp_path, "c2")
        stream.wait_for(lambda m: m["t"] == "campaign" and m["name"] == "c2")
    finally:
        stream.close()


def test_tail_command_is_confined_to_campaign(tmp_path):
    folder = make_campaign(tmp_path)
    (tmp_path / "secret.txt").write_text("nope")
    stream = Stream({"roots": [str(folder.parent)], "interval": 0.1})
    try:
        stream.wait_for(lambda m: m["t"] == "campaign")
        cases = {
            "ok": ("a/attempts/0001/stdout.log", True),
            "up": ("../secret.txt", False),
            "abs": (str(tmp_path / "secret.txt"), False),
        }
        for key, (path, _) in cases.items():
            stream.send({"id": key, "cmd": "tail", "folder": str(folder), "path": path})
        stream.send({"id": "out", "cmd": "tail", "folder": str(tmp_path), "path": "secret.txt"})
        replies = {
            key: stream.wait_for(lambda m, k=key: m["t"] == "reply" and m["id"] == k)
            for key in [*cases, "out"]
        }
    finally:
        stream.close()
    assert replies["ok"]["ok"] and "Step      1" in replies["ok"]["text"]
    for key in ("up", "abs", "out"):
        assert not replies[key]["ok"] and "nope" not in json.dumps(replies[key])


def test_cancel_command_writes_request(tmp_path):
    folder = make_campaign(tmp_path)
    stream = Stream({"roots": [str(tmp_path)], "interval": 0.1})
    try:
        stream.wait_for(lambda m: m["t"] == "campaign")
        stream.send({"id": 1, "cmd": "cancel", "folder": str(folder)})
        assert stream.wait_for(lambda m: m["t"] == "reply")["ok"]
        stream.wait_for(lambda m: m["t"] == "campaign" and m["cancel_requested"])
    finally:
        stream.close()
    assert (folder / "cancel.request").exists()


def test_malformed_status_is_reported_not_fatal(tmp_path):
    folder = make_campaign(tmp_path)
    (folder / "b" / "status.json").write_text("{broken")
    messages = run_once({"roots": [str(tmp_path)]})
    assert any(m["t"] == "warning" and "b/status.json" in m["path"] for m in messages)
    assert any(m["t"] == "study" and m["name"] == "a" for m in messages)


def test_worker_exit_and_mirrors(tmp_path):
    folder = make_campaign(tmp_path)
    time.sleep(0.01)
    write_json(folder / "worker-exit.json", {"returncode": 4})
    mirror = tmp_path / "downloaded"
    write_json(
        mirror / "remote.json", {"remote_folder": "/r/campaigns/downloaded", "pid": os.getpid()}
    )
    write_json(mirror / "download.json", {"host": "u@h"})
    write_json(mirror / "campaign.json", {"state": "completed"})
    write_json(mirror / "worker.json", {"pid": os.getpid()})
    messages = run_once({"roots": [str(tmp_path)]})
    campaign = next(m for m in messages if m["t"] == "campaign" and m["name"] == "c1")
    assert campaign["alive"] is False and campaign["exit"]["returncode"] == 4
    assert campaign["mirror"] is None
    snapshot = next(m for m in messages if m["t"] == "campaign" and m["name"] == "downloaded")
    assert snapshot["mirror"]["remote_folder"] == "/r/campaigns/downloaded"
    assert snapshot["download"] == {"host": "u@h"}
    assert snapshot["alive"] is False, "a downloaded copy never reports a live local pid"


def test_missing_root_is_not_fatal(tmp_path):
    messages = run_once({"roots": [str(tmp_path / "absent")]})
    assert messages[0]["t"] == "hello"


def test_source_is_small_and_stdlib_only():
    assert len(SOURCE) < 24000
    stdlib = set(sys.stdlib_module_names)
    for node in ast.walk(ast.parse(SOURCE)):
        if isinstance(node, ast.Import):
            assert all(alias.name.split(".")[0] in stdlib for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0 and node.module.split(".")[0] in stdlib


def test_event_and_log_messages_carry_end_offsets(tmp_path):
    folder = make_campaign(tmp_path)
    messages = run_once({"roots": [str(tmp_path)]})
    events = [m for m in messages if m["t"] == "event"]
    assert events[0]["end"] == events[1]["offset"]
    assert events[-1]["end"] == (folder / "events.jsonl").stat().st_size
    log = next(m for m in messages if m["t"] == "log")
    assert log["end"] == (folder / "worker.log").stat().st_size


def test_broken_campaign_file_warns_once(tmp_path):
    folder = make_campaign(tmp_path)
    (folder / "campaign.json").write_text("{nope")
    stream = Stream({"roots": [str(tmp_path)], "interval": 0.05})
    try:
        stream.wait_for(lambda m: m["t"] == "campaign")
        time.sleep(0.5)
    finally:
        stream.close()
    warnings = [m for m in stream.messages if m["t"] == "warning"]
    assert len(warnings) == 1 and warnings[0]["path"] == "campaign.json"


def test_download_json_alone_marks_a_copy(tmp_path):
    copy = tmp_path / "collected"
    write_json(copy / "download.json", {"host": "u@h", "folder": "/r/campaigns/collected"})
    write_json(copy / "worker.json", {"pid": os.getpid()})
    messages = run_once({"roots": [str(tmp_path)]})
    snapshot = next(m for m in messages if m["t"] == "campaign")
    assert snapshot["alive"] is False and snapshot["mirror"] is None
    assert snapshot["download"]["folder"] == "/r/campaigns/collected"


def test_convergence_summary_of_a_finished_study():
    from pydelling.monitor.watcher_script import convergence

    folder = FIXTURE.parent / "_tmp_convergence"
    try:
        work = folder / "attempts" / "0001"
        work.mkdir(parents=True, exist_ok=True)
        (work / "stdout.log").write_text(FIXTURE.read_text())
        (work / "model.in").write_text("TIME\n  FINAL_TIME 86400000.0 s\nEND\n")
        summary = convergence(str(work), "model.in")
    finally:
        import shutil

        shutil.rmtree(folder, ignore_errors=True)
    assert summary["step"] == 951 and summary["final_time_s"] == 86400000.0
    assert summary["sim_time_s"] == pytest.approx(8.64e7) and summary["cuts"] == 0
    assert 2 <= len(summary["points"]) <= 256


def test_convergence_command_is_confined(tmp_path):
    folder = make_campaign(tmp_path)
    stream = Stream({"roots": [str(tmp_path)], "interval": 0.1})
    try:
        stream.wait_for(lambda m: m["t"] == "campaign")
        stream.send(
            {"id": "ok", "cmd": "convergence", "folder": str(folder), "path": "a/attempts/0001"}
        )
        stream.send({"id": "bad", "cmd": "convergence", "folder": str(folder), "path": "../.."})
        ok = stream.wait_for(lambda m: m["t"] == "reply" and m["id"] == "ok")
        bad = stream.wait_for(lambda m: m["t"] == "reply" and m["id"] == "bad")
    finally:
        stream.close()
    assert ok["ok"] and ok["summary"]["step"] == 1 and ok["summary"]["final_time_s"] == 1e5
    assert not bad["ok"]


def test_huge_single_line_log_still_sends_its_tail(tmp_path):
    folder = make_campaign(tmp_path)
    (folder / "worker.log").write_text("x" * 100000 + "END\n")
    log = next(m for m in run_once({"roots": [str(tmp_path)]}) if m["t"] == "log")
    assert log["text"].endswith("END\n") and log["skipped"] > 0
    assert len(log["text"]) <= 16384


def test_cursor_lets_a_reconnect_skip_unchanged_studies(tmp_path):
    folder = make_campaign(tmp_path)
    first = run_once({"roots": [str(tmp_path)]})
    cursor = next(m for m in first if m["t"] == "cursor")
    assert cursor["folder"] == str(folder)
    known = {
        str(folder): {
            "mtime": cursor["mtime"],
            "event_offset": (folder / "events.jsonl").stat().st_size,
            "log_offset": (folder / "worker.log").stat().st_size,
        }
    }
    again = run_once({"roots": [str(tmp_path)], "known": known})
    assert not [m for m in again if m["t"] == "study"]
