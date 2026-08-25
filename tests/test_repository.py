from __future__ import annotations

import unittest
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]


class RepositoryStructureTest(unittest.TestCase):
    def test_required_paths_exist(self) -> None:
        required_paths = [
            ".github/workflows/ci.yml",
            ".github/workflows/release.yml",
            "delivery/apply-release",
            "delivery/verify-release",
            "delivery/online/fetch-release",
            "delivery/offline/build-bundle",
            "delivery/offline/import-bundle",
            "docs/deployment-contract.md",
            "pki/config/ca.template.json",
            "pki/ensure-server-certificate",
            "pki/validate-ca-state",
            "pki/verify-server-certificate",
            "release/build-assets",
            "release/manifest.example.json",
            "release/manifest.schema.json",
            "release/manifests/README.md",
            "release/pull-images",
            "release/release_manifest.py",
            "release/validate-manifest",
            "targets/edge/compose.yaml",
            "targets/server/compose.yaml",
            "tests/validate-repository",
        ]
        missing = [path for path in required_paths if not (REPOSITORY / path).is_file()]
        self.assertEqual([], missing)

    def test_agent_instruction_symlink(self) -> None:
        agent_file = REPOSITORY / "AGENTS.md"
        self.assertTrue(agent_file.is_symlink())
        self.assertEqual(Path(".agents/AGENTS.md"), agent_file.readlink())


if __name__ == "__main__":
    unittest.main()
