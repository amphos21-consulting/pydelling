"""FastAPI router exposing :class:`RunsService` (for pydelling-cloud).

``app.include_router(create_router(service), prefix="/v1/runs")`` gives the same
endpoints as the standalone server; authentication is left to the host app.
FastAPI is imported lazily so pydelling keeps no hard dependency on it.
"""

import asyncio
import json

from .service import NotFound
from .transport import TransportError


def create_router(service):
    from fastapi import APIRouter, Body, HTTPException
    from fastapi.responses import StreamingResponse

    router = APIRouter()

    async def call(function, *args, **kwargs):
        try:
            return await asyncio.to_thread(function, *args, **kwargs)
        except NotFound as exc:
            raise HTTPException(404, str(exc)) from exc
        except (ValueError, KeyError) as exc:
            raise HTTPException(400, str(exc)) from exc
        except TransportError as exc:
            raise HTTPException(502, str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(409, str(exc)) from exc

    @router.get("/overview")
    async def overview(
        status: str | None = None,
        host: str | None = None,
        q: str | None = None,
        active: bool = False,
    ):
        return await call(service.overview, status=status, host=host, q=q, active=active)

    @router.get("/hosts")
    async def hosts():
        return await call(service.hosts)

    @router.get("/entries")
    async def entries():
        return await call(service.entries)

    @router.get("/preview")
    async def preview(entry: str, path: str, host: str | None = None):
        return await call(service.preview, entry, path, host)

    @router.get("/runs/{run_id}")
    async def run_detail(run_id: str):
        return await call(service.run_detail, run_id)

    @router.get("/runs/{run_id}/events")
    async def events(run_id: str, after: int = 0):
        return await call(service.events, run_id, after)

    @router.get("/runs/{run_id}/log")
    async def worker_log(run_id: str, live: bool = False):
        return await call(service.worker_log, run_id, live=live)

    @router.get("/runs/{run_id}/tables")
    async def tables(run_id: str):
        return await call(service.tables, run_id)

    @router.get("/runs/{run_id}/table")
    async def table(run_id: str, path: str, offset: int = 0, limit: int = 100, q: str = ""):
        return await call(service.table, run_id, path, offset=offset, limit=limit, query=q)

    @router.get("/runs/{run_id}/studies/{name}")
    async def study(run_id: str, name: str):
        return await call(service.study, run_id, name)

    @router.get("/runs/{run_id}/studies/{name}/log")
    async def study_log(run_id: str, name: str, stream: str = "stdout"):
        return await call(service.study_log, run_id, name, stream)

    @router.post("/hosts/{host_id}/preflight")
    async def preflight(host_id: str):
        return await call(service.preflight, host_id)

    @router.post("/hosts/{host_id}/reconnect")
    async def reconnect(host_id: str):
        return await call(service.reconnect, host_id)

    @router.post("/launch")
    async def launch(payload: dict = Body(...)):  # noqa: B008 -- FastAPI idiom
        return await call(service.launch, payload)

    @router.post("/runs/{run_id}/cancel")
    async def cancel(run_id: str):
        return await call(service.cancel, run_id)

    @router.post("/runs/{run_id}/resume")
    async def resume(run_id: str):
        return await call(service.resume, run_id)

    @router.post("/runs/{run_id}/collect")
    async def collect(run_id: str, payload: dict = Body(default={})):  # noqa: B008
        return await call(
            service.collect,
            run_id,
            raw=bool(payload.get("raw")),
            full_logs=bool(payload.get("full_logs")),
        )

    @router.get("/stream")
    async def stream(rev: int = 0, event_id: int = 0):
        async def frames():
            nonlocal rev, event_id
            yield f"event: ready\ndata: {json.dumps({'rev': rev, 'event_id': event_id})}\n\n"
            while True:
                data = await asyncio.to_thread(service.changes, rev, event_id)
                if data["hosts"] or data["runs"] or data["studies"] or data["events"]:
                    yield f"event: changes\ndata: {json.dumps(data, default=str)}\n\n"
                rev, event_id = data["rev"], data["event_id"]
                await asyncio.sleep(0.5)

        return StreamingResponse(frames(), media_type="text/event-stream")

    return router
