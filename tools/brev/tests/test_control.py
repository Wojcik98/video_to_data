"""Check lifecycle decisions without creating cloud resources."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


class ControlTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.trace = self.path / "trace.jsonl"
        self.bin = self.path / "bin"
        self.bin.mkdir()
        script = """#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
with open(os.environ["TRACE"], "a") as f:
    f.write(json.dumps([Path(sys.argv[0]).name, *sys.argv[1:]]) + "\\n")
if Path(sys.argv[0]).name == "brev" and sys.argv[1] == "ls":
    print(os.environ["LISTING"])
    sys.exit(int(os.environ.get("LIST_RC", "0")))
if Path(sys.argv[0]).name == "brev" and sys.argv[1] == "search":
    print(os.environ["OFFERS"])
if Path(sys.argv[0]).name == "brev" and sys.argv[1] == "create" and "--help" not in sys.argv:
    with open(os.environ["TRACE"], "a") as f:
        f.write(json.dumps(["create-input", sys.stdin.read()]) + "\\n")
if Path(sys.argv[0]).name == "ssh":
    command = sys.argv[-1]
    if 'printf' in command:
        print("/home/ubuntu/workspace/video_to_data")
"""
        for name in ("brev", "ssh"):
            tool = self.bin / name
            tool.write_text(script)
            tool.chmod(0o755)
        self.env = dict(
            os.environ,
            PATH=f"{self.bin}:{os.environ['PATH']}",
            TRACE=str(self.trace),
            LISTING='{"workspaces": null}',
            V2D_BREV_NAME="v2d-l40s",
            OFFERS=json.dumps(
                [
                    {
                        "type": "gpu-l40s-d.1gpu-16vcpu-96gb",
                        "gpu_count": 1,
                        "provider": "nebius",
                        "gpu_name": "L40S",
                        "stoppable": True,
                        "target_disk_gb": 500,
                    }
                ]
            ),
        )

    def invoke(self, *args):
        return subprocess.run(
            [sys.executable, "-m", "tools.brev.cli", *args],
            cwd=ROOT,
            env=self.env,
            capture_output=True,
            text=True,
        )

    def calls(self):
        return (
            [json.loads(line) for line in self.trace.read_text().splitlines()]
            if self.trace.exists()
            else []
        )

    def listing(self, status):
        self.env["LISTING"] = json.dumps(
            {
                "workspaces": [
                    {
                        "name": "v2d-l40s",
                        "status": status,
                        "instance_type": "gpu-l40s-d.1gpu-16vcpu-96gb",
                    }
                ]
            }
        )

    def test_new_instance_is_one_stoppable_nebius_with_500gb(self):
        result = self.invoke("up")
        self.assertEqual(result.returncode, 0, result.stderr)
        create = next(
            c for c in self.calls() if c[:2] == ["brev", "create"] and "--help" not in c
        )
        self.assertNotIn("--type", create)
        selected = json.loads(
            next(c[1] for c in self.calls() if c[0] == "create-input")
        )
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["type"], "gpu-l40s-d.1gpu-16vcpu-96gb")
        self.assertEqual(selected[0]["target_disk_gb"], 500)
        self.assertIn("--startup-script", create)

    def test_missing_selected_offer_does_not_fall_back_to_other_gpu(self):
        self.env["OFFERS"] = "[]"
        self.assertNotEqual(self.invoke("up").returncode, 0)
        self.assertFalse(any(c[:2] == ["brev", "create"] for c in self.calls()))

    def test_running_instance_does_not_start_or_create(self):
        self.listing("RUNNING")
        result = self.invoke("up")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(
            any(c[:2] in (["brev", "create"], ["brev", "start"]) for c in self.calls())
        )

    def test_stopped_instance_resumes_by_name(self):
        self.listing("STOPPED")
        result = self.invoke("up")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(["brev", "start", "v2d-l40s"], self.calls())
        self.assertFalse(any(c[:2] == ["brev", "create"] for c in self.calls()))

    def test_unknown_failed_or_duplicate_listing_does_not_create(self):
        for listing, rc in [
            ("not json", "0"),
            ('{"unexpected": []}', "0"),
            ('{"workspaces": null}', "1"),
            (json.dumps({"workspaces": [{"name": "v2d-l40s"}] * 2}), "0"),
        ]:
            with self.subTest(listing=listing):
                self.trace.unlink(missing_ok=True)
                self.env.update(LISTING=listing, LIST_RC=rc)
                self.assertNotEqual(self.invoke("up").returncode, 0)
                self.assertFalse(any(c[:2] == ["brev", "create"] for c in self.calls()))

    def test_unhealthy_or_wrong_instance_does_not_start(self):
        for status in ("UNHEALTHY", "DELETING", "UNKNOWN"):
            self.listing(status)
            self.assertNotEqual(self.invoke("up").returncode, 0)

    def test_exec_preserves_literal_shell_characters(self):
        value = "a 'quote' $HOME; $(touch unwanted)"
        result = self.invoke("exec", "--", "printf", "%s", value)
        self.assertEqual(result.returncode, 0, result.stderr)
        import shlex

        command = [call for call in self.calls() if call[0] == "ssh"][-1][-1]
        self.assertTrue(command.endswith(shlex.join(["printf", "%s", value])))

    def test_transfer_rejects_traversal_and_git_history(self):
        for source in ("../secret", "/etc/passwd", ".git/config", ".ssh/key"):
            with self.subTest(source=source):
                self.assertNotEqual(
                    self.invoke("push", source, "uploads").returncode, 0
                )

    def test_git_settings_preserve_multiline_aliases(self):
        from tools.brev.cli import git_settings

        raw = "user.name\nAn Author\0alias.example\n!printf 'a\\nb'\n\0"
        self.assertEqual(
            git_settings(raw),
            [("user.name", "An Author"), ("alias.example", "!printf 'a\\nb'\n")],
        )


if __name__ == "__main__":
    unittest.main()
