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

    def test_ci_and_release_use_the_container_validation_entrypoint(self) -> None:
        for workflow_name, job_name in (("ci.yml", "ci"), ("release.yml", "build")):
            with self.subTest(workflow=workflow_name, job=job_name):
                steps = load_workflow(workflow_name)["jobs"][job_name]["steps"]
                commands = "\n".join(step.get("run", "") for step in steps)
                self.assertIn("tests/validate-container", commands)


class ComponentImagesWorkflowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.workflow = load_workflow("component-images.yml")
        self.jobs = self.workflow["jobs"]

    def test_runs_only_by_manual_dispatch(self) -> None:
        self.assertEqual(["workflow_dispatch"], list(self.workflow["on"]))
        self.assertEqual({"contents": "read"}, self.workflow["permissions"])

    def test_package_write_permission_is_isolated_to_build_job(self) -> None:
        for name, job in self.jobs.items():
            permissions = job.get("permissions", {})
            with self.subTest(job=name):
                self.assertNotIn(
                    "contents", [k for k, v in permissions.items() if v == "write"]
                )
                self.assertNotIn("pull-requests", permissions)
                self.assertNotIn("id-token", permissions)
                if name == "build":
                    self.assertEqual(
                        {"contents": "read", "packages": "write"}, permissions
                    )
                else:
                    self.assertNotEqual("write", permissions.get("packages"))
        self.assertEqual("read", self.jobs["resolve"]["permissions"]["packages"])

    def test_workflow_has_no_secrets_or_automation_triggers(self) -> None:
        text = WORKFLOWS.joinpath("component-images.yml").read_text(encoding="utf-8")
        self.assertNotIn("secrets.", text)
        self.assertNotIn("schedule", self.workflow["on"])
        self.assertNotIn("create-github-app-token", text)

    def test_build_job_runs_no_component_code(self) -> None:
        steps = self.jobs["build"]["steps"]
        commands = "\n".join(step.get("run", "") for step in steps)
        self.assertNotRegex(commands, r"source/[A-Za-z0-9._/-]+\s")
        for token in ("make ", "npm ", "pip ", "bash source", "./source"):
            self.assertNotIn(token, commands)
        references = [step.get("uses", "") for step in steps]
        self.assertTrue(
            all(
                reference.split("@")[0]
                in {
                    "actions/checkout",
                    "actions/upload-artifact",
                    "docker/setup-buildx-action",
                    "docker/login-action",
                    "docker/build-push-action",
                }
                for reference in references
                if reference
            )
        )

    def test_build_uses_native_runner_and_no_latest_tag(self) -> None:
        build = self.jobs["build"]
        self.assertEqual("${{ matrix.runner }}", build["runs-on"])
        text = WORKFLOWS.joinpath("component-images.yml").read_text(encoding="utf-8")
        self.assertNotIn("qemu", text.lower())
        self.assertNotIn(":latest", text)

    def test_expressions_are_not_interpolated_into_scripts(self) -> None:
        for name, job in self.jobs.items():
            for step in job["steps"]:
                with self.subTest(job=name, step=step.get("name")):
                    self.assertNotIn("${{", step.get("run", ""))


if __name__ == "__main__":
    unittest.main()
