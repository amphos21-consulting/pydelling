"""Launch, cancel and collect runs; every action is recorded in the registry.

* Campaign entries run the project's declared command (e.g. ``run_models.py run
  --config <path> --detach``) as a detached local process; that CLI reports its own
  phases through :class:`~pydelling.monitor.reporter.Reporter`.
* Script entries use the generic pipeline here: preflight → deploy the project
  files → start ``uv run python <script> <args>`` under the worker supervisor.
"""

import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from pydelling.managers.batch import CANCEL_FILE
from pydelling.managers.ssh_executor import WORKER_SUPERVISOR

from .preflight import run_preflight
from .registry import CLIENT_PHASES, derive_status
from .reporter import Reporter
from .transport import make_transport
from .watcher_script import process_alive


def spawn_detached(argv, cwd, log_path, env=None):
    """Start ``argv`` detached from this process (and its console); return the pid."""
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    options = {}
    if os.name == "nt":
        options["creationflags"] = (
            subprocess.DETACHED_PROCESS
            | subprocess.CREATE_NEW_PROCESS_GROUP
            | subprocess.CREATE_NO_WINDOW
        )
    else:
        options["start_new_session"] = True
    with log_path.open("ab") as log:
        process = subprocess.Popen(
            [str(a) for a in argv],
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            env={**os.environ, **(env or {})},
            **options,
        )
    # Reap in the background so finished launchers never linger as zombies.
    threading.Thread(target=process.wait, daemon=True).start()
    return process.pid


def terminate(pid):
    """Stop a local process and its children (process group / job tree)."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, check=False)
        return
    try:
        if os.getpgid(pid) == pid:
            os.killpg(pid, signal.SIGTERM)
        else:
            os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass


def launch_log(project, run_id, action):
    return project.local_runs / ".launch-logs" / f"{run_id}-{action}-{int(time.time())}.log"


def launch_entry(
    project,
    registry,
    entry_id,
    path,
    *,
    host_id=None,
    action="run",
    args=(),
    origin="ui",
    spawn=True,
):
    """Validate an entry, create/refresh its run row and start the launcher process."""
    entry, path = project.resolve_entry(entry_id, path)
    if entry.kind == "script" and action != "run":
        raise ValueError("Los scripts solo admiten la acción run")
    command = entry.run if action == "run" else entry.resume
    if entry.kind == "campaign" and not command:
        raise ValueError(f"La entrada {entry_id} no define la acción {action}")
    target = project.describe(entry_id, path, host_id=host_id)
    project.host(target["host_id"])
    created = (
        {}
        if registry.find_run(target["host_id"], target["remote_folder"])
        else {
            "origin": origin,
            "kind": entry.kind,
        }
    )
    run_id = registry.ensure_run(
        target["host_id"], target["remote_folder"], name=target["name"], **created
    )
    fields = {
        "status": "queued",
        "phase": "queued",
        "launch_failed": 0,
        "error": None,
        "entry_id": entry_id,
        "entry_path": path,
        "local_folder": target.get("local_folder"),
    }
    if entry.kind == "script":
        fields["argv_json"] = [str(a) for a in args]
    if target.get("study_count"):
        fields["preview_json"] = {"study_count": target["study_count"]}
    registry.update_run(run_id, **fields)
    if entry.kind == "campaign":
        argv = [sys.executable, *[part.replace("{path}", path) for part in command]]
    else:
        argv = [sys.executable, "-m", "pydelling.monitor", "launch-script"]
        argv += ["--project", str(project.root), "--run", run_id]
    registry.add_event(
        run_id, "launch.queued", payload={"action": action, "origin": origin, "argv": argv[1:]}
    )
    if spawn:
        pid = spawn_detached(
            argv,
            project.root,
            launch_log(project, run_id, action),
            env={"PYDELLING_RUNS_ORIGIN": origin},
        )
        registry.update_run(run_id, launcher_pid=pid)
    return run_id


def start_local_worker(folder, argv, cwd):
    """Local twin of ``SSHExecutor.launch_worker``: worker.json, worker.log, exit code."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    for stale in (CANCEL_FILE, "worker-exit.json"):
        (folder / stale).unlink(missing_ok=True)
    pid = spawn_detached(
        [sys.executable, "-c", WORKER_SUPERVISOR, json.dumps(argv), str(folder)],
        cwd,
        folder / "worker.log",
        env={"PYDELLING_RUNS_WORKER": "1"},
    )
    state = {"pid": pid, "start": None, "launched": time.time()}
    temp = folder / "worker.json.tmp"
    temp.write_text(json.dumps(state))
    os.replace(temp, folder / "worker.json")
    return state


def launch_script(project, registry, run_id):
    """Run the generic script pipeline for ``run_id`` (called by the detached launcher)."""
    run = registry.get_run(run_id)
    if run is None or run.get("kind") != "script":
        raise ValueError(f"Run {run_id} is not a script launch")
    host = project.host(run["host_id"])
    reporter = Reporter(registry, run_id)
    reporter.begin("run")
    script, args = run["entry_path"], [str(a) for a in run.get("argv_json") or []]
    try:
        with reporter.stage("preflight", status="preflight"):
            result = run_preflight(
                host,
                on_check=lambda c: reporter.event(
                    "preflight.check",
                    message=f"{c['label']}: {c['detail']}",
                    level={"fail": "error", "warn": "warning"}.get(c["status"], "info"),
                    **c,
                ),
            )
            if not result["ok"]:
                failed = next(c for c in result["checks"] if c["status"] == "fail")
                raise RuntimeError(f"{failed['label']}: {failed['detail']}")
        if host.transport == "local":
            with reporter.stage("start", status="starting"):
                state = start_local_worker(
                    run["remote_folder"],
                    [sys.executable, str(project.root / script), *args],
                    project.root,
                )
                reporter.on_event("worker.started", pid=state["pid"])
            return state
        executor = make_transport(host).executor()
        files = sorted({*project.deploy_files(), Path(script)})
        with reporter.stage("deploy", status="deploying"):
            release, release_id = executor.deploy(project.root, files, on_event=reporter.on_event)
        reporter.update(release_id=release_id)
        with reporter.stage("start", status="starting"):
            executor.command(["mkdir", "-p", run["remote_folder"]])
            argv = [host.uv, "run", "--locked", "--no-dev", "--project", release]
            argv += ["python", f"{release}/{script}", *args]
            state = executor.launch_worker(release, run["remote_folder"], argv)
            reporter.on_event("worker.started", pid=state.get("pid"))
        return state
    except BaseException as exc:
        reporter.fail(str(exc) or type(exc).__name__)
        raise


def cancel_run(project, registry, run_id, supervisor=None):
    """Stop a launch in its client phase, or ask the worker to stop cooperatively."""
    run = registry.get_run(run_id)
    if run is None:
        raise ValueError(f"Unknown run: {run_id}")
    if run["status"] in CLIENT_PHASES and run.get("launcher_pid"):
        if process_alive({"pid": run["launcher_pid"]}):
            terminate(run["launcher_pid"])
        message = "Lanzamiento cancelado antes de iniciar el worker"
        registry.update_run(
            run_id, status="cancelled", launch_failed=1, error=message, launcher_pid=None
        )
        registry.add_event(run_id, "launch.cancelled", level="warning", message=message)
        return
    command = {"cmd": "cancel", "folder": run["remote_folder"], "origin": "monitor"}
    if supervisor is not None:
        reply = supervisor.request(run["host_id"], command)
        if not reply.get("ok"):
            raise RuntimeError(reply.get("error", "No se pudo cancelar"))
    else:
        make_transport(project.host(run["host_id"])).cancel(run["remote_folder"])
    updates = {"cancel_requested": 1}
    status = derive_status({**run, **updates})
    registry.update_run(run_id, **updates, status=status, phase=status)
    registry.add_event(run_id, "cancel.sent", level="warning", message="Cancelación enviada")


def collect_run(project, registry, run_id, raw=False):
    """Download results of a finished remote run into its local folder."""
    run = registry.get_run(run_id)
    if run is None:
        raise ValueError(f"Unknown run: {run_id}")
    if run.get("worker_alive"):
        raise ValueError("El worker sigue escribiendo resultados; descarga cuando termine")
    host = project.host(run["host_id"])
    if host.transport == "local":
        return Path(run["remote_folder"])
    local = Path(run.get("local_folder") or project.local_runs / run["name"])
    reporter = Reporter(registry, run_id)
    with reporter.stage("collect"):
        make_transport(host).executor().collect(run["remote_folder"], local, raw=raw)
    marker = local / "remote.json"
    if not marker.exists():
        marker.write_text(json.dumps({"remote_folder": run["remote_folder"], "host": host.ssh}))
    registry.update_run(run_id, local_folder=str(local))
    return local
