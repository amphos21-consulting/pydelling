"""Client-side launch phases written to the project registry.

CLIs (``run_models.py``, ``python -m pydelling.monitor``) report preflight, deploy and
start stages here; the dashboard shows them live. Reporting never breaks a launch:
registry problems are printed and ignored, and inside a detached worker
(``PYDELLING_RUNS_WORKER=1``) there is nothing to report from the client side.
"""

import os
import sqlite3
import sys
import time
from contextlib import contextmanager

from .config import load_project
from .registry import Registry


def _warn(exc):
    print(f"[pydelling.monitor] registro no disponible: {exc}", file=sys.stderr)


class Reporter:
    def __init__(self, registry, run_id):
        self.registry = registry
        self.run_id = run_id

    @classmethod
    def open(
        cls, project_root, *, host_id, remote_folder, name, kind="campaign", origin=None, **fields
    ):
        if os.environ.get("PYDELLING_RUNS_WORKER") or os.environ.get("PYDELLING_RUNS_DISABLE"):
            return None
        try:
            registry = Registry(load_project(project_root).registry_path)
            created = {}
            if registry.find_run(host_id, remote_folder) is None:
                origin = origin or os.environ.get("PYDELLING_RUNS_ORIGIN") or "cli"
                created = {"origin": origin, "kind": kind}
            run_id = registry.ensure_run(host_id, remote_folder, name=name, **created, **fields)
        except (OSError, ValueError, sqlite3.Error) as exc:
            _warn(exc)
            return None
        return cls(registry, run_id)

    def _safe(self, method, *args, **kwargs):
        try:
            return method(*args, **kwargs)
        except sqlite3.Error as exc:
            _warn(exc)
            return None

    def begin(self, action="run"):
        """Start a new launch generation: forget facts about the previous worker."""
        self.update(
            status="queued",
            phase="queued",
            launch_failed=0,
            error=None,
            worker_json=None,
            worker_alive=None,
            exit_code=None,
            campaign_json=None,
            cancel_requested=0,
            launcher_pid=os.getpid(),
            started_at=None,
            finished_at=None,
        )
        self.event("launch.requested", action=action, pid=os.getpid())

    def update(self, **fields):
        self._safe(self.registry.update_run, self.run_id, **fields)

    def event(self, event_type, message=None, level="info", **payload):
        self._safe(
            self.registry.add_event,
            self.run_id,
            event_type,
            level=level,
            message=message,
            payload=payload or None,
        )

    def status(self, status, **fields):
        self.update(status=status, phase=status, **fields)

    def on_event(self, event_type, **payload):
        """Adapter for ``SSHExecutor(on_event=...)`` callbacks."""
        self.event(event_type, **payload)
        if event_type == "worker.started":
            self.status("running", launcher_pid=None)
        elif event_type == "deploy.synced" and payload.get("release"):
            self.update(release_id=payload["release"])

    @contextmanager
    def stage(self, name, status=None):
        if status:
            self.status(status)
        started = time.monotonic()
        self.event(f"{name}.started")
        try:
            yield self
        except BaseException as exc:
            self.event(f"{name}.failed", message=str(exc) or type(exc).__name__, level="error")
            raise
        self.event(f"{name}.done", seconds=round(time.monotonic() - started, 3))

    def fail(self, message, status="failed"):
        self.update(status=status, launch_failed=1, error=message, launcher_pid=None)
        self.event("launch.failed", message=message, level="error")
