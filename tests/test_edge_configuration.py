from __future__ import annotations

import copy
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from delivery.edge_configuration import (
    MAX_CONFIGURATION_BYTES,
    https_origin,
    read_configuration,
    validate_runtime,
)
from tests.edge_fixtures import runtime_document

REPOSITORY = Path(__file__).resolve().parents[1]
ENVIRONMENT = {
    "SITE_ID": "example-site",
    "EDGE_ID": "example-edge",
    "CONFIG_REVISION": "example-config-r1",
    "BACKEND_ORIGIN": "https://monitoring.example.invalid",
}


class EdgeConfigurationTest(unittest.TestCase):
    def test_accepts_deployment_structure_without_reimplementing_message_validation(
        self,
    ):
        validate_runtime(runtime_document(), ENVIRONMENT)

    def test_rejects_v1_missing_and_unknown_fields(self):
        for document in (
            {},
            [],
            None,
            {"SITE_ID": "example-site"},
            {**runtime_document(), "token": "must-not-print"},
        ):
            with self.subTest(document=type(document)), self.assertRaises(ValueError):
                validate_runtime(document, ENVIRONMENT)
        for key in runtime_document():
            document = runtime_document()
            del document[key]
            with self.subTest(missing=key), self.assertRaises(ValueError):
                validate_runtime(document, ENVIRONMENT)

    def test_rejects_registration_identity_and_schema_mismatch(self):
        for key, value in (
            ("site_id", "other"),
            ("edge_id", "other"),
            ("config_revision", "other"),
            ("schema_version", "1.0"),
            ("message_type", "edge_status"),
        ):
            document = runtime_document()
            document["configuration"][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_runtime(document, ENVIRONMENT)

    def test_rejects_missing_duplicate_and_unmapped_sensors(self):
        for sensors in (
            [],
            [{"sensor_id": "a"}],
            [{"sensor_id": "a"}] * 2,
            [{"sensor_id": {}}, {"sensor_id": "b"}],
            [{"sensor_id": "a"}, {"sensor_id": "b"}],
        ):
            document = runtime_document()
            document["configuration"]["sensors"] = sensors
            with self.subTest(sensors=sensors), self.assertRaises(ValueError):
                validate_runtime(document, ENVIRONMENT)

    def test_rejects_non_private_duplicate_and_long_socket_paths(self):
        for endpoint in (
            "tcp:0.0.0.0:9000",
            "unix:relative",
            "unix:/",
            "unix://socket",
            "unix:/a/../socket",
            "unix:/a//socket",
            "unix:/" + "x" * 107,
            "unix:/sockets/a/scan.sock",
            None,
        ):
            document = runtime_document()
            document["delivery_endpoint"] = endpoint
            with self.subTest(endpoint=endpoint), self.assertRaises(ValueError):
                validate_runtime(document, ENVIRONMENT)

    def test_rejects_storage_status_overlap_and_invalid_absolute_paths(self):
        for key in ("storage_dir", "status_dir", "clock_domain_file", "token_file"):
            for value in ("relative", "/", "//", "//status", "/a/../b", "/a\n", None):
                document = runtime_document()
                document[key] = value
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    validate_runtime(document, ENVIRONMENT)
        for value in ("/status", "/status/outbox", "/"):
            document = runtime_document()
            document["storage_dir"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_runtime(document, ENVIRONMENT)

    def test_https_origin_accepts_ports_ipv6_and_one_trailing_slash(self):
        for origin in (
            "https://monitoring.example.invalid:8443",
            "https://[::1]",
            ENVIRONMENT["BACKEND_ORIGIN"] + "/",
        ):
            self.assertEqual(origin.rstrip("/"), https_origin(origin))
        document = runtime_document()
        document["backend_origin"] += "/"
        validate_runtime(document, ENVIRONMENT)

    def test_rejects_origin_credentials_paths_ports_and_control_characters(self):
        for origin in (
            "http://example.invalid",
            "https://u:p@example.invalid",
            "https://@example.invalid",
            "https://example.invalid/api",
            "https://example.invalid?token=hidden",
            "https://example.invalid#fragment",
            "https://example.invalid:0",
            "https://example.invalid:65536",
            "https://example.invalid:bad",
            " https://example.invalid",
            "https://exam\nple.invalid",
            "https://exam%70le.invalid",
        ):
            with self.subTest(origin=origin), self.assertRaises(ValueError):
                https_origin(origin)
        document = runtime_document()
        document["backend_origin"] = "https://other.example.invalid"
        with self.assertRaisesRegex(ValueError, "BACKEND_ORIGIN"):
            validate_runtime(document, ENVIRONMENT)

    def test_read_preserves_bytes_and_rejects_duplicate_json_and_symlinks(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "runtime.json"
            content = json.dumps(runtime_document(), indent=2).encode() + b"\n"
            path.write_bytes(content)
            before = path.stat()
            self.assertEqual(content, read_configuration(path, ENVIRONMENT))
            self.assertEqual(before.st_ino, path.stat().st_ino)
            self.assertEqual(before.st_mtime_ns, path.stat().st_mtime_ns)
            for content in (
                b'{"token":"hidden","token":"hidden"}',
                b"NaN",
                json.dumps(runtime_document())
                .replace('"schema_version": "2.0"', '"schema_version": 1e10000')
                .encode(),
                json.dumps(runtime_document()).encode("utf-16"),
                b"\xff",
                b"{hidden",
                b"[" * 2000,
            ):
                path.write_bytes(content)
                with self.subTest(content=content[:10]), self.assertRaises(ValueError):
                    read_configuration(path, ENVIRONMENT)
            link = Path(temporary) / "link"
            link.symlink_to(path)
            with self.assertRaises(ValueError):
                read_configuration(link, ENVIRONMENT)
            link.unlink()
            link.hardlink_to(path)
            with self.assertRaises(ValueError):
                read_configuration(path, ENVIRONMENT)

    def test_rejects_oversized_configuration(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "runtime.json"
            with path.open("wb") as output:
                output.truncate(MAX_CONFIGURATION_BYTES + 1)
            with self.assertRaisesRegex(ValueError, "too large"):
                read_configuration(path, ENVIRONMENT)

    def test_validator_cli_does_not_print_configuration_or_create_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            environment = root / "edge.env"
            config = root / "config.json"
            environment.write_text(
                (REPOSITORY / "targets/edge/hardware/.env.example")
                .read_text()
                .replace(
                    "CONFIG_FILE=/opt/ajin/config/edge-v2.runtime.json",
                    "CONFIG_FILE=/config.json",
                )
            )
            document = runtime_document()
            document["configuration"]["edge_id"] = "do-not-print-this-identity"
            config.write_text(json.dumps(document))
            before = copy.copy(config.stat())
            result = subprocess.run(
                [
                    str(REPOSITORY / "delivery/validate-edge-configuration"),
                    str(environment),
                    "--root",
                    str(root),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(0, result.returncode)
            self.assertNotIn(
                "do-not-print-this-identity", result.stdout + result.stderr
            )
            self.assertEqual(before.st_mtime_ns, config.stat().st_mtime_ns)
            config.write_text(json.dumps(runtime_document()))
            result = subprocess.run(
                [
                    str(REPOSITORY / "delivery/validate-edge-configuration"),
                    str(environment),
                    "--root",
                    str(root),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, result.returncode, result.stderr)


if __name__ == "__main__":
    unittest.main()
