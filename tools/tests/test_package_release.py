import gzip
import hashlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from package_release import package

SHA = "a" * 40
IMAGE = {
    "Id": "sha256:" + "b" * 64,
    "Os": "linux",
    "Architecture": "amd64",
    "Config": {
        "Labels": {
            "org.opencontainers.image.source": "https://github.com/niuroumiantt/mail2leads",
            "org.opencontainers.image.revision": SHA,
        }
    },
}


class Process:
    def __init__(self, code=0):
        self.stdout = io.BytesIO(b"docker image archive")
        self.returncode = code
        self.args = ["docker", "image", "save"]

    def wait(self):
        return self.returncode

    def kill(self):
        self.returncode = -9


class PackageReleaseTests(unittest.TestCase):
    def test_packages_image_and_binds_archive_to_source_sha(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch("package_release.subprocess.check_output", return_value=json.dumps([IMAGE])),
            patch("package_release.subprocess.Popen", return_value=Process()),
        ):
            manifest = package(SHA, "12345", "1", Path(directory))
            archive = Path(directory) / "aimail-image.tar.gz"
            with gzip.open(archive, "rb") as saved:
                self.assertEqual(saved.read(), b"docker image archive")
            self.assertEqual(manifest["source_sha"], SHA)
            self.assertEqual(manifest["archive"]["image_id"], IMAGE["Id"])
            archive_hash = hashlib.sha256(archive.read_bytes()).hexdigest()
            self.assertEqual(manifest["archive"]["sha256"], archive_hash)
            self.assertIn(SHA, (Path(directory) / "release.json").read_text())

    def test_rejects_wrong_platform_or_revision_before_export(self):
        for field, value in [("Architecture", "arm64"), ("Os", "darwin")]:
            candidate = {**IMAGE, field: value}
            with (
                patch(
                    "package_release.subprocess.check_output", return_value=json.dumps([candidate])
                ),
                patch("package_release.subprocess.Popen") as export,
            ):
                with self.assertRaisesRegex(RuntimeError, "provenance"):
                    package(SHA, "12345", "1", Path("unused"))
                export.assert_not_called()
        wrong = {
            **IMAGE,
            "Config": {
                "Labels": {
                    "org.opencontainers.image.source": IMAGE["Config"]["Labels"][
                        "org.opencontainers.image.source"
                    ],
                    "org.opencontainers.image.revision": "c" * 40,
                }
            },
        }
        with (
            patch("package_release.subprocess.check_output", return_value=json.dumps([wrong])),
            patch("package_release.subprocess.Popen") as export,
        ):
            with self.assertRaisesRegex(RuntimeError, "provenance"):
                package(SHA, "12345", "1", Path("unused"))
            export.assert_not_called()

    def test_rejects_bad_source_and_run_identity(self):
        for args in [("bad", "1", "1"), (SHA, "x", "1"), (SHA, "1", "0")]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                package(*args, Path("unused"))

    def test_fails_if_docker_export_fails(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch("package_release.subprocess.check_output", return_value=json.dumps([IMAGE])),
            patch("package_release.subprocess.Popen", return_value=Process(code=2)),
        ):
            with self.assertRaises(subprocess.CalledProcessError):
                package(SHA, "12345", "1", Path(directory))
            self.assertFalse((Path(directory) / "aimail-image.tar.gz").exists())


if __name__ == "__main__":
    unittest.main()
