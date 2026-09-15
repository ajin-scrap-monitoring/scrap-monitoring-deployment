from __future__ import annotations

import copy
import subprocess
import tempfile
import unittest
from pathlib import Path

from delivery.release_applier import release_variables as applied_release_variables
from release.release_manifest import release_variables as validated_release_variables
from release.target_validation import compose_model, validate_target, validate_targets
from tests.test_release import manifest_with_components


def write_target(
    repository: Path,
    target: str,
    scenario: str,
    services: str,
) -> None:
    target_directory = repository / "targets" / target / scenario
    target_directory.mkdir(parents=True)
    target_directory.joinpath(".env.example").write_text("", encoding="utf-8")
    target_directory.joinpath("compose.yaml").write_text(
        f"name: test-{target}\n\nservices:\n{services}",
        encoding="utf-8",
    )


class ReleaseTargetValidationTest(unittest.TestCase):
    def test_compose_model_does_not_read_untracked_dotenv(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary)
            write_target(
                repository,
                "edge",
                "hardware",
                "  edge:\n"
                "    image: ${EDGE_COMPONENT_IMAGE}\n"
                "    environment:\n"
                "      UNTRACKED: ${UNTRACKED:?missing}\n",
            )
            project = repository / "targets" / "edge" / "hardware"
            project.joinpath(".env").write_text("UNTRACKED=local\n", encoding="utf-8")

            with self.assertRaises(subprocess.CalledProcessError):
                compose_model(
                    project,
                    {"EDGE_COMPONENT_IMAGE": "example.invalid/image:fixed"},
                    interpolate=True,
                )

    def test_validation_and_application_use_the_same_release_variables(self) -> None:
        manifest = copy.deepcopy(manifest_with_components())
        second = copy.deepcopy(manifest["targets"]["edge"]["components"][0])
        second["name"] = "second-edge-component"
        second["sourceRevision"] = "c" * 40
        second["image"] = "ghcr.io/ajin-scrap-monitoring/second-edge@sha256:" + "c" * 64
        manifest["targets"]["edge"]["components"].append(second)
        for scenario in ("hardware", "simulation"):
            manifest["targets"]["edge"]["scenarios"][scenario].append(
                "second-edge-component"
            )

        for target in ("edge", "server"):
            for scenario in ("hardware", "simulation"):
                with self.subTest(target=target, scenario=scenario):
                    self.assertEqual(
                        applied_release_variables(manifest, target, scenario),
                        validated_release_variables(manifest, target, scenario),
                    )

    def test_accepts_compose_images_bound_to_manifest_variables(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary)
            for target, variable in (
                ("edge", "EDGE_COMPONENT_IMAGE"),
                ("server", "SERVER_COMPONENT_IMAGE"),
            ):
                for scenario in ("hardware", "simulation"):
                    write_target(
                        repository,
                        target,
                        scenario,
                        f"  {target}:\n    image: ${{{variable}}}\n",
                    )

            validate_targets(repository, manifest_with_components())

    def test_rejects_compose_without_services(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary)
            write_target(repository, "edge", "hardware", "  {}\n")

            with self.assertRaisesRegex(ValueError, "has no services"):
                validate_target(
                    repository, manifest_with_components(), "edge", "hardware"
                )

    def test_rejects_hardcoded_compose_image(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary)
            manifest = manifest_with_components()
            image = manifest["targets"]["edge"]["components"][0]["image"]
            write_target(
                repository, "edge", "hardware", f"  edge:\n    image: {image}\n"
            )

            with self.assertRaisesRegex(ValueError, "release image variable"):
                validate_target(repository, manifest, "edge", "hardware")

    def test_rejects_manifest_image_not_used_by_compose(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary)
            manifest = copy.deepcopy(manifest_with_components())
            second = copy.deepcopy(manifest["targets"]["edge"]["components"][0])
            second["name"] = "second-edge-component"
            second["sourceRevision"] = "c" * 40
            second["image"] = (
                "ghcr.io/ajin-scrap-monitoring/second-edge@sha256:" + "c" * 64
            )
            manifest["targets"]["edge"]["components"].append(second)
            manifest["targets"]["edge"]["scenarios"]["hardware"].append(
                "second-edge-component"
            )
            write_target(
                repository,
                "edge",
                "hardware",
                "  edge:\n    image: ${EDGE_COMPONENT_IMAGE}\n",
            )

            with self.assertRaisesRegex(ValueError, "not used by Compose"):
                validate_target(repository, manifest, "edge", "hardware")

    def test_rejects_compose_build(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary)
            write_target(
                repository,
                "edge",
                "hardware",
                "  edge:\n    image: ${EDGE_COMPONENT_IMAGE}\n    build: .\n",
            )

            with self.assertRaisesRegex(ValueError, "must not build"):
                validate_target(
                    repository, manifest_with_components(), "edge", "hardware"
                )


if __name__ == "__main__":
    unittest.main()
