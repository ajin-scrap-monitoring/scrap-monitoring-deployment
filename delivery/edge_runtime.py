from __future__ import annotations

import argparse
import os
import stat
import subprocess
import sys
from pathlib import Path, PurePosixPath

EDGE_RUNTIME_UID = 10001
EDGE_RUNTIME_GID = 10001
DIRECTORY_MODE = 0o750
PARENT_MODE = 0o755
DEFAULT_ENVIRONMENT_PATH = PurePosixPath("etc/scrap-monitoring/edge.env")
RUNTIME_SUBDIRECTORIES = (
    "sockets",
    "sockets/a",
    "sockets/b",
    "sockets/observations",
    "sockets/delivery",
    "status",
    "outbox",
    "clock",
)
POSTGRESQL_INIT_FILES = (
    "init.sh",
    "roles.sql",
    "runtime-grants.sql",
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="install-edge-runtime",
        description=(
            "Create and validate the host directories required by the Edge v2 Compose stack."
        ),
    )
    parser.add_argument(
        "--environment",
        type=Path,
        default=None,
        help="Path to the validated edge.env file (defaults to <root>/etc/scrap-monitoring/edge.env).",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("/"),
        help="Host root directory override for isolated testing.",
    )
    return parser.parse_args(argv)


def resolve_host_root(root: Path) -> Path:
    candidate = Path(os.path.abspath(root))
    if root.is_symlink() or not root.is_dir():
        raise ValueError(
            f"host root must be an existing non-symbolic directory: {root}"
        )
    current = Path(candidate.anchor)
    for part in candidate.parts[1:]:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"host root path must not contain symlinks: {current}")
    return Path(os.path.realpath(candidate))


def resolve_existing_file(path: Path, label: str) -> Path:
    candidate = Path(os.path.abspath(path))
    current = Path(candidate.anchor)
    for part in candidate.parts[1:]:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"{label} path must not contain symlinks: {current}")
    if path.is_symlink() or not path.is_file():
        raise ValueError(
            f"{label} must be an existing non-symbolic regular file: {path}"
        )
    return path


def parse_environment_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError("invalid line in edge environment file")
        key, value = line.split("=", maxsplit=1)
        values[key] = value
    return values


def validate_absolute_directory_value(raw: str, name: str) -> PurePosixPath:
    if not raw or "\x00" in raw or not raw.startswith("/"):
        raise ValueError(f"{name} must be an absolute path")
    parts = [part for part in raw.split("/") if part]
    if not parts or any(part in {".", ".."} for part in parts):
        raise ValueError(f"{name} must be a canonical non-root directory path")
    return PurePosixPath("/", *parts)


def resolve_target_path(
    host_root: Path, absolute_path: PurePosixPath, label: str
) -> tuple[Path, list[Path]]:
    relative_parts = absolute_path.parts[1:]
    current = host_root
    lineage: list[Path] = []
    for part in relative_parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"{label} path contains a symbolic link: {current}")
        if current.exists() and not current.is_dir():
            raise ValueError(f"{label} path is not a directory: {current}")
        lineage.append(current)
    return current, lineage


def ensure_directory(path: Path, mode: int, *, apply_owner: bool) -> None:
    if path.is_symlink():
        raise ValueError(f"runtime path must not be symbolic: {path}")
    if path.exists() and not path.is_dir():
        raise ValueError(f"runtime path must be a directory: {path}")
    if not path.exists():
        path.mkdir(mode=mode)
    if path.is_symlink() or not path.is_dir():
        raise ValueError(f"runtime path must be a non-symbolic directory: {path}")
    os.chmod(path, mode)
    if apply_owner:
        os.chown(path, EDGE_RUNTIME_UID, EDGE_RUNTIME_GID)
    metadata = os.lstat(path)
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise ValueError(f"runtime path is invalid after creation: {path}")
    if stat.S_IMODE(metadata.st_mode) != mode:
        raise ValueError(f"runtime directory mode mismatch: {path}")
    if apply_owner and (
        metadata.st_uid != EDGE_RUNTIME_UID or metadata.st_gid != EDGE_RUNTIME_GID
    ):
        raise ValueError(f"runtime directory owner mismatch: {path}")


def install_edge_runtime(
    environment_path: Path | None,
    root_directory: Path,
) -> tuple[Path, Path]:
    host_root = resolve_host_root(root_directory)
    apply_owner = host_root == Path("/")
    if apply_owner and os.geteuid() != 0:
        raise PermissionError(
            "installing Edge runtime directories requires root privileges"
        )

    raw_environment = (
        environment_path
        if environment_path is not None
        else host_root.joinpath(*DEFAULT_ENVIRONMENT_PATH.parts)
    )
    resolved_environment = resolve_existing_file(raw_environment, "Edge environment")

    validator = Path(__file__).resolve().with_name("validate-environment")
    validation = subprocess.run(
        [str(validator), "edge", str(resolved_environment)],
        check=False,
        capture_output=True,
        text=True,
    )
    if validation.returncode != 0:
        detail = validation.stderr.strip() or "edge environment validation failed"
        raise ValueError(detail)

    environment = parse_environment_file(resolved_environment)
    runtime_posix = validate_absolute_directory_value(
        environment.get("RUNTIME_DIR", ""), "RUNTIME_DIR"
    )
    control_posix = validate_absolute_directory_value(
        environment.get("CONTROL_DIR", ""), "CONTROL_DIR"
    )
    reserved_subdirectories = {
        runtime_posix,
        *(runtime_posix / subdirectory for subdirectory in RUNTIME_SUBDIRECTORIES),
    }
    if control_posix in reserved_subdirectories:
        raise ValueError("CONTROL_DIR must not collide with RUNTIME_DIR subdirectories")

    runtime_host, runtime_lineage = resolve_target_path(
        host_root, runtime_posix, "Edge runtime"
    )
    subdir_plans: list[tuple[Path, list[Path]]] = []
    for subdirectory in RUNTIME_SUBDIRECTORIES:
        subdir_plans.append(
            resolve_target_path(
                host_root, runtime_posix / subdirectory, f"Edge runtime {subdirectory}"
            )
        )
    control_host, control_lineage = resolve_target_path(
        host_root, control_posix, "Edge control directory"
    )

    # Create missing parent directories above RUNTIME_DIR without changing system dirs.
    for parent in runtime_lineage[:-1]:
        if not parent.exists():
            ensure_directory(parent, PARENT_MODE, apply_owner=False)
    ensure_directory(runtime_host, DIRECTORY_MODE, apply_owner=apply_owner)
    managed_dirs = {runtime_host}

    for _, lineage in subdir_plans:
        for component in lineage[len(runtime_lineage) :]:
            if component in managed_dirs:
                continue
            ensure_directory(component, DIRECTORY_MODE, apply_owner=apply_owner)
            managed_dirs.add(component)

    for component in control_lineage[:-1]:
        if component in managed_dirs:
            continue
        if component.is_relative_to(runtime_host):
            ensure_directory(component, DIRECTORY_MODE, apply_owner=apply_owner)
            managed_dirs.add(component)
        elif not component.exists():
            ensure_directory(component, PARENT_MODE, apply_owner=False)
    ensure_directory(control_host, DIRECTORY_MODE, apply_owner=apply_owner)
    return runtime_host, control_host


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        runtime_host, control_host = install_edge_runtime(args.environment, args.root)
    except (OSError, PermissionError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1
    print(f"edge runtime directories prepared: {runtime_host} ({control_host})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
