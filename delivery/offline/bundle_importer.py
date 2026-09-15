from __future__ import annotations

import argparse
import shutil
import subprocess
import tarfile
from pathlib import Path

from release_verifier import verify_release

TARGET_PLATFORMS = {
    "edge": "linux/arm64",
    "server": "linux/amd64",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import a verified offline bundle.")
    parser.add_argument("--version", required=True)
    parser.add_argument("--target", choices=sorted(TARGET_PLATFORMS), required=True)
    parser.add_argument("--bundle", dest="package", type=Path, required=True)
    parser.add_argument("--checksums", type=Path, required=True)
    return parser.parse_args()


def load_image_archive(bundle: Path, member_name: str) -> None:
    with tarfile.open(bundle, mode="r:gz") as archive:
        member = archive.getmember(member_name)
        if not member.isfile():
            raise ValueError(f"image archive is not a regular file: {member_name}")
        source = archive.extractfile(member)
        if source is None:
            raise ValueError(f"image archive cannot be read: {member_name}")

        with (
            source,
            subprocess.Popen(
                ["docker", "image", "load"], stdin=subprocess.PIPE
            ) as process,
        ):
            if process.stdin is None:
                process.kill()
                raise RuntimeError("docker image load input is unavailable")
            try:
                shutil.copyfileobj(source, process.stdin, length=1024 * 1024)
                process.stdin.close()
            except BrokenPipeError:
                pass
            return_code = process.wait()
        if return_code != 0:
            raise RuntimeError(f"docker image load failed with code {return_code}")


def verify_local_images(manifest: dict[str, object], target: str) -> None:
    expected_platform = TARGET_PLATFORMS[target]
    for component in manifest["targets"][target]["components"]:
        image = component["image"]
        result = subprocess.run(
            [
                "docker",
                "image",
                "inspect",
                "--format",
                "{{.Os}}/{{.Architecture}}",
                image,
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"imported image digest is unavailable: {image}")
        if result.stdout.strip() != expected_platform:
            raise RuntimeError(f"imported image platform does not match: {image}")


def import_bundle(args: argparse.Namespace) -> None:
    if shutil.which("docker") is None:
        raise RuntimeError("docker is required")
    mode, manifest = verify_release(args)
    if mode != "offline":
        raise ValueError("release package is not an offline bundle")

    image_archive = f"images/{args.target}-images.tar"
    load_image_archive(args.package, image_archive)
    verify_local_images(manifest, args.target)


def main() -> None:
    args = parse_args()
    try:
        import_bundle(args)
    except (OSError, RuntimeError, tarfile.TarError, ValueError) as error:
        raise SystemExit(f"offline bundle import failed: {error}") from error
    print(args.package)


if __name__ == "__main__":
    main()
