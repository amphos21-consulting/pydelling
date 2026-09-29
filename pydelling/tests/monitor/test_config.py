import sys
import textwrap

import pytest

from pydelling.monitor.config import default_script_args, load_project, parse_script_options

PYPROJECT = """
[project]
name = "demo"

[tool.pydelling.monitor]
registry = "state/registry.sqlite"
local_runs = "out"
adapter = "demo_adapter"

[tool.pydelling.monitor.entries.campaign]
label = "Campaign"
kind = "campaign"
glob = ["cases/*/*.yaml"]
run = ["run.py", "run", "--config", "{path}"]
resume = ["run.py", "resume", "--config", "{path}"]

[tool.pydelling.monitor.entries.script]
label = "Script"
kind = "script"
glob = ["scripts/*.py"]

[[tool.pydelling.monitor.hosts]]
id = "cluster"
ssh = "me@cluster"
root = "/scratch/me"
uv = "/opt/uv"
executable = "/opt/pflotran"
"""

ADAPTER = """
def hosts(root):
    return [{"id": "macario", "ssh": "u@10.0.0.1", "root": "/home/u/k", "uv": "/u/uv"},
            {"id": "cluster", "ssh": "dup@x", "root": "/dup"}]

def describe(root, path):
    return {"name": "c-" + path.split("/")[1], "host_id": "macario",
            "remote_folder": "/home/u/k/campaigns/x", "local_folder": str(root / "out/x"),
            "study_count": 3}

def deploy_files(root):
    return ["run.py"]
"""


@pytest.fixture
def project(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text(PYPROJECT)
    for rel in ["cases/a/study.yaml", "cases/b/smoke.yaml", "scripts/job.py", "other.py"]:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text("x")
    (tmp_path / "demo_adapter.py").write_text(ADAPTER)
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.delitem(sys.modules, "demo_adapter", raising=False)
    return load_project(tmp_path / "cases")


def test_loads_settings_relative_to_pyproject(project, tmp_path):
    assert project.root == tmp_path
    assert project.registry_path == tmp_path / "state/registry.sqlite"
    assert project.local_runs == tmp_path / "out"


def test_entries_list_only_matching_files(project):
    assert project.entries["campaign"].paths(project.root) == [
        "cases/a/study.yaml",
        "cases/b/smoke.yaml",
    ]
    assert project.entries["script"].paths(project.root) == ["scripts/job.py"]


@pytest.mark.parametrize(
    "path",
    [
        "other.py",
        "../outside.yaml",
        "/etc/passwd",
        "cases/a/../../other.py",
        "cases\\a\\study.yaml",
    ],
)
def test_resolve_entry_rejects_undeclared_paths(project, path):
    with pytest.raises(ValueError):
        project.resolve_entry("campaign", path)


def test_resolve_entry_and_unknown_entry(project):
    entry, path = project.resolve_entry("campaign", "cases/a/study.yaml")
    assert entry.run == ["run.py", "run", "--config", "{path}"] and path == "cases/a/study.yaml"
    with pytest.raises(ValueError):
        project.resolve_entry("nope", "cases/a/study.yaml")


def test_hosts_merge_local_explicit_and_adapter(project):
    hosts = {h.id: h for h in project.hosts()}
    assert list(hosts) == ["local", "cluster", "macario"]
    assert hosts["local"].transport == "local" and hosts["local"].root == str(project.local_runs)
    assert hosts["cluster"].ssh == "me@cluster", "explicit hosts win over adapter duplicates"
    assert hosts["cluster"].campaigns_root == "/scratch/me/campaigns"
    assert hosts["macario"].uv == "/u/uv"
    with pytest.raises(ValueError):
        project.host("missing")


def test_describe_and_deploy_files_use_adapter(project):
    assert project.describe("campaign", "cases/a/study.yaml")["name"] == "c-a"
    script = project.describe("script", "scripts/job.py", host_id="macario")
    assert script["name"].startswith("job-") and script["host_id"] == "macario"
    assert script["remote_folder"] == f"/home/u/k/campaigns/{script['name']}"
    assert [p.as_posix() for p in project.deploy_files()] == ["run.py"]


def test_defaults_without_section(tmp_path):
    (tmp_path / "pyproject.toml").write_text(textwrap.dedent('[project]\nname = "x"\n'))
    project = load_project(tmp_path)
    assert project.entries == {}
    assert [h.id for h in project.hosts()] == ["local"]
    assert project.registry_path == tmp_path / "runs/registry.sqlite"


def test_registry_path_can_be_overridden(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n')
    monkeypatch.setenv("PYDELLING_MONITOR_REGISTRY", str(tmp_path / "elsewhere.sqlite"))
    assert load_project(tmp_path).registry_path == tmp_path / "elsewhere.sqlite"


OPTIONS_SCRIPT = '''
import sys
MONITOR = {
    "options": [
        {"name": "action", "label": "Acción", "choices": ["run", "prepare"], "default": "run"},
        {"name": "--backend", "choices": ["local", "ssh"]},
        {"name": "--detach", "flag": True, "default": True},
        {"name": "--seed", "default": "42"},
        {"name": "bad name"},
        {"name": "--wrong", "choices": ["a"], "default": "b"},
        {"name": "--empty", "choices": []},
    ]
}
raise SystemExit("never executed by the monitor")
'''


def test_script_options_are_read_without_running_the_script(project):
    (project.root / "scripts" / "opts.py").write_text(OPTIONS_SCRIPT)
    options = project.script_options("script", "scripts/opts.py")
    assert [o["name"] for o in options] == ["action", "--backend", "--detach", "--seed"]
    assert options[0]["label"] == "Acción" and options[1]["label"] == "--backend"
    assert options[2]["flag"] is True
    assert project.describe("script", "scripts/opts.py")["options"] == options
    assert default_script_args(options) == ["run", "--detach", "--seed", "42"]


@pytest.mark.parametrize(
    "source",
    ["", "x = 1", "MONITOR = 3", "MONITOR = {'options': 'run'}", "MONITOR = dict(a=1)", "def ("],
)
def test_scripts_without_a_valid_declaration_have_no_options(source):
    assert parse_script_options(source) == []


def test_script_declares_the_host_the_form_preselects(project):
    source = 'MONITOR = {"host": "%s"}\n'
    (project.root / "scripts" / "on_macario.py").write_text(source % "macario")
    (project.root / "scripts" / "on_unknown.py").write_text(source % "nowhere")
    assert project.script_host("script", "scripts/on_macario.py") == "macario"
    assert project.script_host("script", "scripts/on_unknown.py") is None
    assert project.script_host("script", "scripts/job.py") is None
    assert project.describe("script", "scripts/on_macario.py")["host_id"] == "macario"
    assert project.describe("script", "scripts/on_macario.py", host_id="local")["host_id"] == "local"
    assert project.describe("script", "scripts/job.py")["host_id"] == "local"
