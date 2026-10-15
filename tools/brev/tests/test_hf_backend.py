"""Check HF transaction order with a local repository substitute."""

import importlib
import json
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from tools.brev.artifacts import checksum, inventory


class HFTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.staging = self.root / "staging"
        self.staging.mkdir()
        (self.staging / "mesh.glb").write_bytes(b"mesh")
        (self.staging / "_v2d").mkdir()
        (self.staging / "_v2d/manifest.json").write_text(
            json.dumps({"files": inventory(self.staging)})
        )
        self.hub = self.root / "hub"
        self.hub.mkdir()
        self.private = True
        self.fail_folder = False
        self.events = []
        owner = self

        class API:
            def create_repo(self, repo, **kwargs):
                owner.events.append(("create", kwargs["private"]))

            def repo_info(self, repo, **kwargs):
                return types.SimpleNamespace(private=owner.private, sha="a" * 40)

            def list_repo_files(self, repo, **kwargs):
                return [
                    p.relative_to(owner.hub).as_posix()
                    for p in owner.hub.rglob("*")
                    if p.is_file()
                ]

            def upload_file(self, *, path_or_fileobj, path_in_repo, **kwargs):
                owner.events.append(("file", path_in_repo))
                target = owner.hub / path_in_repo
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(
                    Path(path_or_fileobj).read_bytes()
                    if isinstance(path_or_fileobj, str)
                    else path_or_fileobj.read()
                )
                return types.SimpleNamespace(oid="b" * 40)

            def upload_folder(self, *, folder_path, path_in_repo, **kwargs):
                owner.events.append(("folder", path_in_repo))
                if owner.fail_folder:
                    raise ConnectionError("test disconnect")
                shutil.copytree(
                    folder_path, owner.hub / path_in_repo, dirs_exist_ok=True
                )

        fake = types.ModuleType("huggingface_hub")
        fake.HfApi = API
        fake.hf_hub_download = lambda repo, filename, **kwargs: str(self.hub / filename)
        fake.snapshot_download = lambda **kwargs: None
        self.patch = mock.patch.dict(sys.modules, {"huggingface_hub": fake})
        self.patch.start()
        self.addCleanup(self.patch.stop)
        sys.modules.pop("tools.brev.hf_backend", None)
        self.backend = importlib.import_module("tools.brev.hf_backend")
        self.addCleanup(sys.modules.pop, "tools.brev.hf_backend", None)

    def upload(self):
        with mock.patch.object(
            sys,
            "argv",
            [
                "backend",
                "upload",
                "author/results",
                "dataset",
                "run-1",
                str(self.staging),
                "private",
            ],
        ):
            self.backend.main()

    def test_private_default_refuses_existing_public_repository_before_upload(self):
        self.private = False
        with self.assertRaises(ValueError):
            self.upload()
        self.assertEqual(self.events, [("create", True)])

    def test_completion_marker_is_last_and_failed_transfer_can_resume(self):
        self.fail_folder = True
        with self.assertRaises(ConnectionError):
            self.upload()
        self.assertFalse((self.hub / "runs/run-1/_v2d/complete.json").exists())
        self.fail_folder = False
        self.upload()
        self.assertEqual(self.events[-1], ("file", "runs/run-1/_v2d/complete.json"))
        marker = json.loads((self.hub / "runs/run-1/_v2d/complete.json").read_text())
        self.assertEqual(
            marker["manifest_sha256"], checksum(self.staging / "_v2d/manifest.json")
        )
        with self.assertRaises(ValueError):
            self.upload()
