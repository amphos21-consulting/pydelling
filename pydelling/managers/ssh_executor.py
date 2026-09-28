"""Generic OpenSSH deployment and detached workers, usable from Windows/macOS.

No passwords are accepted or serialized. Authentication is delegated to OpenSSH.
The tar fallback uses only the Python stdlib on the client and Linux tar remotely.
"""

import hashlib
import json
import os
import shlex
import shutil
import subprocess
import tarfile
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from .batch import CANCEL_FILE, EVENTS_FILE, BatchResult, atomic_json, file_hash, fingerprint

# Remote snippets run with the host's python3 (stdlib only, Linux: fcntl and /proc).
WORKER_LAUNCHER = """import fcntl,json,os,pathlib,subprocess,sys,time
folder=pathlib.Path(sys.argv[1])
def start_token(pid):
 try: return (pathlib.Path('/proc')/str(pid)/'stat').read_text().split()[21]
 except OSError: return None
with (folder/'.launch.lock').open('a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX)
 marker=folder/'worker.json'
 if marker.exists():
  old=json.loads(marker.read_text())
  proc=pathlib.Path('/proc')/str(old['pid'])/'stat'
  if proc.exists() and proc.read_text().split()[21]==old.get('start') and proc.read_text().split()[2]!='Z':
   print(json.dumps(old)); sys.exit(0)
 for stale in ('cancel.request','worker-exit.json'):
  (folder/stale).unlink(missing_ok=True)
 env=dict(os.environ,PYDELLING_RUNS_WORKER='1')
 with (folder/'worker.log').open('ab') as log:
  p=subprocess.Popen([sys.executable,'-c',sys.argv[4],sys.argv[2],str(folder)],stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True,cwd=sys.argv[3],env=env)
 state={'pid':p.pid,'start':start_token(p.pid),'launched':time.time()}
 temp=marker.with_suffix('.tmp'); temp.write_text(json.dumps(state)); os.replace(temp,marker)
 print(json.dumps(state))
"""

WORKER_SUPERVISOR = """import json,os,pathlib,subprocess,sys,time
argv=json.loads(sys.argv[1]); folder=pathlib.Path(sys.argv[2])
try:
 code=subprocess.call(argv)
except OSError as exc:
 print(f'Cannot start worker: {exc}',file=sys.stderr,flush=True); code=127
temp=folder/'worker-exit.json.tmp'
temp.write_text(json.dumps({'returncode':code,'finished':time.time()}))
os.replace(temp,folder/'worker-exit.json')
sys.exit(code)
"""

CANCEL_REQUEST = """import json,os,pathlib,sys,time
folder=pathlib.Path(sys.argv[1]); marker=folder/sys.argv[2]
if folder.is_dir() and not marker.exists():
 temp=marker.with_suffix('.tmp'); temp.write_text(json.dumps({'origin':'ssh','requested':time.time()})); os.replace(temp,marker)
 with (folder/sys.argv[3]).open('a') as log:
  log.write(json.dumps({'origin':'ssh','ts':time.time(),'type':'cancel.requested'},sort_keys=True)+chr(10))
"""


@dataclass
class SSHExecutor:
    host: str
    root: str
    uv: str = "/home/macario/.local/bin/uv"
    ssh_options: list = field(default_factory=list)
    transfer: str = "auto"
    runtime: str | None = None
    local_options: dict = field(default_factory=dict)
    entrypoint: str = "run_models.py"
    ssh: str = "ssh"

    def __post_init__(self):
        if not self.host or self.host.startswith("-") or any(c.isspace() for c in self.host):
            raise ValueError("Invalid SSH host")
        if not self.root.startswith("/") or ".." in PurePosixPath(self.root).parts:
            raise ValueError("Remote root must be an absolute path without traversal")
        if self.transfer not in ("auto", "rsync", "tar"):
            raise ValueError("transfer must be auto, rsync or tar")

    def command(self, argv, *, capture=True):
        return subprocess.run(
            [self.ssh, *self.ssh_options, self.host, shlex.join(list(map(str, argv)))],
            check=True,
            text=True,
            capture_output=capture,
        )

    def python(self, code, *args):
        return self.command(["python3", "-c", code, *args]).stdout

    def deploy(self, workspace, files, on_event=None):
        """Deploy only explicit source files into a content-addressed release.

        ``on_event(event_type, **payload)`` receives the stage boundaries
        (``deploy.hashed``, ``deploy.uploaded``, ``deploy.verified``, ``deploy.synced``).
        """
        emit = on_event or (lambda event_type, **payload: None)
        workspace = Path(workspace).resolve()
        files = sorted({Path(f) for f in files})
        hashes = {}
        for relative in files:
            source = workspace / relative
            if relative.is_absolute() or ".." in relative.parts or source.is_symlink():
                raise ValueError(f"Unsafe source path: {relative}")
            hashes[relative.as_posix()] = file_hash(source)
        release = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()[:20]
        destination = f"{self.root}/releases/{release}"
        emit("deploy.hashed", files=len(hashes), release=release)
        self.command(["mkdir", "-p", destination], capture=False)
        # rsync preserves exact source bytes; no --delete outside an isolated release.
        use_rsync = self.transfer == "rsync"
        if self.transfer == "auto" and os.name != "nt" and shutil.which("rsync"):
            help_text = subprocess.run(
                ["rsync", "--help"], capture_output=True, text=True, check=True
            ).stdout
            use_rsync = "--protect-args" in help_text or "--secluded-args" in help_text
        if use_rsync:
            with tempfile.TemporaryDirectory() as temp:
                listing = Path(temp) / "files.txt"
                listing.write_text("\n".join(hashes) + "\n")
                subprocess.run(
                    [
                        "rsync",
                        "-a",
                        "--protect-args",
                        "--files-from",
                        str(listing),
                        "-e",
                        shlex.join([self.ssh, *self.ssh_options]),
                        str(workspace) + "/",
                        f"{self.host}:{destination}/",
                    ],
                    check=True,
                )
        else:
            with tempfile.TemporaryDirectory() as temp:
                archive = Path(temp) / "source.tar.gz"
                with tarfile.open(archive, "w:gz") as tar:
                    for relative in files:
                        tar.add(workspace / relative, arcname=relative.as_posix(), recursive=False)
                self._upload(archive, destination + "/source.tar.gz")
                self.command(["tar", "-xzf", destination + "/source.tar.gz", "-C", destination])
        emit("deploy.uploaded", transfer="rsync" if use_rsync else "tar")
        self.python(
            "import hashlib,json,pathlib,sys; root=pathlib.Path(sys.argv[1]); "
            "expected=json.loads(sys.argv[2]); "
            "assert all(hashlib.sha256((root/p).read_bytes()).hexdigest()==h for p,h in expected.items())",
            destination,
            json.dumps(hashes),
        )
        emit("deploy.verified")
        self.command(
            [self.uv, "sync", "--locked", "--no-dev", "--project", destination], capture=False
        )
        emit("deploy.synced", release=release)
        return destination, release

    def _upload(self, local, remote):
        # stdin data channel, not a command string or a credential file.
        with Path(local).open("rb") as stream:
            subprocess.run(
                [
                    self.ssh,
                    *self.ssh_options,
                    self.host,
                    shlex.join(
                        [
                            "python3",
                            "-c",
                            "import pathlib,sys; pathlib.Path(sys.argv[1]).write_bytes(sys.stdin.buffer.read())",
                            remote,
                        ]
                    ),
                ],
                stdin=stream,
                check=True,
            )

    def start(self, release, config, campaign, *, resume=False, on_event=None):
        """Detach a worker. A remote OS lock serializes launch and execution."""
        if not campaign or any(
            c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
            for c in campaign
        ):
            raise ValueError("Unsafe campaign name")
        folder = f"{self.root}/campaigns/{campaign}"
        self.command(["mkdir", "-p", folder])
        # Do not rewrite a running worker's configuration.
        self.python(
            """import fcntl,json,os,pathlib,sys
p=pathlib.Path(sys.argv[1]); text=sys.argv[2]
with (p.parent/'.config.lock').open('a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX)
 if p.exists():
  assert json.loads(p.read_text())==json.loads(text), 'Incompatible remote configuration'
 else:
  tmp=p.with_suffix('.tmp'); tmp.write_text(text); os.replace(tmp,p)
""",
            folder + "/config.json",
            json.dumps(config, sort_keys=True, indent=2),
        )
        action = "resume" if resume else "run"
        argv = [
            self.uv,
            "run",
            "--locked",
            "--no-dev",
            "--project",
            release,
            "python",
            release + "/" + self.entrypoint,
            action,
            "--config",
            folder + "/config.json",
            "--backend",
            "local",
            "--output",
            folder,
        ]
        state = self.launch_worker(release, folder, argv)
        if on_event:
            on_event("worker.started", pid=state.get("pid"))
        return {"remote_folder": folder, "release": release, **state}

    def launch_worker(self, release, folder, argv):
        """Launch arbitrary argv once, independently of the SSH channel.

        The argv runs under a tiny stdlib supervisor that records the exit code in
        ``worker-exit.json`` so monitors can tell a crash from a clean finish. A new
        launch clears stale ``cancel.request``/``worker-exit.json`` files.
        """
        state = json.loads(
            self.python(WORKER_LAUNCHER, folder, json.dumps(argv), release, WORKER_SUPERVISOR)
        )
        return state

    def cancel(self, folder):
        """Request cooperative cancellation of the campaign in ``folder``."""
        self.python(CANCEL_REQUEST, folder, CANCEL_FILE, EVENTS_FILE)

    def configuration(self, folder):
        return json.loads(
            self.python(
                "import json,pathlib,sys; p=pathlib.Path(sys.argv[1]); "
                'print(p.read_text() if p.exists() else "null")',
                folder + "/config.json",
            )
        )

    def run_batch(
        self, studies, folder, requirements, *, resume=True, provenance=None, batch_name="batch"
    ):
        """Run arbitrary PflotranStudy objects in a previously deployed uv runtime.

        ``runtime`` is the remote release returned by deploy(); ``local_options``
        configures the remote LocalExecutor. No KiMoDa code is required.
        """
        if not self.runtime:
            raise ValueError("SSH run_batch requires runtime from deploy()")
        name = Path(folder).name
        if not name or any(
            c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
            for c in name
        ):
            raise ValueError("Unsafe batch folder name")
        remote = f"{self.root}/campaigns/{name}"
        studies = list(studies)
        self.command(["mkdir", "-p", remote])
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            descriptions = []
            for study in studies:
                if Path(study.name).name != study.name or study.name in (".", ".."):
                    raise ValueError("Unsafe study name")
                study.to_file(temp / study.name)
                descriptions.append(
                    {
                        "name": study.name,
                        "input": study.input_file_name,
                        "auxiliary": list(study.aux_files),
                    }
                )
            job = {
                "studies": descriptions,
                "requirements": requirements,
                "executor": self.local_options,
                "provenance": provenance,
                "resume": resume,
                "batch_name": batch_name,
            }
            digest = fingerprint(
                {
                    "job": job,
                    "files": {
                        str(p.relative_to(temp)): file_hash(p)
                        for p in temp.rglob("*")
                        if p.is_file()
                    },
                }
            )
            request = fingerprint(
                {
                    "job": {k: v for k, v in job.items() if k != "resume"},
                    "decks": {s.name: s.render() for s in studies},
                    "runtime": self.runtime,
                }
            )
            self.python(
                "import pathlib,sys; p=pathlib.Path(sys.argv[1]); "
                'assert not p.exists() or p.read_text()==sys.argv[2], "Incompatible remote batch"; '
                "p.write_text(sys.argv[2])",
                remote + "/batch-request.txt",
                request,
            )
            inputs = f"{remote}/inputs/{digest}"
            job["inputs"] = inputs
            atomic_json(temp / "job.json", job)
            archive = temp / "inputs.tar.gz"
            with tarfile.open(archive, "w:gz") as tar:
                for path in sorted(temp.iterdir()):
                    if path != archive:
                        tar.add(path, arcname=path.name)
            self.command(["mkdir", "-p", inputs])
            self._upload(archive, inputs + "/inputs.tar.gz")
            self.command(["tar", "-xzf", inputs + "/inputs.tar.gz", "-C", inputs])
        argv = [
            self.uv,
            "run",
            "--locked",
            "--no-dev",
            "--project",
            self.runtime,
            "python",
            "-m",
            "pydelling.managers.batch_worker",
            inputs + "/job.json",
            remote,
        ]
        self.launch_worker(self.runtime, remote, argv)
        while True:
            state = self.status(remote)
            if not state["worker_alive"]:
                if state.get("campaign.json", {}).get("state") not in ("completed", "failed"):
                    raise RuntimeError(state["log_tail"])
                if state.get("campaign.json", {}).get("error"):
                    raise RuntimeError(state["campaign.json"]["error"])
                records = {
                    Path(path).parent.name: record for path, record in state["studies"].items()
                }
                if set(records) != {s.name for s in studies}:
                    raise RuntimeError(
                        "Remote batch did not produce all study states: " + state["log_tail"]
                    )
                return BatchResult(records)
            time.sleep(1)

    def status(self, folder):
        code = """import json,pathlib,sys
p=pathlib.Path(sys.argv[1]); result={}
for name in ('campaign.json','worker.json','worker-exit.json'):
 f=p/name
 if f.exists(): result[name]=json.loads(f.read_text())
w=result.get('worker.json',{}); proc=pathlib.Path('/proc')/str(w.get('pid',0))/'stat'
try:
 stat=proc.read_text().split(); result['worker_alive']=stat[21]==w.get('start') and stat[2]!='Z'
except FileNotFoundError:
 result['worker_alive']=False
result['studies']={str(f.relative_to(p)):json.loads(f.read_text()) for f in p.glob('*/status.json')}
log=p/'worker.log'
result['log_tail']=log.read_text(errors='replace')[-4000:] if log.exists() else ''
print(json.dumps(result))
"""
        return json.loads(self.python(code, folder))

    def collect(self, folder, destination, *, raw=False):
        """Retrieve allowlisted artifacts, rejecting archive traversal and links."""
        destination = Path(destination).resolve()
        destination.mkdir(parents=True, exist_ok=True)
        code = """import pathlib,sys,tarfile
root=pathlib.Path(sys.argv[1]); raw=sys.argv[2]=='1'
allowed={'.json','.jsonl','.yaml','.csv','.parquet','.png','.log','.in','.out','.dat'}
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|gz') as tar:
 for p in sorted(root.rglob('*')):
  if p.is_file() and not p.is_symlink() and (p.suffix in allowed or (raw and p.suffix in {'.h5','.xmf'})):
   tar.add(p,arcname=str(p.relative_to(root)),recursive=False)
"""
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / "results.tar.gz"
            with archive.open("wb") as stream:
                subprocess.run(
                    [
                        self.ssh,
                        *self.ssh_options,
                        self.host,
                        shlex.join(["python3", "-c", code, folder, "1" if raw else "0"]),
                    ],
                    stdout=stream,
                    check=True,
                )
            with tarfile.open(archive) as tar:
                for member in tar:
                    target = destination / member.name
                    if not member.isfile() or not target.resolve().is_relative_to(destination):
                        raise ValueError("Unsafe result archive member")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with tar.extractfile(member) as source, target.open("wb") as dest:
                        shutil.copyfileobj(source, dest)
        atomic_json(
            destination / "download.json", {"host": self.host, "folder": folder, "raw": raw}
        )
