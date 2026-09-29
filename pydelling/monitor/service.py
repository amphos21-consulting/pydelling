"""Use cases behind the dashboard, shared by the stdlib server and the FastAPI router.

Rows leaving the service are *slim*: no log tails, series or source inventories in
lists and streams (those are fetched on demand), so live updates stay small even
for campaigns with thousands of studies.
"""

import json
import os
import subprocess
import sys
from pathlib import Path, PurePosixPath

from pydelling.managers.ssh_executor import is_truncated

from .launcher import cancel_run, launch_entry, launch_log, spawn_detached
from .preflight import run_preflight
from .registry import ACTIVE, TERMINAL
from .tables import DEFAULT_PAGE, list_tables, read_table
from .transport import TransportError, make_transport
from .watcher_script import SUMMARY_KEYS, convergence

PROGRESS_KEYS = (*SUMMARY_KEYS, "final_time_s")
COLLECT_PROGRESS_KEYS = ("files", "total_files", "bytes", "total_bytes", "elapsed")

CAMPAIGN_KEYS = ("state", "error", "started", "finished", "platform")
STAGE_LABELS = {
    "preflight": "Comprobación de acceso",
    "deploy": "Despliegue",
    "start": "Arranque del worker",
    "collect": "Descarga de resultados",
}
BATCH_LABELS = {"verification": "Verificación", "training": "Entrenamiento", "batch": "Estudios"}
LOG_FILES = {"stdout": "stdout.log", "stderr": "stderr.log"}


class NotFound(LookupError):
    pass


def slim_run(run, *, detail=False):
    if run is None:
        return None
    result = {k: v for k, v in run.items() if k not in ("log_tail", "config_json")}
    if not detail:
        result.pop("argv_json", None)
    campaign = run.get("campaign_json")
    if isinstance(campaign, dict):
        result["campaign_json"] = {k: campaign[k] for k in CAMPAIGN_KEYS if k in campaign}
    if detail:
        result["log_tail"] = run.get("log_tail") or ""
        result["config_json"] = run.get("config_json")
    return result


def slim_study(study):
    return {k: v for k, v in study.items() if k != "series_json"}


def stages(run, events, local=False, progress=None):
    """Pipeline stages of the latest launch, derived from client and worker events.

    ``local`` runs never deploy nor download; a pending client stage followed by a
    stage that already ran is reported as skipped. ``progress`` is the latest
    ``collect.progress`` event (kept out of ``events``, which holds milestones only):
    when it belongs to the current download, the collect stage carries its counters.
    """
    last_launch = max(
        (e["id"] for e in events if e["event_type"] in ("launch.requested", "launch.queued")),
        default=0,
    )
    current = [e for e in events if e["id"] >= last_launch]
    result = []
    client_seen = any(
        e["event_type"].split(".")[0] in ("launch", "preflight", "deploy", "start")
        or e["event_type"] == "worker.started"
        for e in current
    )
    for name in ("preflight", "deploy", "start"):
        stage = {"id": name, "label": STAGE_LABELS[name], "status": "pending", "steps": []}
        for event in current:
            kind = event["event_type"]
            if kind == f"{name}.started":
                stage.update(status="running", started=event["ts"])
            elif kind == f"{name}.done":
                stage.update(status="done", finished=event["ts"])
            elif kind == f"{name}.failed":
                stage.update(status="failed", finished=event["ts"], detail=event.get("message"))
            elif kind.startswith(f"{name}.") or (name == "start" and kind == "worker.started"):
                stage["steps"].append(kind)
                if name == "start" and kind == "worker.started" and stage["status"] == "pending":
                    stage.update(status="done", finished=event["ts"])
        if stage.get("started") is not None and stage.get("finished") is not None:
            stage["seconds"] = round(stage["finished"] - stage["started"], 3)
        if stage["status"] == "pending" and (not client_seen or (local and name == "deploy")):
            stage["status"] = "skipped"
        result.append(stage)
    for index, stage in enumerate(result):
        later = result[index + 1 :]
        if stage["status"] == "pending" and any(s["status"] != "pending" for s in later):
            stage["status"] = "skipped"
    batches = {}
    for event in current:
        payload = event.get("payload_json") or {}
        if event["event_type"] not in ("batch.started", "batch.finished"):
            continue
        name = payload.get("batch", "batch")
        stage = batches.setdefault(
            name,
            {
                "id": f"batch:{name}",
                "label": BATCH_LABELS.get(name, name.capitalize()),
                "status": "running",
                "steps": [],
            },
        )
        if event["event_type"] == "batch.started":
            stage.update(status="running", started=event["ts"], total=payload.get("studies"))
        else:
            counts = payload.get("counts") or {}
            failed = counts.get("failed", 0) or counts.get("interrupted", 0)
            stage.update(status="failed" if failed else "done", finished=event["ts"], counts=counts)
            if stage.get("started") is not None:
                stage["seconds"] = round(event["ts"] - stage["started"], 3)
    if run.get("status") in TERMINAL:
        for stage in batches.values():
            if stage["status"] == "running":
                stage["status"] = "failed" if run["status"] != "completed" else "done"
    result.extend(batches.values())
    collect = {"id": "collect", "label": STAGE_LABELS["collect"], "status": "pending", "steps": []}
    started_id = 0
    for event in events:  # a download may happen after the launch it belongs to
        if event["id"] < last_launch:
            continue
        kind = event["event_type"]
        if kind == "collect.queued":
            collect.update(status="queued")
        elif kind == "collect.started":
            started_id = event["id"]
            collect = {**collect, "status": "running", "started": event["ts"]}
            for key in ("finished", "seconds", "detail"):
                collect.pop(key, None)
        elif kind == "collect.done":
            collect.update(status="done", finished=event["ts"])
        elif kind == "collect.failed":
            collect.update(status="failed", finished=event["ts"], detail=event.get("message"))
    if collect.get("started") is not None and collect.get("finished") is not None:
        collect["seconds"] = round(collect["finished"] - collect["started"], 3)
    tick = (progress or {}).get("payload_json")
    if tick and progress["id"] > started_id > 0:
        collect["progress"] = {k: tick.get(k) for k in COLLECT_PROGRESS_KEYS}
    if local and collect["status"] == "pending":
        collect["status"] = "skipped"
    result.append(collect)
    return result


class RunsService:
    def __init__(self, project, registry, supervisor=None):
        self.project = project
        self.registry = registry
        self.supervisor = supervisor

    # Queries -----------------------------------------------------------------------------
    def _run(self, run_id):
        run = self.registry.get_run(run_id)
        if run is None:
            raise NotFound(f"Run desconocido: {run_id}")
        return run

    def hosts(self):
        configured = {h.id: h for h in self.project.hosts()}
        rows = {h["id"]: h for h in self.registry.list_hosts()}
        result = []
        for host_id, host in configured.items():
            row = rows.get(host_id, {})
            result.append(
                {
                    **host.as_dict(),
                    "stream_state": row.get("stream_state", "offline"),
                    "stream_error": row.get("stream_error"),
                    "heartbeat": row.get("heartbeat_json"),
                    "hello": row.get("hello_json"),
                }
            )
        return result

    def overview(self, *, status=None, host=None, q=None, active=False, limit=200):
        rev, event_id = self.registry.current_rev(), self.registry.last_event_id()
        runs = self.registry.list_runs(status=status, host=host, q=q, active=active, limit=limit)
        return {
            "hosts": self.hosts(),
            "runs": [slim_run(r) for r in runs],
            "kpis": self.registry.kpis(),
            "rev": rev,
            "event_id": event_id,
            "project": {"root": str(self.project.root), "name": self.project.root.name},
        }

    def run_detail(self, run_id):
        run = self._run(run_id)
        milestones = self.registry.milestones(run_id)
        recent = {e["id"]: e for e in self.registry.last_events(run_id, 200)}
        events = sorted(
            {**recent, **{e["id"]: e for e in milestones}}.values(), key=lambda e: e["id"]
        )
        return {
            "run": slim_run(run, detail=True),
            "studies": [slim_study(s) for s in self.registry.studies(run_id)],
            "events": events,
            "stages": stages(
                run,
                milestones,
                local=self._is_local(run["host_id"]),
                progress=self.registry.last_event(run_id, "collect.progress"),
            ),
            "actions": self.actions(run),
        }

    def _is_local(self, host_id):
        return any(h.id == host_id and h.transport == "local" for h in self.project.hosts())

    def actions(self, run):
        host = next((h for h in self.project.hosts() if h.id == run["host_id"]), None)
        local_folder = run.get("local_folder")
        return {
            "delete": run["status"] not in ACTIVE and not run.get("worker_alive"),
            "cancel": run["status"] in ACTIVE,
            "resume": run.get("entry_id") in self.project.entries
            and run.get("kind") == "campaign"
            and run["status"] not in ACTIVE,
            "collect": bool(host and host.transport == "ssh") and not run.get("worker_alive"),
            "open": bool(local_folder and Path(local_folder).is_dir()),
        }

    def events(self, run_id, after=0):
        self._run(run_id)
        return self.registry.events(run_id, after=after)

    def study(self, run_id, name):
        run = self._run(run_id)
        for study in self.registry.studies(run_id):
            if study["name"] == name:
                if self._needs_convergence(study):
                    summary = self._convergence(run, study)
                    if summary and summary.get("points"):
                        fields = {
                            k: summary[k] for k in PROGRESS_KEYS if summary.get(k) is not None
                        }
                        self.registry.upsert_study(run_id, name, points=summary["points"], **fields)
                        study = next(s for s in self.registry.studies(run_id) if s["name"] == name)
                return study
        raise NotFound(f"Estudio desconocido: {name}")

    @staticmethod
    def _needs_convergence(study):
        finished = study.get("state") in ("completed", "failed", "interrupted")
        return finished and study.get("workdir") and not study.get("series_json")

    def _convergence(self, run, study):
        """Parse a finished study's output: local copy first, then the live host.

        A collected log tail (see ``SSHExecutor.collect``) would give a partial series,
        so it is skipped in favour of the host.
        """
        relative = PurePosixPath(study["name"], study["workdir"]).as_posix()
        for base in (run.get("local_folder"), run["remote_folder"]):
            log = Path(base or "") / relative / "stdout.log"
            if base and log.is_file() and not is_truncated(log):
                return convergence(str(Path(base) / relative))
        stream = self.supervisor.streams.get(run["host_id"]) if self.supervisor else None
        if stream is None or not stream.connected:
            return None  # never block the UI on a new SSH handshake to an offline host
        command = {"cmd": "convergence", "folder": run["remote_folder"], "path": relative}
        try:
            reply = stream.request(command, timeout=30)
        except TransportError:
            return None
        return reply.get("summary") if reply.get("ok") else None

    def study_log(self, run_id, name, stream="stdout"):
        run = self._run(run_id)
        study = self.study(run_id, name)
        if not study.get("workdir"):
            raise ValueError("El estudio todavía no tiene carpeta de ejecución")
        filename = LOG_FILES.get(stream)
        if filename is None:
            raise ValueError("stream debe ser stdout o stderr")
        relative = PurePosixPath(name, study["workdir"], filename).as_posix()
        return {"text": self._tail(run, relative), "path": relative}

    def worker_log(self, run_id, live=False):
        run = self._run(run_id)
        if live:
            return {"text": self._tail(run, "worker.log")}
        return {"text": run.get("log_tail") or ""}

    def _tail(self, run, relative):
        command = {"cmd": "tail", "folder": run["remote_folder"], "path": relative}
        command["bytes"] = 131072
        if self.supervisor is not None:
            reply = self.supervisor.request(run["host_id"], command)
        else:
            replies = make_transport(self.project.host(run["host_id"])).watcher_once(
                [{**command, "id": 1}]
            )
            reply = next(m for m in replies if m["t"] == "reply")
        if not reply.get("ok"):
            raise ValueError(reply.get("error", "No disponible"))
        return reply.get("text", "")

    def entries(self):
        return [
            {
                "id": entry.id,
                "label": entry.label,
                "kind": entry.kind,
                "paths": entry.paths(self.project.root),
                "resume": bool(entry.resume),
            }
            for entry in self.project.entries.values()
        ]

    def preview(self, entry_id, path, host_id=None):
        return self.project.describe(entry_id, path, host_id=host_id)

    def changes(self, rev, event_id):
        data = self.registry.changes(rev, event_id)
        data["runs"] = [slim_run(r) for r in data["runs"]]
        data["studies"] = [slim_study(s) for s in data["studies"]]
        data["hosts"] = [
            {
                "id": h["id"],
                "stream_state": h["stream_state"],
                "stream_error": h["stream_error"],
                "heartbeat": h.get("heartbeat_json"),
                "hello": h.get("hello_json"),
            }
            for h in data["hosts"]
        ]
        return data

    # Actions -----------------------------------------------------------------------------
    def preflight(self, host_id):
        return run_preflight(self.project.host(host_id))

    def reconnect(self, host_id):
        self.project.host(host_id)
        if self.supervisor is not None:
            self.supervisor.reconnect(host_id)
        return {"ok": True}

    def launch(self, payload):
        entry = payload.get("entry")
        path = payload.get("path")
        if not isinstance(entry, str) or not isinstance(path, str):
            raise ValueError("entry y path son obligatorios")  # noqa: TRY004 -- HTTP 400
        args = payload.get("args") or []
        if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
            raise ValueError("args debe ser una lista de textos")
        run_id = launch_entry(
            self.project,
            self.registry,
            entry,
            path,
            host_id=payload.get("host") or None,
            args=args,
            origin="ui",
        )
        return {"run_id": run_id}

    def _delete_files(self, runs, skipped):
        source = Path(__file__).with_name("cleanup_script.py").read_text()
        targets = {}
        for run in runs:
            host = self.project.host(run["host_id"])
            targets[(host.id, run["remote_folder"])] = (host, host.campaigns_root)
            if run.get("local_folder"):
                local = self.project.local_host()
                targets[(local.id, run["local_folder"])] = (local, str(self.project.local_runs))
        # Validate all destinations first. If deletion fails, retain history for retry.
        permitted = []
        for (host_id, folder), (host, root) in targets.items():
            result = json.loads(make_transport(host).python(
                source, str(root), folder, "check", timeout=120
            ))
            if result["skipped"]:
                skipped.append({"host_id": host_id, "folder": folder, "reason": result["reason"]})
            else:
                permitted.append((host, root, folder))
        for host, root, folder in permitted:
            result = json.loads(make_transport(host).python(
                source, str(root), folder, "delete", timeout=120
            ))
            if result["skipped"]:
                skipped.append({"host_id": host.id, "folder": folder, "reason": result["reason"]})

    def _delete_history(self, run_id=None, *, files=False):
        skipped = []
        deleted = self.registry.delete_runs(
            run_id,
            before_delete=(lambda runs: self._delete_files(runs, skipped)) if files else None,
        )
        return {"deleted_runs": deleted, "skipped_folders": skipped}

    def delete(self, run_id, *, files=False):
        self._run(run_id)
        return self._delete_history(run_id, files=files)

    def clear_history(self, *, files=False):
        return self._delete_history(files=files)

    def cancel(self, run_id):
        self._run(run_id)
        try:
            cancel_run(self.project, self.registry, run_id, supervisor=self.supervisor)
        except TransportError as exc:
            raise RuntimeError(str(exc)) from exc
        return {"ok": True}

    def resume(self, run_id):
        run = self._run(run_id)
        if run["status"] in ACTIVE:
            raise ValueError("El run sigue activo")
        if not run.get("entry_id") or not run.get("entry_path"):
            raise ValueError("Este run no tiene una entrada conocida; lánzalo desde su YAML")
        new_id = launch_entry(
            self.project,
            self.registry,
            run["entry_id"],
            run["entry_path"],
            host_id=run["host_id"],
            action="resume",
            origin="ui",
        )
        return {"run_id": new_id}

    def collect(self, run_id, raw=False, full_logs=False):
        run = self._run(run_id)
        if run.get("worker_alive"):
            raise ValueError("El worker sigue escribiendo resultados; descarga cuando termine")
        host = self.project.host(run["host_id"])
        if host.transport != "ssh":
            raise ValueError("Los runs locales ya están en este equipo")
        argv = [sys.executable, "-m", "pydelling.monitor", "collect"]
        argv += ["--project", str(self.project.root), "--run", run_id]
        if raw:
            argv.append("--raw")
        if full_logs:
            argv.append("--full-logs")
        payload = {"raw": bool(raw), "full_logs": bool(full_logs)}
        self.registry.add_event(run_id, "collect.queued", payload=payload)
        spawn_detached(argv, self.project.root, launch_log(self.project, run_id, "collect"))
        return {"ok": True}

    def _results_folder(self, run):
        """Where this machine holds the run's files: the download, or the run itself if local."""
        local = run.get("local_folder")
        if local and Path(local).is_dir():
            return Path(local)
        if self._is_local(run["host_id"]) and Path(run["remote_folder"]).is_dir():
            return Path(run["remote_folder"])
        return None

    def tables(self, run_id):
        """CSV tables of the run available on this machine (empty until downloaded)."""
        base = self._results_folder(self._run(run_id))
        return {"tables": list_tables(base) if base else []}

    def table(self, run_id, path, offset=0, limit=DEFAULT_PAGE, query=""):
        """One page of a downloaded CSV table; ``query`` filters rows by text."""
        base = self._results_folder(self._run(run_id))
        if base is None:
            raise NotFound("Este run todavía no tiene resultados en este equipo; descárgalos primero")
        return read_table(base, path or "", offset=offset, limit=limit, query=query)

    def open_folder(self, run_id):
        run = self._run(run_id)
        folder = run.get("local_folder")
        if not folder or not Path(folder).is_dir():
            raise ValueError("No hay carpeta local para este run")
        if os.name == "nt":
            os.startfile(folder)
        else:
            opener = "open" if sys.platform == "darwin" else "xdg-open"
            subprocess.Popen([opener, folder])
        return {"ok": True, "folder": folder}
