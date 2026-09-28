"""Run commands, one-shot snippets and the watcher on a host (OpenSSH or local).

Background connections always use ``BatchMode=yes``: a password prompt would hang
the monitor, so authentication failures are classified and reported instead. On
POSIX clients connections are multiplexed (``ControlMaster``) so ``just connect``
can open one authenticated master that every later command reuses.
"""

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

from pydelling.managers.batch import CANCEL_FILE, EVENTS_FILE, request_cancel
from pydelling.managers.ssh_executor import CANCEL_REQUEST, SSHExecutor

BACKGROUND = [
    "-o",
    "BatchMode=yes",
    "-o",
    "ConnectTimeout=10",
    "-o",
    "ServerAliveInterval=15",
    "-o",
    "ServerAliveCountMax=3",
]
CONTROL_PATH = "~/.ssh/pydelling-%C"
WATCHER_SOURCE = (Path(__file__).with_name("watcher_script.py")).read_text()
AUTH_HINT = (
    "El host no acepta el acceso sin contraseña. Instala tu clave con "
    "`just ssh-key-install {host}` o, en macOS/Linux, abre una sesión con `just connect {host}`."
)


class TransportError(RuntimeError):
    def __init__(self, state, message):
        super().__init__(message)
        self.state = state


def ssh_binary():
    return os.environ.get("PYDELLING_SSH", "ssh")


def mux_options(existing, *, windows=None, env=None, home=None):
    """ControlMaster options for POSIX clients, unless disabled or already configured."""
    windows = os.name == "nt" if windows is None else windows
    env = os.environ if env is None else env
    home = Path.home() if home is None else Path(home)
    if windows or env.get("PYDELLING_SSH_MUX") == "0" or not (home / ".ssh").is_dir():
        return []
    if any("ControlPath" in option or "ControlMaster" in option for option in existing):
        return []
    return [
        "-o",
        "ControlMaster=auto",
        "-o",
        f"ControlPath={CONTROL_PATH}",
        "-o",
        "ControlPersist=600",
    ]


def ssh_options(host, *, interactive=False):
    options = list(host.ssh_options) + mux_options(host.ssh_options)
    return options if interactive else options + BACKGROUND


def classify_ssh_failure(returncode, stderr):
    """Map OpenSSH stderr to a host state the UI can explain."""
    text = (stderr or "").strip()
    lower = text.lower()
    line = next((x for x in reversed(text.splitlines()) if x.strip()), f"ssh exit {returncode}")
    if "host key verification failed" in lower or "remote host identification" in lower:
        return "host_key", line
    if any(
        s in lower
        for s in ("permission denied", "authentication failed", "no more authentication methods")
    ):
        return "auth_required", line
    if any(
        s in lower
        for s in (
            "could not resolve",
            "timed out",
            "connection refused",
            "no route to host",
            "network is unreachable",
            "connection closed",
            "connection reset",
        )
    ):
        return "unreachable", line
    return "error", line


class Transport:
    """``interactive`` lets OpenSSH prompt in the user's terminal (CLI use only)."""

    def __init__(self, host, interactive=False):
        self.host = host
        self.interactive = interactive

    def argv(self, remote_argv, *, interactive=None):
        interactive = self.interactive if interactive is None else interactive
        remote_argv = [str(a) for a in remote_argv]
        if self.host.transport == "local":
            if remote_argv and remote_argv[0] == "python3":
                remote_argv = [sys.executable, *remote_argv[1:]]
            return remote_argv
        options = ssh_options(self.host, interactive=interactive)
        return [ssh_binary(), *options, self.host.ssh, shlex.join(remote_argv)]

    def run(self, remote_argv, *, input=None, timeout=60, check=True):
        # Interactive calls keep stdin/stderr on the terminal so OpenSSH can ask for a
        # password; background calls capture everything and never prompt.
        capture = {"capture_output": True} if not self.interactive else {"stdout": subprocess.PIPE}
        try:
            result = subprocess.run(
                self.argv(remote_argv),
                input=input,
                **capture,
                text=True,
                timeout=timeout,
                check=False,
            )
        except FileNotFoundError as exc:
            raise TransportError("missing_ssh", f"OpenSSH no encontrado: {exc}") from exc
        except subprocess.TimeoutExpired as exc:
            raise TransportError("unreachable", f"Sin respuesta tras {timeout} s") from exc
        if check and result.returncode != 0:
            if self.host.transport == "ssh" and result.returncode == 255:
                raise TransportError(*classify_ssh_failure(255, result.stderr or ""))
            detail = (result.stderr or result.stdout or "").strip()[-2000:]
            raise TransportError("error", detail or f"exit {result.returncode}")
        return result

    def python(self, code, *args, timeout=60):
        return self.run(["python3", "-c", code, *args], timeout=timeout).stdout

    def watcher_argv(self):
        return self.argv(["python3", "-u", "-c", WATCHER_SOURCE])

    def watcher_once(self, commands, *, scan=False, timeout=60):
        """Run the watcher once for ``commands`` (tail/cancel) without a live stream."""
        init = {"roots": [self.host.campaigns_root], "once": True, "scan": scan}
        init["commands"] = commands
        result = self.run(
            ["python3", "-u", "-c", WATCHER_SOURCE], input=json.dumps(init) + "\n", timeout=timeout
        )
        return [json.loads(line) for line in result.stdout.splitlines() if line.strip()]

    def tail(self, folder, relative, nbytes=65536):
        replies = self.watcher_once(
            [{"id": 1, "cmd": "tail", "folder": folder, "path": relative, "bytes": nbytes}]
        )
        reply = next(m for m in replies if m["t"] == "reply")
        if not reply["ok"]:
            raise TransportError("error", reply["error"])
        return reply["text"]

    def cancel(self, folder):
        if self.host.transport == "local":
            request_cancel(folder, origin="monitor")
        else:
            self.python(CANCEL_REQUEST, folder, CANCEL_FILE, EVENTS_FILE)

    def executor(self):
        if self.host.transport == "local":
            return None
        return SSHExecutor(
            host=self.host.ssh,
            root=self.host.root,
            uv=self.host.uv,
            ssh_options=ssh_options(self.host),
            transfer=self.host.transfer,
            ssh=ssh_binary(),
        )


def make_transport(host, interactive=False):
    return Transport(host, interactive=interactive)
