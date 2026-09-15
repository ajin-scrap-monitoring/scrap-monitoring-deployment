from __future__ import annotations

import re
import unittest
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
EXCLUDED_DIRECTORIES = {".git", ".venv", "__pycache__", "dist", "node_modules"}
FORBIDDEN_NAMES = {"ca.json", "root_ca.sha256"}
FORBIDDEN_SUFFIXES = {".crt", ".key", ".pem", ".password"}
FORBIDDEN_PATTERNS = {
    "PEM data": re.compile(r"-----BEGIN (?:CERTIFICATE|.*PRIVATE KEY)-----"),
    "Tailscale DNS name": re.compile(
        r"\b[a-z0-9-]+\.tail[a-z0-9]+\.ts\.net\b", re.IGNORECASE
    ),
    "Tailscale address": re.compile(
        r"\b100\.(?:6[4-9]|[7-9][0-9]|1[01][0-9]|12[0-7])(?:\.[0-9]{1,3}){2}\b"
    ),
    "RFC 1918 address": re.compile(
        r"\b(?:10(?:\.[0-9]{1,3}){3}|192\.168(?:\.[0-9]{1,3}){2}|172\.(?:1[6-9]|2[0-9]|3[01])(?:\.[0-9]{1,3}){2})\b"
    ),
}


def repository_files() -> list[Path]:
    files = []
    for path in REPOSITORY.rglob("*"):
        if any(part in EXCLUDED_DIRECTORIES for part in path.parts):
            continue
        if path.is_file():
            files.append(path)
    return files


class PublicContentTest(unittest.TestCase):
    def test_sensitive_file_names_are_absent(self) -> None:
        sensitive = [
            path.relative_to(REPOSITORY)
            for path in repository_files()
            if path.name in FORBIDDEN_NAMES or path.suffix in FORBIDDEN_SUFFIXES
        ]
        self.assertEqual([], sensitive)

    def test_private_content_patterns_are_absent(self) -> None:
        findings = []
        for path in repository_files():
            try:
                content = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for label, pattern in FORBIDDEN_PATTERNS.items():
                if pattern.search(content):
                    findings.append(f"{path.relative_to(REPOSITORY)}: {label}")
        self.assertEqual([], findings)


if __name__ == "__main__":
    unittest.main()
