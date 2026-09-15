from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import re
import stat
import tarfile
from pathlib import Path, PurePosixPath
from typing import Any

VERSION_PATTERN = re.compile(r"^v[0-9]+\.[0-9]+\.[0-9]+$")
DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")
CHECKSUM_LINE_PATTERN = re.compile(r"^([0-9a-f]{64})  ([A-Za-z0-9._-]+)$")
NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*$")
SOURCE_REPOSITORY_PATTERN = re.compile(
    r"^https://github\.com/ajin-scrap-monitoring/[a-z0-9][a-z0-9._-]*$"
)
SOURCE_REVISION_PATTERN = re.compile(r"^[0-9a-f]{40}$")
IMAGE_PATTERN = re.compile(
    r"^ghcr\.io/ajin-scrap-monitoring/"
    r"[a-z0-9][a-z0-9._/-]*@sha256:[0-9a-f]{64}$"
)
NOTICE_PATTERN = re.compile(r"^notices/[A-Za-z0-9][A-Za-z0-9._/-]*\.md$")
ARCHIVE_PATH_PATTERN = re.compile(r"^[A-Za-z0-9._/-]+$")
TARGET_PLATFORMS = {
    "edge": "linux/arm64",
    "server": "linux/amd64",
}
COMMON_MEMBERS = {
    "README.md",
    "requirements-tooling.txt",
    "delivery/README.md",
    "delivery/apply-release",
    "delivery/generate-auth-secret",
    "delivery/install-auth-secret",
    "delivery/release_applier.py",
    "delivery/release_verifier.py",
    "delivery/retire-auth-secret",
    "delivery/validate-auth-secrets",
    "delivery/validate-environment",
    "delivery/verify-release",
    "notices/README.md",
    "release/manifest.schema.json",
    "release/package.schema.json",
    "release/release_manifest.py",
    "release/validate-manifest",
    "release-manifest.json",
    "release-package.json",
}
MODE_MEMBERS = {
    "online": {
        "delivery/online/README.md",
        "delivery/online/fetch-release",
    },
    "offline": {
        "delivery/offline/README.md",
        "delivery/offline/bundle_importer.py",
        "delivery/offline/import-bundle",
    },
}
MAX_METADATA_SIZE = 1024 * 1024
MAX_CHECKSUM_SIZE = 1024 * 1024
MAX_ARCHIVE_MEMBERS = 4096


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify a release package.")
    parser.add_argument("--version", required=True)
    parser.add_argument("--target", choices=sorted(TARGET_PLATFORMS), required=True)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--checksums", type=Path, required=True)
    return parser.parse_args()


def require_regular_file(path: Path, label: str) -> None:
    if path.is_symlink() or not path.exists():
        raise ValueError(f"{label} is missing or symbolic: {path}")
    if not stat.S_ISREG(path.stat().st_mode):
        raise ValueError(f"{label} is not a regular file: {path}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def expected_checksum(checksums: Path, package_name: str) -> str:
    if checksums.stat().st_size > MAX_CHECKSUM_SIZE:
        raise ValueError("checksum manifest is too large")
    entries: dict[str, str] = {}
    for line_number, line in enumerate(
        checksums.read_text(encoding="utf-8").splitlines(), start=1
    ):
        match = CHECKSUM_LINE_PATTERN.fullmatch(line)
        if match is None:
            raise ValueError(f"invalid checksum line: {line_number}")
        digest, name = match.groups()
        if name in entries:
            raise ValueError(f"duplicate checksum entry: {name}")
        entries[name] = digest
    if package_name not in entries:
        raise ValueError(f"package checksum is missing: {package_name}")
    return entries[package_name]


def safe_member_name(name: str) -> bool:
    path = PurePosixPath(name)
    return (
        not path.is_absolute()
        and bool(path.parts)
        and path.as_posix() == name
        and ARCHIVE_PATH_PATTERN.fullmatch(name) is not None
        and all(part not in {"", ".", ".."} for part in path.parts)
    )


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    document: dict[str, Any] = {}
    for key, value in pairs:
        if key in document:
            raise ValueError(f"duplicate JSON field: {key}")
        document[key] = value
    return document


def archive_members(archive: tarfile.TarFile) -> dict[str, tarfile.TarInfo]:
    members: dict[str, tarfile.TarInfo] = {}
    for index, member in enumerate(archive, start=1):
        if index > MAX_ARCHIVE_MEMBERS:
            raise ValueError("archive contains too many members")
        if not safe_member_name(member.name):
            raise ValueError(f"unsafe archive path: {member.name}")
        if member.name in members:
            raise ValueError(f"duplicate archive member: {member.name}")
        if not member.isfile():
            raise ValueError(f"archive member is not a regular file: {member.name}")
        if member.mode not in {0o644, 0o755}:
            raise ValueError(f"invalid archive member mode: {member.name}")
        if member.pax_headers:
            raise ValueError(f"archive member has unexpected metadata: {member.name}")
        if (
            member.uid != 0
            or member.gid != 0
            or member.uname != "root"
            or member.gname != "root"
            or member.mtime != 0
        ):
            raise ValueError(
                f"archive member metadata is not normalized: {member.name}"
            )
        members[member.name] = member
    return members


def read_json_member(
    archive: tarfile.TarFile,
    members: dict[str, tarfile.TarInfo],
    name: str,
) -> tuple[dict[str, Any], bytes]:
    member = members.get(name)
    if member is None:
        raise ValueError(f"required archive member is missing: {name}")
    if member.size > MAX_METADATA_SIZE:
        raise ValueError(f"archive metadata is too large: {name}")
    source = archive.extractfile(member)
    if source is None:
        raise ValueError(f"archive member cannot be read: {name}")
    content = source.read(MAX_METADATA_SIZE + 1)
    if len(content) > MAX_METADATA_SIZE:
        raise ValueError(f"archive metadata is too large: {name}")
    document = json.loads(
        content.decode("utf-8"),
        object_pairs_hook=unique_object,
    )
    if not isinstance(document, dict):
        raise TypeError(f"archive metadata is not an object: {name}")
    return document, content


def validate_package_descriptor(
    package: dict[str, Any],
    version: str,
    target: str,
) -> str:
    required = {
        "schemaVersion",
        "version",
        "target",
        "mode",
        "platform",
        "manifestSha256",
    }
    mode = package.get("mode")
    expected = required | ({"imageArchive"} if mode == "offline" else set())
    if set(package) != expected:
        raise ValueError("package descriptor fields do not match the schema")
    if type(package["schemaVersion"]) is not int or package["schemaVersion"] != 1:
        raise ValueError("unsupported package schema version")
    if package["version"] != version or package["target"] != target:
        raise ValueError("package version or target does not match the request")
    if mode not in MODE_MEMBERS:
        raise ValueError("invalid package mode")
    if package["platform"] != TARGET_PLATFORMS[target]:
        raise ValueError("package platform does not match the target")
    if not isinstance(package["manifestSha256"], str) or not DIGEST_PATTERN.fullmatch(
        package["manifestSha256"]
    ):
        raise ValueError("invalid manifest digest")
    if mode == "offline":
        expected_archive = f"images/{target}-images.tar"
        if package["imageArchive"] != expected_archive:
            raise ValueError("image archive does not match the target")
    return mode


def validate_component(component: Any) -> tuple[str, str, set[str]]:
    if not isinstance(component, dict):
        raise TypeError("component is not an object")
    visibility = component.get("packageVisibility")
    required = {
        "name",
        "sourceRepository",
        "sourceRevision",
        "version",
        "image",
        "packageVisibility",
        "pullAuthentication",
        "notices",
    }
    expected = required | ({"privateReason"} if visibility == "private" else set())
    if set(component) != expected:
        raise ValueError("component fields do not match the schema")

    name = component["name"]
    image = component["image"]
    if not isinstance(name, str) or not NAME_PATTERN.fullmatch(name):
        raise ValueError("invalid component name")
    if not isinstance(component["sourceRepository"], str) or not (
        SOURCE_REPOSITORY_PATTERN.fullmatch(component["sourceRepository"])
    ):
        raise ValueError(f"invalid source repository: {name}")
    if not isinstance(component["sourceRevision"], str) or not (
        SOURCE_REVISION_PATTERN.fullmatch(component["sourceRevision"])
    ):
        raise ValueError(f"invalid source revision: {name}")
    if not isinstance(component["version"], str) or not VERSION_PATTERN.fullmatch(
        component["version"]
    ):
        raise ValueError(f"invalid component version: {name}")
    if not isinstance(image, str) or not IMAGE_PATTERN.fullmatch(image):
        raise ValueError(f"invalid component image: {name}")
    image_path = image.removeprefix("ghcr.io/ajin-scrap-monitoring/").split(
        "@", maxsplit=1
    )[0]
    if any(part in {"", ".", ".."} for part in image_path.split("/")):
        raise ValueError(f"invalid component image path: {name}")

    if visibility == "public":
        if component["pullAuthentication"] != "none":
            raise ValueError(f"invalid public package authentication: {name}")
    elif visibility == "private":
        reason = component["privateReason"]
        if (
            not isinstance(reason, str)
            or not reason
            or len(reason) > 500
            or component["pullAuthentication"] != "ghcr-read-token"
        ):
            raise ValueError(f"invalid private package contract: {name}")
    else:
        raise ValueError(f"invalid package visibility: {name}")

    notices = component["notices"]
    if not isinstance(notices, list) or len(notices) != len(set(notices)):
        raise ValueError(f"invalid component notices: {name}")
    for notice in notices:
        if not isinstance(notice, str) or not NOTICE_PATTERN.fullmatch(notice):
            raise ValueError(f"invalid notice path: {name}")
        if not safe_member_name(notice):
            raise ValueError(f"unsafe notice path: {name}")
    return name, image, set(notices)


def validate_manifest(manifest: dict[str, Any], version: str) -> set[str]:
    if set(manifest) != {"schemaVersion", "version", "targets"}:
        raise ValueError("manifest fields do not match the schema")
    if (
        type(manifest["schemaVersion"]) is not int
        or manifest["schemaVersion"] != 1
        or manifest["version"] != version
    ):
        raise ValueError("manifest schema or version does not match the request")
    targets = manifest["targets"]
    if not isinstance(targets, dict) or set(targets) != set(TARGET_PLATFORMS):
        raise ValueError("manifest targets do not match the schema")

    names: set[str] = set()
    images: set[str] = set()
    notices: set[str] = set()
    for target, platform_name in TARGET_PLATFORMS.items():
        target_manifest = targets[target]
        if not isinstance(target_manifest, dict) or set(target_manifest) != {
            "platform",
            "components",
        }:
            raise ValueError(f"invalid target manifest: {target}")
        if target_manifest["platform"] != platform_name:
            raise ValueError(f"invalid target platform: {target}")
        components = target_manifest["components"]
        if not isinstance(components, list) or not components:
            raise ValueError(f"component list is empty: {target}")
        for component in components:
            name, image, component_notices = validate_component(component)
            if name in names:
                raise ValueError(f"duplicate component name: {name}")
            if image in images:
                raise ValueError(f"duplicate component image: {image}")
            names.add(name)
            images.add(image)
            notices.update(component_notices)
    return notices


def validate_payload(
    members: set[str],
    target: str,
    mode: str,
    notices: set[str],
) -> None:
    required = COMMON_MEMBERS | MODE_MEMBERS[mode] | notices
    required.add(f"targets/{target}/compose.yaml")
    if target == "server":
        required.add("pki/validate-ca-state")
    if mode == "offline":
        required.add(f"images/{target}-images.tar")
    missing = sorted(required - members)
    if missing:
        raise ValueError(f"required package member is missing: {missing[0]}")

    allowed_prefixes = ("docs/", f"targets/{target}/")
    if target == "server":
        allowed_prefixes += ("pki/",)
    for name in members:
        allowed = name in required or name.startswith(allowed_prefixes)
        if not allowed:
            raise ValueError(f"package member is outside the allowlist: {name}")


def verify_release(args: argparse.Namespace) -> tuple[str, dict[str, Any]]:
    if not VERSION_PATTERN.fullmatch(args.version):
        raise ValueError(f"invalid release version: {args.version}")
    require_regular_file(args.package, "package")
    require_regular_file(args.checksums, "checksum manifest")

    expected_digest = expected_checksum(args.checksums, args.package.name)
    actual_digest = sha256(args.package)
    if not hmac.compare_digest(actual_digest, expected_digest):
        raise ValueError("package checksum does not match")

    with tarfile.open(args.package, mode="r:gz") as archive:
        members = archive_members(archive)
        package, _ = read_json_member(archive, members, "release-package.json")
        manifest, manifest_bytes = read_json_member(
            archive, members, "release-manifest.json"
        )
        mode = validate_package_descriptor(package, args.version, args.target)
        expected_name = f"scrap-monitoring-{args.target}-{args.version}-{mode}.tar.gz"
        if args.package.name != expected_name:
            raise ValueError("package filename does not match its descriptor")
        actual_manifest_digest = hashlib.sha256(manifest_bytes).hexdigest()
        if not hmac.compare_digest(actual_manifest_digest, package["manifestSha256"]):
            raise ValueError("manifest digest does not match the package descriptor")
        notices = validate_manifest(manifest, args.version)
        validate_payload(set(members), args.target, mode, notices)
    return mode, manifest


def main() -> None:
    args = parse_args()
    try:
        verify_release(args)
    except (
        KeyError,
        OSError,
        TypeError,
        UnicodeError,
        json.JSONDecodeError,
        tarfile.TarError,
        ValueError,
    ) as error:
        raise SystemExit(f"release verification failed: {error}") from error
    print(args.package)


if __name__ == "__main__":
    main()
