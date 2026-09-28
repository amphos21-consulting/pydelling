"""Importing pydelling must not change the caller's environment."""
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

PROBE = textwrap.dedent("""
    import json, logging, warnings, io, contextlib
    root_handlers_before = list(logging.getLogger().handlers)
    import pydelling.config as cfg
    from pydelling.managers import PflotranStudy  # noqa: F401  (pulls in most of the package)
    stderr = io.StringIO()
    with contextlib.redirect_stderr(stderr):
        warnings.warn("probe-warning", UserWarning)
    pkg = logging.getLogger("pydelling")
    print(json.dumps({
        "root_handlers_changed": logging.getLogger().handlers != root_handlers_before,
        "warning_visible": "probe-warning" in stderr.getvalue(),
        "pkg_handlers": len(pkg.handlers),
        "pkg_propagate": pkg.propagate,
        "used_default_config": cfg.used_default_config,
        "config_file": str(cfg._config_file),
        "globals_loaded": bool(cfg.config.globals.explicit_writer_dict),
    }))
""")


def run_probe(cwd, **env):
    result = subprocess.run([sys.executable, "-c", PROBE], cwd=cwd, capture_output=True, text=True,
                            env={**os.environ, **env}, timeout=300)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


class TestImportSideEffects(TestCase):
    def test_import_creates_no_files_and_leaves_globals_alone(self):
        with TemporaryDirectory() as tmp:
            state = run_probe(tmp, PYDELLING_LOGGING="package")
            self.assertEqual(list(Path(tmp).iterdir()), [])
        self.assertFalse(state["root_handlers_changed"])
        self.assertTrue(state["warning_visible"])
        self.assertEqual(state["pkg_handlers"], 1)
        self.assertFalse(state["pkg_propagate"])

    def test_logging_mode_none(self):
        with TemporaryDirectory() as tmp:
            state = run_probe(tmp, PYDELLING_LOGGING="none")
        self.assertEqual(state["pkg_handlers"], 0)
        self.assertTrue(state["pkg_propagate"])

    def test_logging_mode_root(self):
        with TemporaryDirectory() as tmp:
            state = run_probe(tmp, PYDELLING_LOGGING="root")
        self.assertTrue(state["root_handlers_changed"])
        self.assertEqual(state["pkg_handlers"], 0)

    def test_non_yaml_config_named_files_are_ignored(self):
        with TemporaryDirectory() as tmp:
            (Path(tmp) / "config").mkdir()
            (Path(tmp) / "tsconfig.json").write_text("{}")
            state = run_probe(tmp)
        self.assertTrue(state["used_default_config"])
        self.assertTrue(state["globals_loaded"])

    def test_config_from_environment_variable(self):
        with TemporaryDirectory() as tmp:
            config_file = Path(tmp) / "project_settings.yaml"
            config_file.write_text("globals:\n  is_globals_loaded: false\nmy_option: 3\n")
            state = run_probe(tmp, PYDELLING_CONFIG=str(config_file))
        self.assertFalse(state["used_default_config"])
        self.assertEqual(state["config_file"], str(config_file))
        self.assertTrue(state["globals_loaded"])


class TestConfigureLogging(TestCase):
    def tearDown(self):
        from pydelling.config import configure_logging
        configure_logging("package")

    def test_invalid_mode(self):
        from pydelling.config import configure_logging
        with self.assertRaises(ValueError):
            configure_logging("verbose")

    def test_switching_modes_does_not_stack_handlers(self):
        import logging
        from pydelling.config import configure_logging

        def ours(logger):
            return [h for h in logger.handlers if getattr(h, "_pydelling_console", False)]

        for mode in ("package", "root", "package", "none", "package"):
            configure_logging(mode)
        self.assertEqual(len(ours(logging.getLogger("pydelling"))), 1)
        self.assertEqual(ours(logging.getLogger()), [])
