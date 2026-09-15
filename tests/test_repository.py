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
            "delivery/release_applier.py",
            "delivery/generate-auth-secret",
            "delivery/install-auth-secret",
            "delivery/retire-auth-secret",
            "delivery/validate-auth-secrets",
            "delivery/validate-environment",
            "delivery/verify-release",
            "tests/test_delivery_release.py",
            "tests/test_delivery_integration.py",
            "tests/test_apply_release.py",
            "tests/test_pki.py",
            "docs/configuration-management.md",
            "delivery/online/fetch-release",
            "delivery/release_verifier.py",
            "delivery/offline/bundle_importer.py",
            "delivery/offline/import-bundle",
            "docs/deployment-contract.md",
            "pki/config/ca.template.json",
            "pki/ensure-server-certificate",
            "pki/validate-ca-state",
            "pki/verify-server-certificate",
            "notices/README.md",
            "release/build-assets",
            "release/manifest.example.json",
            "release/manifest.schema.json",
            "release/package.schema.json",
            "release/manifests/README.md",
            "release/pull-images",
            "release/release_manifest.py",
            "release/validate-manifest",
            "targets/edge/compose.yaml",
            "targets/server/compose.yaml",
            "tests/validate-repository",
            "tests/validate-test-host",
        ]
        missing = [path for path in required_paths if not (REPOSITORY / path).is_file()]
        self.assertEqual([], missing)

    def test_agent_instruction_symlink(self) -> None:
        agent_file = REPOSITORY / "AGENTS.md"
        self.assertTrue(agent_file.is_symlink())
        self.assertEqual(Path(".agents/AGENTS.md"), agent_file.readlink())


if __name__ == "__main__":
    unittest.main()
