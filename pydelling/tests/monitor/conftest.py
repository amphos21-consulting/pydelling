import itertools
import sys
import time

import pytest

from pydelling.monitor.config import load_project
from pydelling.monitor.registry import Registry

_counter = itertools.count()

PYPROJECT = """
[project]
name = "sample"

[tool.pydelling.monitor]
registry = "runs/registry.sqlite"
local_runs = "runs"
adapter = "{adapter}"

[tool.pydelling.monitor.entries.campaign]
label = "Campaña"
kind = "campaign"
glob = ["cases/*.yaml"]
run = ["fake_cli.py", "run", "{{path}}"]
resume = ["fake_cli.py", "resume", "{{path}}"]

[tool.pydelling.monitor.entries.script]
label = "Script"
kind = "script"
glob = ["scripts/*.py"]
"""

ADAPTER = """
from pathlib import Path

def hosts(root):
    return []

def describe(root, path):
    name = Path(path).stem
    folder = str(Path(root) / "runs" / name)
    return {"name": name, "host_id": "local", "remote_folder": folder,
            "local_folder": folder, "study_count": 2}

def deploy_files(root):
    return ["scripts/job.py"]
"""

FAKE_CLI = """import json, os, sys, time
with open("launched.json", "w") as out:
    json.dump({"argv": sys.argv, "pid": os.getpid(),
               "origin": os.environ.get("PYDELLING_RUNS_ORIGIN")}, out)
time.sleep(float(os.environ.get("FAKE_CLI_SLEEP", "0")))
"""

JOB = """import sys
print("hello from job", *sys.argv[1:], flush=True)
raise SystemExit(int(sys.argv[1]) if len(sys.argv) > 1 else 0)
"""


@pytest.fixture
def project(tmp_path, monkeypatch):
    adapter = f"sample_adapter_{next(_counter)}"
    (tmp_path / "pyproject.toml").write_text(PYPROJECT.format(adapter=adapter))
    (tmp_path / f"{adapter}.py").write_text(ADAPTER)
    (tmp_path / "fake_cli.py").write_text(FAKE_CLI)
    (tmp_path / "cases").mkdir()
    (tmp_path / "cases" / "alpha.yaml").write_text("campaign: alpha\n")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "job.py").write_text(JOB)
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.delitem(sys.modules, adapter, raising=False)
    return load_project(tmp_path)


@pytest.fixture
def registry(project):
    return Registry(project.registry_path)


def wait_until(predicate, timeout=10.0, interval=0.05):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(interval)
    raise AssertionError("condition not reached before timeout")
