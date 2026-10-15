from __future__ import annotations

import importlib.util
import json
import os
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

PATH = Path(__file__).resolve().parents[1] / "tools/check-component-updates"
from importlib.machinery import SourceFileLoader

SPEC = importlib.util.spec_from_loader(
    "component_updates", SourceFileLoader("component_updates", str(PATH))
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ComponentUpdateTest(unittest.TestCase):
    def test_baseline_has_exactly_one_full_matching_source_link(self):
        document = (PATH.parents[1] / "docs/implementation.md").read_text()
        self.assertEqual(5, len(MODULE.source_revisions(document)))
        for content in (document.replace("/tree/", "/commit/"), document + document):
            with self.assertRaises(ValueError):
                MODULE.source_revisions(content)

    def test_reports_changed_source_and_does_not_claim_image_validation(self):
        with patch.object(
            MODULE,
            "github_json",
            side_effect=[{"object": {"sha": "b" * 40}}, {"tag_name": "v0.2.0"}],
        ):
            report = MODULE.check_updates({"example": "a" * 40})
        self.assertTrue(report[0]["sourceChanged"])
        self.assertFalse(report[0]["imageVerified"])
        self.assertEqual("v0.2.0", report[0]["latestRelease"])

    def test_missing_release_is_distinct_from_unavailable_metadata(self):
        with patch.object(
            MODULE, "github_json", side_effect=[{"object": {"sha": "a" * 40}}, None]
        ):
            report = MODULE.check_updates({"example": "a" * 40})
        self.assertFalse(report[0]["sourceChanged"])
        self.assertIsNone(report[0]["latestRelease"])
        for status in (401, 403, 429, 500):
            with (
                patch.object(
                    MODULE,
                    "urlopen",
                    side_effect=HTTPError(
                        "https://api.github.com", status, "hidden", None, None
                    ),
                ),
                self.assertRaises(ValueError),
            ):
                MODULE.github_json("example", "releases/latest", missing_release=True)

    def test_only_release_404_means_no_release(self):
        with patch.object(
            MODULE,
            "urlopen",
            side_effect=HTTPError("https://api.github.com", 404, "hidden", None, None),
        ):
            self.assertIsNone(
                MODULE.github_json("example", "releases/latest", missing_release=True)
            )
            with self.assertRaises(ValueError):
                MODULE.github_json("example", "git/ref/heads/main")

    def test_rejects_invalid_revision_and_version(self):
        for responses in (
            [{"object": {"sha": "main"}}],
            [{"object": {"sha": "a" * 40}}, {"tag_name": "latest"}],
        ):
            with (
                patch.object(MODULE, "github_json", side_effect=responses),
                self.assertRaises(ValueError),
            ):
                MODULE.check_updates({"example": "a" * 40})

    def test_authenticated_request_is_bounded_and_does_not_return_credentials(self):
        response = BytesIO(json.dumps({"object": {"sha": "a" * 40}}).encode())
        with (
            patch.dict(os.environ, {"GH_TOKEN": "test-private-value"}),
            patch.object(MODULE, "urlopen", return_value=response) as request,
        ):
            result = MODULE.github_json("example", "git/ref/heads/main")
        self.assertEqual("a" * 40, result["object"]["sha"])
        self.assertEqual(
            "Bearer test-private-value",
            request.call_args.args[0].get_header("Authorization"),
        )
        self.assertEqual(15, request.call_args.kwargs["timeout"])
        with (
            patch.object(
                MODULE,
                "urlopen",
                return_value=BytesIO(b"x" * (MODULE.MAX_RESPONSE_BYTES + 1)),
            ),
            self.assertRaises(ValueError),
        ):
            MODULE.github_json("example", "git/ref/heads/main")

    def test_release_change_is_detected_even_when_source_matches(self):
        with patch.object(
            MODULE,
            "github_json",
            side_effect=[{"object": {"sha": "a" * 40}}, {"tag_name": "v0.2.0"}],
        ):
            report = MODULE.check_updates({"example": "a" * 40}, {"example": "v0.1.0"})
        self.assertFalse(report[0]["sourceChanged"])
        self.assertTrue(report[0]["releaseChanged"])
        document = (PATH.parents[1] / "docs/implementation.md").read_text()
        versions = MODULE.release_versions(document)
        self.assertEqual("v0.2.0", versions["scrap-monitoring-dashboard"])
        self.assertIsNone(versions["scrap-monitoring-backend"])


if __name__ == "__main__":
    unittest.main()
