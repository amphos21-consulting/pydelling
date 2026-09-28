"""Keep one watcher stream per host and fold its messages into the registry.

Each host gets a thread that starts the watcher (``ssh … python3 -c``, or the local
interpreter), sends it the offsets already stored, applies every message, and
reconnects with exponential backoff. Commands (``tail``, ``cancel``) travel over the
same stream, so a password-free handshake happens once per connection.
"""

import itertools
import json
import subprocess
import threading

from .registry import CLIENT_PHASES, derive_status
from .transport import WATCHER_SOURCE, TransportError, classify_ssh_failure, make_transport
from .watcher_script import process_alive

STUDY_FIELDS = ("state", "attempt", "started", "finished", "runtime_s", "returncode", "error")
PROGRESS_FIELDS = (
    "sim_time_s",
    "final_time_s",
    "dt_s",
    "step",
    "cuts",
    "newton",
    "wall_s",
    "unit",
)


def summarize(event):
    """One-line human message for a worker event."""
    kind = event.get("type", "")
    if kind == "study.state":
        text = f"{event.get('study')}: {event.get('state')}"
        return f"{text} — {event['error']}" if event.get("error") else text
    if kind == "batch.started":
        return f"{event.get('batch')}: {event.get('pending')} de {event.get('studies')} estudios"
    if kind == "batch.finished":
        counts = ", ".join(f"{k} {v}" for k, v in sorted((event.get("counts") or {}).items()))
        return f"{event.get('batch')}: {counts}"
    if kind == "verification.gate":
        return "Verificación analítica superada" if event.get("passed") else "Verificación fallida"
    if kind == "campaign.state":
        return f"Campaña {event.get('state')}"
    if kind == "cancel.requested":
        return "Cancelación solicitada"
    return None


def event_level(event):
    if event.get("state") in ("failed",) or event.get("passed") is False:
        return "error"
    if (
        event.get("state") in ("interrupted", "cancelled")
        or event.get("type") == "cancel.requested"
    ):
        return "warning"
    return "info"


class HostStream(threading.Thread):
    def __init__(self, supervisor, host):
        super().__init__(name=f"runs-stream-{host.id}", daemon=True)
        self.supervisor = supervisor
        self.host = host
        self.transport = make_transport(host)
        self.stopping = threading.Event()
        self.wake = threading.Event()
        self.process = None
        self.pending = {}
        self.ids = itertools.count(1)
        self.connected = False
        self._write_lock = threading.Lock()

    def run(self):
        registry = self.supervisor.registry
        backoff = 1.0
        while not self.stopping.is_set():
            registry.set_host_stream(self.host.id, "connecting")
            stderr = []
            try:
                self.process = subprocess.Popen(
                    self.transport.watcher_argv(),
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            except OSError as exc:
                registry.set_host_stream(self.host.id, "missing_ssh", str(exc))
                self._sleep(backoff)
                backoff = min(60.0, backoff * 2)
                continue
            reader = threading.Thread(
                target=stderr.extend, args=(self.process.stderr,), daemon=True
            )
            reader.start()
            init = {
                "roots": [self.host.campaigns_root],
                "known": registry.known(self.host.id),
                "interval": self.supervisor.interval,
            }
            try:
                self._send(init)
                for line in self.process.stdout:
                    try:
                        message = json.loads(line)
                    except ValueError:
                        continue
                    if message.get("t") == "hello":
                        self.connected = True
                        backoff = 1.0
                    if message.get("t") == "reply":
                        waiter = self.pending.pop(message.get("id"), None)
                        if waiter:
                            waiter[1].update(message)
                            waiter[0].set()
                        continue
                    try:
                        self.supervisor.apply(self.host.id, message)
                    except Exception as exc:  # noqa: BLE001 -- one bad message must not kill the stream
                        registry.set_host_stream(
                            self.host.id, "connected", f"{type(exc).__name__}: {exc}"
                        )
            except (OSError, ValueError):
                pass
            self.connected = False
            code = self.process.wait()
            reader.join(timeout=2)
            for event, _ in list(self.pending.values()):
                event.set()
            self.pending.clear()
            if self.stopping.is_set():
                break
            text = "".join(stderr)[-4000:]
            if self.host.transport == "ssh" and code == 255:
                state, message = classify_ssh_failure(code, text)
            else:
                state, message = "error", text.strip()[-500:] or f"watcher exit {code}"
            registry.set_host_stream(self.host.id, state, message)
            self._sleep(backoff)
            backoff = min(60.0, backoff * 2)
        registry.set_host_stream(self.host.id, "offline")

    def _sleep(self, seconds):
        self.wake.wait(seconds)
        self.wake.clear()

    def _send(self, message):
        with self._write_lock:
            self.process.stdin.write(json.dumps(message) + "\n")
            self.process.stdin.flush()

    def request(self, command, timeout=15):
        if not self.connected or self.process is None:
            raise TransportError("offline", "Sin conexión en vivo con el host")
        request_id = next(self.ids)
        done, reply = threading.Event(), {}
        self.pending[request_id] = (done, reply)
        self._send({**command, "id": request_id})
        if not done.wait(timeout) or not reply:
            self.pending.pop(request_id, None)
            raise TransportError("unreachable", "El host no respondió a tiempo")
        return reply

    def stop(self):
        self.stopping.set()
        self.wake.set()
        if self.process and self.process.poll() is None:
            try:
                self.process.stdin.close()
            except OSError:
                pass
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()


class Supervisor:
    def __init__(self, project, registry, *, hosts=None, interval=1.0):
        self.project = project
        self.registry = registry
        self.interval = interval
        self._hosts = hosts
        self.streams = {}
        self.run_ids = {}
        self.snapshots = {}  # local folder of a downloaded copy -> run id
        self._maintenance = None
        self._stopping = threading.Event()
        self._known_hosts = set()

    def hosts(self):
        return list(self._hosts) if self._hosts is not None else self.project.hosts()

    def host(self, host_id):
        for host in self.hosts():
            if host.id == host_id:
                return host
        raise ValueError(f"Unknown host: {host_id}")

    def register_hosts(self):
        for host in self.hosts():
            self.registry.upsert_host(host.registry_fields())

    def start(self):
        self.register_hosts()
        for host in self.hosts():
            stream = HostStream(self, host)
            self.streams[host.id] = stream
            stream.start()
        self._maintenance = threading.Thread(target=self._maintain_loop, daemon=True)
        self._maintenance.start()

    def stop(self):
        self._stopping.set()
        for stream in self.streams.values():
            stream.stop()
        for stream in self.streams.values():
            stream.join(timeout=10)

    def reconnect(self, host_id):
        stream = self.streams.get(host_id)
        if stream:
            stream.wake.set()
            if stream.process and stream.process.poll() is None:
                stream.process.terminate()

    def _maintain_loop(self):
        while not self._stopping.wait(5):
            try:
                self.maintain()
            except Exception:  # noqa: BLE001, S110 -- best-effort background housekeeping
                pass

    def maintain(self):
        """Fail runs whose client-side launcher died before starting a worker."""
        for run in self.registry.list_runs(active=True, limit=1000):
            if run["status"] not in CLIENT_PHASES:
                continue
            pid = self.registry.get_run(run["id"]).get("launcher_pid")
            if pid and process_alive({"pid": pid}) is False:
                message = "El proceso lanzador terminó antes de iniciar el worker"
                self.registry.update_run(
                    run["id"], status="failed", launch_failed=1, error=message, launcher_pid=None
                )
                self.registry.add_event(run["id"], "launch.lost", level="error", message=message)

    def request(self, host_id, command, timeout=15):
        """Send a watcher command over the live stream, or a one-shot connection."""
        stream = self.streams.get(host_id)
        if stream is not None and stream.connected:
            return stream.request(command, timeout)
        replies = make_transport(self.host(host_id)).watcher_once([{**command, "id": 1}])
        return next(m for m in replies if m["t"] == "reply")

    def sync_once(self, host_id):
        """One full scan without a live stream (``python -m pydelling.monitor sync``)."""
        self.register_hosts()
        transport = make_transport(self.host(host_id))
        init = {
            "roots": [transport.host.campaigns_root],
            "known": self.registry.known(host_id),
            "once": True,
        }
        result = transport.run(
            ["python3", "-u", "-c", WATCHER_SOURCE],
            input=json.dumps(init) + "\n",
            timeout=300,
        )
        for line in result.stdout.splitlines():
            if line.strip():
                self.apply(host_id, json.loads(line))
        self.registry.set_host_stream(host_id, "offline")

    # Message application ---------------------------------------------------------------
    def _ensure_host(self, host_id):
        if host_id in self._known_hosts:
            return
        if self.registry.get_host(host_id) is None:
            try:
                self.registry.upsert_host(self.host(host_id).registry_fields())
            except ValueError:
                self.registry.upsert_host({"id": host_id, "transport": "ssh"})
        self._known_hosts.add(host_id)

    def apply(self, host_id, message):
        kind = message.get("t")
        if kind in ("hello", "heartbeat"):
            self._ensure_host(host_id)
        if kind == "hello":
            self.registry.set_host_stream(host_id, "connected", hello=message)
        elif kind == "heartbeat":
            self.registry.set_host_stream(host_id, "connected", heartbeat=message)
        elif kind == "campaign":
            self._campaign(host_id, message)
        elif kind in ("study", "event", "log", "progress"):
            run_id, live = self._target(host_id, message["folder"])
            if run_id is None or not live:
                return
            getattr(self, f"_{kind}")(run_id, message)
        elif kind == "cursor":
            if (host_id, message["folder"]) in self.snapshots:
                return  # downloaded copies never claim the live host's cursor
            run_id, _ = self._target(host_id, message["folder"])
            if run_id:
                self.registry.update_run(run_id, remote_mtime=message["mtime"])
        elif kind == "warning":
            run_id, _ = self._target(host_id, message["folder"])
            if run_id:
                self.registry.add_event(
                    run_id,
                    "watcher.warning",
                    source="monitor",
                    level="warning",
                    message=f"{message.get('path')}: {message.get('message')}",
                )

    def _target(self, host_id, folder):
        """(run id, whether its data should be applied) for a watcher folder."""
        key = (host_id, folder)
        if key in self.snapshots:
            run_id = self.snapshots[key]
            run = self.registry.get_run(run_id)
            return run_id, bool(run) and run.get("remote_mtime") is None
        run_id = self.run_ids.get(key)
        if run_id is None:
            run = self.registry.find_run(host_id, folder)
            run_id = run["id"] if run else None
            if run_id:
                self.run_ids[key] = run_id
        return run_id, True

    def _host_for_copy(self, remote_folder, download):
        hosts = [h for h in self.hosts() if h.transport == "ssh"]
        target = (download or {}).get("host")
        for host in hosts:
            if target and host.ssh == target:
                return host.id
        for host in hosts:
            if remote_folder.startswith(host.campaigns_root.rstrip("/") + "/"):
                return host.id
        return None

    def _campaign(self, host_id, message):
        folder = message["folder"]
        mirror = message.get("mirror") or {}
        download = message.get("download") or {}
        if not mirror.get("remote_folder") and download.get("folder"):
            mirror = {"remote_folder": download["folder"]}
        snapshot = False
        if mirror.get("remote_folder"):
            remote_host = self._host_for_copy(mirror["remote_folder"], message.get("download"))
            if remote_host:
                snapshot = True
                run = self._ensure(remote_host, mirror["remote_folder"], message)
                self.snapshots[(host_id, folder)] = run["id"]
                if run.get("local_folder") != folder:
                    self.registry.update_run(run["id"], local_folder=folder)
                if message.get("download"):
                    # Idempotent marker (fixed offset): the results exist on this machine.
                    self.registry.add_event(
                        run["id"],
                        "collect.done",
                        source="monitor",
                        remote_offset=-1,
                        message=f"Resultados descargados en {folder}",
                    )
                if run.get("remote_mtime") is not None:
                    return  # the live host already owns this run
        if not snapshot:
            run = self._ensure(host_id, folder, message)
            self.run_ids[(host_id, folder)] = run["id"]
        exit_info = message.get("exit") or {}
        updates = {
            "campaign_json": message.get("campaign"),
            "worker_json": message.get("worker"),
            "worker_alive": 1 if message.get("alive") else 0,
            "exit_code": exit_info.get("returncode"),
            "cancel_requested": 1 if message.get("cancel_requested") else 0,
            "config_json": message.get("config"),
        }
        worker = message.get("worker") or {}
        campaign = message.get("campaign") or {}
        started = worker.get("launched") or campaign.get("started")
        if started:
            updates["started_at"] = started
        finished = exit_info.get("finished") or campaign.get("finished")
        if finished and not message.get("alive"):
            updates["finished_at"] = finished
        preview = message.get("preview")
        if isinstance(preview, dict) and preview.get("study_count"):
            updates["preview_json"] = preview
        if not snapshot:
            updates["remote_mtime"] = message.get("mtime")
            if host_id == "local" or self._is_local(host_id):
                updates.setdefault("local_folder", folder)
        error = (message.get("campaign") or {}).get("error")
        if error:
            updates["error"] = error
        merged = {**run, **updates}
        status = derive_status(merged)
        if status != run.get("status"):
            updates["status"] = status
            updates["phase"] = status
            self.registry.add_event(
                run["id"],
                "run.status",
                source="monitor",
                level="error" if status in ("failed", "lost") else "info",
                message=f"{run.get('status')} → {status}",
                payload={"from": run.get("status"), "to": status},
            )
        self.registry.update_run(run["id"], **updates)

    def _is_local(self, host_id):
        try:
            return self.host(host_id).transport == "local"
        except ValueError:
            return False

    def _ensure(self, host_id, remote_folder, message):
        run = self.registry.find_run(host_id, remote_folder)
        if run is None:
            config = message.get("config") or {}
            kind = "campaign" if (config or message.get("campaign")) else "script"
            # Only inputs on disk (``prepare``): nothing was launched from this folder.
            launched = any(message.get(k) for k in ("campaign", "worker", "exit", "mirror"))
            launched = launched or bool(message.get("download")) or not message.get("preview")
            self.registry.ensure_run(
                host_id,
                remote_folder,
                name=config.get("campaign") or message.get("name"),
                kind=kind,
                origin="discovered",
                status="unknown" if launched else "prepared",
            )
            run = self.registry.find_run(host_id, remote_folder)
        return run

    def _study(self, run_id, message):
        status = message.get("status") or {}
        fields = {k: status.get(k) for k in STUDY_FIELDS if k in status}
        if "workdir" in status:
            fields["workdir"] = status["workdir"]
        self.registry.upsert_study(run_id, message["name"], **fields)

    def _event(self, run_id, message):
        event = message.get("event") or {}
        self.registry.add_event(
            run_id,
            event.get("type", "event"),
            source="worker",
            level=event_level(event),
            message=summarize(event),
            payload=event,
            remote_offset=message.get("offset"),
            ts=event.get("ts"),
        )
        if message.get("end") is not None:
            self.registry.update_run(run_id, event_offset=message["end"])

    def _log(self, run_id, message):
        self.registry.append_log(run_id, message.get("text", ""), message.get("end", 0))

    def _progress(self, run_id, message):
        fields = {k: message.get(k) for k in PROGRESS_FIELDS if message.get(k) is not None}
        self.registry.upsert_study(
            run_id, message["study"], points=message.get("points") or None, **fields
        )
