import json
import os

import pytest

from pydelling.monitor.cleanup_script import cleanup


def test_cleanup_blocks_roots_outside_paths_and_symlinks(tmp_path):
    root = tmp_path / "runs"
    root.mkdir()
    outside = tmp_path / "source"
    outside.mkdir()
    link = root / "link"
    link.symlink_to(outside, target_is_directory=True)
    for target in (root, outside, link, root / ".." / "source"):
        with pytest.raises(ValueError, match="segura"):
            cleanup(root, target, delete=True)
    assert root.exists() and outside.exists()


def test_cleanup_checks_worker_and_is_retryable(tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    (run / "worker.json").write_text(json.dumps({"pid": os.getpid()}))
    with pytest.raises(ValueError, match="activo"):
        cleanup(tmp_path, run, delete=True)
    (run / "worker.json").unlink()
    (run / "data.sqlite").write_text("result database")
    cleanup(tmp_path, run)
    assert run.exists()
    cleanup(tmp_path, run, delete=True)
    assert not run.exists()
    cleanup(tmp_path, run, delete=True)


@pytest.mark.parametrize("kind", ["root", "outside", "reserved", "link", "broken"])
def test_script_reports_excluded_destinations(tmp_path, kind):
    import subprocess
    import sys
    from pathlib import Path

    from pydelling.monitor import cleanup_script

    root = tmp_path / "runs"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    reserved = root / ".reserved"
    reserved.mkdir()
    link = root / "link"
    link.symlink_to(outside, target_is_directory=True)
    broken = root / "broken"
    broken.symlink_to(tmp_path / "missing", target_is_directory=True)
    folder = {"root": root, "outside": outside, "reserved": reserved,
              "link": link, "broken": broken}[kind]
    for mode in ("check", "delete"):
        reply = subprocess.run(
            [sys.executable, "-c", Path(cleanup_script.__file__).read_text(),
             str(root), str(folder), mode], capture_output=True, text=True, check=True,
        )
        result = json.loads(reply.stdout)
        assert result["skipped"] and result["reason"]
    assert folder.exists() or folder.is_symlink()


@pytest.mark.parametrize("delete", [False, True])
def test_missing_external_results_are_already_clean(tmp_path, delete):
    root = tmp_path / "runs"
    root.mkdir()
    cleanup(root, tmp_path / "old-pytest" / "out", delete=delete)
    assert root.exists()
