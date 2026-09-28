"""``python -m pydelling.monitor``: dashboard, launches, access checks and run history.

Every command works the same on macOS, Linux and Windows (PowerShell). Nothing here
reads or stores passwords: ``connect`` and ``ssh-key-install`` hand the terminal to
OpenSSH so *you* type the password once, where OpenSSH asks for it.
"""

import argparse
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

from .config import load_project
from .registry import Registry

STATUS = {
    "queued": "En cola",
    "preflight": "Comprobando acceso",
    "deploying": "Desplegando",
    "starting": "Arrancando",
    "running": "En ejecución",
    "cancelling": "Cancelando",
    "completed": "Completado",
    "failed": "Fallido",
    "cancelled": "Cancelado",
    "interrupted": "Interrumpido",
    "lost": "Worker perdido",
    "unknown": "Sin sincronizar",
    "prepared": "Preparado",
}
MARK = {"ok": "✓", "warn": "!", "fail": "✗", "skip": "·"}
KEY_INSTALL = (
    "import os,pathlib,sys\n"
    "key=sys.stdin.read().strip()\n"
    "d=pathlib.Path.home()/'.ssh'; d.mkdir(mode=0o700,exist_ok=True)\n"
    "f=d/'authorized_keys'\n"
    "lines=f.read_text().splitlines() if f.exists() else []\n"
    "if key not in lines:\n"
    " with f.open('a') as out: out.write(key+chr(10))\n"
    "os.chmod(f,0o600)\n"
    "print('ya estaba instalada' if key in lines else 'instalada')\n"
)


def build_parser():
    parser = argparse.ArgumentParser(
        prog="python -m pydelling.monitor",
        description="Monitor en vivo, lanzamiento e historial de runs de simulación.",
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND", title="comandos")

    def add(name, text, hidden=False):
        command = sub.add_parser(name, **({} if hidden else {"help": text}), description=text)
        command.add_argument(
            "--project", type=Path, default=Path.cwd(), help="carpeta con pyproject.toml"
        )
        return command

    for name, text in (
        ("ui", "abre el dashboard en vivo"),
        ("demo", "dashboard con datos simulados"),
    ):
        command = add(name, text)
        command.add_argument("--port", type=int, default=8765)
        command.add_argument("--no-browser", action="store_true", help="no abrir el navegador")
        command.add_argument("--verbose", action="store_true", help="registrar peticiones HTTP")
        if name == "demo":
            command.add_argument(
                "--duration", type=float, default=150.0, help="segundos del run vivo"
            )
    add("hosts", "hosts configurados y estado de su conexión")
    add("preflight", "comprueba el acceso a un host (SSH, uv, PFLOTRAN, disco…)").add_argument(
        "host"
    )
    listing = add("list", "runs del historial")
    listing.add_argument("--active", action="store_true")
    listing.add_argument("--host")
    listing.add_argument("--status")
    listing.add_argument("--limit", type=int, default=30)
    add("show", "detalle de un run (acepta prefijo del id)").add_argument("run")
    launch = add("launch", "lanza una entrada declarada: campaña o script")
    launch.add_argument("entry", help="id de la entrada, p. ej. campaign o script")
    launch.add_argument("path", help="fichero declarado por la entrada")
    launch.add_argument("--host", help="host de destino (scripts)")
    launch.add_argument("args", nargs="*", help="argumentos del script (tras --)")
    add("launch-script", "", hidden=True).add_argument("--run", required=True)
    add("cancel", "cancela un run (cooperativo: detiene los solvers en curso)").add_argument("run")
    collect = add("collect", "descarga los resultados de un run remoto")
    collect.add_argument("run", nargs="?")
    collect.add_argument("--run", dest="run_option")
    collect.add_argument("--raw", action="store_true", help="incluye HDF5/XMF")
    add("sync", "importa una vez el estado de los hosts").add_argument("host", nargs="?")
    add("connect", "abre una sesión SSH compartida (macOS/Linux)").add_argument("host")
    add("ssh-key-install", "instala tu clave pública SSH en un host").add_argument("host")
    return parser


def open_registry(project):
    return Registry(project.registry_path)


def resolve_run(registry, prefix):
    matches = [r for r in registry.list_runs(limit=100000) if r["id"].startswith(prefix)]
    if len(matches) != 1:
        raise ValueError(f"'{prefix}' no identifica un único run ({len(matches)} coincidencias)")
    return matches[0]["id"]


def ago(ts):
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts)) if ts else "—"


def pct(value):
    return "—" if value is None else f"{value * 100:.0f} %"


def print_checks(result):
    for check in result["checks"]:
        timing = f" ({check['ms']} ms)" if check.get("ms") else ""
        print(f"  {MARK[check['status']]} {check['label']}: {check['detail']}{timing}")
        if check.get("hint"):
            print(f"    {check['hint']}")


def serve_project(project, args, *, demo_root=None):
    from .server import make_server
    from .service import RunsService
    from .supervisor import Supervisor

    registry = open_registry(project)
    supervisor = Supervisor(project, registry)
    supervisor.start()
    service = RunsService(project, registry, supervisor)
    server = token = None
    for port in range(args.port, args.port + 10):
        try:
            server, token = make_server(service, port=port, verbose=args.verbose)
            break
        except OSError:
            continue
    if server is None:
        supervisor.stop()
        raise OSError(f"Puertos {args.port}-{args.port + 9} ocupados; usa --port")
    url = f"http://127.0.0.1:{server.server_address[1]}/#token={token}"
    if demo_root:
        print(f"Proyecto de demostración: {demo_root}")
    print(f"Monitor de runs: {url}")
    print("Ctrl+C para salir. Los workers remotos siguen ejecutándose.", flush=True)
    if not args.no_browser:
        import webbrowser

        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nCerrando el monitor…")
    finally:
        server.shutdown()
        server.server_close()
        supervisor.stop()
    return 0


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 0
    try:
        return run(args)
    except KeyboardInterrupt:
        return 130
    except (ValueError, LookupError, FileNotFoundError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except (OSError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def run(args):
    from .transport import TransportError, ssh_binary

    if args.command == "demo":
        from .demo import create_demo_project

        root, _ = create_demo_project(live_duration=args.duration)
        return serve_project(load_project(root), args, demo_root=root)
    project = load_project(args.project)
    if args.command == "ui":
        return serve_project(project, args)
    registry = open_registry(project)

    if args.command == "hosts":
        rows = {h["id"]: h for h in registry.list_hosts()}
        for host in project.hosts():
            state = rows.get(host.id, {}).get("stream_state", "sin datos")
            target = host.ssh or "local"
            print(
                f"{host.id:<14} {host.transport:<6} {target:<32} {state:<14} {host.campaigns_root}"
            )
        return 0

    if args.command == "preflight":
        from .preflight import run_preflight

        host = project.host(args.host)
        print(f"Comprobando {host.id} ({host.ssh or 'local'})…")
        result = run_preflight(host)
        print_checks(result)
        print("Acceso correcto." if result["ok"] else f"Acceso con fallos ({result['state']}).")
        return 0 if result["ok"] else 1

    if args.command == "list":
        runs = registry.list_runs(
            status=args.status, host=args.host, active=args.active, limit=args.limit
        )
        if not runs:
            print("No hay runs registrados. Prueba `sync` o lanza uno.")
        for run_row in runs:
            label = STATUS.get(run_row["status"], run_row["status"])
            print(
                f"{label:<19} {run_row['name']:<28} {run_row['host_id']:<10} "
                f"{pct(run_row['progress']):>6}  {ago(run_row['started_at'] or run_row['created_at'])}"
                f"  {run_row['id']}"
            )
        return 0

    if args.command == "show":
        from .service import RunsService

        run_id = resolve_run(registry, args.run)
        detail = RunsService(project, registry).run_detail(run_id)
        run_row = detail["run"]
        print(f"{run_row['name']} — {STATUS.get(run_row['status'], run_row['status'])}")
        print(f"  host: {run_row['host_id']}  carpeta: {run_row['remote_folder']}")
        if run_row.get("entry_path"):
            print(f"  entrada: {run_row['entry_path']}")
        if run_row.get("error"):
            print(f"  error: {run_row['error']}")
        counts = run_row.get("counts_json") or {}
        if counts:
            print("  estudios: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
        print("  fases:")
        for stage in detail["stages"]:
            print(f"    {stage['label']:<26} {stage['status']}")
        print("  actividad reciente:")
        for event in detail["events"][-12:]:
            text = event.get("message") or event["event_type"]
            print(f"    {time.strftime('%H:%M:%S', time.localtime(event['ts']))} {text}")
        tail = (run_row.get("log_tail") or "").splitlines()[-15:]
        if tail:
            print("  log del worker:")
            for line in tail:
                print(f"    {line}")
        return 0

    if args.command in ("launch", "launch-script"):
        from .launcher import launch_entry, launch_script

        if args.command == "launch-script":
            launch_script(project, registry, args.run)
            return 0
        entry, _ = project.resolve_entry(args.entry, args.path)
        if entry.kind == "campaign":
            run_id = launch_entry(
                project, registry, args.entry, args.path, action="run", origin="cli"
            )
            print("Campaña lanzada en segundo plano; sigue su progreso con `ui` o `show`.")
        else:
            run_id = launch_entry(
                project,
                registry,
                args.entry,
                args.path,
                host_id=args.host,
                args=args.args,
                origin="cli",
                spawn=False,
            )
            state = launch_script(project, registry, run_id)
            print(
                f"Worker iniciado (pid {state.get('pid')}) en {registry.get_run(run_id)['host_id']}."
            )
        print(f"run {run_id}")
        return 0

    if args.command == "cancel":
        from .launcher import cancel_run

        run_id = resolve_run(registry, args.run)
        cancel_run(project, registry, run_id)
        print(f"Cancelación enviada a {run_id}.")
        return 0

    if args.command == "collect":
        from .launcher import collect_run

        run_id = resolve_run(registry, args.run or args.run_option or "")
        folder = collect_run(project, registry, run_id, raw=args.raw)
        print(f"Resultados en {folder}")
        return 0

    if args.command == "sync":
        from .supervisor import Supervisor

        supervisor = Supervisor(project, registry)
        targets = [args.host] if args.host else [h.id for h in project.hosts()]
        failed = False
        for host_id in targets:
            try:
                supervisor.sync_once(host_id)
                count = len(registry.known(host_id))
                print(f"✓ {host_id}: {count} runs")
            except TransportError as exc:
                failed = True
                registry.set_host_stream(host_id, exc.state, str(exc))
                print(f"✗ {host_id}: {exc}")
        return 1 if failed and args.host else 0

    if args.command == "connect":
        from .transport import CONTROL_PATH

        host = project.host(args.host)
        if host.transport != "ssh":
            raise ValueError(f"{host.id} no es un host SSH")
        if os.name == "nt":
            print("OpenSSH para Windows no admite sesiones compartidas (ControlMaster).")
            print(f"Instala tu clave una vez: just ssh-key-install {host.id}")
            return 1
        (Path.home() / ".ssh").mkdir(mode=0o700, exist_ok=True)
        options = ["-o", f"ControlPath={CONTROL_PATH}"]
        check = subprocess.run(
            [ssh_binary(), *host.ssh_options, *options, "-O", "check", host.ssh],
            capture_output=True,
            check=False,
        )
        if check.returncode == 0:
            print(f"Ya hay una sesión compartida abierta con {host.id}.")
            return 0
        print(f"Abriendo sesión compartida con {host.ssh} (OpenSSH te pedirá la contraseña)…")
        options += ["-o", "ControlMaster=yes", "-o", "ControlPersist=8h"]
        # Adding -M as well changes ControlMaster=yes to ask in OpenSSH;
        # background clients then cannot obtain permission to reuse the session.
        result = subprocess.run(
            [ssh_binary(), *host.ssh_options, *options, "-N", "-f", host.ssh], check=False
        )
        if result.returncode == 0:
            print("Sesión abierta durante 8 h; el monitor y `just run` la reutilizan.")
        return result.returncode

    if args.command == "ssh-key-install":
        host = project.host(args.host)
        if host.transport != "ssh":
            raise ValueError(f"{host.id} no es un host SSH")
        private = Path.home() / ".ssh" / "id_ed25519"
        public = private.with_suffix(".pub")
        if not public.exists():
            print(f"No hay clave en {public}; creando una (elige una frase de paso si quieres).")
            (Path.home() / ".ssh").mkdir(mode=0o700, exist_ok=True)
            subprocess.run(["ssh-keygen", "-t", "ed25519", "-f", str(private)], check=True)
        print(f"Instalando {public.name} en {host.ssh} (OpenSSH te pedirá la contraseña)…")
        remote = shlex.join(["python3", "-c", KEY_INSTALL])
        result = subprocess.run(
            [ssh_binary(), *host.ssh_options, host.ssh, remote],
            input=public.read_text().strip() + "\n",
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return result.returncode
        probe = subprocess.run(
            [ssh_binary(), *host.ssh_options, "-o", "BatchMode=yes", host.ssh, "true"],
            capture_output=True,
            check=False,
        )
        print(
            "Acceso sin contraseña verificado."
            if probe.returncode == 0
            else "La clave se instaló pero el acceso sin contraseña sigue fallando; revisa el agente SSH."
        )
        return probe.returncode

    raise ValueError(f"Comando desconocido: {args.command}")


if __name__ == "__main__":
    sys.exit(main())
