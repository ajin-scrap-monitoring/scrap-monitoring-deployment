from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
VALIDATE_ENVIRONMENT = REPOSITORY / "delivery" / "validate-environment"


class EnvironmentValidationTest(unittest.TestCase):
    def test_accepts_environment_matching_public_schema(self) -> None:
        for target in ("edge", "server"):
            with (
                self.subTest(target=target),
                tempfile.TemporaryDirectory() as temporary,
            ):
                environment = Path(temporary) / f"{target}.env"
                environment.write_text(
                    (REPOSITORY / "targets" / target / ".env.example").read_text(
                        encoding="utf-8"
                    ),
                    encoding="utf-8",
                )
                result = subprocess.run(
                    [str(VALIDATE_ENVIRONMENT), target, str(environment)],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(0, result.returncode, result.stderr)

    def test_rejects_missing_key(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            environment = Path(temporary) / "edge.env"
            lines = (
                (REPOSITORY / "targets" / "edge" / ".env.example")
                .read_text(encoding="utf-8")
                .splitlines()
            )
            lines = [line for line in lines if not line.startswith("SITE_ID=")]
            environment.write_text("\n".join(lines) + "\n", encoding="utf-8")

            result = subprocess.run(
                [str(VALIDATE_ENVIRONMENT), "edge", str(environment)],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn("SITE_ID", result.stderr)

    def test_rejects_unknown_key_without_printing_value(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            environment = Path(temporary) / "edge.env"
            lines = (
                (REPOSITORY / "targets" / "edge" / ".env.example")
                .read_text(encoding="utf-8")
                .splitlines()
            )
            lines.append("UNEXPECTED_VALUE=do-not-print-this-value")
            environment.write_text("\n".join(lines) + "\n", encoding="utf-8")

            result = subprocess.run(
                [str(VALIDATE_ENVIRONMENT), "edge", str(environment)],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn("UNEXPECTED_VALUE", result.stderr)
            self.assertNotIn("do-not-print-this-value", result.stderr)


if __name__ == "__main__":
    unittest.main()
