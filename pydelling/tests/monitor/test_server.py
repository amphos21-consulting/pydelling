import http.client
import json
import threading
import time

import pytest

from pydelling.monitor.server import make_server
from pydelling.monitor.service import RunsService, stages
from pydelling.tests.monitor.conftest import wait_until


@pytest.fixture
def served(project, registry):
    service = RunsService(project, registry)
    server, token = make_server(service, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server, token, registry
    server.shutdown()
    server.server_close()


def call(served, method, path, *, body=None, token=True, host=None, content_type=None):
    server, secret, _ = served
    port = server.server_address[1]
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    headers = {"Host": host or f"127.0.0.1:{port}"}
    if token:
        headers["Authorization"] = f"Bearer {secret}"
    payload = None
    if body is not None:
        payload = json.dumps(body)
        headers["Content-Type"] = content_type or "application/json"
    connection.request(method, path, body=payload, headers=headers)
    response = connection.getresponse()
    data = response.read()
    connection.close()
    kind = response.getheader("Content-Type", "")
    return response.status, (json.loads(data) if "json" in kind else data.decode()), response


def seed(registry, **fields):
    run_id = registry.ensure_run("local", "/tmp/campaigns/alpha", name="alpha", status="running")
    registry.update_run(
        run_id,
        log_tail="x" * 1000,
        campaign_json={"state": "running", "source": {"files": {"a": 1}}},
        **fields,
    )
    registry.upsert_study(run_id, "s1", state="running", points=[[1, 1, 0]])
    registry.add_event(run_id, "launch.requested")
    return run_id


def test_index_is_served_without_token_with_strict_headers(served):
    status, body, response = call(served, "GET", "/", token=False)
    assert status == 200 and 'id="app"' in body
    csp = response.getheader("Content-Security-Policy")
    assert "default-src 'self'" in csp and "frame-ancestors 'none'" in csp
    assert response.getheader("X-Content-Type-Options") == "nosniff"
    assert call(served, "GET", "/static/../../pyproject.toml", token=False)[0] == 404


def test_api_requires_the_session_token(served):
    assert call(served, "GET", "/api/overview", token=False)[0] == 401
    assert call(served, "GET", "/api/overview")[0] == 200


def test_foreign_host_headers_are_rejected(served):
    assert call(served, "GET", "/api/overview", host="evil.example:80")[0] == 403
    assert call(served, "GET", "/", token=False, host="evil.example")[0] == 403


def test_overview_is_slim(served):
    run_id = seed(served[2])
    status, body, _ = call(served, "GET", "/api/overview")
    assert status == 200 and body["kpis"]["active"] == 1
    run = next(r for r in body["runs"] if r["id"] == run_id)
    assert "log_tail" not in run
    assert {h["id"] for h in body["hosts"]} >= {"local"}
    assert body["rev"] > 0


def test_run_detail_study_and_404(served):
    run_id = seed(served[2])
    status, body, _ = call(served, "GET", f"/api/runs/{run_id}")
    assert status == 200 and body["run"]["name"] == "alpha"
    assert body["run"]["campaign_json"] == {"state": "running"}
    assert body["run"]["log_tail"].startswith("x")
    assert "series_json" not in body["studies"][0]
    assert [s["id"] for s in body["stages"]][:3] == ["preflight", "deploy", "start"]
    status, study, _ = call(served, "GET", f"/api/runs/{run_id}/studies/s1")
    assert status == 200 and study["series_json"] == [[1, 1, 0]]
    assert call(served, "GET", "/api/runs/nope")[0] == 404
    assert call(served, "GET", f"/api/runs/{run_id}/studies/nope")[0] == 404


def test_entries_preview_and_launch_validation(served, project):
    status, entries, _ = call(served, "GET", "/api/entries")
    assert status == 200
    assert {e["id"]: e["paths"] for e in entries}["campaign"] == ["cases/alpha.yaml"]
    status, preview, _ = call(served, "GET", "/api/preview?entry=campaign&path=cases/alpha.yaml")
    assert status == 200 and preview["study_count"] == 2
    bad = {"entry": "campaign", "path": "../pyproject.toml"}
    assert call(served, "POST", "/api/launch", body=bad)[0] == 400
    wrong_type = call(
        served,
        "POST",
        "/api/launch",
        body={"entry": "campaign", "path": "cases/alpha.yaml"},
        content_type="text/plain",
    )
    assert wrong_type[0] == 415
    status, body, _ = call(
        served, "POST", "/api/launch", body={"entry": "campaign", "path": "cases/alpha.yaml"}
    )
    assert status == 200 and body["run_id"]
    wait_until(lambda: (project.root / "launched.json").exists())


def test_tables_are_served_over_http_with_paging_and_confinement(served, tmp_path):
    folder = tmp_path / "download"
    folder.mkdir()
    (folder / "profiles.csv").write_text("a,b\n" + "".join(f"{i},{i * 2}\n" for i in range(30)))
    run_id = served[2].ensure_run("macario", "/r/campaigns/t", name="t", status="completed")
    served[2].update_run(run_id, local_folder=str(folder))
    status, body, _ = call(served, "GET", f"/api/runs/{run_id}/tables")
    assert status == 200 and [t["path"] for t in body["tables"]] == ["profiles.csv"]
    url = f"/api/runs/{run_id}/table?path=profiles.csv&offset=20&limit=5"
    status, page, _ = call(served, "GET", url)
    assert status == 200 and page["total"] == 30 and page["rows"][0] == ["20", "40"]
    status, hits, _ = call(served, "GET", f"/api/runs/{run_id}/table?path=profiles.csv&q=29")
    assert status == 200 and hits["rows"] == [["29", "58"]]
    assert call(served, "GET", f"/api/runs/{run_id}/table?path=../x.csv")[0] == 400
    assert call(served, "GET", f"/api/runs/{run_id}/table?path=profiles.csv&offset=x")[0] == 400
    assert call(served, "GET", f"/api/runs/{run_id}/table?path=profiles.csv", token=False)[0] == 401
    assert call(served, "GET", "/api/runs/nope/tables")[0] == 404


def test_actions_map_errors_to_http(served):
    run_id = seed(served[2])
    served[2].update_run(run_id, worker_alive=1)
    assert call(served, "POST", f"/api/runs/{run_id}/resume", body={})[0] == 400
    assert call(served, "POST", f"/api/runs/{run_id}/collect", body={})[0] == 400
    assert call(served, "POST", "/api/runs/nope/cancel", body={})[0] == 404


def test_sse_streams_ready_then_changes(served):
    server, secret, registry = served
    run_id = seed(registry)
    port = server.server_address[1]
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    rev = registry.current_rev()
    connection.request(
        "GET",
        f"/api/stream?token={secret}&rev={rev}&event_id=999999",
        headers={"Host": f"127.0.0.1:{port}"},
    )
    response = connection.getresponse()
    assert response.getheader("Content-Type").startswith("text/event-stream")
    buffer = b""

    def read_frame():
        nonlocal buffer
        while b"\n\n" not in buffer:
            buffer += response.fp.read1(4096)
        frame, buffer = buffer.split(b"\n\n", 1)
        return frame.decode()

    assert "event: ready" in read_frame()
    time.sleep(0.1)
    registry.upsert_study(run_id, "s2", state="completed")
    frame = read_frame()
    while "event: changes" not in frame:
        frame = read_frame()
    data = json.loads(frame.split("data: ", 1)[1])
    assert [s["name"] for s in data["studies"]] == ["s2"]
    assert all("log_tail" not in r for r in data["runs"])
    connection.close()


def test_stages_follow_the_latest_launch():
    events = [
        {"id": 1, "event_type": "launch.requested", "ts": 1.0, "source": "client"},
        {
            "id": 2,
            "event_type": "preflight.failed",
            "ts": 2.0,
            "source": "client",
            "message": "old",
        },
        {"id": 3, "event_type": "launch.requested", "ts": 10.0, "source": "client"},
        {"id": 4, "event_type": "preflight.started", "ts": 10.0, "source": "client"},
        {"id": 5, "event_type": "preflight.done", "ts": 12.0, "source": "client"},
        {"id": 6, "event_type": "deploy.started", "ts": 12.0, "source": "client"},
        {"id": 7, "event_type": "deploy.hashed", "ts": 12.5, "source": "client"},
        {"id": 8, "event_type": "deploy.done", "ts": 40.0, "source": "client"},
        {"id": 9, "event_type": "worker.started", "ts": 41.0, "source": "client"},
        {
            "id": 10,
            "event_type": "batch.started",
            "ts": 42.0,
            "source": "worker",
            "payload_json": {"batch": "verification", "studies": 2, "pending": 2},
        },
        {
            "id": 11,
            "event_type": "batch.finished",
            "ts": 50.0,
            "source": "worker",
            "payload_json": {"batch": "verification", "counts": {"completed": 2}},
        },
        {
            "id": 12,
            "event_type": "batch.started",
            "ts": 51.0,
            "source": "worker",
            "payload_json": {"batch": "training", "studies": 4, "pending": 4},
        },
    ]
    result = {s["id"]: s for s in stages({"status": "running", "kind": "campaign"}, events)}
    assert result["preflight"]["status"] == "done" and result["preflight"]["seconds"] == 2.0
    assert result["deploy"]["status"] == "done" and "deploy.hashed" in result["deploy"]["steps"]
    assert result["start"]["status"] == "done"
    assert result["batch:verification"]["status"] == "done"
    assert result["batch:training"]["status"] == "running"
    assert result["collect"]["status"] == "pending"


def test_stages_skip_client_phases_for_worker_only_runs():
    events = [
        {"id": 2, "event_type": "run.status", "ts": 0.5, "source": "client"},
        {"id": 3, "event_type": "watcher.warning", "ts": 0.6, "source": "client"},
        {
            "id": 1,
            "event_type": "batch.started",
            "ts": 1.0,
            "source": "worker",
            "payload_json": {"batch": "batch", "studies": 1, "pending": 1},
        },
    ]
    result = {s["id"]: s for s in stages({"status": "running", "kind": "campaign"}, events)}
    assert result["preflight"]["status"] == result["deploy"]["status"] == "skipped"


def test_fastapi_router_mounts(project, registry):
    fastapi = pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from pydelling.monitor.fastapi_router import create_router

    app = fastapi.FastAPI()
    app.include_router(create_router(RunsService(project, registry)), prefix="/v1/runs")
    seed(registry)
    body = TestClient(app).get("/v1/runs/overview").json()
    assert body["runs"][0]["name"] == "alpha"


def test_local_runs_skip_deploy_and_collect():
    events = [
        {"id": 1, "event_type": "launch.requested", "ts": 1.0, "source": "client"},
        {"id": 2, "event_type": "preflight.started", "ts": 1.0, "source": "client"},
        {"id": 3, "event_type": "preflight.done", "ts": 1.1, "source": "client"},
        {"id": 4, "event_type": "start.started", "ts": 1.2, "source": "client"},
        {"id": 5, "event_type": "start.done", "ts": 1.3, "source": "client"},
    ]
    result = {
        s["id"]: s for s in stages({"status": "completed", "kind": "script"}, events, local=True)
    }
    assert result["deploy"]["status"] == "skipped"
    assert result["collect"]["status"] == "skipped"
    remote = {s["id"]: s for s in stages({"status": "completed", "kind": "script"}, events)}
    assert remote["deploy"]["status"] == "skipped", "a later stage ran, so this one never will"
    assert remote["collect"]["status"] == "pending"


def test_finished_study_convergence_is_parsed_lazily_from_the_local_copy(project, registry):
    from pathlib import Path

    fixture = Path(__file__).with_name("pflotran_rc1_stdout.txt")
    copy = project.local_runs / "old"
    work = copy / "s1" / "attempts" / "0001"
    work.mkdir(parents=True)
    (work / "stdout.log").write_text(fixture.read_text())
    (work / "model.in").write_text("TIME\n  FINAL_TIME 86400000.0 s\nEND\n")
    run_id = registry.ensure_run("macario", "/r/campaigns/old", name="old", status="completed")
    registry.update_run(run_id, local_folder=str(copy))
    registry.upsert_study(run_id, "s1", state="completed", workdir="attempts/0001")
    study = RunsService(project, registry).study(run_id, "s1")
    assert study["step"] == 951 and len(study["series_json"]) >= 2
    assert registry.studies(run_id)[0]["series_json"], "the parsed series is cached"


def test_convergence_is_parsed_from_a_flat_study_folder(project, registry):
    from pathlib import Path

    fixture = Path(__file__).with_name("pflotran_rc1_stdout.txt")
    copy = project.local_runs / "flat"
    work = copy / "s1"
    work.mkdir(parents=True)
    (work / "stdout.log").write_text(fixture.read_text())
    (work / "model.in").write_text("TIME\n  FINAL_TIME 86400000.0 s\nEND\n")
    run_id = registry.ensure_run("macario", "/r/campaigns/flat", name="flat", status="completed")
    registry.update_run(run_id, local_folder=str(copy))
    registry.upsert_study(run_id, "s1", state="completed", workdir=".")
    assert RunsService(project, registry).study(run_id, "s1")["step"] == 951


def test_truncated_local_log_tail_is_not_parsed_as_the_full_series(project, registry):
    from pathlib import Path

    from pydelling.managers.ssh_executor import TRUNCATED_MARKER

    fixture = Path(__file__).with_name("pflotran_rc1_stdout.txt").read_text()
    copy = project.local_runs / "tail"
    work = copy / "s1" / "attempts" / "0001"
    work.mkdir(parents=True)
    (work / "stdout.log").write_text(f"{TRUNCATED_MARKER}: last 1 of 2 bytes\n" + fixture)
    run_id = registry.ensure_run("macario", "/r/campaigns/tail", name="tail", status="completed")
    registry.update_run(run_id, local_folder=str(copy))
    registry.upsert_study(run_id, "s1", state="completed", workdir="attempts/0001")
    study = RunsService(project, registry).study(run_id, "s1")
    assert not study.get("series_json"), "a tail must not stand in for the full log"


def test_stages_survive_thousands_of_study_events(project, registry):
    run_id = registry.ensure_run("macario", "/r/campaigns/big", name="big", status="running")
    for kind in (
        "launch.requested",
        "preflight.started",
        "preflight.done",
        "deploy.started",
        "deploy.done",
        "start.started",
        "worker.started",
        "start.done",
    ):
        registry.add_event(run_id, kind)
    for i in range(1000):
        registry.add_event(
            run_id,
            "study.state",
            source="worker",
            remote_offset=i,
            payload={"study": f"s{i}", "state": "completed"},
        )
    registry.add_event(
        run_id,
        "study.state",
        source="worker",
        remote_offset=5000,
        level="error",
        payload={"study": "bad", "state": "failed"},
    )
    detail = RunsService(project, registry).run_detail(run_id)
    stages_by_id = {s["id"]: s for s in detail["stages"]}
    assert stages_by_id["preflight"]["status"] == "done"
    assert stages_by_id["deploy"]["status"] == "done"
    types = [e["event_type"] for e in detail["events"]]
    assert "launch.requested" in types and "deploy.done" in types
    assert any(e["level"] == "error" for e in detail["events"])


def test_delete_and_clear_history_endpoints(served):
    registry = served[2]
    run = seed(registry)
    path = f"/api/runs/{run}/delete"
    assert call(served, "POST", path, body={}, token=False)[0] == 401
    assert call(served, "POST", path, body={})[0] == 400
    registry.update_run(run, status="completed", worker_alive=0)
    status, data, _ = call(served, "POST", path, body={})
    assert status == 200 and data["deleted_runs"] == [run]
    assert call(served, "GET", f"/api/runs/{run}")[0] == 404
    assert call(served, "POST", path, body={})[0] == 404
    registry.ensure_run("local", "/tmp/another", status="failed")
    assert call(served, "POST", "/api/history/clear", body={})[0] == 200
    assert registry.kpis()["total"] == 0


def test_delete_files_is_optional_and_checks_paths(project, registry):
    service = RunsService(project, registry)
    folder = project.local_runs / "done"
    folder.mkdir(parents=True)
    (folder / "results.csv").write_text("data")
    run = registry.ensure_run("local", str(folder), status="completed", local_folder=str(folder))
    service.delete(run)
    assert folder.exists()
    run = registry.ensure_run("local", str(folder), status="completed", local_folder=str(folder))
    service.delete(run, files=True)
    assert not folder.exists() and registry.get_run(run) is None
    outside = project.root / "source"
    outside.mkdir()
    run = registry.ensure_run("local", str(outside), status="completed")
    safe = project.local_runs / "another"
    safe.mkdir()
    safe_run = registry.ensure_run("local", str(safe), status="completed")
    result = service.clear_history(files=True)
    assert set(result["deleted_runs"]) == {run, safe_run}
    assert result["skipped_folders"] == [{
        "host_id": "local", "folder": str(outside),
        "reason": f"Carpeta de run no segura: {outside}",
    }]
    assert outside.exists() and registry.get_run(run) is None
    assert not safe.exists()


def test_remote_cleanup_failure_keeps_history(project, registry, monkeypatch):
    from pydelling.monitor import service as module
    from pydelling.monitor.transport import TransportError

    run = registry.ensure_run("local", str(project.local_runs / "done"), status="completed")

    class Unavailable:
        def python(self, *args, **kwargs):
            raise TransportError("unreachable", "Host offline")

    monkeypatch.setattr(module, "make_transport", lambda host: Unavailable())
    with pytest.raises(TransportError, match="offline"):
        RunsService(project, registry).clear_history(files=True)
    assert registry.get_run(run)


def collect_events(*extra):
    launch = {"id": 1, "event_type": "launch.requested", "ts": 1.0, "source": "client"}
    return [launch, *extra]


def test_collect_stage_carries_progress_of_the_current_download():
    tick = {
        "id": 9,
        "event_type": "collect.progress",
        "ts": 12.0,
        "payload_json": {"files": 3, "total_files": 10, "bytes": 30, "total_bytes": 100, "elapsed": 2.0},
    }
    started = {"id": 5, "event_type": "collect.started", "ts": 10.0, "source": "client"}
    run = {"status": "completed", "kind": "campaign"}
    stage = {s["id"]: s for s in stages(run, collect_events(started), progress=tick)}["collect"]
    assert stage["status"] == "running"
    assert stage["progress"] == {
        "files": 3,
        "total_files": 10,
        "bytes": 30,
        "total_bytes": 100,
        "elapsed": 2.0,
    }
    done = {"id": 10, "event_type": "collect.done", "ts": 14.0, "source": "client"}
    stage = {s["id"]: s for s in stages(run, collect_events(started, done), progress=tick)}
    assert stage["collect"]["status"] == "done" and stage["collect"]["seconds"] == 4.0
    assert stage["collect"]["progress"]["files"] == 3


def test_collect_stage_ignores_progress_of_a_previous_download_and_tracks_queueing():
    old = {"id": 3, "event_type": "collect.progress", "ts": 5.0, "payload_json": {"files": 9}}
    queued = {"id": 4, "event_type": "collect.queued", "ts": 6.0, "source": "client"}
    run = {"status": "completed", "kind": "campaign"}
    stage = {s["id"]: s for s in stages(run, collect_events(queued), progress=old)}["collect"]
    assert stage["status"] == "queued" and "progress" not in stage
    started = {"id": 5, "event_type": "collect.started", "ts": 7.0, "source": "client"}
    failed = {
        "id": 6,
        "event_type": "collect.failed",
        "ts": 8.0,
        "message": "ssh cayó",
        "source": "client",
    }
    stage = {s["id"]: s for s in stages(run, collect_events(queued, started, failed))}["collect"]
    assert stage["status"] == "failed" and stage["detail"] == "ssh cayó"
    assert "progress" not in stage


def test_run_detail_exposes_download_progress_without_flooding_events(project, registry):
    run_id = registry.ensure_run("macario", "/r/campaigns/c1", name="c1", status="completed")
    registry.add_event(run_id, "launch.requested")
    registry.add_event(run_id, "collect.started")
    for n in range(300):
        registry.add_event(
            run_id, "collect.progress", payload={"files": n, "total_files": 300, "bytes": n}
        )
    detail = RunsService(project, registry).run_detail(run_id)
    assert not [e for e in detail["events"] if e["event_type"] == "collect.progress"]
    collect = {s["id"]: s for s in detail["stages"]}["collect"]
    assert collect["status"] == "running" and collect["progress"]["files"] == 299
    assert registry.last_event(run_id, "collect.progress")["payload_json"]["files"] == 299
    assert registry.last_event(run_id, "nope") is None
    assert "collect.progress" not in {e["event_type"] for e in registry.milestones(run_id)}


def test_cleanup_validates_all_workers_before_deleting(project, registry):
    import os

    from pydelling.monitor.transport import TransportError

    safe = project.local_runs / "first"
    busy = project.local_runs / "busy"
    for folder in (safe, busy):
        folder.mkdir(parents=True)
        registry.ensure_run("local", str(folder), status="completed")
    (busy / "worker.json").write_text(json.dumps({"pid": os.getpid()}))
    with pytest.raises(TransportError, match="activo"):
        RunsService(project, registry).clear_history(files=True)
    assert safe.exists() and busy.exists() and registry.kpis()["total"] == 2


def test_cleanup_delete_failure_retains_all_history(project, registry, monkeypatch):
    from pydelling.monitor import service as module
    from pydelling.monitor.transport import TransportError, make_transport

    safe = project.local_runs / "done"
    safe.mkdir(parents=True)
    outside = project.root / "external"
    outside.mkdir()
    for folder in (safe, outside):
        registry.ensure_run("local", str(folder), status="completed")

    class FailingDelete:
        def __init__(self, host):
            self.transport = make_transport(host)

        def python(self, source, root, folder, mode, **kwargs):
            if mode == "delete":
                raise TransportError("error", "Deletion failed")
            return self.transport.python(source, root, folder, mode, **kwargs)

    monkeypatch.setattr(module, "make_transport", FailingDelete)
    with pytest.raises(TransportError, match="Deletion failed"):
        RunsService(project, registry).clear_history(files=True)
    assert registry.kpis()["total"] == 2
    assert safe.exists() and outside.exists()


def test_cleanup_missing_external_results_has_no_preserved_folders(project, registry):
    missing = project.root / "old-pytest" / "out"
    run = registry.ensure_run("local", str(missing), status="completed")
    result = RunsService(project, registry).clear_history(files=True)
    assert result == {"deleted_runs": [run], "skipped_folders": []}
    assert registry.get_run(run) is None
