"""Standalone, stdlib-only cleanup executed on the machine owning the results."""

import json
import os
import shutil
import sys
from pathlib import Path


def process_alive(worker):
    """True/False when the worker pid can be checked, None when unknown."""
    pid = worker.get("pid")
    if not pid:
        return None
    if os.path.isdir("/proc/self"):
        try:
            with open(f"/proc/{pid}/stat") as stream:
                text = stream.read()
        except OSError:
            return False
        fields = text[text.rindex(")") + 2 :].split()
        token = worker.get("start")
        return fields[0] != "Z" and (token is None or fields[19] == str(token))
    if os.name == "nt":
        import ctypes

        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, int(pid))
        if not handle:
            return False
        code = ctypes.c_ulong()
        ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
        ctypes.windll.kernel32.CloseHandle(handle)
        return code.value == 259
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    try:  # a reaped child of ours is gone, but an unreaped zombie still answers kill(0)
        return os.waitpid(int(pid), os.WNOHANG) == (0, 0)
    except ChildProcessError:
        return True


def cleanup(root, folder, *, delete=False):
    root = Path(root).expanduser().resolve()
    path = Path(folder).expanduser()
    # Only direct run directories: never roots, source trees, symlinks or parents.
    if not path.is_absolute() or path.is_symlink() or path.resolve().parent != root:
        raise ValueError(f"Carpeta de run no segura: {folder}")
    if path.name.startswith("."):
        raise ValueError(f"Carpeta reservada: {folder}")
    if not path.exists():
        return
    if not path.is_dir():
        raise ValueError(f"No es una carpeta: {folder}")
    worker_path = path / "worker.json"
    if worker_path.exists():
        worker = json.loads(worker_path.read_text())
        if not worker.get("pid") or int(worker["pid"]) <= 0:
            raise ValueError(f"No se puede verificar el worker en {folder}")
        if process_alive(worker) is not False:
            raise ValueError(f"El worker sigue activo en {folder}")
    if delete:
        shutil.rmtree(path)


if __name__ == "__main__":
    cleanup(sys.argv[1], sys.argv[2], delete=sys.argv[3] == "delete")
