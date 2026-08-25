from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

VERSION_PATTERN = re.compile(r"^v[0-9]+\.[0-9]+\.[0-9]+$")


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
        manifest = json.load(manifest_file)

    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(manifest)
    if manifest["version"] != version:
        raise ValueError("manifest version does not match release version")

    if require_components:
        for target in ("edge", "server"):
            if not manifest["targets"][target]["components"]:
                raise ValueError(f"{target} component list is empty")

    return manifest
