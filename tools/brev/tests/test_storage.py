"""Check storage boundaries before external transfers."""

import importlib
import tempfile
import unittest
from pathlib import Path


def load(test, module):
    try:
        return importlib.import_module("tools.brev." + module)
    except ModuleNotFoundError:
        test.fail(f"The {module} module is missing.")


class ImageTests(unittest.TestCase):
    def test_pull_requires_digest_and_unique_local_names(self):
        images = load(self, "images")
        digest = "ghcr.io/author/v2d/robotic-grounding@sha256:" + "a" * 64
        good = {
            "schema_version": 1,
            "source_revision": "b" * 40,
            "images": [{"local": "robotic-grounding:latest", "digest": digest}],
        }
        self.assertEqual(images.validate_manifest(good), good["images"])
        for records in (
            [{"local": "robotic-grounding:latest", "digest": "ghcr.io/a/b:latest"}],
            good["images"] * 2,
            [{"local": "--bad", "digest": digest}],
            [],
        ):
            with self.subTest(records=records), self.assertRaises(ValueError):
                images.validate_manifest(dict(good, images=records))

    def test_image_profile_matches_canonical_hamer_build(self):
        images = load(self, "images")
        script = (
            images.ROOT / "reconstruction/scripts/build_ego_reconstruction_packages.sh"
        ).read_text()
        import re

        match = re.search(r"hamer\)\s+MODULES=\(([^)]+)\)", script)
        self.assertEqual(
            images.EGO_IMAGES,
            ["v2d_" + value + ":latest" for value in match[1].split()],
        )


class ArtifactTests(unittest.TestCase):
    def test_manifest_has_real_hashes_and_rejects_links_and_credentials(self):
        artifacts = load(self, "artifacts")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "mesh.glb").write_bytes(b"mesh")
            manifest = artifacts.inventory(root)
            self.assertEqual(
                manifest["mesh.glb"]["sha256"],
                "d30ca7a7a32bf5772dc5eb2a2e7bd35737eff795ad74f2479b359716b59abdfa",
            )
            (root / ".env").write_text("TOKEN=private")
            with self.assertRaises(ValueError):
                artifacts.inventory(root)
            (root / ".env").unlink()
            (root / "link").symlink_to(root / "mesh.glb")
            with self.assertRaises(ValueError):
                artifacts.inventory(root)

    def test_private_upload_does_not_accept_existing_public_repo(self):
        artifacts = load(self, "artifacts")
        with self.assertRaises(ValueError):
            artifacts.check_visibility(is_private=False, allow_public=False)
        artifacts.check_visibility(is_private=True, allow_public=False)
        artifacts.check_visibility(is_private=False, allow_public=True)

    def test_download_verification_rejects_missing_or_changed_files(self):
        artifacts = load(self, "artifacts")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "result.txt").write_text("good")
            expected = artifacts.inventory(root)
            artifacts.verify(root, expected)
            (root / "result.txt").write_text("changed")
            with self.assertRaises(ValueError):
                artifacts.verify(root, expected)
            with self.assertRaises(ValueError):
                artifacts.verify(root, {"../secret": {"size": 1, "sha256": "a" * 64}})


if __name__ == "__main__":
    unittest.main()
