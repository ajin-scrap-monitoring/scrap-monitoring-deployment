from __future__ import annotations

import copy
import hashlib
import json
import sys
import unittest
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "release"))

import component_images
from component_images import Response

ORG = "ajin-scrap-monitoring"
MAIN = "a" * 40
TAG_SHA = "b" * 40
DIGEST = "sha256:" + "c" * 64
BACKEND_REF = f"ghcr.io/{ORG}/scrap-monitoring-backend@sha256:" + "d" * 64
EDGE_REF = f"ghcr.io/{ORG}/ajin-lidar-driver@sha256:" + "e" * 64
NAMESPACE = f"ghcr.io/{ORG}/scrap-monitoring-deployment"

SOURCES = {
    "organization": ORG,
    "buildNamespace": NAMESPACE,
    "components": [
        {
            "name": "ajin-lidar-driver",
            "repository": "ajin-edge-platform",
            "target": "edge",
            "platform": "linux/arm64",
            "runner": "ubuntu-24.04-arm",
            "dockerfile": "services/lidar-driver/Dockerfile",
            "context": ".",
            "officialImage": {"asset": "release-manifest.json", "key": "lidar-driver"},
            "minimumRelease": "v0.2.0",
        },
        {
            "name": "scrap-monitoring-backend",
            "repository": "scrap-monitoring-backend",
            "target": "server",
            "platform": "linux/amd64",
            "runner": "ubuntu-latest",
            "dockerfile": "Dockerfile",
            "context": ".",
            "officialImage": {"asset": "image-reference.txt"},
            "minimumRelease": "v0.2.0",
        },
        {
            "name": "ajin-camera-media-service",
            "repository": "ajin-camera-media-service",
            "target": "server",
            "platform": "linux/amd64",
            "runner": "ubuntu-latest",
            "dockerfile": "Dockerfile",
            "context": ".",
            "officialImage": {"asset": "image-reference.txt"},
            "minimumRelease": "v0.1.0",
        },
    ],
}


class FakeNetwork:
    def __init__(self, releases, built=None):
        self.releases = releases
        self.built = built or {}
        self.requests: list[tuple[str, str]] = []

    def __call__(self, url: str, headers: dict[str, str], method: str) -> Response:
        self.requests.append((method, url))
        prefix = f"https://api.github.com/repos/{ORG}/"
        if url.startswith(prefix):
            repository, _, route = url[len(prefix) :].partition("/")
            tag = self.releases.get(repository, {}).get("tag")
            if route == "releases/latest":
                if tag is None:
                    return 404, {}, b""
                return 200, {}, json.dumps({"tag_name": tag}).encode()
            ref = route.removeprefix("commits/")
            sha = MAIN if ref == "main" else TAG_SHA
            return 200, {}, json.dumps({"sha": sha}).encode()
        if url.startswith(f"https://github.com/{ORG}/"):
            repository, _, rest = url[len(f"https://github.com/{ORG}/") :].partition(
                "/releases/download/"
            )
            _, _, name = rest.partition("/")
            assets = self.releases.get(repository, {}).get("assets", {})
            if name in assets:
                return 200, {}, assets[name]
            return 404, {}, b""
        if url.startswith("https://ghcr.io/token"):
            return 200, {}, json.dumps({"token": "t"}).encode()
        if url.startswith("https://ghcr.io/v2/"):
            for name, digest in self.built.items():
                if url.endswith(f"/{name}/manifests/sha-{MAIN}"):
                    return 200, {"docker-content-digest": digest}, b""
            return 404, {}, b""
        raise AssertionError(url)


def backend_release(reference: str = BACKEND_REF, tag: str = "v0.2.0"):
    content = reference.encode() + b"\n"
    sums = f"{hashlib.sha256(content).hexdigest()}  image-reference.txt\n".encode()
    return {"tag": tag, "assets": {"image-reference.txt": content, "SHA256SUMS": sums}}


def edge_release(tag: str):
    manifest = json.dumps({"images": {"lidar-driver": EDGE_REF}}).encode()
    return {"tag": tag, "assets": {"release-manifest.json": manifest}}


def by_name(result):
    return {component["name"]: component for component in result["components"]}


class ResolveTest(unittest.TestCase):
    def test_official_release_is_preferred(self) -> None:
        network = FakeNetwork({"scrap-monitoring-backend": backend_release()})
        result = component_images.resolve(
            SOURCES, network, None, "scrap-monitoring-backend"
        )
        backend = by_name(result)["scrap-monitoring-backend"]
        self.assertEqual("official", backend["action"])
        self.assertEqual(BACKEND_REF, backend["image"])
        self.assertEqual("v0.2.0", backend["version"])
        self.assertEqual(TAG_SHA, backend["sourceRevision"])
        self.assertEqual([], result["matrix"]["include"])
        self.assertFalse(result["hasBuild"])

    def test_release_below_minimum_is_built_from_main(self) -> None:
        network = FakeNetwork({"ajin-edge-platform": edge_release("v0.1.1")})
        result = component_images.resolve(SOURCES, network, None, "ajin-lidar-driver")
        driver = by_name(result)["ajin-lidar-driver"]
        self.assertEqual("build", driver["action"])
        self.assertEqual("deployment-build", driver["imageProvider"])
        self.assertEqual(MAIN, driver["sourceRevision"])
        self.assertNotIn("version", driver)
        self.assertEqual(
            f"{NAMESPACE}/ajin-lidar-driver:sha-{MAIN}", driver["buildImage"]
        )
        entry = result["matrix"]["include"][0]
        self.assertEqual("ubuntu-24.04-arm", entry["runner"])
        self.assertEqual("linux/arm64", entry["platform"])
        self.assertTrue(result["hasBuild"])

    def test_edge_release_at_minimum_uses_release_manifest(self) -> None:
        network = FakeNetwork({"ajin-edge-platform": edge_release("v0.2.0")})
        result = component_images.resolve(SOURCES, network, None, "ajin-lidar-driver")
        self.assertEqual(EDGE_REF, by_name(result)["ajin-lidar-driver"]["image"])

    def test_missing_release_builds_and_existing_image_is_reused(self) -> None:
        network = FakeNetwork({}, built={"ajin-camera-media-service": DIGEST})
        result = component_images.resolve(
            SOURCES, network, "token", "ajin-camera-media-service"
        )
        media = by_name(result)["ajin-camera-media-service"]
        self.assertEqual("existing", media["action"])
        self.assertEqual(
            f"{NAMESPACE}/ajin-camera-media-service@{DIGEST}", media["image"]
        )
        self.assertEqual([], result["matrix"]["include"])

    def test_checksum_mismatch_falls_back_to_build(self) -> None:
        release = backend_release()
        release["assets"]["SHA256SUMS"] = b"0" * 64 + b"  image-reference.txt\n"
        network = FakeNetwork({"scrap-monitoring-backend": release})
        result = component_images.resolve(
            SOURCES, network, None, "scrap-monitoring-backend"
        )
        self.assertEqual("build", by_name(result)["scrap-monitoring-backend"]["action"])

    def test_foreign_image_reference_is_rejected(self) -> None:
        release = backend_release("ghcr.io/other/image@sha256:" + "d" * 64)
        network = FakeNetwork({"scrap-monitoring-backend": release})
        with self.assertRaises(ValueError):
            component_images.resolve(SOURCES, network, None, "scrap-monitoring-backend")

    def test_selection_rejects_unknown_component(self) -> None:
        with self.assertRaises(ValueError):
            component_images.resolve(SOURCES, FakeNetwork({}), None, "unknown")

    def test_all_selects_every_component_and_queries_each_repository_once(self) -> None:
        network = FakeNetwork({})
        result = component_images.resolve(SOURCES, network, None, "all")
        self.assertEqual(3, len(result["components"]))
        latest = [url for _, url in network.requests if url.endswith("releases/latest")]
        self.assertEqual(3, len(latest))

    def test_only_get_and_head_requests_are_made(self) -> None:
        network = FakeNetwork({})
        component_images.resolve(SOURCES, network, "token", "all")
        self.assertLessEqual(
            {method for method, _ in network.requests}, {"GET", "HEAD"}
        )


class MergeAndCandidateTest(unittest.TestCase):
    def resolved(self):
        network = FakeNetwork({"scrap-monitoring-backend": backend_release()})
        return component_images.resolve(SOURCES, network, None, "all")

    def test_merge_requires_every_build_result(self) -> None:
        resolved = self.resolved()
        with self.assertRaises(ValueError):
            component_images.merge(resolved, [])
        builds = [
            {
                "name": "ajin-lidar-driver",
                "image": f"{NAMESPACE}/ajin-lidar-driver@{DIGEST}",
            },
            {
                "name": "ajin-camera-media-service",
                "image": f"{NAMESPACE}/ajin-camera-media-service@{DIGEST}",
            },
        ]
        final = component_images.merge(resolved, builds)
        self.assertEqual(3, len(final["components"]))
        self.assertTrue(all(component["image"] for component in final["components"]))

    def test_update_candidate_replaces_synced_and_keeps_fixed_components(self) -> None:
        resolved = self.resolved()
        final = component_images.merge(
            resolved,
            [
                {
                    "name": "ajin-lidar-driver",
                    "image": f"{NAMESPACE}/ajin-lidar-driver@{DIGEST}",
                },
                {
                    "name": "ajin-camera-media-service",
                    "image": f"{NAMESPACE}/ajin-camera-media-service@{DIGEST}",
                },
            ],
        )
        manifest = json.loads(
            (REPOSITORY / "release" / "manifest.example.json").read_text()
        )
        manifest["version"] = "v0.0.0"
        fixed = copy.deepcopy(
            [
                c
                for c in manifest["targets"]["server"]["components"]
                if c["name"] == "postgres"
            ]
        )
        candidate = component_images.update_candidate(manifest, final)
        server = {c["name"]: c for c in candidate["targets"]["server"]["components"]}
        self.assertEqual(fixed[0], server["postgres"])
        self.assertEqual(
            "component-release", server["scrap-monitoring-backend"]["imageProvider"]
        )
        self.assertEqual("v0.2.0", server["scrap-monitoring-backend"]["version"])
        media = server["ajin-camera-media-service"]
        self.assertEqual("deployment-build", media["imageProvider"])
        self.assertNotIn("version", media)
        self.assertEqual(
            ["ajin-lidar-driver"],
            [
                c["name"]
                for c in candidate["targets"]["edge"]["components"]
                if c["name"] == "ajin-lidar-driver"
            ],
        )

    def test_update_candidate_rejects_unbuilt_results(self) -> None:
        manifest = json.loads(
            (REPOSITORY / "release" / "manifest.example.json").read_text()
        )
        with self.assertRaises(ValueError):
            component_images.update_candidate(manifest, self.resolved())

    def test_placeholder_revisions_block_finalization(self) -> None:
        manifest = json.loads(
            (REPOSITORY / "release" / "manifest.example.json").read_text()
        )
        self.assertTrue(component_images.finalize_blockers(manifest))


class SourcesConfigurationTest(unittest.TestCase):
    def test_repository_configuration_matches_the_rules(self) -> None:
        sources = component_images.load_sources()
        components = {c["name"]: c for c in sources["components"]}
        self.assertEqual(8, len(components))
        for component in components.values():
            expected_edge = component["target"] == "edge"
            self.assertEqual(
                "linux/arm64" if expected_edge else "linux/amd64", component["platform"]
            )
            self.assertEqual(
                "ubuntu-24.04-arm" if expected_edge else "ubuntu-latest",
                component["runner"],
            )
            self.assertTrue(
                component_images.VERSION_PATTERN.fullmatch(component["minimumRelease"])
            )
        self.assertEqual(
            "services/camera-edge", components["ajin-camera-edge"]["context"]
        )
        self.assertEqual("v0.2.0", components["ajin-lidar-driver"]["minimumRelease"])
        for name, component in components.items():
            if name != "ajin-camera-edge":
                self.assertEqual(".", component["context"])


if __name__ == "__main__":
    unittest.main()
