from __future__ import annotations

import argparse
import json
import math
import os
import stat
import sys
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

MAX_CONFIGURATION_BYTES = 16 * 1024 * 1024
RUNTIME_FIELDS = {
    "configuration",
    "drivers",
    "delivery_endpoint",
    "observation_endpoint",
    "storage_dir",
    "status_dir",
    "clock_domain_file",
    "backend_origin",
    "token_file",
}


def absolute_path(value: object) -> str:
    if not isinstance(value, str) or not value.startswith("/"):
        raise ValueError("runtime paths must be absolute")
    path = PurePosixPath(value)
    if (
        value == "/"
        or value.startswith("//")
        or str(path) != value
        or ".." in path.parts
        or any(ord(c) < 32 or ord(c) == 127 for c in value)
    ):
        raise ValueError("runtime paths must be normalized and non-root")
    return value


def https_origin(value: object) -> str:
    if not isinstance(value, str) or any(ord(c) <= 32 or ord(c) >= 127 for c in value):
        raise ValueError("Backend requires a credential-free HTTPS origin")
    try:
        parsed = urlsplit(value)
        valid = (
            parsed.scheme == "https"
            and parsed.hostname
            and not parsed.username
            and not parsed.password
            and not parsed.query
            and not parsed.fragment
            and parsed.path in ("", "/")
            and "@" not in parsed.netloc
            and not any(c in parsed.netloc for c in ("\\", "%"))
            and (parsed.port is None or 1 <= parsed.port <= 65535)
        )
    except ValueError:
        valid = False
    if not valid:
        raise ValueError("Backend requires a credential-free HTTPS origin")
    return value.rstrip("/")


def validate_runtime(document: object, environment: dict[str, str]) -> None:
    if not isinstance(document, dict) or set(document) != RUNTIME_FIELDS:
        raise ValueError("Edge runtime must contain exactly the supported fields")
    registration = document["configuration"]
    if not isinstance(registration, dict) or (
        registration.get("schema_version") != "2.0"
        or registration.get("message_type") != "edge_configuration"
    ):
        raise ValueError("Edge runtime requires a v2 configuration registration")
    for field, key in (
        ("site_id", "SITE_ID"),
        ("edge_id", "EDGE_ID"),
        ("config_revision", "CONFIG_REVISION"),
    ):
        if registration.get(field) != environment[key]:
            raise ValueError(f"Edge configuration does not match {key}")
    sensors = registration.get("sensors")
    if not isinstance(sensors, list) or len(sensors) != 2:
        raise ValueError("Edge configuration requires two LiDAR sensors")
    sensor_ids = [s.get("sensor_id") if isinstance(s, dict) else None for s in sensors]
    if (
        any(not isinstance(s, str) or not s for s in sensor_ids)
        or len(set(sensor_ids)) != 2
    ):
        raise ValueError("Edge configuration requires distinct sensor identifiers")
    drivers = document["drivers"]
    if not isinstance(drivers, dict) or set(drivers) != set(sensor_ids):
        raise ValueError("driver endpoints must match configuration sensor identifiers")
    endpoints = [
        document["delivery_endpoint"],
        document["observation_endpoint"],
        *drivers.values(),
    ]
    paths = []
    for endpoint in endpoints:
        if not isinstance(endpoint, str) or not endpoint.startswith("unix:/"):
            raise ValueError("Edge runtime requires private Unix domain sockets")
        path = absolute_path(endpoint.removeprefix("unix:"))
        if len(path.encode()) > 107:
            raise ValueError("Unix domain socket path exceeds the Linux limit")
        paths.append(path)
    if len(set(paths)) != len(paths):
        raise ValueError("Edge runtime requires distinct socket endpoints")
    for key in ("storage_dir", "status_dir", "token_file", "clock_domain_file"):
        absolute_path(document[key])
    storage, statuses = (
        PurePosixPath(document["storage_dir"]),
        PurePosixPath(document["status_dir"]),
    )
    if (
        storage == statuses
        or storage in statuses.parents
        or statuses in storage.parents
    ):
        raise ValueError("Edge outbox and status directories must not overlap")
    if https_origin(document["backend_origin"]) != https_origin(
        environment["BACKEND_ORIGIN"]
    ):
        raise ValueError("Edge runtime does not match BACKEND_ORIGIN")


def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Edge configuration contains duplicate JSON fields")
        result[key] = value
    return result


def reject_constant(value: str) -> None:
    raise ValueError("Edge configuration requires finite JSON values")


def finite_float(value: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("Edge configuration requires finite JSON values")
    return result


def read_configuration(path: Path, environment: dict[str, str]) -> bytes:
    for entry in (path, *path.parents):
        if entry.is_symlink():
            raise ValueError("Edge configuration path must not contain symbolic links")
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as source:
        metadata = os.fstat(source.fileno())
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise ValueError("Edge configuration must be a single-link regular file")
        content = source.read(MAX_CONFIGURATION_BYTES + 1)
    if len(content) > MAX_CONFIGURATION_BYTES:
        raise ValueError("Edge configuration is too large")
    try:
        document = json.loads(
            content.decode("utf-8"),
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
            parse_float=finite_float,
        )
    except (UnicodeError, json.JSONDecodeError, RecursionError) as error:
        raise ValueError("Edge configuration must be valid UTF-8 JSON") from error
    validate_runtime(document, environment)
    return content


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate Edge v2 deployment inputs without running services."
    )
    parser.add_argument("environment_file", type=Path)
    parser.add_argument("--root", type=Path, default=Path("/"))
    args = parser.parse_args()
    try:
        environment = {}
        for line in args.environment_file.read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            if "=" not in line:
                raise ValueError("invalid environment line")
            key, value = line.split("=", 1)
            if key in environment or not value:
                raise ValueError("duplicate or empty environment input")
            environment[key] = value
        root = args.root.absolute()
        if not root.is_dir() or root.is_symlink():
            raise ValueError("host root must be an existing non-symbolic directory")
        config = absolute_path(environment["CONFIG_FILE"])
        read_configuration(root / config.lstrip("/"), environment)
    except (OSError, ValueError, KeyError, TypeError):
        print(
            "Edge v2 deployment configuration is invalid or unavailable",
            file=sys.stderr,
        )
        return 1
    print("Edge v2 deployment configuration valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
