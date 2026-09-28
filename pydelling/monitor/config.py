"""Project settings from ``[tool.pydelling.monitor]`` in ``pyproject.toml``.

A project declares where the registry lives, which files may be launched (entries)
and, optionally, an adapter module providing ``hosts(root)``, ``describe(root, path)``
and ``deploy_files(root)``. The local machine is always available as host ``local``.
"""

import importlib
import os
import shutil
import socket
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path, PurePosixPath

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10
    import tomli as tomllib


@dataclass
class Host:
    id: str
    transport: str = "ssh"
    ssh: str | None = None
    root: str = ""
    uv: str = "uv"
    ssh_options: list = field(default_factory=list)
    executable: str | None = None
    mpiexec: str | None = None
    database: str | None = None
    label: str | None = None
    transfer: str = "auto"

    def __post_init__(self):
        if self.transport not in ("ssh", "local"):
            raise ValueError(f"Host {self.id}: transport must be ssh or local")
        if self.transport == "ssh" and not self.ssh:
            raise ValueError(f"Host {self.id}: ssh target required")

    @property
    def campaigns_root(self):
        """Folder whose children are campaigns (remote ``<root>/campaigns``; local runs dir)."""
        return self.root if self.transport == "local" else f"{self.root.rstrip('/')}/campaigns"

    def as_dict(self):
        data = asdict(self)
        data["campaigns_root"] = self.campaigns_root
        return data

    def registry_fields(self):
        options = {
            k: getattr(self, k)
            for k in ("ssh_options", "executable", "mpiexec", "database", "transfer")
        }
        return {
            "id": self.id,
            "label": self.label or self.id,
            "transport": self.transport,
            "ssh": self.ssh,
            "root": self.root,
            "uv": self.uv,
            "options": {**options, "campaigns_root": self.campaigns_root},
        }


HOST_FIELDS = set(Host.__dataclass_fields__)


@dataclass
class Entry:
    id: str
    label: str
    kind: str
    globs: list
    run: list | None = None
    resume: list | None = None

    def paths(self, root):
        root = Path(root).resolve()
        found = set()
        for pattern in self.globs:
            for path in root.glob(pattern):
                if path.is_file() and not path.is_symlink():
                    resolved = path.resolve()
                    if resolved.is_relative_to(root):
                        found.add(resolved.relative_to(root).as_posix())
        return sorted(found)


class Project:
    def __init__(self, root, settings):
        self.root = Path(root).resolve()
        self.settings = settings
        override = os.environ.get("PYDELLING_MONITOR_REGISTRY")
        self.registry_path = (
            Path(override)
            if override
            else self.root / settings.get("registry", "runs/registry.sqlite")
        )
        self.local_runs = self.root / settings.get("local_runs", "runs")
        self.entries = {}
        for entry_id, spec in settings.get("entries", {}).items():
            kind = spec.get("kind", "campaign")
            if kind not in ("campaign", "script"):
                raise ValueError(f"Entry {entry_id}: kind must be campaign or script")
            if kind == "campaign" and not spec.get("run"):
                raise ValueError(f"Entry {entry_id}: campaign entries need a run command")
            self.entries[entry_id] = Entry(
                id=entry_id,
                label=spec.get("label", entry_id),
                kind=kind,
                globs=list(spec.get("glob", [])),
                run=spec.get("run"),
                resume=spec.get("resume"),
            )
        self._adapter = None
        self._explicit_hosts = [Host(**self._host_spec(h)) for h in settings.get("hosts", [])]

    @staticmethod
    def _host_spec(spec):
        unknown = set(spec) - HOST_FIELDS
        if unknown:
            raise ValueError(f"Unknown host settings: {sorted(unknown)}")
        return dict(spec)

    @property
    def adapter(self):
        name = self.settings.get("adapter")
        if name and self._adapter is None:
            self._adapter = importlib.import_module(name)
        return self._adapter

    def local_host(self):
        return Host(
            id="local",
            transport="local",
            root=str(self.local_runs),
            uv=shutil.which("uv") or "uv",
            label=f"Este equipo ({socket.gethostname().split('.')[0]})",
        )

    def hosts(self):
        hosts = {"local": self.local_host()}
        for host in self._explicit_hosts:
            hosts.setdefault(host.id, host)
        if self.adapter is not None and hasattr(self.adapter, "hosts"):
            for spec in self.adapter.hosts(self.root):
                hosts.setdefault(spec["id"], Host(**self._host_spec(spec)))
        return list(hosts.values())

    def host(self, host_id):
        for host in self.hosts():
            if host.id == host_id:
                return host
        raise ValueError(f"Unknown host: {host_id}")

    def resolve_entry(self, entry_id, path):
        entry = self.entries.get(entry_id)
        if entry is None:
            raise ValueError(f"Unknown entry: {entry_id}")
        text = str(path)
        pure = PurePosixPath(text)
        if "\\" in text or pure.is_absolute() or ".." in pure.parts:
            raise ValueError("Entry paths must be relative POSIX paths inside the project")
        if text not in entry.paths(self.root):
            raise ValueError(f"{text} is not declared by entry {entry_id}")
        return entry, text

    def describe(self, entry_id, path, host_id=None):
        """Target of a launch: name, host, remote/local folders and a short preview."""
        entry, path = self.resolve_entry(entry_id, path)
        if entry.kind == "campaign":
            if self.adapter is None or not hasattr(self.adapter, "describe"):
                raise ValueError("Campaign entries need an adapter with describe()")
            return {"kind": "campaign", **self.adapter.describe(self.root, path)}
        host = self.host(host_id or "local")
        name = f"{PurePosixPath(path).stem}-{time.strftime('%Y%m%d-%H%M%S')}"
        return {
            "kind": "script",
            "name": name,
            "host_id": host.id,
            "remote_folder": str(PurePosixPath(host.campaigns_root) / name)
            if host.transport == "ssh"
            else str(Path(host.campaigns_root) / name),
            "local_folder": str(self.local_runs / name),
        }

    def deploy_files(self):
        if self.adapter is None or not hasattr(self.adapter, "deploy_files"):
            raise ValueError("Deploying scripts needs an adapter with deploy_files()")
        return [Path(p) for p in self.adapter.deploy_files(self.root)]


def find_pyproject(start):
    start = Path(start).resolve()
    for folder in [start, *start.parents]:
        if (folder / "pyproject.toml").is_file():
            return folder / "pyproject.toml"
    raise FileNotFoundError(f"No pyproject.toml above {start}")


def load_project(root=None):
    pyproject = find_pyproject(root or Path.cwd())
    data = tomllib.loads(pyproject.read_text())
    settings = data.get("tool", {}).get("pydelling", {}).get("monitor", {})
    return Project(pyproject.parent, settings)
