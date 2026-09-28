"""Simulated campaigns for trying the dashboard without PFLOTRAN or a remote host.

The simulator writes exactly the files a real pydelling batch writes (status.json,
events.jsonl, worker.json/worker-exit.json, PFLOTRAN-like stdout), so the monitor
exercises its real code path. It honours ``cancel.request`` like LocalExecutor.
"""

import os
import random
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from pydelling.managers.batch import append_event, atomic_json, cancel_requested

PYPROJECT = """[project]
name = "monitor-demo"

[tool.pydelling.monitor]
registry = "runs/registry.sqlite"
local_runs = "runs"

[tool.pydelling.monitor.entries.script]
label = "Script de ejemplo"
kind = "script"
glob = ["scripts/*.py"]
"""

SCRIPT = """import sys, time
for i in range(10):
    print(f"paso {i + 1}/10", flush=True)
    time.sleep(1)
print("hecho", sys.argv[1:], flush=True)
"""

FINAL_TIME = 86400000.0


def study_status(folder, name, **state):
    atomic_json(folder / name / "status.json", state)


def write_deck(workdir):
    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / "model.in").write_text(f"TIME\n  FINAL_TIME {FINAL_TIME} s\nEND\n")


def simulate_study(folder, name, *, duration, fail=False, rng=None):
    """Advance one fake PFLOTRAN study; return its final state."""
    rng = rng or random.Random(name)
    workdir = folder / name / "attempts" / "0001"
    write_deck(workdir)
    started = time.time()
    base = {"attempt": 1, "workdir": "attempts/0001", "started": started}
    base["command"] = ["pflotran", "-pflotranin", "model.in"]
    study_status(folder, name, state="running", **base)
    append_event(folder, "study.state", study=name, state="running", attempt=1)
    steps = 60
    cuts = 0
    newton = 0
    with (workdir / "stdout.log").open("a") as out:
        for step in range(1, steps + 1):
            if cancel_requested(folder):
                return finish(folder, name, base, "interrupted", "Batch cancelled", started)
            fraction = step / steps
            t = FINAL_TIME**fraction if step < steps else FINAL_TIME
            dt = t * (1 - FINAL_TIME ** (-1 / steps)) * (0.6 + 0.8 * rng.random())
            if rng.random() < 0.06:
                cuts += 1
            newton += 1 + int(rng.random() * 3)
            out.write("== REACTIVE TRANSPORT ==========================\n")
            out.write(f" Step {step:6d} Time=  {t:.5E} Dt=  {dt:.5E} [s] conv_reason: 2\n")
            out.write(
                f"  newton = {1:3d} [{newton:8d}] linear = {1:5d} [{newton:10d}] "
                f"cuts = {0:2d} [{cuts:4d}]\n"
            )
            out.flush()
            if fail and fraction > 0.55:
                return finish(folder, name, base, "failed", "PFLOTRAN returned 86", started)
            time.sleep(duration / steps)
        out.write(f"\n Wall Clock Time:  {time.time() - started:.4E} [sec]\n")
    return finish(folder, name, base, "completed", None, started)


def finish(folder, name, base, state, error, started):
    runtime = time.time() - started
    record = {**base, "state": state, "finished": time.time(), "runtime_s": runtime}
    if state == "completed":
        record["outputs"] = {str(FINAL_TIME): "model.h5"}
    if error:
        record["error"] = error
    study_status(folder, name, **record)
    details = {"error": error} if error else {}
    append_event(
        folder,
        "study.state",
        study=name,
        state=state,
        attempt=1,
        runtime_s=round(runtime, 3),
        **details,
    )
    with (folder / "worker.log").open("a") as log:
        log.write(f"{time.strftime('%H:%M:%S')} {name}: {state} en {runtime:.1f} s\n")
    return state


def run_campaign(folder, *, studies, workers, duration, fail=(), verification=2):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "cancel.request").unlink(missing_ok=True)
    atomic_json(folder / "config.json", {"campaign": folder.name, "case": "demo", "version": 1})
    atomic_json(folder / "preview.json", {"study_count": studies + verification})
    atomic_json(
        folder / "worker.json", {"pid": os.getpid(), "start": None, "launched": time.time()}
    )
    atomic_json(folder / "campaign.json", {"state": "running", "started": time.time()})
    rng = random.Random(folder.name)
    batches = [
        ("verification", [f"verification-{k}" for k in ("transport", "flow")[:verification]]),
        ("training", [f"pilot-{i:06d}" for i in range(studies)]),
    ]
    for _, names in batches:
        for name in names:
            study_status(folder, name, state="pending")
    state = "completed"
    for batch, names in batches:
        if not names:
            continue
        append_event(folder, "batch.started", batch=batch, studies=len(names), pending=len(names))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [
                pool.submit(
                    simulate_study,
                    folder,
                    name,
                    duration=duration * (0.6 + 0.8 * rng.random()),
                    fail=name in fail,
                    rng=random.Random(name),
                )
                for name in names
            ]
            results = [f.result() for f in futures]
        counts = {s: results.count(s) for s in set(results)}
        append_event(folder, "batch.finished", batch=batch, counts=counts)
        if batch == "verification":
            passed = counts == {"completed": len(names)}
            append_event(folder, "verification.gate", passed=passed)
        if any(r != "completed" for r in results):
            state = "cancelled" if cancel_requested(folder) else "failed"
            break
    atomic_json(folder / "campaign.json", {"state": state, "finished": time.time()})
    code = 0 if state == "completed" else 1
    atomic_json(folder / "worker-exit.json", {"returncode": code, "finished": time.time()})
    return state


def create_demo_project(root=None, *, live_duration=150.0):
    """Create a throwaway project with finished history and one live campaign."""
    root = Path(root or tempfile.mkdtemp(prefix="pydelling-monitor-demo-"))
    root.mkdir(parents=True, exist_ok=True)
    (root / "pyproject.toml").write_text(PYPROJECT)
    (root / "scripts").mkdir(exist_ok=True)
    (root / "scripts" / "hola.py").write_text(SCRIPT)
    runs = root / "runs"
    run_campaign(runs / "rc1-demo-verificacion", studies=0, workers=2, duration=0.3)
    run_campaign(
        runs / "rc1-demo-barrido", studies=10, workers=5, duration=0.4, fail=("pilot-000004",)
    )
    live = threading.Thread(
        target=run_campaign,
        args=(runs / "rc1-demo-en-vivo",),
        kwargs={"studies": 36, "workers": 6, "duration": live_duration / 7},
        daemon=True,
    )
    live.start()
    return root, live
