from __future__ import annotations

import argparse
import fcntl
import grp
import json
import os
import re
import stat
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

CONFIGURATION_PATH = Path("etc/scrap-monitoring/dashboard/runtime-config.json")
MAX_CONFIGURATION_BYTES = 4096
CAMERA_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._~-]{0,127}")
JAVASCRIPT_WHITESPACE = (
    "\t\n\v\f\r \u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006"
    "\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000\ufeff"
)


def validate_document(document: object) -> dict[str, object]:
    if not isinstance(document, dict) or set(document) != {
        "schemaVersion",
        "pitId",
        "cameraId",
    }:
        raise ValueError(
            "Dashboard configuration must contain exactly the required fields"
        )
    version = document["schemaVersion"]
    if type(version) not in (int, float) or version != 1:
        raise ValueError("unsupported Dashboard configuration schemaVersion")
    pit_id = document["pitId"]
    if (
        not isinstance(pit_id, str)
        or not 1 <= len(pit_id) <= 50
        or not pit_id.strip(JAVASCRIPT_WHITESPACE)
        or any(ord(character) < 32 or ord(character) == 127 for character in pit_id)
        or any(0xD800 <= ord(character) <= 0xDFFF for character in pit_id)
    ):
        raise ValueError("invalid Dashboard pitId")
    camera_id = document["cameraId"]
    if not isinstance(camera_id, str) or not CAMERA_ID_PATTERN.fullmatch(camera_id):
        raise ValueError("invalid Dashboard cameraId")
    return document


def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    document: dict[str, object] = {}
    for key, value in pairs:
        if key in document:
            raise ValueError("duplicate Dashboard configuration field")
        document[key] = value
    return document


def reject_json_constant(value: str) -> None:
    raise ValueError("invalid Dashboard configuration JSON constant")


def reject_symbolic_path(path: Path) -> None:
    for component in (path, *path.parents):
        if component.is_symlink():
            raise ValueError("Dashboard configuration paths must not be symbolic")


def host_context(root: Path) -> tuple[Path, int, int]:
    root = root.absolute()
    reject_symbolic_path(root)
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("host root must be an existing directory")
    if root == Path("/"):
        if os.geteuid() != 0:
            raise ValueError(
                "host Dashboard configuration operations require root privileges"
            )
        try:
            group = grp.getgrnam("scrap-admin")
        except KeyError as error:
            raise ValueError(
                "run install-container-runtime --target server first"
            ) from error
        if group.gr_gid == 0:
            raise ValueError("scrap-admin must not use the root group ID")
        return root, 0, group.gr_gid
    metadata = root.stat()
    return root, metadata.st_uid, metadata.st_gid


def require_directory(path: Path, owner: int, group: int) -> None:
    reject_symbolic_path(path)
    metadata = path.stat()
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o750
        or metadata.st_uid != owner
        or metadata.st_gid != group
    ):
        raise ValueError(
            "Dashboard configuration directory ownership or mode is invalid"
        )


def prepare_directory(path: Path, owner: int, group: int) -> None:
    reject_symbolic_path(path)
    if not path.exists():
        path.mkdir(mode=0o750)
        os.chown(path, owner, group)
        path.chmod(0o750)
    require_directory(path, owner, group)


def require_file_metadata(
    metadata: os.stat_result, owner: int, group: int, mode: int
) -> None:
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or stat.S_IMODE(metadata.st_mode) != mode
        or metadata.st_uid != owner
        or metadata.st_gid != group
    ):
        raise ValueError(
            "Dashboard configuration file ownership, mode or link count is invalid"
        )


def load_configuration(path: Path, owner: int, group: int) -> dict[str, object]:
    reject_symbolic_path(path)
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as source:
        require_file_metadata(os.fstat(source.fileno()), owner, group, 0o644)
        payload = source.read(MAX_CONFIGURATION_BYTES + 1)
    if len(payload) > MAX_CONFIGURATION_BYTES:
        raise ValueError("Dashboard configuration exceeds the size limit")
    try:
        document = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=unique_object,
            parse_constant=reject_json_constant,
        )
    except (UnicodeError, json.JSONDecodeError, RecursionError) as error:
        raise ValueError("invalid Dashboard configuration JSON") from error
    return validate_document(document)


def require_identifiers(
    document: dict[str, object], pit_id: str | None, camera_id: str | None
) -> None:
    if pit_id is not None and document["pitId"] != pit_id:
        raise ValueError("Dashboard pitId does not match the expected identifier")
    if camera_id is not None and document["cameraId"] != camera_id:
        raise ValueError("Dashboard cameraId does not match the expected identifier")


@contextmanager
def configuration_lock(path: Path, owner: int, group: int) -> Iterator[None]:
    reject_symbolic_path(path)
    flags = os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK
    try:
        descriptor = os.open(path, flags | os.O_CREAT | os.O_EXCL, 0o600)
        created = True
    except FileExistsError:
        descriptor = os.open(path, flags)
        created = False
    with os.fdopen(descriptor, "r+b") as lock:
        if created:
            os.fchown(lock.fileno(), owner, group)
            os.fchmod(lock.fileno(), 0o600)
        metadata = os.fstat(lock.fileno())
        require_file_metadata(metadata, owner, group, 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def configuration_directories(root: Path) -> tuple[Path, Path]:
    directory = (root / CONFIGURATION_PATH).parent
    return directory.parent, directory


@contextmanager
def directory_lock(path: Path) -> Iterator[None]:
    reject_symbolic_path(path)
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        os.close(descriptor)


def install_configuration(root: Path, pit_id: str, camera_id: str) -> bool:
    document = validate_document(
        {"schemaVersion": 1, "pitId": pit_id, "cameraId": camera_id}
    )
    root, owner, group = host_context(root)
    configuration_root, directory = configuration_directories(root)
    etc = configuration_root.parent
    reject_symbolic_path(etc)
    if not etc.exists():
        etc.mkdir(mode=0o755, exist_ok=True)
    if not etc.is_dir():
        raise ValueError("host etc path must be a directory")
    with directory_lock(etc):
        prepare_directory(configuration_root, owner, group)
        prepare_directory(directory, owner, group)
    path = root / CONFIGURATION_PATH
    lock_group = 0 if root == Path("/") else root.stat().st_gid
    with configuration_lock(directory / ".configuration.lock", owner, lock_group):
        reject_symbolic_path(path)
        if path.exists():
            existing = load_configuration(path, owner, group)
            require_identifiers(existing, pit_id, camera_id)
            return False
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".runtime-config.", dir=directory
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as destination:
                os.fchown(destination.fileno(), owner, group)
                os.fchmod(destination.fileno(), 0o644)
                destination.write(
                    (json.dumps(document, ensure_ascii=False, indent=2) + "\n").encode(
                        "utf-8"
                    )
                )
                destination.flush()
                os.fsync(destination.fileno())
            load_configuration(temporary, owner, group)
            try:
                os.link(temporary, path, follow_symlinks=False)
            except FileExistsError as error:
                raise ValueError(
                    "Dashboard configuration appeared; existing file preserved"
                ) from error
        finally:
            temporary.unlink(missing_ok=True)
        directory_descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
        load_configuration(path, owner, group)
    return True


def validate_configuration(
    root: Path, pit_id: str | None, camera_id: str | None
) -> None:
    root, owner, group = host_context(root)
    for directory in configuration_directories(root):
        require_directory(directory, owner, group)
    document = load_configuration(root / CONFIGURATION_PATH, owner, group)
    require_identifiers(document, pit_id, camera_id)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Manage host Dashboard runtime configuration."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    install = commands.add_parser(
        "install", help="Install or preserve Dashboard configuration."
    )
    install.add_argument("--pit-id", required=True)
    install.add_argument("--camera-id", required=True)
    validate = commands.add_parser(
        "validate", help="Validate installed Dashboard configuration."
    )
    validate.add_argument("--expected-pit-id")
    validate.add_argument("--expected-camera-id")
    for command in (install, validate):
        command.add_argument("--root", type=Path, default=Path("/"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.command == "install":
            created = install_configuration(args.root, args.pit_id, args.camera_id)
            print(
                "Dashboard runtime configuration installed."
                if created
                else "Existing Dashboard runtime configuration preserved."
            )
        else:
            validate_configuration(
                args.root, args.expected_pit_id, args.expected_camera_id
            )
            print("Dashboard runtime configuration valid.")
    except (OSError, ValueError) as error:
        print(f"Dashboard configuration failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
