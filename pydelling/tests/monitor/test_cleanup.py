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
