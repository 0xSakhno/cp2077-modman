"""POSIX launcher and desktop-entry tests without downloading packages."""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class LauncherTests(unittest.TestCase):
    def run_command(self, args, *, cwd=None, env=None):
        proc = subprocess.run(
            [str(a) for a in args],
            cwd=cwd,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=20,
            check=False,
        )
        self.assertEqual(
            proc.returncode, 0,
            f"Command failed: {args}\nstdout={proc.stdout}\nstderr={proc.stderr}",
        )
        return proc.stdout

    def test_scripts_have_valid_syntax_and_executable_permissions(self):
        for script in ("run.sh", "install-desktop.sh"):
            with self.subTest(script=script):
                path = ROOT / script
                self.assertTrue(os.access(path, os.X_OK), f"{script} must be executable")
                self.run_command(["sh", "-n", path])

    def test_help_and_environment_check_do_not_install(self):
        env = dict(os.environ, PYTHON="intentionally-missing-python")
        for script in ("run.sh", "install-desktop.sh"):
            with self.subTest(script=script):
                output = self.run_command([ROOT / script, "--help"], env=env)
                self.assertIn("Usage:", output)
        self.assertIn(
            "Python:",
            self.run_command([ROOT / "run.sh", "--check"], env=dict(os.environ, PYTHON=sys.executable)),
        )

    def test_launch_from_another_working_directory_with_spaces(self):
        with tempfile.TemporaryDirectory() as base:
            root = Path(base)
            app = root / "mod manager with spaces"
            app.mkdir()
            shutil.copy2(ROOT / "run.sh", app / "run.sh")
            (app / "requirements.txt").write_text("PySide6>=6.8,<7\n")
            (app / "gui.py").write_text("# test GUI\n")
            fake_python = app / ".venv/bin/python"
            fake_python.parent.mkdir(parents=True)
            fake_python.write_text(
                "#!/bin/sh\n"
                "if [ \"$1\" = \"-c\" ]; then exit 0; fi\n"
                "printf '%s\\n' \"$1\" > \"$CP2077_TEST_LOG\"\n"
            )
            fake_python.chmod(0o755)
            launch_log = root / "launched.txt"
            env = dict(
                os.environ, PYTHON=sys.executable, CP2077_TEST_LOG=str(launch_log)
            )
            self.run_command([app / "run.sh"], cwd=root, env=env)
            self.assertEqual(launch_log.read_text().strip(), str(app / "gui.py"))

    def test_desktop_installer_is_optional_and_reversible(self):
        with tempfile.TemporaryDirectory() as base:
            root = Path(base)
            app = root / "mod manager with spaces"
            app.mkdir()
            shutil.copy2(ROOT / "install-desktop.sh", app / "install-desktop.sh")
            fake_launcher = app / "run.sh"
            fake_launcher.write_text(
                "#!/bin/sh\n"
                "printf '%s\\n' \"$1\" > \"$CP2077_TEST_LOG\"\n"
            )
            fake_launcher.chmod(0o755)
            data_home = root / "xdg-data"
            setup_log = root / "setup.log"
            env = dict(
                os.environ,
                XDG_DATA_HOME=str(data_home),
                CP2077_TEST_LOG=str(setup_log),
            )
            self.run_command([app / "install-desktop.sh"], cwd=root, env=env)
            self.assertEqual(setup_log.read_text().strip(), "--setup")
            desktop = data_home / "applications/cp2077-modman.desktop"
            self.assertTrue(desktop.is_file())
            desktop_data = desktop.read_text()
            self.assertIn("Type=Application", desktop_data)
            self.assertIn("Terminal=false", desktop_data)
            self.assertIn("Exec=/bin/sh " + '"' + str(app / "run.sh") + '"', desktop_data)

            self.run_command([app / "install-desktop.sh", "--uninstall"], cwd=root, env=env)
            self.assertFalse(desktop.exists())


if __name__ == "__main__":
    unittest.main()
