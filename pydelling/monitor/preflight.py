"""Access checklist for a host: OpenSSH, authentication, Python, uv, root, disk, solver.

All remote checks run in one stdlib probe over a single connection, so a preflight
costs one SSH handshake. Results are UI-ready: ``{id, label, status, detail, ms}``
with ``status`` in ``ok | warn | fail | skip``.
"""

import json
import shutil
import time

from .transport import AUTH_HINT, TransportError, make_transport, ssh_binary

PROBE = r"""import json,os,shutil,subprocess,sys,time,uuid
spec=json.loads(sys.argv[1]); out=[]
def check(key,label,fn):
 t=time.time()
 try: status,detail=fn()
 except Exception as exc: status,detail='fail',f'{type(exc).__name__}: {exc}'
 out.append({'id':key,'label':label,'status':status,'detail':detail,'ms':round((time.time()-t)*1000)})
def python():
 v=sys.version.split()[0]
 return ('ok' if sys.version_info>=(3,8) else 'fail'),f'Python {v} ({sys.executable})'
def uv():
 path=shutil.which(os.path.expanduser(spec['uv'] or 'uv'))
 if not path: return 'fail',f"No se encuentra {spec['uv']}"
 r=subprocess.run([path,'--version'],capture_output=True,text=True,timeout=30)
 return ('ok' if r.returncode==0 else 'fail'),(r.stdout or r.stderr).strip() or path
def root():
 root=os.path.expanduser(spec['root']); os.makedirs(root,exist_ok=True)
 probe=os.path.join(root,'.pydelling-probe-'+uuid.uuid4().hex)
 with open(probe,'w') as f: f.write('ok')
 os.remove(probe)
 return 'ok',f'{root} existe y admite escritura'
def disk():
 u=shutil.disk_usage(os.path.expanduser(spec['root'])); free=u.free/1e9
 status='fail' if free<1 else 'warn' if free<5 else 'ok'
 return status,f'{free:.1f} GB libres de {u.total/1e9:.0f} GB'
def tool(name):
 def fn():
  if name=='tar' and os.name=='nt': return 'skip','No necesario'
  path=shutil.which(name)
  return ('ok',path) if path else ('fail',f'{name} no disponible')
 return fn
def file(key,executable):
 def fn():
  value=spec.get(key)
  if not value: return 'skip','No configurado'
  path=os.path.expanduser(value)
  if executable:
   found=shutil.which(path)
   if not found: return 'fail',f'No existe o no es ejecutable: {path}'
   path=found
  elif not os.path.isfile(path): return 'fail',f'No existe: {path}'
  return 'ok',f'{path} ({os.path.getsize(path)/1e6:.1f} MB)'
 return fn
def load():
 cpus=os.cpu_count()
 if hasattr(os,'getloadavg'):
  one=os.getloadavg()[0]
  return ('warn' if cpus and one>cpus else 'ok'),f'Carga {one:.2f} con {cpus} CPUs'
 return 'ok',f'{cpus} CPUs'
check('python','Python 3 en el host',python)
check('uv','uv',uv)
check('root','Carpeta de trabajo',root)
check('disk','Espacio en disco',disk)
check('tar','tar',tool('tar'))
check('executable','Ejecutable PFLOTRAN',file('executable',True))
check('mpiexec','mpiexec',file('mpiexec',True))
check('database','Base de datos geoquímica',file('database',False))
check('load','Carga del host',load)
print(json.dumps(out))
"""


def run_preflight(host, on_check=None, timeout=90, interactive=False):
    """Check that ``host`` can deploy and run.

    Background checks never prompt (BatchMode). ``interactive=True`` (terminal CLIs)
    lets OpenSSH ask for a password once; with multiplexing the rest reuse it.
    """
    emit = on_check or (lambda check: None)
    checks = []

    def add(check):
        checks.append(check)
        emit(check)

    def result(state):
        return {
            "ok": all(c["status"] != "fail" for c in checks),
            "state": state,
            "host": host.id,
            "checks": checks,
        }

    if host.transport == "ssh" and not shutil.which(ssh_binary()):
        add(
            {
                "id": "openssh",
                "label": "Cliente OpenSSH",
                "status": "fail",
                "detail": f"No se encuentra `{ssh_binary()}` en el PATH",
                "ms": 0,
            }
        )
        return result("missing_ssh")
    spec = {
        "root": host.root,
        "uv": host.uv,
        "executable": host.executable,
        "mpiexec": host.mpiexec,
        "database": host.database,
    }
    started = time.monotonic()
    try:
        transport = make_transport(host, interactive=interactive)
        output = transport.python(PROBE, json.dumps(spec), timeout=timeout)
    except TransportError as exc:
        check = {
            "id": "connection",
            "label": "Conexión y autenticación",
            "status": "fail",
            "detail": str(exc),
            "ms": round((time.monotonic() - started) * 1000),
        }
        if exc.state == "auth_required":
            check["hint"] = AUTH_HINT.format(host=host.id)
        add(check)
        return result(exc.state)
    if host.transport == "ssh":
        add(
            {
                "id": "connection",
                "label": "Conexión y autenticación",
                "status": "ok",
                "detail": f"{host.ssh}" + ("" if interactive else " sin contraseña (BatchMode)"),
                "ms": round((time.monotonic() - started) * 1000),
            }
        )
    for check in json.loads(output):
        add(check)
    return result("ok")
