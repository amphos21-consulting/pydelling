"""Project settings from ``[tool.pydelling.monitor]`` in ``pyproject.toml``.

A project declares where the registry lives, which files may be launched (entries)
and, optionally, an adapter module providing ``hosts(root)``, ``describe(root, path)``
and ``deploy_files(root)``. The local machine is always available as host ``local``.
"""

import ast
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


def _declaration(source: str) -> dict:
    """The literal ``MONITOR`` dict of a script's source, parsed and never executed."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return {}
    for node in tree.body:
        targets = [node.target] if isinstance(node, ast.AnnAssign) else getattr(node, "targets", [])
        if any(isinstance(t, ast.Name) and t.id == "MONITOR" for t in targets):
            try:
                declared = ast.literal_eval(node.value)
            except (ValueError, TypeError, AttributeError):
                return {}
            return declared if isinstance(declared, dict) else {}
    return {}


def parse_script_host(source: str) -> str | None:
    """Host id a script declares as ``MONITOR = {"host": "macario"}`` (None when absent).

    Args:
        source: Python source of the script.

    Returns:
        str | None: The host the launch form preselects.
    """
    host = _declaration(source).get("host")
    return host if isinstance(host, str) and host else None


def parse_script_options(source: str) -> list[dict]:
    """Launch options a script declares in a module-level ``MONITOR`` literal.

    The script is parsed, never executed. ``MONITOR = {"options": [...]}`` lists the
    arguments the launch form offers; each option is a dict with:

    * ``name``: ``"--backend"`` for a flag/option, ``"action"`` (no dashes) for a
      positional argument.
    * ``label``: text shown in the form (defaults to ``name``).
    * ``choices``: list of texts, shown as a dropdown.
    * ``flag``: True for an option without value (a checkbox).
    * ``default``: text (or True for a flag) used when the launch gives no arguments.

    Anything malformed is ignored, so a broken declaration never blocks a launch.

    Args:
        source: Python source of the script.

    Returns:
        list[dict]: Validated options in declaration order (empty when none).
    """
    options = _declaration(source).get("options")
    found = []
    for raw in options if isinstance(options, list) else []:
        name = raw.get("name") if isinstance(raw, dict) else None
        if not isinstance(name, str) or not name or any(c.isspace() for c in name):
            continue
        choices = raw.get("choices")
        if choices is not None and not (
            isinstance(choices, list) and choices and all(isinstance(c, str) for c in choices)
        ):
            continue
        flag = raw.get("flag") is True and name.startswith("-") and choices is None
        default = raw.get("default")
        valid_default = default is None or (default is True if flag else isinstance(default, str))
        if not valid_default or (choices and default is not None and default not in choices):
            continue
        label = raw.get("label")
        found.append(
            {
                "name": name,
                "label": label if isinstance(label, str) else name,
                "choices": choices,
                "flag": flag,
                "default": default,
            }
        )
    return found


def default_script_args(options: list[dict]) -> list[str]:
    """Arguments a script runs with when a launch gives none (from each ``default``).

    Args:
        options: Options from :func:`parse_script_options`.

    Returns:
        list[str]: Positionals and flags in declaration order, e.g. ``["run"]``.
    """
    args: list[str] = []
    for option in options:
        if option["default"] is None:
            continue
        if not option["name"].startswith("-"):
            args.append(option["default"])
        elif option["flag"]:
            args.append(option["name"])
        else:
            args += [option["name"], option["default"]]
    return args


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

    def _script_source(self, entry_id: str, path: str) -> str:
        entry, path = self.resolve_entry(entry_id, path)
        if entry.kind != "script":
            return ""
        try:
            return (self.root / path).read_text(errors="replace")
        except OSError:
            return ""

    def script_options(self, entry_id: str, path: str) -> list[dict]:
        """Launch options declared by a script of a ``script`` entry (see above)."""
        return parse_script_options(self._script_source(entry_id, path))

    def script_host(self, entry_id: str, path: str) -> str | None:
        """Host a script asks the launch form to preselect, if it is a known host."""
        host = parse_script_host(self._script_source(entry_id, path))
        return host if host in {h.id for h in self.hosts()} else None

    def describe(self, entry_id, path, host_id=None):
        """Target of a launch: name, host, remote/local folders and a short preview."""
        entry, path = self.resolve_entry(entry_id, path)
        if entry.kind == "campaign":
            if self.adapter is None or not hasattr(self.adapter, "describe"):
                raise ValueError("Campaign entries need an adapter with describe()")
            return {"kind": "campaign", **self.adapter.describe(self.root, path)}
        host = self.host(host_id or self.script_host(entry_id, path) or "local")
        name = f"{PurePosixPath(path).stem}-{time.strftime('%Y%m%d-%H%M%S')}"
        return {
            "kind": "script",
            "options": self.script_options(entry_id, path),
            "default_host": self.script_host(entry_id, path),
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
