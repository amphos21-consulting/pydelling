import threading

import pytest

from pydelling.monitor.registry import Registry, derive_status


@pytest.fixture
def registry(tmp_path):
    return Registry(tmp_path / "registry.sqlite")


def test_schema_is_idempotent_and_wal(tmp_path):
    first = Registry(tmp_path / "r.sqlite")
    first.upsert_host({"id": "local", "transport": "local", "root": "/tmp"})
    second = Registry(tmp_path / "r.sqlite")
    assert [h["id"] for h in second.list_hosts()] == ["local"]
    assert second.journal_mode() == "wal"


def test_ensure_run_is_get_or_create_per_host_and_folder(registry):
    a = registry.ensure_run("macario", "/r/campaigns/c1", name="c1", origin="ui")
    b = registry.ensure_run("macario", "/r/campaigns/c1", name="c1", entry_path="cases/x.yaml")
    c = registry.ensure_run("local", "/r/campaigns/c1", name="c1")
    assert a == b != c
    run = registry.get_run(a)
    assert run["origin"] == "ui" and run["entry_path"] == "cases/x.yaml"
    assert registry.find_run("macario", "/r/campaigns/c1")["id"] == a
    assert registry.find_run("macario", "/nope") is None


def test_json_fields_round_trip(registry):
    run = registry.ensure_run("h", "/f", name="f", argv_json=["a", "b c"])
    registry.update_run(run, campaign_json={"state": "running"}, counts_json={"running": 2})
    loaded = registry.get_run(run)
    assert loaded["argv_json"] == ["a", "b c"]
    assert loaded["campaign_json"] == {"state": "running"}


def test_events_are_deduplicated_by_remote_offset(registry):
    run = registry.ensure_run("h", "/f", name="f")
    assert registry.add_event(run, "study.state", source="worker", remote_offset=0)
    assert not registry.add_event(run, "study.state", source="worker", remote_offset=0)
    assert registry.add_event(run, "note")
    assert registry.add_event(run, "note")
    events = registry.events(run)
    assert [e["event_type"] for e in events] == ["study.state", "note", "note"]
    assert registry.events(run, after=events[0]["id"])[0]["id"] == events[1]["id"]


def test_changes_cursor_sees_writes_from_other_connections(tmp_path):
    path = tmp_path / "r.sqlite"
    reader, writer = Registry(path), Registry(path)
    base = reader.changes(0, 0)
    run = writer.ensure_run("h", "/f", name="f")
    writer.upsert_study(run, "a", state="running")
    writer.add_event(run, "hello")
    delta = reader.changes(base["rev"], base["event_id"])
    assert [r["id"] for r in delta["runs"]] == [run]
    assert [s["name"] for s in delta["studies"]] == ["a"]
    assert [e["event_type"] for e in delta["events"]] == ["hello"]
    empty = reader.changes(delta["rev"], delta["event_id"])
    assert not (empty["runs"] or empty["studies"] or empty["events"] or empty["hosts"])


def test_concurrent_writers_do_not_lose_events(tmp_path):
    path = tmp_path / "r.sqlite"
    run = Registry(path).ensure_run("h", "/f", name="f")

    def write(i):
        registry = Registry(path)
        for j in range(20):
            registry.add_event(run, "x", payload={"i": i, "j": j})

    threads = [threading.Thread(target=write, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(Registry(path).events(run, limit=1000)) == 80


def test_study_progress_series_is_merged_sorted_and_capped(registry):
    run = registry.ensure_run("h", "/f", name="f")
    registry.upsert_study(run, "a", state="running", points=[[2, 1, 0], [1, 1, 0]])
    registry.upsert_study(run, "a", points=[[2, 1, 0], [3, 1, 1]], sim_time_s=3, final_time_s=6)
    study = registry.studies(run)[0]
    assert study["series_json"] == [[1, 1, 0], [2, 1, 0], [3, 1, 1]]
    assert study["progress"] == pytest.approx(0.5)
    registry.upsert_study(run, "a", points=[[t, 1, 0] for t in range(10, 1000)])
    series = registry.studies(run)[0]["series_json"]
    assert len(series) <= 256 and series[0][0] == 1 and series[-1][0] == 999


def test_counts_and_progress_follow_studies(registry):
    run = registry.ensure_run("h", "/f", name="f", preview_json={"study_count": 4})
    registry.upsert_study(run, "a", state="completed")
    registry.upsert_study(run, "b", state="running")
    registry.upsert_study(run, "c", state="failed")
    loaded = registry.get_run(run)
    assert loaded["counts_json"] == {"completed": 1, "running": 1, "failed": 1, "pending": 1}
    assert loaded["progress"] == pytest.approx(0.5)


def test_completed_study_reports_full_progress(registry):
    run = registry.ensure_run("h", "/f", name="f")
    registry.upsert_study(run, "a", state="running", sim_time_s=1, final_time_s=10)
    registry.upsert_study(run, "a", state="completed")
    assert registry.studies(run)[0]["progress"] == 1.0


def test_log_tail_is_bounded(registry):
    run = registry.ensure_run("h", "/f", name="f")
    registry.append_log(run, "a" * 70000 + "\n", 70001)
    registry.append_log(run, "tail\n", 70006)
    loaded = registry.get_run(run)
    assert loaded["log_tail"].endswith("tail\n") and len(loaded["log_tail"]) <= 65536
    assert loaded["log_offset"] == 70006


def test_list_runs_filters_and_kpis(registry):
    a = registry.ensure_run("macario", "/r/a", name="alpha", status="running")
    registry.ensure_run("local", "/r/b", name="beta", status="completed")
    registry.upsert_study(a, "s1", state="running")
    assert [r["name"] for r in registry.list_runs(active=True)] == ["alpha"]
    assert [r["name"] for r in registry.list_runs(host="local")] == ["beta"]
    assert [r["name"] for r in registry.list_runs(q="alp")] == ["alpha"]
    assert [r["name"] for r in registry.list_runs(status="completed")] == ["beta"]
    kpis = registry.kpis()
    assert kpis["active"] == 1 and kpis["running_studies"] == 1


def test_status_timestamps(registry):
    run = registry.ensure_run("h", "/f", name="f")
    registry.update_run(run, status="running")
    assert registry.get_run(run)["started_at"] is not None
    registry.update_run(run, status="completed")
    assert registry.get_run(run)["finished_at"] is not None
    registry.update_run(run, status="preflight")
    assert registry.get_run(run)["finished_at"] is None


@pytest.mark.parametrize(
    ("run", "expected"),
    [
        ({"status": "deploying"}, "deploying"),
        ({"status": "starting", "worker_json": {"pid": 1}, "worker_alive": True}, "running"),
        ({"status": "deploying", "campaign_json": {"state": "completed"}}, "deploying"),
        ({"status": "running", "worker_alive": True, "cancel_requested": True}, "cancelling"),
        (
            {"status": "running", "worker_alive": False, "campaign_json": {"state": "completed"}},
            "completed",
        ),
        ({"status": "running", "worker_alive": False, "exit_code": 0}, "completed"),
        ({"status": "running", "worker_alive": False, "exit_code": 2}, "failed"),
        (
            {"status": "running", "worker_alive": False, "exit_code": 1, "cancel_requested": True},
            "cancelled",
        ),
        (
            {"status": "running", "worker_alive": False, "campaign_json": {"state": "running"}},
            "lost",
        ),
        ({"status": "running", "worker_alive": False, "worker_json": {"pid": 3}}, "lost"),
        ({"status": "failed", "error": "preflight"}, "failed"),
        (
            {"status": "failed", "launch_failed": 1, "campaign_json": {"state": "completed"}},
            "failed",
        ),
        ({"status": "cancelled", "launch_failed": 1, "worker_json": {"pid": 1}}, "cancelled"),
    ],
)
def test_derive_status(run, expected):
    assert derive_status(run) == expected


def test_delete_cascades_streams_and_blocks_rediscovery(registry):
    run = registry.ensure_run("local", "/runs/old", status="completed", log_tail="private log")
    registry.upsert_study(run, "study", state="completed", points=[[1, 2, 0]])
    registry.add_event(run, "finished")
    rev = registry.current_rev()
    assert registry.delete_runs(run) == [run]
    assert registry.get_run(run) is None
    assert registry.studies(run) == [] and registry.events(run) == []
    assert registry.changes(rev, 0)["deleted_runs"] == [run]
    reopened = Registry(registry.path)
    assert reopened.ensure_run("local", "/runs/old", origin="discovered") is None
    # A deliberate new launch can reuse a folder, with a fresh identity.
    new = reopened.ensure_run("local", "/runs/old", origin="ui")
    assert new and new != run
    registry.add_event(run, "late event")
    registry.upsert_study(run, "late study", state="completed")
    assert registry.events(run) == [] and registry.studies(run) == []


def test_clear_skips_active_runs_and_is_not_paginated(registry):
    for i in range(205):
        registry.ensure_run("local", f"/runs/{i}", status="completed")
    active = registry.ensure_run("local", "/runs/active", status="running")
    alive = registry.ensure_run("local", "/runs/alive", status="completed", worker_alive=1)
    cleaned = []
    assert len(registry.delete_runs(before_delete=lambda rows: cleaned.extend(rows))) == 205
    assert {r["id"] for r in cleaned}.isdisjoint({active, alive})
    assert registry.kpis()["total"] == 2
    with pytest.raises(ValueError, match="activos"):
        registry.delete_runs()
    with pytest.raises(ValueError, match="activo"):
        registry.delete_runs(active)
    registry.update_run(active, status="completed")
    registry.update_run(alive, worker_alive=0)
    assert len(registry.delete_runs()) == 2
    assert registry.kpis()["total"] == 0


def test_cancel_without_worker_does_not_stay_cancelling():
    assert derive_status({'status': 'cancelling', 'worker_alive': 0}) == 'cancelled'
    assert derive_status({'status': 'cancelling', 'worker_alive': None}) == 'cancelling'
