import tempfile
import unittest
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
import sys
from unittest.mock import patch

from packaging.version import Version

from config.loader import save_model_name

from click.testing import CliRunner

from main import main


class PostalCliTests(unittest.TestCase):
    def test_version_reports_installed_package_version(self):
        result = CliRunner().invoke(main, ["--version"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn(f"postal, version {version('postalcli')}", result.output)

    @patch("main._latest_version", return_value=Version("999.0.0"))
    @patch("main.subprocess.run")
    def test_upgrade_installs_newer_version(self, run, latest_version):
        run.return_value.returncode = 0

        result = CliRunner().invoke(main, ["upgrade"])

        self.assertEqual(result.exit_code, 0)
        run.assert_called_once_with(
            [sys.executable, "-m", "pip", "install", "--upgrade", "postalcli"],
            check=False,
        )

    @patch("main._latest_version", return_value=Version("0.0.34"))
    @patch("main.subprocess.run")
    def test_upgrade_does_not_run_pip_when_current(self, run, latest_version):
        result = CliRunner().invoke(main, ["upgrade"])

        self.assertEqual(result.exit_code, 0)
        run.assert_not_called()

    @patch("main._latest_version", return_value=Version("999.0.0"))
    @patch("main.installed_version", return_value="0.0.34")
    def test_upgrade_notice_is_returned_for_newer_version(self, installed, latest_version):
        from main import _upgrade_notice

        self.assertIn("postal upgrade", _upgrade_notice())

    @patch("main.installed_version", side_effect=PackageNotFoundError("postalcli"))
    def test_upgrade_notice_is_skipped_without_package_metadata(self, installed):
        from main import _upgrade_notice

        self.assertIsNone(_upgrade_notice())

    @patch("main.installed_version", side_effect=PackageNotFoundError("postalcli"))
    def test_upgrade_reports_missing_package_metadata(self, installed):
        result = CliRunner().invoke(main, ["upgrade"])

        self.assertEqual(result.exit_code, 1)
        self.assertIn("install postalcli before upgrading", result.output)


class ModelConfigPersistenceTests(unittest.TestCase):
    def test_save_model_name_updates_existing_model_section(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.toml"
            path.write_text("max_turns = 5\n\n[model]\nname = \"old/model\"\ntemperature = 1\n", encoding="utf-8")

            with patch("config.loader.get_system_config_path", return_value=path), patch(
                "config.loader._get_project_config", return_value=None
            ):
                save_model_name("new/model")

            self.assertIn('name = "new/model"', path.read_text(encoding="utf-8"))
            self.assertIn("temperature = 1", path.read_text(encoding="utf-8"))

    def test_save_model_name_creates_missing_config(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "config.toml"

            with patch("config.loader.get_system_config_path", return_value=path), patch(
                "config.loader._get_project_config", return_value=None
            ):
                save_model_name("new/model")

            self.assertIn('[model]\nname = "new/model"', path.read_text(encoding="utf-8"))


class UpgradePlatformTests(unittest.TestCase):
    def run_upgrade(
        self, platform="darwin", managed=False, pipx="/opt/homebrew/bin/pipx",
        environment_name="postalcli", returncode=0, error=None,
    ):
        with tempfile.TemporaryDirectory() as directory:
            environment = Path(directory) / "venvs" / environment_name
            environment.mkdir(parents=True)
            if managed:
                (environment / "pipx_metadata.json").write_text("{}", encoding="utf-8")
            with (
                patch("main.sys.platform", platform),
                patch("main.sys.prefix", str(environment)),
                patch("main.shutil.which", return_value=pipx) as which,
                patch("main.installed_version", return_value="0.0.1"),
                patch("main._latest_version", return_value=Version("999.0.0")),
                patch("main.subprocess.run", side_effect=error) as run,
            ):
                run.return_value.returncode = returncode
                result = CliRunner().invoke(main, ["upgrade"])
        return result, run, which

    def test_macos_pipx_install_uses_pipx(self):
        result, run, which = self.run_upgrade(managed=True)
        self.assertEqual(result.exit_code, 0, result.output)
        which.assert_called_once_with("pipx")
        run.assert_called_once_with(
            ["/opt/homebrew/bin/pipx", "upgrade", "postalcli"], check=False,
        )
        self.assertIn("Restart Postal", result.output)

    def test_macos_pipx_install_preserves_environment_suffix(self):
        result, run, _ = self.run_upgrade(managed=True, environment_name="postalcli-dev")
        self.assertEqual(result.exit_code, 0, result.output)
        run.assert_called_once_with(
            ["/opt/homebrew/bin/pipx", "upgrade", "postalcli-dev"], check=False,
        )

    def test_macos_pip_install_uses_current_python_even_when_pipx_is_available(self):
        result, run, which = self.run_upgrade()
        self.assertEqual(result.exit_code, 0, result.output)
        which.assert_not_called()
        run.assert_called_once_with(
            [sys.executable, "-m", "pip", "install", "--upgrade", "postalcli"], check=False,
        )

    def test_macos_without_pipx_uses_pip_for_regular_installation(self):
        result, run, _ = self.run_upgrade(pipx=None)
        self.assertEqual(result.exit_code, 0, result.output)
        run.assert_called_once_with(
            [sys.executable, "-m", "pip", "install", "--upgrade", "postalcli"], check=False,
        )

    def test_macos_managed_install_reports_missing_pipx(self):
        result, run, _ = self.run_upgrade(managed=True, pipx=None)
        self.assertEqual(result.exit_code, 1)
        self.assertIn("pipx is not on PATH", result.output)
        run.assert_not_called()

    def test_windows_and_linux_use_current_python_pip(self):
        for platform in ("win32", "linux"):
            with self.subTest(platform=platform):
                result, run, which = self.run_upgrade(platform=platform, managed=True)
                self.assertEqual(result.exit_code, 0, result.output)
                which.assert_not_called()
                run.assert_called_once_with(
                    [sys.executable, "-m", "pip", "install", "--upgrade", "postalcli"], check=False,
                )

    def test_failed_pipx_upgrade_does_not_retry_with_another_installer(self):
        result, run, _ = self.run_upgrade(managed=True, returncode=1)
        self.assertEqual(result.exit_code, 1)
        self.assertIn("postal upgrade failed", result.output)
        self.assertEqual(run.call_count, 1)

    def test_upgrade_reports_installer_launch_failure(self):
        result, run, _ = self.run_upgrade(error=FileNotFoundError("installer unavailable"))
        self.assertEqual(result.exit_code, 1)
        self.assertIn("Could not start the upgrade", result.output)
        self.assertEqual(run.call_count, 1)


if __name__ == "__main__":
    unittest.main()
