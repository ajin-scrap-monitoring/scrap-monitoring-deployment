from __future__ import annotations

import re
import unittest
from pathlib import Path

import yaml

REPOSITORY = Path(__file__).resolve().parents[1]
WORKFLOWS = REPOSITORY / ".github" / "workflows"
ACTION_REFERENCE_PATTERN = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")


def load_workflow(name: str) -> dict[str, object]:
    return yaml.load(
        WORKFLOWS.joinpath(name).read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )


class WorkflowPolicyTest(unittest.TestCase):
    def test_ci_runs_for_main_pull_requests_and_pushes(self) -> None:
        workflow = load_workflow("ci.yml")
        self.assertEqual(
            {"pull_request": {"branches": ["main"]}, "push": {"branches": ["main"]}},
            workflow["on"],
        )

    def test_release_runs_only_for_version_tags(self) -> None:
        workflow = load_workflow("release.yml")
        self.assertEqual(
            {"push": {"tags": ["v[0-9]+.[0-9]+.[0-9]+"]}},
            workflow["on"],
        )

    def test_external_actions_are_pinned_to_commits(self) -> None:
        for workflow_path in sorted(WORKFLOWS.glob("*.yml")):
            workflow = load_workflow(workflow_path.name)
            for job_name, job in workflow["jobs"].items():
                for step in job.get("steps", []):
                    reference = step.get("uses")
                    if reference is None or reference.startswith("./"):
                        continue
                    with self.subTest(workflow=workflow_path.name, job=job_name):
                        self.assertRegex(reference, ACTION_REFERENCE_PATTERN)

    def test_all_jobs_have_timeouts(self) -> None:
        for workflow_path in sorted(WORKFLOWS.glob("*.yml")):
            workflow = load_workflow(workflow_path.name)
            for job_name, job in workflow["jobs"].items():
                with self.subTest(workflow=workflow_path.name, job=job_name):
                    self.assertIn("timeout-minutes", job)

    def test_ci_keeps_required_status_context_and_read_permission(self) -> None:
        workflow = load_workflow("ci.yml")
        self.assertEqual({"contents": "read"}, workflow["permissions"])
        self.assertEqual("CI", workflow["jobs"]["ci"]["name"])

    def test_checkout_does_not_persist_credentials(self) -> None:
        for workflow_path in sorted(WORKFLOWS.glob("*.yml")):
            workflow = load_workflow(workflow_path.name)
            for job_name, job in workflow["jobs"].items():
                for step in job.get("steps", []):
                    if not step.get("uses", "").startswith("actions/checkout@"):
                        continue
                    with self.subTest(workflow=workflow_path.name, job=job_name):
                        self.assertEqual(
                            "false", step.get("with", {}).get("persist-credentials")
                        )

    def test_release_write_permission_is_isolated_to_publish_job(self) -> None:
        workflow = load_workflow("release.yml")
        jobs = workflow["jobs"]
        self.assertEqual({"contents": "read"}, workflow["permissions"])
        self.assertNotIn("permissions", jobs["build"])
        self.assertEqual({"contents": "write"}, jobs["publish"]["permissions"])
        self.assertEqual("build", jobs["publish"]["needs"])

    def test_release_publish_does_not_checkout_repository(self) -> None:
        workflow = load_workflow("release.yml")
        publish_steps = workflow["jobs"]["publish"]["steps"]
        action_references = [step.get("uses", "") for step in publish_steps]
        self.assertFalse(
            any(
                reference.startswith("actions/checkout@")
                for reference in action_references
            )
        )

    def test_release_build_runs_publishability_checks(self) -> None:
        workflow = load_workflow("release.yml")
        build_steps = workflow["jobs"]["build"]["steps"]
        commands = "\n".join(step.get("run", "") for step in build_steps)
        self.assertIn("--require-public-packages", commands)
        self.assertIn("release/validate-targets", commands)
        self.assertIn("release/verify-assets", commands)

    def test_ci_and_release_use_the_same_validation_toolchain(self) -> None:
        ci_steps = load_workflow("ci.yml")["jobs"]["ci"]["steps"]
        release_steps = load_workflow("release.yml")["jobs"]["build"]["steps"]
        setup_names = {
            "Set up Node.js",
            "Set up Go",
            "Set up uv",
            "Set up Docker Compose",
        }
        ci_setup = {
            step["name"]: step for step in ci_steps if step["name"] in setup_names
        }
        release_setup = {
            step["name"]: step for step in release_steps if step["name"] in setup_names
        }
        self.assertEqual(ci_setup, release_setup)


if __name__ == "__main__":
    unittest.main()
