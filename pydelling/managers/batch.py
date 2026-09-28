"""Durable PFLOTRAN batches. Execution never changes process cwd or global env."""

import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

import h5py
import numpy as np

TIME_UNITS = {
    "s": 1.0,
    "sec": 1.0,
    "min": 60.0,
    "h": 3600.0,
    "hr": 3600.0,
    "d": 86400.0,
    "day": 86400.0,
    "y": 31557600.0,
    "yr": 31557600.0,
}


def time_seconds(key):
    match = re.fullmatch(r"Time:\s*([+\-\d.eEdD]+)\s*\[?(\w+)\]?", key.strip())
    if not match or match[2].lower() not in TIME_UNITS:
        raise ValueError(f"Unsupported PFLOTRAN time key: {key}")
    return float(match[1].replace("D", "E").replace("d", "e")) * TIME_UNITS[match[2].lower()]


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")
    os.replace(tmp, path)


EVENTS_FILE = "events.jsonl"
CANCEL_FILE = "cancel.request"
_EVENTS_LOCK = threading.Lock()


def append_event(folder, event_type, **payload):
    """Append one JSON line to the campaign event log read by monitors."""
    record = {**payload, "ts": time.time(), "type": event_type}
    line = (json.dumps(record, sort_keys=True, default=str) + "\n").encode()
    path = Path(folder) / EVENTS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    # One write() per O_APPEND line keeps records whole across threads/processes.
    with _EVENTS_LOCK:
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            os.write(fd, line)
        finally:
            os.close(fd)


def cancel_requested(folder):
    return (Path(folder) / CANCEL_FILE).exists()


def request_cancel(folder, origin="api"):
    """Ask running batches in ``folder`` to stop; idempotent and cross-platform."""
    if cancel_requested(folder):
        return
    atomic_json(Path(folder) / CANCEL_FILE, {"origin": origin, "requested": time.time()})
    append_event(folder, "cancel.requested", origin=origin)


def clear_cancel(folder):
    (Path(folder) / CANCEL_FILE).unlink(missing_ok=True)


@contextmanager
def campaign_lock(folder):
    """OS-owned lock, automatically released after a crash (including Windows)."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / ".lock").open("a+b") as stream:
        stream.seek(0)
        if os.name == "nt":
            import msvcrt

            if stream.read(1) == b"":
                stream.write(b"0")
                stream.flush()
            stream.seek(0)
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise RuntimeError("Campaign is already running") from exc
        else:
            import fcntl

            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise RuntimeError("Campaign is already running") from exc
        try:
            yield
        finally:
            if os.name == "nt":
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def check_outputs(folder, expected_times, required_variables):
    """Require every requested HDF5 time/variable and finite numerical output."""
    found = {}
    for path in Path(folder).glob("*.h5"):
        with h5py.File(path, "r") as data:
            for key in data:
                if not key.startswith("Time:"):
                    continue
                seconds = time_seconds(key)
                if all(name in data[key] for name in required_variables):
                    for name in required_variables:
                        values = data[key][name][...]
                        if not values.size or not np.isfinite(values).all():
                            raise ValueError(f"Invalid values in {path.name}: {name}")
                    found[seconds] = path.name
    for expected in expected_times:
        if not any(np.isclose(expected, actual, rtol=2e-5, atol=1e-5) for actual in found):
            raise ValueError(f"Missing complete HDF5 snapshot at {expected} s")
    if not found:
        raise ValueError("No complete HDF5 output")
    return {str(t): name for t, name in found.items()}


@dataclass
class BatchResult:
    states: dict

    @property
    def successful(self):
        return all(s["state"] == "completed" for s in self.states.values())


@dataclass
class LocalExecutor:
    executable: str = "pflotran"
    workers: int = 4
    mpi_ranks: int = 1
    mpiexec: str = "mpiexec"
    timeout: float = 3600.0
    env: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.workers < 1 or self.mpi_ranks < 1 or self.timeout <= 0:
            raise ValueError("workers, mpi_ranks and timeout must be positive")

    def provenance(self):
        binary = shutil.which(self.executable) or self.executable
        if not Path(binary).is_file():
            raise FileNotFoundError(f"PFLOTRAN executable not found: {self.executable}")
        # Prefer the actual executable in configuration, not a shell wrapper.
        return {
            "binary": str(Path(binary).resolve()),
            "sha256": file_hash(binary),
            "mpi_ranks": self.mpi_ranks,
            "mpiexec": self.mpiexec,
            "env": self.env,
        }

    def _execute(self, study, folder, expected_times, required_variables, identity):
        state_path = folder / "status.json"
        campaign = folder.parent
        previous = json.loads(state_path.read_text()) if state_path.exists() else {}
        if self._stop.is_set() or cancel_requested(campaign):
            if previous.get("state") == "running":
                previous["state"] = "interrupted"
                atomic_json(folder / previous["workdir"] / "status.json", previous)
            now = time.time()
            state = {
                "state": "interrupted",
                "identity": identity,
                "error": "Cancelled before start",
                "started": now,
                "finished": now,
                "runtime_s": 0.0,
            }
            atomic_json(state_path, state)
            append_event(campaign, "study.state", study=study.name, state="interrupted")
            return state
        attempts = folder / "attempts"
        attempts.mkdir(exist_ok=True)
        attempt = max([int(p.name) for p in attempts.iterdir() if p.name.isdigit()] + [0]) + 1
        work = attempts / f"{attempt:04d}"
        work.mkdir()
        state = {
            "state": "running",
            "attempt": attempt,
            "identity": identity,
            "started": time.time(),
            "workdir": str(work.relative_to(folder)),
        }
        if previous.get("state") == "running":
            previous["state"] = "interrupted"
            atomic_json(folder / previous["workdir"] / "status.json", previous)
        atomic_json(state_path, state)
        process = None
        try:
            study.to_file(work)
            command = [self.executable, "-pflotranin", study.input_file_name]
            if self.mpi_ranks > 1:
                command = [self.mpiexec, "-n", str(self.mpi_ranks)] + command
            state["command"] = command
            with (work / "stdout.log").open("wb") as out, (work / "stderr.log").open("wb") as err:
                process = subprocess.Popen(
                    command,
                    cwd=work,
                    env={**os.environ, **self.env},
                    stdout=out,
                    stderr=err,
                    start_new_session=os.name != "nt",
                )
                state["pid"] = process.pid
                proc = Path(f"/proc/{process.pid}/stat")
                state["process_start"] = proc.read_text().split()[21] if proc.exists() else None
                atomic_json(state_path, state)
                append_event(
                    campaign, "study.state", study=study.name, state="running", attempt=attempt
                )
                deadline = time.monotonic() + self.timeout
                while True:
                    if self._stop.is_set() or cancel_requested(campaign):
                        raise InterruptedError("Batch cancelled")
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise subprocess.TimeoutExpired(command, self.timeout)
                    try:
                        state["returncode"] = process.wait(timeout=min(0.2, remaining))
                        break
                    except subprocess.TimeoutExpired:
                        continue
            if state["returncode"] != 0:
                raise RuntimeError(f"PFLOTRAN returned {state['returncode']}")
            state["outputs"] = check_outputs(work, expected_times, required_variables)
            state["output_hashes"] = {
                name: file_hash(work / name) for name in set(state["outputs"].values())
            }
            state["state"] = "completed"
        except (
            Exception,  # noqa: BLE001 -- record per-study errors, including library failures
            KeyboardInterrupt,
            SystemExit,
        ) as exc:  # persist failure before returning
            if process and process.poll() is None:
                if os.name == "nt":
                    subprocess.run(
                        ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                        capture_output=True,
                        check=False,
                    )
                else:
                    os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            state["state"] = (
                "interrupted"
                if isinstance(exc, (KeyboardInterrupt, SystemExit, InterruptedError))
                else "failed"
            )
            state["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            state["finished"] = time.time()
            state["runtime_s"] = state["finished"] - state["started"]
            atomic_json(work / "status.json", state)
            atomic_json(state_path, state)
            details = {"error": state["error"]} if "error" in state else {}
            append_event(
                campaign,
                "study.state",
                study=study.name,
                state=state["state"],
                attempt=attempt,
                runtime_s=round(state["runtime_s"], 3),
                **details,
            )
        return state

    @contextmanager
    def pipeline(self, folder):
        """Hold the campaign lock across several gated batches and collection."""
        folder = Path(folder).resolve()
        with campaign_lock(folder):
            self._locked_folder = folder
            try:
                yield
            finally:
                self._locked_folder = None

    def run_batch(
        self, studies, folder, requirements, *, resume=True, provenance=None, batch_name="batch"
    ):
        folder = Path(folder).resolve()
        if getattr(self, "_locked_folder", None) == folder:
            return self._run_locked(studies, folder, requirements, resume, provenance, batch_name)
        with campaign_lock(folder):
            return self._run_locked(studies, folder, requirements, resume, provenance, batch_name)

    def _run_locked(self, studies, folder, requirements, resume, provenance, batch_name):
        studies = list(studies)
        names = [s.name for s in studies]
        if len(set(names)) != len(names) or any(
            not re.fullmatch(r"[\w.-]+", n) or n in (".", "..") for n in names
        ):
            raise ValueError("Study names must be unique safe directory names")
        identity_data = {
            "solver": self.provenance(),
            "provenance": provenance,
            "requirements": requirements,
            "studies": {
                s.name: {
                    "deck": s.render(),
                    "files": {name: file_hash(p) for name, p in s.aux_files.items()},
                }
                for s in studies
            },
        }
        identity = fingerprint(identity_data)
        if not re.fullmatch(r"[A-Za-z0-9_-]+", batch_name):
            raise ValueError("Unsafe batch name")
        manifest_path = folder / f"{batch_name}-batch.json"
        if manifest_path.exists() and json.loads(manifest_path.read_text())["identity"] != identity:
            raise ValueError("Incompatible campaign: use a new campaign directory")
        atomic_json(manifest_path, {"identity": identity, **identity_data})
        states = {}
        pending = []
        for study in studies:
            study_folder = folder / study.name
            study_folder.mkdir(exist_ok=True)
            status = study_folder / "status.json"
            state = json.loads(status.read_text()) if status.exists() else {"state": "pending"}
            if state["state"] == "running" and state.get("process_start"):
                proc = Path(f"/proc/{state.get('pid')}/stat")
                if (
                    proc.exists()
                    and proc.read_text().split()[21] == state["process_start"]
                    and proc.read_text().split()[2] != "Z"
                ):
                    raise RuntimeError(
                        f"Solver for {study.name} is still running; refusing duplicate execution"
                    )
            if resume and state["state"] == "completed":
                try:
                    check_outputs(study_folder / state["workdir"], **requirements[study.name])
                    if any(
                        file_hash(study_folder / state["workdir"] / name) != digest
                        for name, digest in state.get("output_hashes", {}).items()
                    ):
                        raise ValueError("Output content changed")
                    states[study.name] = state
                    continue
                except (ValueError, OSError, KeyError):
                    pass
            if not status.exists():
                atomic_json(status, state)
            pending.append((study, study_folder))
        self._stop = threading.Event()
        append_event(
            folder, "batch.started", batch=batch_name, studies=len(studies), pending=len(pending)
        )
        try:
            with ThreadPoolExecutor(max_workers=self.workers) as pool:
                futures = [
                    (
                        s.name,
                        pool.submit(
                            self._execute, s, dest, **requirements[s.name], identity=identity
                        ),
                    )
                    for s, dest in pending
                ]
                try:
                    for name, future in futures:
                        states[name] = future.result()
                except KeyboardInterrupt:
                    self._stop.set()
                    raise
        finally:
            counts = {}
            for record in states.values():
                counts[record["state"]] = counts.get(record["state"], 0) + 1
            append_event(folder, "batch.finished", batch=batch_name, counts=counts)
        return BatchResult(states)
