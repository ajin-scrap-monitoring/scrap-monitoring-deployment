from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath
from typing import Any

from jsonschema import Draft202012Validator

VERSION_PATTERN = re.compile(r"^v[0-9]+\.[0-9]+\.[0-9]+$")


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    document: dict[str, Any] = {}
    for key, value in pairs:
        if key in document:
            raise ValueError(f"duplicate JSON field: {key}")
        document[key] = value
    return document


def validate_notice(repository: Path, notice: str) -> None:
    relative = PurePosixPath(notice)
    if (
        relative.is_absolute()
        or relative.as_posix() != notice
        or ".." in relative.parts
    ):
        raise ValueError(f"invalid notice path: {notice}")

    notices_root = (repository / "notices").resolve()
    notice_path = repository.joinpath(*relative.parts)
    try:
        resolved_notice = notice_path.resolve(strict=True)
    except FileNotFoundError as error:
        raise ValueError(f"notice file not found: {notice}") from error
    try:
        resolved_notice.relative_to(notices_root)
    except ValueError as error:
        raise ValueError(f"notice is outside the notice directory: {notice}") from error

    current = repository
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            raise ValueError(f"notice must not be a symbolic link: {notice}")
    if not notice_path.is_file():
        raise ValueError(f"notice is not a regular file: {notice}")


def validate_components(
    repository: Path,
    manifest: dict[str, Any],
    *,
    require_components: bool,
) -> None:
    names: set[str] = set()
    images: set[str] = set()

    for target in ("edge", "server"):
        components = manifest["targets"][target]["components"]
        if require_components and not components:
            raise ValueError(f"{target} component list is empty")
        for component in components:
            name = component["name"]
            if name in names:
                raise ValueError(f"duplicate component name: {name}")
            names.add(name)

            image = component["image"]
            if image in images:
                raise ValueError(f"duplicate component image: {image}")
            images.add(image)
            image_path = image.removeprefix("ghcr.io/ajin-scrap-monitoring/").split(
                "@", maxsplit=1
            )[0]
            if any(part in {"", ".", ".."} for part in image_path.split("/")):
                raise ValueError(f"invalid component image path: {name}")

            for notice in component["notices"]:
                validate_notice(repository, notice)


def load_manifest(
    repository: Path,
    manifest_path: Path,
    version: str,
    *,
    require_components: bool = False,
) -> dict[str, Any]:
    if not VERSION_PATTERN.fullmatch(version):
        raise ValueError(f"invalid release version: {version}")

    schema_path = repository / "release" / "manifest.schema.json"
    with schema_path.open(encoding="utf-8") as schema_file:
        schema = json.load(schema_file)
    with manifest_path.open(encoding="utf-8") as manifest_file:
        manifest = json.load(manifest_file, object_pairs_hook=unique_object)

    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(manifest)
    if manifest["version"] != version:
        raise ValueError("manifest version does not match release version")

    validate_components(
        repository,
        manifest,
        require_components=require_components,
    )

    return manifest
