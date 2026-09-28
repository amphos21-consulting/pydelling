"""A stand-in for OpenSSH that runs the remote command locally through ``sh -c``.

It lets the tests exercise the real SSH code path (argv building, quoting, stdin
streams, exit codes) without a server. ``FAKE_SSH_DENY=1`` imitates a password-only
host rejecting ``BatchMode`` logins.
"""

import os
import sys
from pathlib import Path

OPTIONS_WITH_VALUE = set("oSpilFJEcmbOLRDWweQB")


def install(tmp_path, monkeypatch):
    """Create ``fake-ssh`` and a ``python3`` shim; point ``PYDELLING_SSH`` at them."""
    bin_dir = tmp_path / "fake-bin"
    bin_dir.mkdir()
    python3 = bin_dir / "python3"
    python3.symlink_to(sys.executable)
    ssh = bin_dir / "fake-ssh"
    ssh.write_text(f"#!{sys.executable}\n" + Path(__file__).read_text())
    ssh.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("PYDELLING_SSH", str(ssh))
    monkeypatch.setenv("FAKE_SSH_LOG", str(tmp_path / "fake-ssh.log"))
    return ssh


def main():
    args = sys.argv[1:]
    with open(os.environ["FAKE_SSH_LOG"], "a") as log:
        log.write(repr(args) + "\n")
    i = 0
    while i < len(args) and args[i].startswith("-"):
        i += 2 if args[i][1:] in OPTIONS_WITH_VALUE else 1
    if os.environ.get("FAKE_SSH_DENY"):
        print(f"{args[i]}: Permission denied (publickey,password).", file=sys.stderr)
        raise SystemExit(255)
    command = " ".join(args[i + 1 :])
    os.execvp("sh", ["sh", "-c", command])


if __name__ == "__main__":
    main()
