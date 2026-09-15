from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

try:
    from .release_manifest import release_variables
except ImportError:
    from release_manifest import release_variables

ENVIRONMENT_KEY_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")
GENERATED_ENVIRONMENT = {
    "edge": {"CONFIG_SHA256": "0" * 64},
    "server": {},
}


def read_example_environment(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"invalid environment line: {path}:{line_number}")
        key, value = line.split("=", maxsplit=1)
        if not ENVIRONMENT_KEY_PATTERN.fullmatch(key) or key in values:
            raise ValueError(f"invalid environment key: {path}:{line_number}")
        values[key] = value
    return values


def compose_model(
    project: Path,
    environment: dict[str, str],
    *,
    interpolate: bool,
) -> dict[str, Any]:
    command = [
        "docker",
        "compose",
        "--project-directory",
        str(project),
        "--env-file",
        str(project / ".env.example"),
        "config",
    ]
    if not interpolate:
        command.append("--no-interpolate")
    command.extend(("--format", "json"))
    process_environment = {"PATH": os.environ.get("PATH", os.defpath)}
    process_environment.update(environment)
    result = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        env=process_environment,
    )
    model = json.loads(result.stdout)
    if not isinstance(model, dict):
        raise TypeError("Compose model is not an object")
    return model


def target_services(model: dict[str, Any], target: str) -> dict[str, dict[str, Any]]:
    services = model.get("services")
    if not isinstance(services, dict) or not services:
        raise ValueError(f"Compose target has no services: {target}")
    if not all(
        isinstance(name, str) and isinstance(value, dict)
        for name, value in services.items()
    ):
        raise TypeError(f"Compose target has an invalid service: {target}")
    return services


def validate_target(repository: Path, manifest: dict[str, Any], target: str) -> None:
    project = repository / "targets" / target
    environment = read_example_environment(project / ".env.example")
    variables = release_variables(manifest, target)
    environment.update(variables)
    environment.update(GENERATED_ENVIRONMENT[target])

    unresolved = target_services(
        compose_model(project, environment, interpolate=False), target
    )
    resolved = target_services(
        compose_model(project, environment, interpolate=True), target
    )
    if set(unresolved) != set(resolved):
        raise ValueError(f"Compose service set changed after interpolation: {target}")

    expected_bindings = {
        f"${{{name}}}": value
        for name, value in variables.items()
        if name.endswith("_IMAGE")
    }
    used_bindings: set[str] = set()
    resolved_images: set[str] = set()
    for service_name, service in unresolved.items():
        if "build" in service:
            raise ValueError(f"Compose service must not build an image: {service_name}")
        raw_image = service.get("image")
        if raw_image not in expected_bindings:
            raise ValueError(
                f"Compose service image is not a release image variable: {service_name}"
            )
        used_bindings.add(raw_image)
        resolved_image = resolved[service_name].get("image")
        if resolved_image != expected_bindings[raw_image]:
            raise ValueError(
                f"Compose service image does not match the manifest: {service_name}"
            )
        resolved_images.add(resolved_image)

    missing_bindings = sorted(set(expected_bindings) - used_bindings)
    if missing_bindings:
        raise ValueError(
            f"Manifest image is not used by Compose: {target}: {missing_bindings[0]}"
        )
    expected_images = {
        component["image"] for component in manifest["targets"][target]["components"]
    }
    if resolved_images != expected_images:
        raise ValueError(f"Compose image set does not match the manifest: {target}")


def validate_targets(repository: Path, manifest: dict[str, Any]) -> None:
    for target in ("edge", "server"):
        validate_target(repository, manifest, target)
