from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import platform
import shutil
import stat
import subprocess
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

try:
    from .release_verifier import TARGET_PLATFORMS, archive_members, verify_release
except ImportError:
    from release_verifier import TARGET_PLATFORMS, archive_members, verify_release

MACHINE_PLATFORMS = {
    "aarch64": "linux/arm64",
    "arm64": "linux/arm64",
    "x86_64": "linux/amd64",
    "amd64": "linux/amd64",
}
RUNTIME_EXCLUDED_PREFIXES = ("delivery/online/", "delivery/offline/", "images/")
RUNTIME_EXCLUDED_FILES = {"release-package.json"}
CERTIFICATE_FILES = ("server.crt", "server.key", "server-fullchain.pem")
MAX_EDGE_CONFIG_SIZE = 16 * 1024 * 1024


@dataclass(frozen=True)
class LinkState:
    target: str | None


class CertificateSnapshot:
    def __init__(self, tls_directory: Path) -> None:
        self.tls_directory = tls_directory
        self.backup_directory: Path | None = None
        self.existing: set[str] = set()

    def capture(self) -> None:
        parent = self.tls_directory.parent
        if parent.is_symlink() or not parent.is_dir():
            raise ValueError(f"PKI directory is missing or symbolic: {parent}")
        if self.tls_directory.is_symlink() or (
            self.tls_directory.exists() and not self.tls_directory.is_dir()
        ):
            raise ValueError(
                f"TLS directory is not a directory or is symbolic: {self.tls_directory}"
            )
        self.backup_directory = Path(
            tempfile.mkdtemp(prefix=".tls-backup.", dir=parent)
        )
        self.backup_directory.chmod(0o700)
        for name in CERTIFICATE_FILES:
            source = self.tls_directory / name
            if source.is_symlink():
                raise ValueError(f"TLS file must not be symbolic: {source}")
            if source.exists():
                if not source.is_file():
                    raise ValueError(f"TLS path is not a regular file: {source}")
                run_checked(
                    [
                        "cp",
                        "--preserve=mode,ownership,timestamps",
                        "--",
                        str(source),
                        str(self.backup_directory / name),
                    ]
                )
                self.existing.add(name)

    def restore(self) -> None:
        if self.backup_directory is None:
            return
        self.tls_directory.mkdir(parents=True, exist_ok=True)
        for name in CERTIFICATE_FILES:
            destination = self.tls_directory / name
            if name not in self.existing:
                destination.unlink(missing_ok=True)
                continue
            staged = self.tls_directory / f".{name}.rollback"
            staged.unlink(missing_ok=True)
            run_checked(
                [
                    "cp",
                    "--preserve=mode,ownership,timestamps",
                    "--",
                    str(self.backup_directory / name),
                    str(staged),
                ]
            )
            os.replace(staged, destination)

    def cleanup(self) -> None:
        if self.backup_directory is not None:
            shutil.rmtree(self.backup_directory)
            self.backup_directory = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply a verified release package.")
    parser.add_argument("--version", required=True)
    parser.add_argument("--target", choices=sorted(TARGET_PLATFORMS), required=True)
    parser.add_argument("--scenario", choices=("hardware", "simulation"), required=True)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--checksums", type=Path, required=True)
    parser.add_argument("--mode", choices=("online", "offline"), required=True)
    parser.add_argument(
        "--deployment-root",
        type=Path,
        default=Path("/srv/scrap-monitoring/deployment"),
    )
    parser.add_argument("--environment-file", type=Path)
    parser.add_argument("--host-root", type=Path, default=Path("/"))
    parser.add_argument(
        "--lock-file",
        type=Path,
        default=Path("/run/lock/scrap-monitoring-deployment.lock"),
    )
    return parser.parse_args()


def run_checked(
    command: list[str],
    *,
    environment: dict[str, str] | None = None,
    capture_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=True,
        capture_output=capture_output,
        text=True,
        env=environment,
    )


def copy_regular_input(source: Path, destination: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(source, flags)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError(f"release input is not a regular file: {source}")
        with (
            os.fdopen(descriptor, "rb", closefd=False) as input_file,
            destination.open("xb") as output,
        ):
            shutil.copyfileobj(input_file, output, length=1024 * 1024)
        destination.chmod(0o600)
    finally:
        os.close(descriptor)


def snapshot_release_inputs(
    args: argparse.Namespace, deployment_root: Path
) -> tuple[Path, argparse.Namespace]:
    snapshot = Path(tempfile.mkdtemp(prefix=".release-input.", dir=deployment_root))
    snapshot.chmod(0o700)
    try:
        package = snapshot / args.package.name
        checksums = snapshot / args.checksums.name
        copy_regular_input(args.package, package)
        copy_regular_input(args.checksums, checksums)
    except Exception:
        shutil.rmtree(snapshot)
        raise
    values = vars(args).copy()
    values.update(package=package, checksums=checksums)
    return snapshot, argparse.Namespace(**values)


def ensure_directory(path: Path, mode: int = 0o755) -> None:
    if path.is_symlink():
        raise ValueError(f"directory must not be symbolic: {path}")
    existed = path.exists()
    path.mkdir(parents=True, exist_ok=True)
    if not path.is_dir():
        raise ValueError(f"path is not a directory: {path}")
    if not existed:
        path.chmod(mode)


def map_host_path(host_root: Path, configured_path: str) -> Path:
    relative = PurePosixPath(configured_path)
    if (
        not relative.is_absolute()
        or relative.as_posix() != configured_path
        or ".." in relative.parts
    ):
        raise ValueError(
            f"host path must be absolute and normalized: {configured_path}"
        )
    if host_root == Path("/"):
        return Path(configured_path)
    return host_root.joinpath(*relative.parts[1:])


def require_host_path(
    host_root: Path,
    configured_path: str,
    *,
    directory: bool,
    label: str,
    character_device: bool = False,
) -> Path:
    path = map_host_path(host_root, configured_path)
    current = host_root
    for part in path.relative_to(host_root).parts:
        current /= part
        if current.is_symlink():
            raise ValueError(f"{label} path must not contain a symbolic link: {path}")
    if character_device and host_root == Path("/"):
        valid = path.exists() and stat.S_ISCHR(path.stat().st_mode)
    else:
        valid = path.is_dir() if directory else path.is_file()
    if not valid:
        kind = "directory" if directory else "file"
        raise ValueError(f"{label} {kind} is missing: {path}")
    return path


def parse_environment(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        key, value = line.split("=", maxsplit=1)
        values[key] = value
    return values


def unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    document: dict[str, Any] = {}
    for key, value in pairs:
        if key in document:
            raise ValueError(f"duplicate Edge configuration field: {key}")
        document[key] = value
    return document


def validate_environment_file(path: Path, host_root: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"target environment file is missing or symbolic: {path}")
    if stat.S_IMODE(path.stat().st_mode) != 0o640:
        raise ValueError(f"target environment file mode must be 0640: {path}")
    if host_root == Path("/") and path.stat().st_uid != 0:
        raise ValueError(f"target environment file must be owned by root: {path}")


def validate_host_platform(target: str, override: str | None = None) -> str:
    actual = override or MACHINE_PLATFORMS.get(platform.machine().lower())
    expected = TARGET_PLATFORMS[target]
    if actual != expected:
        raise ValueError(
            f"host platform does not match {target}: {actual or 'unknown'}"
        )
    return expected


def scenario_components(
    manifest: dict[str, Any], target: str, scenario: str
) -> list[dict[str, Any]]:
    components = {
        component["name"]: component
        for component in manifest["targets"][target]["components"]
    }
    return [
        components[name] for name in manifest["targets"][target]["scenarios"][scenario]
    ]


def verify_images(
    manifest: dict[str, Any], target: str, scenario: str, mode: str
) -> None:
    expected_platform = TARGET_PLATFORMS[target]
    for component in scenario_components(manifest, target, scenario):
        image = component["image"]
        if mode == "online":
            run_checked(["docker", "pull", "--platform", expected_platform, image])
        result = run_checked(
            [
                "docker",
                "image",
                "inspect",
                "--format",
                "{{.Os}}/{{.Architecture}}",
                image,
            ],
            capture_output=True,
        )
        if result.stdout.strip() != expected_platform:
            raise RuntimeError(f"image platform does not match the target: {image}")


def should_stage(name: str) -> bool:
    return name not in RUNTIME_EXCLUDED_FILES and not name.startswith(
        RUNTIME_EXCLUDED_PREFIXES
    )


def extract_runtime(package: Path, destination: Path) -> None:
    with tarfile.open(package, mode="r:gz") as archive:
        members = archive_members(archive)
        for name, member in sorted(members.items()):
            if not should_stage(name):
                continue
            output = destination.joinpath(*PurePosixPath(name).parts)
            output.parent.mkdir(parents=True, exist_ok=True)
            source = archive.extractfile(member)
            if source is None:
                raise ValueError(f"archive member cannot be read: {name}")
            with source, output.open("xb") as target_file:
                shutil.copyfileobj(source, target_file, length=1024 * 1024)
            output.chmod(member.mode)


def release_variables(
    manifest: dict[str, Any], target: str, scenario: str
) -> dict[str, str]:
    variables = {
        "DEPLOYMENT_REVISION": manifest["version"],
        "DEPLOYMENT_SCENARIO": scenario,
    }
    for component in scenario_components(manifest, target, scenario):
        variable = f"{component['name'].replace('-', '_').upper()}_IMAGE"
        if variable in variables:
            raise ValueError(f"duplicate release environment variable: {variable}")
        variables[variable] = component["image"]
    return variables


def write_environment(path: Path, variables: dict[str, str]) -> None:
    content = "".join(f"{key}={value}\n" for key, value in variables.items())
    write_atomic(path, content.encode(), 0o644)


def write_atomic(path: Path, content: bytes, mode: int) -> None:
    ensure_directory(path.parent)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        temporary.chmod(mode)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def create_edge_generated_environment(
    environment: dict[str, str],
    host_root: Path,
) -> bytes:
    config = require_host_path(
        host_root,
        environment["CONFIG_FILE"],
        directory=False,
        label="Edge configuration",
    )
    config_bytes = config.read_bytes()
    if len(config_bytes) > MAX_EDGE_CONFIG_SIZE:
        raise ValueError("Edge configuration is too large")
    document = json.loads(config_bytes, object_pairs_hook=unique_json_object)
    if not isinstance(document, dict):
        raise TypeError("Edge configuration must be a JSON object")
    for key in ("SITE_ID", "EDGE_ID", "CAMERA_ID", "CONFIG_REVISION"):
        if key in document and document[key] != environment[key]:
            raise ValueError(f"Edge configuration does not match {key}")
    digest = hashlib.sha256(config_bytes).hexdigest()
    return f"CONFIG_SHA256={digest}\n".encode()


def validate_target_inputs(
    stage: Path,
    target: str,
    scenario: str,
    environment_file: Path,
    host_root: Path,
) -> tuple[dict[str, str], bytes | None]:
    validator = stage / "delivery" / "validate-environment"
    run_checked([str(validator), target, scenario, str(environment_file)])
    environment = parse_environment(environment_file)
    if environment["DEPLOYMENT_SCENARIO"] != scenario:
        raise ValueError("target environment scenario does not match the package")
    generated = None
    if target == "edge":
        generated = create_edge_generated_environment(environment, host_root)
        require_host_path(
            host_root,
            environment["RUNTIME_DIR"],
            directory=True,
            label="Edge runtime",
        )
        camera_device = environment["CAMERA_DEVICE"]
        require_host_path(
            host_root,
            camera_device,
            directory=False,
            label="Camera device",
            character_device=True,
        )
        require_host_path(
            host_root,
            environment["EDGE_ROOT_CA_FILE"],
            directory=False,
            label="Edge Root CA",
        )
    else:
        require_host_path(
            host_root,
            environment["BACKEND_DATA_PATH"],
            directory=True,
            label="Backend data",
        )
        require_host_path(
            host_root,
            environment["MEDIA_STORAGE_PATH"],
            directory=True,
            label="Media storage",
        )
    secret_validator = stage / "delivery" / "validate-auth-secrets"
    command = [str(secret_validator), "--root", str(host_root), target]
    if target == "edge":
        command.append(str(environment_file))
    run_checked(command)
    return environment, generated


def compose_environment(
    target_environment: dict[str, str],
    release_environment: dict[str, str],
    generated: bytes | None,
) -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(target_environment)
    environment.update(release_environment)
    if generated is not None:
        key, value = generated.decode().strip().split("=", maxsplit=1)
        environment[key] = value
    return environment


def validate_compose(stage: Path, target: str, environment: dict[str, str]) -> set[str]:
    project = stage / "targets" / target
    base = ["docker", "compose", "--project-directory", str(project)]
    run_checked([*base, "config", "--quiet"], environment=environment)
    result = run_checked(
        [*base, "config", "--services"],
        environment=environment,
        capture_output=True,
    )
    services = set(result.stdout.splitlines())
    if not services:
        raise ValueError(f"Compose target has no services: {target}")
    return services


def tree_digest(root: Path, *, exclude_metadata: bool = False) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"staged path must not be symbolic: {path}")
        if path.is_dir():
            continue
        if exclude_metadata and path == root / "deployment-metadata.json":
            continue
        relative = path.relative_to(root).as_posix().encode()
        digest.update(relative)
        digest.update(b"\0")
        digest.update(f"{stat.S_IMODE(path.stat().st_mode):04o}".encode())
        digest.update(b"\0")
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        digest.update(b"\0")
    return digest.hexdigest()


def deployment_metadata(
    stage: Path,
    manifest: dict[str, Any],
    target: str,
    scenario: str,
) -> dict[str, Any]:
    manifest_digest = hashlib.sha256(
        (stage / "release-manifest.json").read_bytes()
    ).hexdigest()
    return {
        "schemaVersion": 2,
        "version": manifest["version"],
        "target": target,
        "scenario": scenario,
        "platform": TARGET_PLATFORMS[target],
        "manifestSha256": manifest_digest,
        "contentSha256": tree_digest(stage),
    }


def write_metadata(stage: Path, metadata: dict[str, Any]) -> None:
    content = (json.dumps(metadata, indent=2, sort_keys=True) + "\n").encode()
    write_atomic(stage / "deployment-metadata.json", content, 0o644)


def validate_existing_version(path: Path, expected: dict[str, Any]) -> None:
    if path.is_symlink() or not path.is_dir():
        raise ValueError(f"existing version path is invalid: {path}")
    metadata_path = path / "deployment-metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if metadata != expected:
        raise ValueError(f"existing version metadata does not match: {path.name}")
    if tree_digest(path, exclude_metadata=True) != metadata["contentSha256"]:
        raise ValueError(f"existing version content was modified: {path.name}")


def read_link(path: Path, versions: Path) -> LinkState:
    if not path.exists() and not path.is_symlink():
        return LinkState(None)
    if not path.is_symlink():
        raise ValueError(f"deployment pointer is not a symbolic link: {path}")
    raw = os.readlink(path)
    candidate = path.parent / raw
    if candidate.is_symlink():
        raise ValueError(f"deployment pointer target is symbolic: {path}")
    resolved = candidate.resolve(strict=True)
    versions_resolved = versions.resolve(strict=True)
    canonical = f"versions/{resolved.name}"
    if raw != canonical or resolved.parent != versions_resolved:
        raise ValueError(f"deployment pointer is outside versions: {path}")
    return LinkState(canonical)


def set_link(path: Path, target: str | None) -> None:
    if path.exists() and not path.is_symlink():
        raise ValueError(f"deployment pointer is not a symbolic link: {path}")
    if target is None:
        path.unlink(missing_ok=True)
        return
    temporary = path.parent / f".{path.name}.{os.getpid()}"
    temporary.unlink(missing_ok=True)
    os.symlink(target, temporary)
    os.replace(temporary, path)


def compose_is_healthy(
    deployment_root: Path,
    target: str,
    expected_services: set[str],
    environment: dict[str, str],
) -> bool:
    project = deployment_root / "current" / "targets" / target
    base = ["docker", "compose", "--project-directory", str(project)]
    result = subprocess.run(
        [*base, "ps", "--status", "running", "--services"],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    return (
        result.returncode == 0 and set(result.stdout.splitlines()) == expected_services
    )


def write_state(
    state_directory: Path,
    version: str,
    target: str,
    scenario: str,
    result: str,
    current: LinkState,
    previous: LinkState,
) -> None:
    document = {
        "schemaVersion": 2,
        "version": version,
        "target": target,
        "scenario": scenario,
        "result": result,
        "current": current.target,
        "previous": previous.target,
    }
    content = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode()
    write_atomic(state_directory / f"{target}.json", content, 0o644)


def prepare_server_certificate(
    stage: Path,
    environment: dict[str, str],
    host_root: Path,
) -> None:
    pki_root = map_host_path(host_root, "/srv/scrap-monitoring/pki")
    run_checked(
        [
            str(stage / "pki" / "ensure-server-certificate"),
            "--fqdn",
            environment["SERVER_FQDN"],
            "--expected-root-sha256",
            environment["PKI_ROOT_CA_SHA256"],
            "--ca-url",
            environment["PKI_CA_URL"],
            "--root-directory",
            str(pki_root / "root"),
            "--step-ca-directory",
            str(pki_root / "step-ca"),
            "--tls-directory",
            str(pki_root / "tls"),
            "--tls-group",
            environment["DASHBOARD_SCRAP_ADMIN_GID"],
            "--lock-file",
            str(
                map_host_path(host_root, "/run/lock/scrap-monitoring-certificate.lock")
            ),
        ]
    )


def rollback_runtime(
    deployment_root: Path,
    service: str,
    original_current: LinkState,
    original_previous: LinkState,
    certificate_snapshot: CertificateSnapshot | None,
    generated_path: Path | None,
    generated_content: bytes | None,
    generated_mode: int | None,
) -> None:
    subprocess.run(["systemctl", "stop", service], check=False)
    set_link(deployment_root / "current", original_current.target)
    set_link(deployment_root / "previous", original_previous.target)
    if certificate_snapshot is not None:
        certificate_snapshot.restore()
    if generated_path is not None:
        if generated_content is None:
            generated_path.unlink(missing_ok=True)
        else:
            write_atomic(generated_path, generated_content, generated_mode or 0o644)
    if original_current.target is not None:
        subprocess.run(["systemctl", "restart", service], check=False)


def apply_release(
    args: argparse.Namespace, *, host_platform: str | None = None
) -> Path:
    deployment_root = args.deployment_root.resolve()
    host_root = args.host_root.resolve()
    if (
        args.deployment_root == Path("/srv/scrap-monitoring/deployment")
        and os.geteuid() != 0
    ):
        raise PermissionError("default deployment root requires root privileges")
    if args.deployment_root.is_symlink() or args.host_root.is_symlink():
        raise ValueError("deployment root and host root must not be symbolic")
    ensure_directory(deployment_root)
    versions = deployment_root / "versions"
    state_directory = deployment_root / "state"
    ensure_directory(versions)
    ensure_directory(state_directory)
    ensure_directory(args.lock_file.parent)
    if args.lock_file.is_symlink():
        raise ValueError(f"deployment lock must not be symbolic: {args.lock_file}")

    environment_file = args.environment_file or map_host_path(
        host_root, f"/etc/scrap-monitoring/{args.target}.env"
    )
    service = f"scrap-monitoring-{args.target}.service"
    certificate_snapshot: CertificateSnapshot | None = None
    generated_path: Path | None = None
    generated_content: bytes | None = None
    generated_mode: int | None = None
    transition_started = False
    input_snapshot: Path | None = None

    with args.lock_file.open("a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        original_current = read_link(deployment_root / "current", versions)
        original_previous = read_link(deployment_root / "previous", versions)
        try:
            validate_environment_file(environment_file, host_root)
            input_snapshot, stable_args = snapshot_release_inputs(args, deployment_root)
            mode, manifest = verify_release(stable_args)
            if mode != args.mode:
                raise ValueError(f"package mode does not match requested mode: {mode}")
            validate_host_platform(args.target, host_platform)
            verify_images(manifest, args.target, args.scenario, mode)

            with tempfile.TemporaryDirectory(
                prefix=f".{args.version}-{args.scenario}.", dir=versions
            ) as temporary:
                stage = Path(temporary)
                stage.chmod(0o755)
                extract_runtime(stable_args.package, stage)
                release_environment = release_variables(
                    manifest, args.target, args.scenario
                )
                write_environment(
                    stage / "targets" / args.target / "release.env",
                    release_environment,
                )
                target_environment, generated = validate_target_inputs(
                    stage,
                    args.target,
                    args.scenario,
                    environment_file,
                    host_root,
                )
                command_environment = compose_environment(
                    target_environment,
                    release_environment,
                    generated,
                )
                services = validate_compose(stage, args.target, command_environment)
                metadata = deployment_metadata(
                    stage, manifest, args.target, args.scenario
                )
                write_metadata(stage, metadata)

                destination = versions / f"{args.version}-{args.scenario}"
                if destination.exists() or destination.is_symlink():
                    validate_existing_version(destination, metadata)
                    runtime = destination
                else:
                    runtime = stage
                if args.target == "server":
                    tls_directory = map_host_path(
                        host_root, "/srv/scrap-monitoring/pki/tls"
                    )
                    certificate_snapshot = CertificateSnapshot(tls_directory)
                    certificate_snapshot.capture()
                    prepare_server_certificate(runtime, target_environment, host_root)
                if runtime == stage:
                    os.replace(stage, destination)

            new_target = f"versions/{args.version}-{args.scenario}"
            generated_changed = False
            if generated is not None:
                generated_path = state_directory / "edge.generated.env"
                if generated_path.is_symlink():
                    raise ValueError(
                        f"generated environment must not be symbolic: {generated_path}"
                    )
                if generated_path.exists():
                    generated_content = generated_path.read_bytes()
                    generated_mode = stat.S_IMODE(generated_path.stat().st_mode)
                generated_changed = generated_content != generated

            if original_current.target == new_target and not generated_changed:
                active = (
                    subprocess.run(
                        ["systemctl", "is-active", "--quiet", service],
                        check=False,
                    ).returncode
                    == 0
                )
                if active and compose_is_healthy(
                    deployment_root,
                    args.target,
                    services,
                    command_environment,
                ):
                    write_state(
                        state_directory,
                        args.version,
                        args.target,
                        args.scenario,
                        "success",
                        original_current,
                        original_previous,
                    )
                    return destination

            transition_started = True
            if generated is not None and generated_path is not None:
                write_atomic(generated_path, generated, 0o644)
            if original_current.target != new_target:
                set_link(deployment_root / "previous", original_current.target)
            set_link(deployment_root / "current", new_target)
            run_checked(["systemctl", "restart", service])
            if not compose_is_healthy(
                deployment_root,
                args.target,
                services,
                command_environment,
            ):
                raise RuntimeError(f"Compose services are not healthy: {args.target}")

            current = read_link(deployment_root / "current", versions)
            previous = read_link(deployment_root / "previous", versions)
            write_state(
                state_directory,
                args.version,
                args.target,
                args.scenario,
                "success",
                current,
                previous,
            )
            return destination
        except Exception:
            current_after_error = read_link(deployment_root / "current", versions)
            if (
                transition_started
                or current_after_error != original_current
                or certificate_snapshot is not None
            ):
                rollback_runtime(
                    deployment_root,
                    service,
                    original_current,
                    original_previous,
                    certificate_snapshot,
                    generated_path,
                    generated_content,
                    generated_mode,
                )
            write_state(
                state_directory,
                args.version,
                args.target,
                args.scenario,
                "failed",
                original_current,
                original_previous,
            )
            raise
        finally:
            if certificate_snapshot is not None:
                certificate_snapshot.cleanup()
            if input_snapshot is not None:
                shutil.rmtree(input_snapshot)


def main() -> None:
    args = parse_args()
    try:
        destination = apply_release(args)
    except (
        KeyError,
        OSError,
        RuntimeError,
        subprocess.SubprocessError,
        tarfile.TarError,
        TypeError,
        UnicodeError,
        ValueError,
    ) as error:
        raise SystemExit(f"release apply failed: {error}") from error
    print(destination)


if __name__ == "__main__":
    main()
