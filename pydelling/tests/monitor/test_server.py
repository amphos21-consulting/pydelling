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
