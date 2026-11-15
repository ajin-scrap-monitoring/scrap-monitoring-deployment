"""Decide which image each component uses and maintain the candidate manifest.

The decision logic runs without network access when the caller injects `fetch`.
Component Release assets and Git metadata are untrusted data and are validated
against fixed patterns before use.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

SOURCES_PATH = Path(__file__).resolve().parent / "component-sources.json"
VERSION_PATTERN = re.compile(r"^v([0-9]+)\.([0-9]+)\.([0-9]+)$")
REVISION_PATTERN = re.compile(r"^[0-9a-f]{40}$")
DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
MAX_ASSET_BYTES = 1024 * 1024
PLACEHOLDER_REVISION = "0" * 40
BUILD_PROVIDER = "deployment-build"
RELEASE_PROVIDER = "component-release"
MANIFEST_ACCEPT = (
    "application/vnd.oci.image.index.v1+json,"
    "application/vnd.oci.image.manifest.v1+json,"
    "application/vnd.docker.distribution.manifest.list.v2+json,"
    "application/vnd.docker.distribution.manifest.v2+json"
)

Response = tuple[int, dict[str, str], bytes]
Fetch = Callable[[str, dict[str, str], str], Response]


def default_fetch(url: str, headers: dict[str, str], method: str) -> Response:
    request = Request(url, headers=headers, method=method)
    try:
        with urlopen(request, timeout=30) as response:
            body = response.read(MAX_ASSET_BYTES + 1)
            status = response.status
            response_headers = {k.lower(): v for k, v in response.headers.items()}
    except HTTPError as error:
        return error.code, {k.lower(): v for k, v in error.headers.items()}, b""
    if len(body) > MAX_ASSET_BYTES:
        raise ValueError("response exceeds the size limit")
    return status, response_headers, body


def load_sources(path: Path = SOURCES_PATH) -> dict[str, Any]:
    with path.open(encoding="utf-8") as stream:
        document = json.load(stream)
    names = [component["name"] for component in document["components"]]
    if len(names) != len(set(names)):
        raise ValueError("duplicate component in the source configuration")
    return document


def version_key(tag: str) -> tuple[int, int, int]:
    match = VERSION_PATTERN.fullmatch(tag)
    if not match:
        raise ValueError(f"invalid release tag: {tag}")
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def api_headers(token: str | None) -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "scrap-deployment-component-images",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = "Bearer " + token
    return headers


def github_json(
    fetch: Fetch, organization: str, repository: str, route: str, token: str | None
) -> Any | None:
    url = f"https://api.github.com/repos/{organization}/{repository}/{route}"
    status, _, body = fetch(url, api_headers(token), "GET")
    if status == 404:
        return None
    if status != 200:
        raise ValueError(f"GitHub API request failed: {repository} {route} {status}")
    return json.loads(body)


def commit_of(
    fetch: Fetch, organization: str, repository: str, ref: str, token: str | None
) -> str:
    document = github_json(fetch, organization, repository, f"commits/{ref}", token)
    revision = document.get("sha") if isinstance(document, dict) else None
    if not isinstance(revision, str) or not REVISION_PATTERN.fullmatch(revision):
        raise ValueError(f"commit not found: {repository} {ref}")
    return revision


def latest_release(
    fetch: Fetch, organization: str, repository: str, token: str | None
) -> str | None:
    document = github_json(fetch, organization, repository, "releases/latest", token)
    if document is None:
        return None
    tag = document.get("tag_name") if isinstance(document, dict) else None
    if not isinstance(tag, str) or not VERSION_PATTERN.fullmatch(tag):
        raise ValueError(f"invalid latest release tag: {repository}")
    return tag


def asset(
    fetch: Fetch, organization: str, repository: str, tag: str, name: str
) -> bytes | None:
    url = (
        f"https://github.com/{organization}/{repository}/releases/download/{tag}/{name}"
    )
    status, _, body = fetch(
        url, {"User-Agent": "scrap-deployment-component-images"}, "GET"
    )
    if status == 404:
        return None
    if status != 200:
        raise ValueError(f"asset request failed: {repository} {name} {status}")
    return body


def checksum_for(checksums: bytes, name: str) -> str | None:
    matches = []
    for line in checksums.decode("utf-8", "replace").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64}) [ *](\S+)", line)
        if match and match.group(2) == name:
            matches.append(match.group(1))
    return matches[0] if len(matches) == 1 else None


def official_image(
    fetch: Fetch, organization: str, component: dict[str, Any], tag: str
) -> str | None:
    """Return the image reference in a component Release asset, or None when absent."""
    repository = component["repository"]
    spec = component["officialImage"]
    content = asset(fetch, organization, repository, tag, spec["asset"])
    if content is None:
        return None
    if spec["asset"] == "release-manifest.json":
        document = json.loads(content)
        images = document.get("images") if isinstance(document, dict) else None
        reference = images.get(spec["key"]) if isinstance(images, dict) else None
    else:
        checksums = asset(fetch, organization, repository, tag, "SHA256SUMS")
        expected = checksum_for(checksums, spec["asset"]) if checksums else None
        if expected != hashlib.sha256(content).hexdigest():
            return None
        reference = content.decode("utf-8", "replace").strip()
    pattern = (
        rf"^ghcr\.io/{re.escape(organization)}/{re.escape(component['name'])}"
        r"@sha256:[0-9a-f]{64}$"
    )
    if not isinstance(reference, str) or not re.fullmatch(pattern, reference):
        raise ValueError(f"invalid official image reference: {component['name']}")
    return reference


def existing_build_image(
    fetch: Fetch,
    namespace: str,
    name: str,
    revision: str,
    token: str | None,
) -> str | None:
    """Return the digest reference of an image this repository already built."""
    registry, _, path = namespace.partition("/")
    repository_path = f"{path}/{name}"
    auth = {}
    if token:
        auth["Authorization"] = (
            "Basic " + base64.b64encode(f"github:{token}".encode()).decode()
        )
    status, _, body = fetch(
        f"https://{registry}/token?service={registry}"
        f"&scope=repository:{repository_path}:pull",
        auth,
        "GET",
    )
    if status in {401, 403, 404}:
        return None
    if status != 200:
        raise ValueError(f"registry token request failed: {status}")
    bearer = json.loads(body).get("token")
    if not isinstance(bearer, str) or not bearer:
        raise ValueError("registry token response is invalid")
    status, headers, _ = fetch(
        f"https://{registry}/v2/{repository_path}/manifests/sha-{revision}",
        {"Authorization": "Bearer " + bearer, "Accept": MANIFEST_ACCEPT},
        "HEAD",
    )
    if status in {401, 403, 404}:
        return None
    digest = headers.get("docker-content-digest", "")
    if status != 200 or not DIGEST_PATTERN.fullmatch(digest):
        raise ValueError(f"registry manifest request failed: {status}")
    return f"{namespace}/{name}@{digest}"


def select_components(sources: dict[str, Any], selection: str) -> list[dict[str, Any]]:
    components = sources["components"]
    if selection.strip() in {"", "all"}:
        return list(components)
    wanted = [item.strip() for item in selection.split(",") if item.strip()]
    known = {component["name"] for component in components}
    unknown = sorted(set(wanted) - known)
    if unknown:
        raise ValueError(f"unknown component: {', '.join(unknown)}")
    return [component for component in components if component["name"] in wanted]


def resolve(
    sources: dict[str, Any],
    fetch: Fetch,
    token: str | None,
    selection: str = "all",
) -> dict[str, Any]:
    organization = sources["organization"]
    namespace = sources["buildNamespace"]
    selected = select_components(sources, selection)
    releases: dict[str, str | None] = {}
    mains: dict[str, str] = {}
    results = []
    for component in selected:
        repository = component["repository"]
        if repository not in releases:
            releases[repository] = latest_release(
                fetch, organization, repository, token
            )
            mains[repository] = commit_of(
                fetch, organization, repository, "main", token
            )
        tag = releases[repository]
        source = f"https://github.com/{organization}/{repository}"
        result: dict[str, Any] = {
            "name": component["name"],
            "repository": repository,
            "target": component["target"],
            "platform": component["platform"],
            "runner": component["runner"],
            "sourceRepository": source,
            "dockerfile": component["dockerfile"],
            "context": component["context"],
        }
        reference = None
        reason = "no component Release"
        if tag is not None and version_key(tag) < version_key(
            component["minimumRelease"]
        ):
            reason = f"Release {tag} is below {component['minimumRelease']}"
        elif tag is not None:
            reference = official_image(fetch, organization, component, tag)
            reason = f"Release {tag} has no usable image reference"
        if reference is not None:
            result.update(
                imageProvider=RELEASE_PROVIDER,
                version=tag,
                sourceRevision=commit_of(fetch, organization, repository, tag, token),
                image=reference,
                action="official",
                reason=f"official image of Release {tag}",
            )
        else:
            revision = mains[repository]
            existing = existing_build_image(
                fetch, namespace, component["name"], revision, token
            )
            result.update(
                imageProvider=BUILD_PROVIDER,
                sourceRevision=revision,
                image=existing,
                action="existing" if existing else "build",
                reason=reason,
                buildImage=f"{namespace}/{component['name']}:sha-{revision}",
            )
        results.append(result)
    include = [
        {
            key: result[key]
            for key in (
                "name",
                "repository",
                "platform",
                "runner",
                "dockerfile",
                "context",
                "sourceRepository",
                "sourceRevision",
                "buildImage",
            )
        }
        for result in results
        if result["action"] == "build"
    ]
    return {
        "schemaVersion": 1,
        "components": results,
        "matrix": {"include": include},
        "hasBuild": bool(include),
    }


def merge(resolved: dict[str, Any], builds: Iterable[dict[str, str]]) -> dict[str, Any]:
    """Fill the digest references of the built images and return the final result."""
    built = {}
    for record in builds:
        reference = record.get("image", "")
        if not re.fullmatch(r"^[a-z0-9][a-z0-9./_-]*@sha256:[0-9a-f]{64}$", reference):
            raise ValueError(f"invalid build record: {record.get('name')}")
        built[record["name"]] = reference
    components = []
    for result in resolved["components"]:
        result = dict(result)
        if result["action"] == "build":
            if result["name"] not in built:
                raise ValueError(f"build result is missing: {result['name']}")
            result["image"] = built[result["name"]]
        if not result.get("image"):
            raise ValueError(f"image is missing: {result['name']}")
        components.append(result)
    return {"schemaVersion": 1, "components": components}


def candidate_entry(
    result: dict[str, Any], previous: dict[str, Any] | None
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "name": result["name"],
        "sourceRepository": result["sourceRepository"],
        "sourceRevision": result["sourceRevision"],
    }
    if result["imageProvider"] == RELEASE_PROVIDER:
        entry["version"] = result["version"]
    entry.update(
        imageProvider=result["imageProvider"],
        image=result["image"],
        packageVisibility="public",
        pullAuthentication="none",
        notices=list(previous["notices"]) if previous else [],
    )
    return entry


def update_candidate(
    candidate: dict[str, Any], final: dict[str, Any]
) -> dict[str, Any]:
    """Replace or insert the synchronized components; other components stay as they are."""
    for result in final["components"]:
        if not result.get("image"):
            raise ValueError(f"image is missing: {result['name']}")
        components = candidate["targets"][result["target"]]["components"]
        for index, previous in enumerate(components):
            if previous["name"] == result["name"]:
                components[index] = candidate_entry(result, previous)
                break
        else:
            components.append(candidate_entry(result, None))
    return candidate


def finalize_blockers(candidate: dict[str, Any]) -> list[str]:
    blockers = []
    for target in ("edge", "server"):
        for component in candidate["targets"][target]["components"]:
            if component["sourceRevision"] == PLACEHOLDER_REVISION:
                blockers.append(f"placeholder source revision: {component['name']}")
    return blockers
