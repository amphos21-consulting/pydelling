"""SSHExecutor.collect keeps light results and leaves heavy solver output on the host."""

import json
import os
import subprocess
from pathlib import Path

import pytest

from pydelling.managers.ssh_executor import (
    COLLECT_REPORT,
    TRUNCATED_MARKER,
    SSHExecutor,
    is_truncated,
)
from pydelling.tests.monitor import fake_ssh

SCREEN = "".join(f" Step {i:6d} Time= {i:.5E} Dt= 1.0E+00 [s]\n" for i in range(4000))


def make_campaign(root: Path) -> Path:
    """Write a remote campaign with one PFLOTRAN attempt and post-processed tables.

    Args:
        root: Fake remote root.

    Returns:
        Path: The campaign folder.
    """
    campaign = root / "campaigns" / "c1"
    attempt = campaign / "s1" / "attempts" / "0001"
    (attempt / "processed").mkdir(parents=True)
    (attempt / "input_files").mkdir()
    (campaign / "postprocess").mkdir()
    (campaign / "events.jsonl").write_text('{"type": "x"}\n')
    (campaign / "worker.log").write_text("worker ok\n")
    (campaign / "manifest.parquet").write_bytes(b"PAR1")
    (campaign / "postprocess" / "extractions.parquet").write_bytes(b"PAR1")
    (campaign / "s1" / "status.json").write_text('{"state": "completed"}')
    (attempt / "status.json").write_text('{"state": "completed"}')
    (attempt / "processed" / "extractions.parquet").write_bytes(b"PAR1")
    (attempt / "input_files" / "hanford.dat").write_text("1 2 3\n")
    (attempt / "model.in").write_text("SIMULATION\nEND\n")
    (attempt / "model.out").write_text(" PFLOTRAN input echo\n" + SCREEN)
    (attempt / "stdout.log").write_text(SCREEN + " Wall Clock Time: 1.0 [sec]\n")
    (attempt / "stderr.log").write_text("")
    (attempt / "model-mas.dat").write_text("Time Mass\n0 1\n")
    (attempt / "model.h5").write_bytes(b"HDF")
    (campaign / "secret.key").write_text("no")
    return campaign


@pytest.fixture
def executor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SSHExecutor:
    fake_ssh.install(tmp_path, monkeypatch)
    return SSHExecutor("user@host", str(tmp_path / "root"), ssh=os.environ["PYDELLING_SSH"])


def test_default_collect_skips_duplicates_and_tails_large_logs(
    tmp_path: Path, executor: SSHExecutor
) -> None:
    campaign = make_campaign(tmp_path / "root")
    local = tmp_path / "local"
    record = executor.collect(str(campaign), local, log_tail_bytes=4096)
    attempt = local / "s1" / "attempts" / "0001"
    for kept in (
        "events.jsonl",
        "worker.log",
        "manifest.parquet",
        "postprocess/extractions.parquet",
        "s1/status.json",
        "s1/attempts/0001/status.json",
        "s1/attempts/0001/processed/extractions.parquet",
        "s1/attempts/0001/input_files/hanford.dat",
        "s1/attempts/0001/model.in",
        "s1/attempts/0001/stderr.log",
    ):
        assert (local / kept).read_bytes() == (campaign / kept).read_bytes(), kept
    for skipped in ("model.out", "model-mas.dat", "model.h5"):
        assert not (attempt / skipped).exists()
    assert not (local / "secret.key").exists() and not (local / COLLECT_REPORT).exists()

    tail = (attempt / "stdout.log").read_text()
    assert is_truncated(attempt / "stdout.log") and tail.startswith(TRUNCATED_MARKER)
    header, body = tail.split("\n", 1)
    assert str(campaign / "s1/attempts/0001/stdout.log") in header
    assert len(body.encode()) <= 4096 and body.endswith("Wall Clock Time: 1.0 [sec]\n")
    assert body.startswith(" Step")  # cut at a line boundary

    full = campaign / "s1" / "attempts" / "0001"
    assert record["truncated"] == {
        "s1/attempts/0001/stdout.log": (full / "stdout.log").stat().st_size
    }
    assert record["left_on_host"] == {
        f"s1/attempts/0001/{n}": (full / n).stat().st_size
        for n in ("model-mas.dat", "model.h5", "model.out")
    }
    assert json.loads((local / "download.json").read_text()) == record
    assert record["full_logs"] is False and record["log_tail_bytes"] == 4096


def test_full_logs_and_raw_download_everything(tmp_path: Path, executor: SSHExecutor) -> None:
    campaign = make_campaign(tmp_path / "root")
    local = tmp_path / "local"
    record = executor.collect(str(campaign), local, raw=True, full_logs=True, log_tail_bytes=1)
    attempt, source = local / "s1/attempts/0001", campaign / "s1/attempts/0001"
    for name in ("model.out", "stdout.log", "model-mas.dat", "model.h5"):
        assert (attempt / name).read_bytes() == (source / name).read_bytes(), name
    assert not is_truncated(attempt / "stdout.log")
    assert record["truncated"] == {} and record["left_on_host"] == {}
    assert record["log_tail_bytes"] is None


def test_out_file_is_kept_when_stdout_cannot_stand_in(
    tmp_path: Path, executor: SSHExecutor
) -> None:
    campaign = make_campaign(tmp_path / "root")
    attempt = campaign / "s1" / "attempts" / "0001"
    (attempt / "stdout.log").write_text("")  # e.g. -screen_output off
    local = tmp_path / "local"
    record = executor.collect(str(campaign), local, log_tail_bytes=4096)
    copy = local / "s1/attempts/0001/model.out"
    assert is_truncated(copy) and copy.read_text().endswith(SCREEN[-200:])
    assert "s1/attempts/0001/model.out" not in record["left_on_host"]
    assert list(record["truncated"]) == ["s1/attempts/0001/model.out"]


def test_small_logs_travel_whole(tmp_path: Path, executor: SSHExecutor) -> None:
    campaign = make_campaign(tmp_path / "root")
    attempt = campaign / "s1" / "attempts" / "0001"
    (attempt / "model.out").write_text("short run\n")
    (attempt / "stdout.log").write_text("short run\nMPI abort\n")
    local = tmp_path / "local"
    record = executor.collect(str(campaign), local)
    for name in ("model.out", "stdout.log"):  # below the cap, both stay whole
        assert (local / "s1/attempts/0001" / name).read_bytes() == (attempt / name).read_bytes()
    assert record["truncated"] == {}


def test_collect_reports_progress_against_the_host_plan(
    tmp_path: Path, executor: SSHExecutor, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("pydelling.managers.ssh_executor.PROGRESS_INTERVAL", 0)
    campaign = make_campaign(tmp_path / "root")
    events: list[tuple[str, dict]] = []
    local = tmp_path / "local"
    executor.collect(
        str(campaign), local, log_tail_bytes=4096, on_event=lambda kind, **p: events.append((kind, p))
    )
    ticks = [payload for kind, payload in events if kind == "collect.progress"]
    assert len(ticks) == len(events) >= 3
    first, last = ticks[0], ticks[-1]
    assert first["files"] == 0 and first["bytes"] == 0 and first["current"] is None
    written = sorted(p for p in local.rglob("*") if p.is_file() and p.name != "download.json")
    assert last["files"] == last["total_files"] == len(written)
    assert last["bytes"] == last["total_bytes"] == sum(p.stat().st_size for p in written)
    assert [t["bytes"] for t in ticks] == sorted(t["bytes"] for t in ticks)
    assert all(t["bytes"] <= t["total_bytes"] for t in ticks)
    assert not (local / ".pydelling-plan.json").exists()


def test_collect_progress_is_throttled_but_always_closes(
    tmp_path: Path, executor: SSHExecutor
) -> None:
    campaign = make_campaign(tmp_path / "root")
    events: list[dict] = []
    executor.collect(str(campaign), tmp_path / "local", on_event=lambda kind, **p: events.append(p))
    assert 2 <= len(events) <= 4  # plan, (throttled ticks,) final
    assert events[-1]["files"] == events[-1]["total_files"]


def test_collect_reports_the_ssh_exit_status(
    tmp_path: Path, executor: SSHExecutor, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_SSH_DENY", "1")
    with pytest.raises(subprocess.CalledProcessError) as failure:
        executor.collect("/r", tmp_path / "local")
    assert failure.value.returncode == 255


def test_collect_rejects_negative_tail(executor: SSHExecutor, tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        executor.collect("/r", tmp_path, log_tail_bytes=-1)


def test_is_truncated_on_missing_or_plain_files(tmp_path: Path) -> None:
    assert not is_truncated(tmp_path / "missing.log")
    (tmp_path / "a.log").write_text("plain\n")
    assert not is_truncated(tmp_path / "a.log")
