#!/usr/bin/env python3
"""Package the tested linux/amd64 image as an immutable GitHub Release asset."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

REPOSITORY = "niuroumiantt/aimail"
IMAGE = "mail2leads:release"
SHA_RE = re.compile(r"[0-9a-f]{40}")


def package(source_sha: str, run_id: str, run_attempt: str, directory: Path) -> dict:
    if not SHA_RE.fullmatch(source_sha):
        raise ValueError("source SHA must be 40 lowercase hex characters")
    if not run_id.isdecimal() or not run_attempt.isdecimal() or int(run_attempt) < 1:
        raise ValueError("invalid Actions run identity")
    image = json.loads(subprocess.check_output(["docker", "image", "inspect", IMAGE], text=True))[0]
    labels = image.get("Config", {}).get("Labels") or {}
    if (
        image.get("Os") != "linux"
        or image.get("Architecture") != "amd64"
        or labels.get("org.opencontainers.image.source") != f"https://github.com/{REPOSITORY}"
        or labels.get("org.opencontainers.image.revision") != source_sha
    ):
        raise RuntimeError("image platform or OCI provenance labels do not match this build")

    directory.mkdir(parents=True, exist_ok=True)
    archive = directory / "aimail-image.tar.gz"
    sha_file = directory / "aimail-image.tar.gz.sha256"
    manifest_file = directory / "release.json"
    digest = hashlib.sha256()
    size = 0
    producer = subprocess.Popen(["docker", "image", "save", IMAGE], stdout=subprocess.PIPE)
    try:
        with gzip.open(archive, "wb", compresslevel=6) as output:
            assert producer.stdout is not None
            while chunk := producer.stdout.read(1024 * 1024):
                output.write(chunk)
        code = producer.wait()
        if code:
            raise subprocess.CalledProcessError(code, producer.args)
    except BaseException:
        producer.kill()
        producer.wait()
        archive.unlink(missing_ok=True)
        raise
    with archive.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            size += len(chunk)
            digest.update(chunk)
    if size == 0:
        raise RuntimeError("image archive is empty")
    sha = digest.hexdigest()
    sha_file.write_text(f"{sha}  aimail-image.tar.gz\n")
    manifest = {
        "schema_version": 1,
        "repository": REPOSITORY,
        "ref": "refs/heads/main",
        "source_sha": source_sha,
        "platform": "linux/amd64",
        "run_id": run_id,
        "run_attempt": int(run_attempt),
        "archive": {"name": archive.name, "sha256": sha, "size": size, "image_id": image["Id"]},
    }
    manifest_file.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sha", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-attempt", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        manifest = package(args.sha, args.run_id, args.run_attempt, args.output)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"release packaging failed: {exc}", file=sys.stderr)
        return 1
    print(f"Packaged aimail release {manifest['source_sha']} ({manifest['archive']['size']} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
