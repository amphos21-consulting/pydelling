# pydelling.monitor

Live dashboard, access-checked launcher and run history for pydelling batches
(`LocalExecutor` / `SSHExecutor`). Standard library only on the client and on the
remote host (the remote side needs `python3` and, to deploy, `uv`).

```text
python -m pydelling.monitor ui       # dashboard on 127.0.0.1 (prints a tokenised URL)
python -m pydelling.monitor demo     # simulated campaigns, no solver needed
python -m pydelling.monitor --help   # list, show, hosts, preflight, launch, cancel, collect, sync…
```

## Project configuration

```toml
[tool.pydelling.monitor]
registry = "runs/registry.sqlite"     # PYDELLING_MONITOR_REGISTRY overrides it
local_runs = "runs"                   # campaigns of the built-in "local" host
adapter = "my_package.monitor"        # optional module, see below

[tool.pydelling.monitor.entries.campaign]   # launched by running a project command
label = "Campaigns"
kind = "campaign"
glob = ["cases/*/*.yaml"]
run = ["run_models.py", "run", "--config", "{path}", "--detach"]
resume = ["run_models.py", "resume", "--config", "{path}", "--detach"]

[tool.pydelling.monitor.entries.script]     # generic: preflight → deploy → worker
label = "Scripts"
kind = "script"
glob = ["scripts/*.py"]

[[tool.pydelling.monitor.hosts]]
id = "cluster"
ssh = "me@cluster"
root = "/scratch/me/runs"                   # campaigns live in <root>/campaigns/<name>
uv = "/home/me/.local/bin/uv"
executable = "/opt/pflotran/bin/pflotran"   # optional, checked by preflight
```

Adapter functions (all optional): `hosts(root) -> list[dict]` (fields of
`config.Host`), `describe(root, path) -> {name, host_id, remote_folder, local_folder,
study_count?}` for campaign entries, `deploy_files(root) -> list[path]` for scripts.
The dashboard only launches files matched by the declared globs.

Campaign commands should report their phases with
`pydelling.monitor.reporter.Reporter` (`begin`, `stage(...)`, `on_event`, `fail`) and pass
`on_event` to `SSHExecutor.deploy/start`; see KiMoDa's `workflow.py` for a full example.

## Files a campaign exposes (written by `pydelling.managers`)

| File | Writer | Meaning |
|---|---|---|
| `events.jsonl` | `batch.append_event` | `batch.started/finished`, `study.state`, `cancel.requested`, project events |
| `<study>/status.json` | `LocalExecutor` | per-study state, attempt, runtime, error |
| `worker.json` / `worker-exit.json` | `SSHExecutor.launch_worker` | detached worker pid and exit code |
| `cancel.request` | `batch.request_cancel`, `SSHExecutor.cancel` | cooperative cancellation |
| `campaign.json`, `preview.json`, `config.json` | project | campaign state, expected study count, config |

## Architecture

- `watcher_script.py` runs on the host (`python3 -u -c`), scans `<root>/campaigns/*`
  and streams NDJSON deltas (`hello`, `campaign`, `study`, `event`, `log`, `progress`,
  `cursor`, `heartbeat`, `warning`, `reply`); stdin carries `tail`/`cancel` commands.
- `supervisor.py` keeps one stream per host (SSH `BatchMode`, multiplexed on POSIX),
  folds messages into `registry.py` (SQLite WAL; tables mirror pydelling-cloud's
  `Job`/`JobEvent`/`SimulationRun`) and reconnects with backoff.
- `service.py` holds the use cases; `server.py` (stdlib HTTP + SSE) and
  `fastapi_router.py` expose them. `static/` is a no-build Vue 3 app.

## pydelling-cloud

```python
from pydelling.monitor.config import load_project
from pydelling.monitor.fastapi_router import create_router
from pydelling.monitor.registry import Registry
from pydelling.monitor.service import RunsService
from pydelling.monitor.supervisor import Supervisor

project = load_project(project_root)
registry = Registry(project.registry_path)
supervisor = Supervisor(project, registry)
supervisor.start()
app.include_router(create_router(RunsService(project, registry, supervisor)), prefix="/v1/runs")
```

Authentication is left to the host application. The Vue components in
`static/js/components.js` are `{props, setup, template}` objects; moving them into
`.vue` single-file components is a copy of `template` into `<template>` and of the rest
into `<script setup>`.
