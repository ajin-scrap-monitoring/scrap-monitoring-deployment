from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
INSTALL_ENVIRONMENT = REPOSITORY / "delivery" / "install-environment"


class EnvironmentInstallationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.host_root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def install(
        self, target: str = "edge", scenario: str = "hardware"
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                str(INSTALL_ENVIRONMENT),
                "--target",
                target,
                "--scenario",
                scenario,
                "--root",
                str(self.host_root),
            ],
            check=False,
            capture_output=True,
            text=True,
        )

    def environment_file(self, target: str = "edge") -> Path:
        return self.host_root / "etc" / "scrap-monitoring" / f"{target}.env"

    def test_installs_all_target_and_scenario_templates_with_required_modes(
        self,
    ) -> None:
        for target in ("edge", "server"):
            for scenario in ("hardware", "simulation"):
                with self.subTest(target=target, scenario=scenario):
                    result = self.install(target, scenario)
                    self.assertEqual(0, result.returncode, result.stderr)
                    installed = self.environment_file(target)
                    template = (
                        REPOSITORY / "targets" / target / scenario / ".env.example"
                    )
                    self.assertEqual(template.read_bytes(), installed.read_bytes())
                    self.assertEqual(0o640, installed.stat().st_mode & 0o777)
                    self.assertEqual(0o750, installed.parent.stat().st_mode & 0o777)
                    self.assertIn(str(installed), result.stdout)
                    installed.unlink()

    def test_reinstall_preserves_site_values_and_file_bytes(self) -> None:
        self.assertEqual(0, self.install().returncode)
        installed = self.environment_file()
        content = installed.read_text(encoding="utf-8").replace(
            "SITE_ID=example-site", "SITE_ID=custom-site"
        )
        content += "# Site configuration must survive bootstrap retries.\n"
        installed.write_text(content, encoding="utf-8")
        original = installed.read_bytes()

        result = self.install()

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(original, installed.read_bytes())
        self.assertIn("existing environment preserved", result.stdout)
        self.assertNotIn("custom-site", result.stdout + result.stderr)

    def test_rejects_scenario_change_without_overwriting_existing_environment(
        self,
    ) -> None:
        self.assertEqual(0, self.install().returncode)
        installed = self.environment_file()
        original = installed.read_bytes()

        result = self.install(scenario="simulation")

        self.assertNotEqual(0, result.returncode)
        self.assertEqual(original, installed.read_bytes())

    def test_rejects_invalid_existing_schema_without_overwriting_values(self) -> None:
        self.assertEqual(0, self.install().returncode)
        installed = self.environment_file()
        installed.write_text(
            installed.read_text(encoding="utf-8") + "UNEXPECTED=do-not-print\n",
            encoding="utf-8",
        )
        original = installed.read_bytes()

        result = self.install()

        self.assertNotEqual(0, result.returncode)
        self.assertEqual(original, installed.read_bytes())
        self.assertNotIn("do-not-print", result.stdout + result.stderr)

    def test_rejects_wrong_existing_permissions_without_changing_them(self) -> None:
        self.assertEqual(0, self.install().returncode)
        installed = self.environment_file()
        original = installed.read_bytes()
        for path, mode in ((installed, 0o644), (installed.parent, 0o755)):
            with self.subTest(path=path):
                path.chmod(mode)
                result = self.install()
                self.assertNotEqual(0, result.returncode)
                self.assertEqual(mode, path.stat().st_mode & 0o777)
                self.assertEqual(original, installed.read_bytes())
                path.chmod(0o640 if path == installed else 0o750)

    def test_rejects_symbolic_configuration_paths(self) -> None:
        self.assertEqual(0, self.install().returncode)
        installed = self.environment_file()
        outside = self.host_root / "outside.env"
        installed.rename(outside)
        installed.symlink_to(outside)
        original = outside.read_bytes()

        result = self.install()

        self.assertNotEqual(0, result.returncode)
        self.assertEqual(original, outside.read_bytes())
        self.assertTrue(installed.is_symlink())
        installed.unlink()
        directory = installed.parent
        outside_directory = self.host_root / "outside-directory"
        directory.rename(outside_directory)
        directory.symlink_to(outside_directory, target_is_directory=True)

        result = self.install()

        self.assertNotEqual(0, result.returncode)
        self.assertTrue(directory.is_symlink())

    def test_rejects_symbolic_lock_without_changing_its_target(self) -> None:
        self.assertEqual(0, self.install().returncode)
        lock = self.environment_file().parent / ".environment.lock"
        lock.unlink()
        outside = self.host_root / "outside-lock"
        outside.write_text("preserve this file\n", encoding="utf-8")
        lock.symlink_to(outside)

        result = self.install()

        self.assertNotEqual(0, result.returncode)
        self.assertEqual("preserve this file\n", outside.read_text(encoding="utf-8"))

    def test_rejects_hard_link_lock_without_changing_protected_files(self) -> None:
        self.assertEqual(0, self.install().returncode)
        installed = self.environment_file()
        lock = installed.parent / ".environment.lock"
        protected = self.host_root / "protected-file"
        protected.write_bytes(b"preserve the protected file\n")
        for target in (installed, protected):
            with self.subTest(target=target):
                lock.unlink()
                lock.hardlink_to(target)
                original = target.read_bytes()
                mode = target.stat().st_mode
                result = self.install()
                self.assertNotEqual(0, result.returncode)
                self.assertEqual(original, target.read_bytes())
                self.assertEqual(mode, target.stat().st_mode)

    def test_reinstall_does_not_truncate_an_existing_valid_lock(self) -> None:
        self.assertEqual(0, self.install().returncode)
        lock = self.environment_file().parent / ".environment.lock"
        lock.write_bytes(b"preserve lock contents\n")
        original = self.environment_file().read_bytes()
        result = self.install()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(b"preserve lock contents\n", lock.read_bytes())
        self.assertEqual(original, self.environment_file().read_bytes())

    def test_rejects_invalid_target_before_creating_configuration(self) -> None:
        result = self.install(target="invalid")

        self.assertEqual(2, result.returncode)
        self.assertFalse((self.host_root / "etc").exists())


if __name__ == "__main__":
    unittest.main()
