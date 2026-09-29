"""Stdlib JSONL watcher."""

import json
import os
import queue
import re
import shutil
import socket
import sys
import threading
import time

VERSION = 1
LOG_CHUNK = 16384
TAIL_MAX = 262144
POINTS_MAX = 64
PARSE_WINDOW = 1048576
IDLE_SECONDS = 30.0
ACTIVE_WINDOW = 600.0
HEARTBEAT_SECONDS = 5.0
CAMPAIGN_FILES = (
    "campaign.json",
    "worker.json",
    "worker-exit.json",
    "config.json",
    "preview.json",
    "cancel.request",
    "remote.json",
    "download.json",
)
TIME_UNITS = {
    "s": 1.0,
    "sec": 1.0,
    "min": 60.0,
    "m": 60.0,
    "h": 3600.0,
    "hr": 3600.0,
    "d": 86400.0,
    "day": 86400.0,
    "w": 604800.0,
    "y": 31557600.0,
    "yr": 31557600.0,
}
STEP = re.compile(r"^\s*Step\s+(\d+)\s+Time=\s*([-+0-9.eEdD]+)\s+Dt=\s*([-+0-9.eEdD]+)\s+\[(\w+)\]")
ITERATIONS = re.compile(r"newton\s*=\s*\d+\s*\[\s*(\d+)\].*?cuts\s*=\s*\d+\s*\[\s*(\d+)\]")
SYSTEM = re.compile(r"^\s*==\s*([A-Z][A-Z0-9 _-]*?)\s*=+\s*$")
WALL = re.compile(r"Wall Clock Time:\s*([-+0-9.eE]+)")


def to_float(text):
    return float(text.replace("d", "e").replace("D", "E"))


def time_to_seconds(value, unit):
    return value * TIME_UNITS[(unit or "s").lower()]


def final_time_seconds(deck_text):
    """FINAL_TIME of a PFLOTRAN deck in seconds, ignoring ``#``/``!`` comments."""
    for line in deck_text.splitlines():
        line = line.split("#")[0].split("!")[0]
        match = re.match(r"\s*FINAL_TIME\s+(\S+)\s*(\w+)?", line, re.IGNORECASE)
        if match:
            try:
                return time_to_seconds(to_float(match[1]), match[2])
            except (ValueError, KeyError):
                return None
    return None


def parse_progress(lines, state):
    """Update ``state`` with PFLOTRAN screen lines; return new ``[t_s, dt_s, cuts]`` points."""
    points = []
    last = state.get("last_t", float("-inf"))
    for line in lines:
        match = SYSTEM.match(line)
        if match:
            state["system"] = match[1].strip()
            continue
        match = STEP.match(line)
        if match:
            try:
                unit = match[4]
                seconds = time_to_seconds(to_float(match[2]), unit)
                dt = time_to_seconds(to_float(match[3]), unit)
            except (ValueError, KeyError):
                continue
            state.update(step=int(match[1]), sim_time_s=seconds, dt_s=dt, unit=unit)
            if seconds > last:
                points.append([seconds, dt, state.get("cuts", 0)])
                last = seconds
            continue
        match = ITERATIONS.search(line)
        if match:
            system = state.get("system", "SOLVER")
            state.setdefault("newton_by", {})[system] = int(match[1])
            state.setdefault("cuts_by", {})[system] = int(match[2])
            state["newton"] = sum(state["newton_by"].values())
            state["cuts"] = sum(state["cuts_by"].values())
            if points:
                points[-1][2] = state["cuts"]
            continue
        match = WALL.search(line)
        if match:
            state["wall_s"] = float(match[1])
    state["last_t"] = last
    return points


def process_alive(worker):
    """True/False when the worker pid can be checked, None when unknown."""
    pid = worker.get("pid")
    if not pid:
        return None
    if os.path.isdir("/proc/self"):
        try:
            with open(f"/proc/{pid}/stat") as stream:
                text = stream.read()
        except OSError:
            return False
        fields = text[text.rindex(")") + 2 :].split()
        token = worker.get("start")
        return fields[0] != "Z" and (token is None or fields[19] == str(token))
    if os.name == "nt":
        import ctypes

        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, int(pid))
        if not handle:
            return False
        code = ctypes.c_ulong()
        ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
        ctypes.windll.kernel32.CloseHandle(handle)
        return code.value == 259
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    try:  # a reaped child of ours is gone, but an unreaped zombie still answers kill(0)
        return os.waitpid(int(pid), os.WNOHANG) == (0, 0)
    except ChildProcessError:
        return True


def lock_held(folder):
    """Probe the campaign OS lock without blocking (pipelines hold it while running)."""
    path = os.path.join(folder, ".lock")
    if not os.path.exists(path):
        return False
    try:
        stream = open(path, "a+b")  # noqa: SIM115 -- OSError here means "unknown", not "held"
    except OSError:
        return None
    with stream:
        try:
            if os.name == "nt":
                import msvcrt

                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(stream, fcntl.LOCK_UN)
        except OSError:
            return True
    return False


def mtime(path):
    try:
        return os.stat(path).st_mtime
    except OSError:
        return None


def read_json(path):
    with open(path, encoding="utf-8") as stream:
        return json.load(stream)


def read_from(path, offset, limit):
    """Complete lines appended after ``offset`` as bytes: (data, start, end, skipped)."""
    try:
        size = os.path.getsize(path)
    except OSError:
        return b"", offset, offset, 0
    if size < offset:  # truncated or replaced
        offset = 0
    skipped = max(0, size - offset - limit)
    start = offset + skipped
    if start == size:
        return b"", size, size, 0
    with open(path, "rb") as stream:
        stream.seek(start)
        data = stream.read(size - start)
    end = data.rfind(b"\n") + 1
    first = data.find(b"\n") + 1
    if skipped and end and first < end:  # drop the partial first line of a tail window
        data, start = data[first:end], start + first
    else:
        data = data[:end]
    return data, start, start + len(data), skipped


def decimate(points, limit=POINTS_MAX):
    if len(points) <= limit:
        return points
    step = len(points) / (limit - 1)
    return [points[int(i * step)] for i in range(limit - 1)] + [points[-1]]


SUMMARY_KEYS = ("step", "sim_time_s", "dt_s", "unit", "newton", "cuts", "wall_s")


def convergence(workdir, deck=None):
    """Summary and decimated Δt series of a study from its full screen output."""
    if not deck:
        decks = sorted(n for n in os.listdir(workdir) if n.endswith(".in"))
        deck = decks[0] if decks else None
    final = None
    if deck:
        try:
            with open(os.path.join(workdir, deck), errors="replace") as stream:
                final = final_time_seconds(stream.read())
        except OSError:
            pass
    best, best_points = None, []
    sources = ["stdout.log"] + ([os.path.splitext(deck)[0] + ".out"] if deck else [])
    for name in sources:
        path = os.path.join(workdir, name)
        if not os.path.isfile(path):
            continue
        state, points, lines = {}, [], []
        with open(path, errors="replace") as stream:
            for line in stream:
                lines.append(line)
                if len(lines) >= 5000:
                    points.extend(parse_progress(lines, state))
                    lines = []
        points.extend(parse_progress(lines, state))
        if "sim_time_s" in state and (best is None or state["sim_time_s"] > best["sim_time_s"]):
            best, best_points = state, points
    summary = {k: (best or {}).get(k) for k in SUMMARY_KEYS}
    summary.update(final_time_s=final, points=decimate(best_points, 256))
    return summary


class Watcher:
    def __init__(self, roots, known=None, interval=1.0, emit=None):
        self.roots = [os.path.abspath(os.path.expanduser(r)) for r in roots]
        self.known = known or {}
        self.interval = max(0.05, float(interval))
        self.emit = emit or self.write
        self.campaigns = {}
        self.last_beat = 0.0
        self.missing = set()

    @staticmethod
    def write(message):
        sys.stdout.write(json.dumps(message, separators=(",", ":"), allow_nan=False) + "\n")
        sys.stdout.flush()

    def hello(self):
        self.emit(
            {
                "t": "hello",
                "version": VERSION,
                "hostname": socket.gethostname(),
                "cpus": os.cpu_count(),
                "python": sys.version.split()[0],
                "platform": sys.platform,
                "roots": self.roots,
            }
        )

    def heartbeat(self, force=False):
        now = time.time()
        if not force and now - self.last_beat < HEARTBEAT_SECONDS:
            return
        self.last_beat = now
        beat = {"t": "heartbeat", "ts": now, "cpus": os.cpu_count(), "load": None}
        if hasattr(os, "getloadavg"):
            beat["load"] = [round(x, 2) for x in os.getloadavg()]
        for root in self.roots:
            try:
                usage = shutil.disk_usage(root)
            except OSError:
                continue
            beat.update(disk_free=usage.free, disk_total=usage.total)
            break
        self.emit(beat)

    def discover(self):
        for root in self.roots:
            try:
                entries = sorted(os.scandir(root), key=lambda e: e.name)
            except OSError:
                continue
            for entry in entries:
                if entry.name.startswith(".") or not entry.is_dir():
                    continue
                folder = entry.path
                if folder in self.campaigns:
                    continue
                markers = (
                    "campaign.json",
                    "worker.json",
                    "config.json",
                    "events.jsonl",
                    "remote.json",
                    "download.json",
                )
                if any(os.path.exists(os.path.join(folder, m)) for m in markers):
                    known = self.known.get(folder, {})
                    self.campaigns[folder] = {
                        "since": known.get("mtime") or 0.0,
                        "event_offset": known.get("event_offset", 0),
                        "log_offset": known.get("log_offset", 0),
                        "files": {},
                        "studies": {},
                        "tracks": {},
                        "last_scan": 0.0,
                        "last_change": 0.0,
                        "sent": None,
                    }

    def warn(self, folder, path, exc):
        rel = os.path.relpath(path, folder).replace(os.sep, "/")
        self.emit({"t": "warning", "folder": folder, "path": rel, "message": str(exc)})

    def scan(self, force=False):
        for folder in set(self.known) | set(self.campaigns):
            try:
                os.stat(folder)
            except FileNotFoundError:
                if folder not in self.missing:
                    self.emit({"t": "missing", "folder": folder})
                    self.missing.add(folder)
                self.campaigns.pop(folder, None)
            except OSError:
                pass  # Only ENOENT proves absence.
            else:
                self.missing.discard(folder)
        self.discover()
        now = time.time()
        for folder, state in list(self.campaigns.items()):
            active = state["sent"] is None or state["sent"].get("alive")
            active = active or now - state["last_change"] < ACTIVE_WINDOW
            if force or active or now - state["last_scan"] >= IDLE_SECONDS:
                state["last_scan"] = now
                self.scan_campaign(folder, state)
        self.heartbeat()

    def scan_campaign(self, folder, state):
        changed = False
        for name in CAMPAIGN_FILES:
            path = os.path.join(folder, name)
            stamp = mtime(path)
            if stamp == state["files"].get(name, (None,))[0]:
                continue
            value = None
            if stamp is not None and name != "cancel.request":
                try:
                    value = read_json(path)
                except (OSError, ValueError) as exc:
                    self.warn(folder, path, exc)
                    state["files"][name] = (stamp, state["files"].get(name, (None, None))[1])
                    continue
            if name == "config.json" and isinstance(value, dict):
                value = {k: value[k] for k in ("campaign", "case", "version") if k in value}
            state["files"][name] = (stamp, value)
            changed = True
        files = {name: value for name, (_, value) in state["files"].items()}
        stamps = [s for s, _ in state["files"].values() if s]
        message = {
            "t": "campaign",
            "folder": folder,
            "name": os.path.basename(folder),
            "campaign": files.get("campaign.json"),
            "worker": files.get("worker.json"),
            "exit": files.get("worker-exit.json"),
            "config": files.get("config.json"),
            "preview": files.get("preview.json"),
            "cancel_requested": state["files"].get("cancel.request", (None,))[0] is not None,
            "mirror": files.get("remote.json"),
            "download": files.get("download.json"),
            "alive": self.alive(folder, state),
            "mtime": max(stamps + [state["since"]]),
        }
        if changed or state["sent"] is None or message["alive"] != state["sent"]["alive"]:
            self.emit(message)
            state["sent"] = message
            state["last_change"] = time.time()
        if self.scan_studies(folder, state) | self.scan_streams(folder, state):
            state["last_change"] = time.time()
        stamps += [stamp for stamp, _ in state["studies"].values() if stamp]
        newest = max(stamps + [state["since"]])
        if newest > state.get("cursor", 0.0):  # lets a reconnect skip what the client has
            state["cursor"] = newest
            self.emit({"t": "cursor", "folder": folder, "mtime": newest})

    def alive(self, folder, state):
        copy = ("remote.json", "download.json")
        if any(state["files"].get(name, (None,))[0] is not None for name in copy):
            return False  # a downloaded copy: its pids belong to the remote host
        worker_stamp, worker = state["files"].get("worker.json", (None, None))
        exit_stamp = state["files"].get("worker-exit.json", (None,))[0]
        if worker_stamp and exit_stamp and exit_stamp >= worker_stamp:
            return False
        if isinstance(worker, dict):
            result = process_alive(worker)
            if result is not None:
                return result
        return bool(lock_held(folder))

    def scan_studies(self, folder, state):
        changed = False
        try:
            entries = list(os.scandir(folder))
        except OSError:
            return False
        for entry in entries:
            if not entry.is_dir() or entry.name.startswith("."):
                continue
            path = os.path.join(entry.path, "status.json")
            stamp = mtime(path)
            if stamp is None or stamp == state["studies"].get(entry.name, (None,))[0]:
                continue
            try:
                status = read_json(path)
            except (OSError, ValueError) as exc:
                state["studies"][entry.name] = (stamp, None)
                self.warn(folder, path, exc)
                continue
            state["studies"][entry.name] = (stamp, status)
            if status.get("state") == "running":
                self.track(folder, state, entry.name, status)
            if stamp > state["since"]:
                self.emit({"t": "study", "folder": folder, "name": entry.name, "status": status})
                changed = True
        return changed

    def track(self, folder, state, name, status):
        workdir = os.path.join(folder, name, status.get("workdir", ""))
        track = state["tracks"].get(name)
        if track and track["workdir"] == workdir:
            return
        deck = (status.get("command") or [""])[-1]
        final = None
        if deck:
            try:
                with open(os.path.join(workdir, deck), errors="replace") as stream:
                    final = final_time_seconds(stream.read())
            except OSError:
                pass
        stem = os.path.splitext(deck)[0] if deck else None
        sources = ["stdout.log"] + ([stem + ".out"] if stem else [])
        state["tracks"][name] = {
            "workdir": workdir,
            "final": final,
            "sources": {s: {"offset": 0, "state": {}} for s in sources},
            "last_t": float("-inf"),
            "sent": None,
        }

    def scan_streams(self, folder, state):
        changed = False
        data, position, end, _ = read_from(
            os.path.join(folder, "events.jsonl"), state["event_offset"], 1 << 30
        )
        for raw in data.splitlines(keepends=True):
            line = raw.decode("utf-8", "replace")
            try:
                event = json.loads(line)
            except ValueError:
                event = {"type": "invalid", "raw": line[:500]}
            message = {"t": "event", "folder": folder, "offset": position}
            message.update(end=position + len(raw), event=event)
            self.emit(message)
            position += len(raw)
            changed = True
        state["event_offset"] = end
        data, start, end, skipped = read_from(
            os.path.join(folder, "worker.log"), state["log_offset"], LOG_CHUNK
        )
        if data:
            text = data.decode("utf-8", "replace")
            message = {"t": "log", "folder": folder, "offset": start, "end": end, "text": text}
            message["skipped"] = skipped
            self.emit(message)
            changed = True
        state["log_offset"] = end
        for name, track in list(state["tracks"].items()):
            running = (state["studies"].get(name, (None, {}))[1] or {}).get("state") == "running"
            changed |= self.progress(folder, name, track)
            if not running:
                del state["tracks"][name]
        return changed

    def progress(self, folder, name, track):
        points = []
        best = None
        for source, info in track["sources"].items():
            path = os.path.join(track["workdir"], source)
            if info["offset"] == 0:
                size = os.path.getsize(path) if os.path.exists(path) else 0
                info["offset"] = max(0, size - PARSE_WINDOW)
            data, _, info["offset"], _ = read_from(path, info["offset"], PARSE_WINDOW)
            if data:
                lines = data.decode("utf-8", "replace").splitlines()
                for point in parse_progress(lines, info["state"]):
                    if point[0] > track["last_t"]:
                        points.append(point)
                        track["last_t"] = point[0]
            if "sim_time_s" in info["state"] and (
                best is None or info["state"]["sim_time_s"] > best["sim_time_s"]
            ):
                best = info["state"]
        if best is None:
            return False
        keys = ("step", "sim_time_s", "dt_s", "unit", "newton", "cuts", "wall_s")
        summary = {k: best.get(k) for k in keys}
        if summary == track["sent"] and not points:
            return False
        track["sent"] = summary
        message = {"t": "progress", "folder": folder, "study": name, "final_time_s": track["final"]}
        message.update(summary)
        message["points"] = decimate(sorted(points))
        self.emit(message)
        return True

    def resolve(self, folder, relative=""):
        folder = os.path.realpath(folder)
        roots = [os.path.realpath(r) for r in self.roots]
        if os.path.dirname(folder) not in roots:
            raise ValueError("Folder is not a watched campaign")
        if not relative:
            return folder
        if os.path.isabs(relative) or os.path.splitdrive(relative)[0]:
            raise ValueError("Path must be relative to the campaign")
        target = os.path.realpath(os.path.join(folder, relative))
        if os.path.commonpath([folder, target]) != folder:
            raise ValueError("Path escapes the campaign folder")
        return target

    def handle(self, command):
        reply = {"t": "reply", "id": command.get("id"), "ok": True}
        try:
            kind = command.get("cmd")
            if kind == "ping":
                pass
            elif kind == "tail":
                path = self.resolve(command.get("folder", ""), command.get("path", ""))
                size = os.path.getsize(path)
                limit = min(int(command.get("bytes", 65536)), TAIL_MAX)
                with open(path, "rb") as stream:
                    stream.seek(max(0, size - limit))
                    reply.update(text=stream.read().decode("utf-8", "replace"), size=size)
            elif kind == "cancel":
                folder = self.resolve(command.get("folder", ""))
                marker = os.path.join(folder, "cancel.request")
                if not os.path.exists(marker):
                    now = time.time()
                    temp = marker + ".tmp"
                    with open(temp, "w") as stream:
                        json.dump(
                            {"origin": command.get("origin", "monitor"), "requested": now}, stream
                        )
                    os.replace(temp, marker)
                    event = {"origin": command.get("origin", "monitor"), "ts": now}
                    event["type"] = "cancel.requested"
                    with open(os.path.join(folder, "events.jsonl"), "a") as log:
                        log.write(json.dumps(event, sort_keys=True) + "\n")
            elif kind == "convergence":
                workdir = self.resolve(command.get("folder", ""), command.get("path", ""))
                if not os.path.isdir(workdir):
                    raise ValueError("Not a study work directory")
                reply["summary"] = convergence(workdir, command.get("deck"))
            elif kind == "rescan":
                self.scan(force=True)
            else:
                raise ValueError(f"Unknown command: {kind}")
        except (OSError, ValueError, TypeError) as exc:
            reply = {"t": "reply", "id": command.get("id"), "ok": False, "error": str(exc)}
        self.emit(reply)


def main():
    init = json.loads(sys.stdin.readline() or "{}")
    watcher = Watcher(init.get("roots", []), init.get("known"), init.get("interval", 1.0))
    watcher.hello()
    if init.get("once"):
        if init.get("scan", True):
            watcher.scan(force=True)
            watcher.heartbeat(force=True)
        for command in init.get("commands", []):
            watcher.handle(command)
        return
    commands = queue.Queue()

    def read_commands():
        for line in sys.stdin:
            try:
                commands.put(json.loads(line))
            except ValueError:
                continue
        commands.put(None)

    threading.Thread(target=read_commands, daemon=True).start()
    watcher.scan(force=True)
    watcher.heartbeat(force=True)
    while True:
        deadline = time.monotonic() + watcher.interval
        while True:
            try:
                command = commands.get(timeout=max(0.0, deadline - time.monotonic()))
            except queue.Empty:
                break
            if command is None:
                return
            watcher.handle(command)
        watcher.scan()


if __name__ == "__main__":
    try:
        main()
    except (BrokenPipeError, KeyboardInterrupt):
        pass
