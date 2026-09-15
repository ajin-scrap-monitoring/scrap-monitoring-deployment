from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
VALIDATE_CA_STATE = REPOSITORY / "pki" / "validate-ca-state"
VERIFY_SERVER_CERTIFICATE = REPOSITORY / "pki" / "verify-server-certificate"
ENSURE_SERVER_CERTIFICATE = REPOSITORY / "pki" / "ensure-server-certificate"
FQDN = "monitoring.example.invalid"
PEM_CERTIFICATE_LABEL = "CERTIFICATE"
PEM_CERTIFICATE_BEGIN = f"-----BEGIN {PEM_CERTIFICATE_LABEL}-----"


def run_openssl(*arguments: str) -> None:
    subprocess.run(
        ["openssl", *arguments],
        check=True,
        capture_output=True,
        text=True,
    )


def write_public_fixture(path: Path, public_content: str, mode: int) -> None:
    path.write_text(  # lgtm[py/clear-text-storage-sensitive-data]
        public_content,
        encoding="utf-8",
    )
    path.chmod(mode)


def write_random_secret(path: Path) -> None:
    with path.open("xb") as output:
        subprocess.run(
            ["openssl", "rand", "-hex", "32"],
            check=True,
            stdout=output,
        )
    path.chmod(0o600)


def create_ca_state(temporary_path: Path) -> dict[str, Path]:
    bootstrap = temporary_path / "bootstrap"
    root_directory = temporary_path / "root"
    step_ca_directory = temporary_path / "step-ca"
    certs = step_ca_directory / "certs"
    secrets = step_ca_directory / "secrets"
    config = step_ca_directory / "config"
    database = step_ca_directory / "db"
    for directory in (
        bootstrap,
        root_directory,
        step_ca_directory,
        certs,
        secrets,
        config,
        database,
    ):
        directory.mkdir()

    root_key = bootstrap / "root.key"
    root_certificate = root_directory / "root_ca.crt"
    run_openssl(
        "ecparam", "-name", "prime256v1", "-genkey", "-noout", "-out", str(root_key)
    )
    run_openssl(
        "req",
        "-x509",
        "-new",
        "-key",
        str(root_key),
        "-sha256",
        "-days",
        "3650",
        "-subj",
        "/CN=Scrap Monitoring Root CA",
        "-addext",
        "basicConstraints=critical,CA:TRUE,pathlen:1",
        "-addext",
        "keyUsage=critical,keyCertSign,cRLSign",
        "-out",
        str(root_certificate),
    )

    intermediate_plain_key = bootstrap / "intermediate.key"
    intermediate_request = bootstrap / "intermediate.csr"
    intermediate_certificate = certs / "intermediate_ca.crt"
    intermediate_extensions = bootstrap / "intermediate.ext"
    write_public_fixture(
        intermediate_extensions,
        "basicConstraints=critical,CA:TRUE,pathlen:0\n"
        "keyUsage=critical,keyCertSign,cRLSign\n"
        "subjectKeyIdentifier=hash\n"
        "authorityKeyIdentifier=keyid,issuer\n",
        0o600,
    )
    run_openssl(
        "ecparam",
        "-name",
        "prime256v1",
        "-genkey",
        "-noout",
        "-out",
        str(intermediate_plain_key),
    )
    run_openssl(
        "req",
        "-new",
        "-key",
        str(intermediate_plain_key),
        "-subj",
        "/CN=Scrap Monitoring Intermediate CA",
        "-out",
        str(intermediate_request),
    )
    run_openssl(
        "x509",
        "-req",
        "-in",
        str(intermediate_request),
        "-CA",
        str(root_certificate),
        "-CAkey",
        str(root_key),
        "-CAcreateserial",
        "-days",
        "1825",
        "-sha256",
        "-extfile",
        str(intermediate_extensions),
        "-out",
        str(intermediate_certificate),
    )

    intermediate_password = secrets / "intermediate_ca_password"
    provisioner_password = secrets / "provisioner_password"
    write_random_secret(intermediate_password)
    write_random_secret(provisioner_password)
    run_openssl(
        "pkcs8",
        "-topk8",
        "-in",
        str(intermediate_plain_key),
        "-out",
        str(secrets / "intermediate_ca_key"),
        "-passout",
        f"file:{intermediate_password}",
        "-v2",
        "aes-256-cbc",
    )

    step_root_certificate = certs / "root_ca.crt"
    step_root_certificate.write_bytes(root_certificate.read_bytes())
    der = subprocess.check_output(
        ["openssl", "x509", "-in", str(root_certificate), "-outform", "DER"]
    )
    fingerprint = hashlib.sha256(der).hexdigest()
    write_public_fixture(root_directory / "root_ca.sha256", f"{fingerprint}\n", 0o640)
    ca_config = {
        "address": ":9000",
        "dnsNames": ["step-ca", "127.0.0.1"],
        "root": str(certs / "root_ca.crt"),
        "crt": str(intermediate_certificate),
        "key": str(secrets / "intermediate_ca_key"),
        "db": {"type": "badgerv2", "dataSource": str(database)},
        "authority": {
            "claims": {
                "defaultTLSCertDuration": "8760h",
                "maxTLSCertDuration": "8760h",
            },
            "provisioners": [{"type": "JWK", "name": "deployment"}],
        },
    }
    write_public_fixture(config / "ca.json", f"{json.dumps(ca_config)}\n", 0o640)
    write_public_fixture(database / "state", "initialized\n", 0o600)

    root_directory.chmod(0o750)
    step_ca_directory.chmod(0o700)
    certs.chmod(0o755)
    secrets.chmod(0o700)
    config.chmod(0o700)
    database.chmod(0o700)
    root_certificate.chmod(0o640)
    step_root_certificate.chmod(0o644)
    intermediate_certificate.chmod(0o644)
    (secrets / "intermediate_ca_key").chmod(0o600)

    return {
        "root_directory": root_directory,
        "step_ca_directory": step_ca_directory,
        "root_certificate": root_certificate,
        "fingerprint_file": root_directory / "root_ca.sha256",
        "root_key": root_key,
        "intermediate_certificate": intermediate_certificate,
        "intermediate_key": intermediate_plain_key,
    }


def create_server_certificate(
    temporary_path: Path,
    ca: dict[str, Path],
    name: str,
    days: int,
    key: Path | None = None,
) -> tuple[Path, Path]:
    certificate = temporary_path / f"server-{days}.crt"
    if key is None:
        key = temporary_path / f"server-{days}.key"
        run_openssl(
            "ecparam", "-name", "prime256v1", "-genkey", "-noout", "-out", str(key)
        )
    request = temporary_path / f"server-{days}.csr"
    extensions = temporary_path / f"server-{days}.ext"
    write_public_fixture(
        extensions,
        "basicConstraints=critical,CA:FALSE\n"
        "keyUsage=critical,digitalSignature\n"
        "extendedKeyUsage=serverAuth\n"
        f"subjectAltName=DNS:{name}\n",
        0o600,
    )
    run_openssl(
        "req",
        "-new",
        "-key",
        str(key),
        "-subj",
        f"/CN={name}",
        "-out",
        str(request),
    )
    run_openssl(
        "x509",
        "-req",
        "-in",
        str(request),
        "-CA",
        str(ca["intermediate_certificate"]),
        "-CAkey",
        str(ca["intermediate_key"]),
        "-CAcreateserial",
        "-days",
        str(days),
        "-sha256",
        "-extfile",
        str(extensions),
        "-out",
        str(certificate),
    )
    return certificate, key


class PkiValidationTest(unittest.TestCase):
    def test_validates_ca_state_and_server_certificate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            ca = create_ca_state(temporary_path)
            certificate, key = create_server_certificate(temporary_path, ca, FQDN, 365)
            subprocess.run(
                [
                    str(VALIDATE_CA_STATE),
                    "--root-directory",
                    str(ca["root_directory"]),
                    "--step-ca-directory",
                    str(ca["step_ca_directory"]),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                [
                    str(VERIFY_SERVER_CERTIFICATE),
                    "--fqdn",
                    FQDN,
                    "--root",
                    str(ca["root_certificate"]),
                    "--intermediate",
                    str(ca["intermediate_certificate"]),
                    "--certificate",
                    str(certificate),
                    "--key",
                    str(key),
                    "--min-valid-days",
                    "300",
                ],
                check=True,
                capture_output=True,
                text=True,
            )

    def test_rejects_root_fingerprint_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            ca = create_ca_state(Path(temporary))
            (ca["root_directory"] / "root_ca.sha256").write_text(
                f"{'0' * 64}\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    str(VALIDATE_CA_STATE),
                    "--root-directory",
                    str(ca["root_directory"]),
                    "--step-ca-directory",
                    str(ca["step_ca_directory"]),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(0, result.returncode)
            self.assertIn("fingerprint does not match", result.stderr)

    def test_rejects_wrong_server_name(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            ca = create_ca_state(temporary_path)
            certificate, key = create_server_certificate(temporary_path, ca, FQDN, 365)
            result = subprocess.run(
                [
                    str(VERIFY_SERVER_CERTIFICATE),
                    "--fqdn",
                    "other.example.invalid",
                    "--root",
                    str(ca["root_certificate"]),
                    "--intermediate",
                    str(ca["intermediate_certificate"]),
                    "--certificate",
                    str(certificate),
                    "--key",
                    str(key),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(0, result.returncode)
            self.assertIn("requested DNS SAN", result.stderr)


class EnsureServerCertificateTest(unittest.TestCase):
    def install_fake_commands(self, temporary_path: Path) -> Path:
        fake_bin = temporary_path / "bin"
        fake_bin.mkdir()
        fake_step = fake_bin / "step"
        fake_step.write_text(
            """#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >> "${STEP_LOG}"
if [[ "$1" == "ca" && "$2" == "health" ]]; then
  exit 0
fi
if [[ "$1" == "ca" && "$2" == "certificate" ]]; then
  cp "${ISSUED_CERTIFICATE}" "$4"
  cp "${ISSUED_KEY}" "$5"
  exit 0
fi
if [[ "$1" == "ca" && "$2" == "renew" ]]; then
  output=""
  while [[ "$#" -gt 0 ]]; do
    if [[ "$1" == "--out" ]]; then
      output="$2"
      break
    fi
    shift
  done
  cp "${RENEWED_CERTIFICATE}" "${output}"
  exit 0
fi
exit 1
""",
            encoding="utf-8",
        )
        fake_step.chmod(0o755)
        fake_systemctl = fake_bin / "systemctl"
        fake_systemctl.write_text(
            """#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >> "${SYSTEMCTL_LOG}"
exit "${SYSTEMCTL_EXIT_CODE:-0}"
""",
            encoding="utf-8",
        )
        fake_systemctl.chmod(0o755)
        return fake_bin

    def environment(
        self,
        temporary_path: Path,
        fake_bin: Path,
        certificate: Path,
        key: Path,
    ) -> dict[str, str]:
        environment = os.environ.copy()
        environment["PATH"] = f"{fake_bin}{os.pathsep}{environment['PATH']}"
        environment["STEP_LOG"] = str(temporary_path / "step.log")
        environment["SYSTEMCTL_LOG"] = str(temporary_path / "systemctl.log")
        environment["ISSUED_CERTIFICATE"] = str(certificate)
        environment["ISSUED_KEY"] = str(key)
        environment["RENEWED_CERTIFICATE"] = str(certificate)
        return environment

    def ensure_command(self, temporary_path: Path, ca: dict[str, Path]) -> list[str]:
        return [
            str(ENSURE_SERVER_CERTIFICATE),
            "--fqdn",
            FQDN,
            "--expected-root-sha256",
            ca["fingerprint_file"].read_text(encoding="utf-8").strip(),
            "--root-directory",
            str(ca["root_directory"]),
            "--step-ca-directory",
            str(ca["step_ca_directory"]),
            "--tls-directory",
            str(temporary_path / "tls"),
            "--tls-group",
            str(os.getgid()),
            "--lock-file",
            str(temporary_path / "certificate.lock"),
        ]

    def test_issues_and_keeps_current_certificate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            ca = create_ca_state(temporary_path)
            issued_certificate, issued_key = create_server_certificate(
                temporary_path, ca, FQDN, 365
            )
            fake_bin = self.install_fake_commands(temporary_path)
            environment = self.environment(
                temporary_path, fake_bin, issued_certificate, issued_key
            )
            command = self.ensure_command(temporary_path, ca)
            subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
                env=environment,
            )
            tls = temporary_path / "tls"
            self.assertEqual(0o640, (tls / "server.key").stat().st_mode & 0o777)
            self.assertEqual(
                2,
                (tls / "server-fullchain.pem")
                .read_text(encoding="utf-8")
                .count(PEM_CERTIFICATE_BEGIN),
            )

            subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
                env=environment,
            )
            step_log = (temporary_path / "step.log").read_text(encoding="utf-8")
            self.assertEqual(1, step_log.count("ca certificate"))
            self.assertEqual(
                1,
                len(
                    (temporary_path / "systemctl.log")
                    .read_text(encoding="utf-8")
                    .splitlines()
                ),
            )

    def test_rejects_expected_root_fingerprint_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            ca = create_ca_state(temporary_path)
            issued_certificate, issued_key = create_server_certificate(
                temporary_path, ca, FQDN, 365
            )
            fake_bin = self.install_fake_commands(temporary_path)
            environment = self.environment(
                temporary_path, fake_bin, issued_certificate, issued_key
            )
            command = self.ensure_command(temporary_path, ca)
            fingerprint_index = command.index("--expected-root-sha256") + 1
            command[fingerprint_index] = "0" * 64

            result = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                env=environment,
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn("does not match stored state", result.stderr)

    def test_restores_previous_certificate_when_reload_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            ca = create_ca_state(temporary_path)
            old_certificate, key = create_server_certificate(
                temporary_path, ca, FQDN, 30
            )
            renewed_certificate, _ = create_server_certificate(
                temporary_path, ca, FQDN, 365, key=key
            )
            tls = temporary_path / "tls"
            tls.mkdir(mode=0o750)
            (tls / "server.crt").write_bytes(old_certificate.read_bytes())
            (tls / "server.key").write_bytes(key.read_bytes())
            (tls / "server-fullchain.pem").write_bytes(
                old_certificate.read_bytes()
                + ca["intermediate_certificate"].read_bytes()
            )
            for path in tls.iterdir():
                path.chmod(0o640)
            original = (tls / "server.crt").read_bytes()

            fake_bin = self.install_fake_commands(temporary_path)
            environment = self.environment(
                temporary_path, fake_bin, renewed_certificate, key
            )
            environment["RENEWED_CERTIFICATE"] = str(renewed_certificate)
            environment["SYSTEMCTL_EXIT_CODE"] = "1"
            result = subprocess.run(
                self.ensure_command(temporary_path, ca),
                check=False,
                capture_output=True,
                text=True,
                env=environment,
            )
            self.assertNotEqual(0, result.returncode)
            self.assertEqual(original, (tls / "server.crt").read_bytes())
            self.assertIn("previous certificate state was restored", result.stderr)

    def test_renews_certificate_with_existing_key(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            ca = create_ca_state(temporary_path)
            old_certificate, key = create_server_certificate(
                temporary_path, ca, FQDN, 30
            )
            renewed_certificate, _ = create_server_certificate(
                temporary_path, ca, FQDN, 365, key=key
            )
            tls = temporary_path / "tls"
            tls.mkdir(mode=0o750)
            (tls / "server.crt").write_bytes(old_certificate.read_bytes())
            (tls / "server.key").write_bytes(key.read_bytes())
            (tls / "server-fullchain.pem").write_bytes(
                old_certificate.read_bytes()
                + ca["intermediate_certificate"].read_bytes()
            )
            for path in tls.iterdir():
                path.chmod(0o640)

            fake_bin = self.install_fake_commands(temporary_path)
            environment = self.environment(
                temporary_path, fake_bin, renewed_certificate, key
            )
            environment["RENEWED_CERTIFICATE"] = str(renewed_certificate)
            subprocess.run(
                self.ensure_command(temporary_path, ca),
                check=True,
                capture_output=True,
                text=True,
                env=environment,
            )
            self.assertEqual(
                renewed_certificate.read_bytes(),
                (tls / "server.crt").read_bytes(),
            )
            self.assertEqual(key.read_bytes(), (tls / "server.key").read_bytes())
            self.assertIn(
                "ca renew",
                (temporary_path / "step.log").read_text(encoding="utf-8"),
            )


if __name__ == "__main__":
    unittest.main()
