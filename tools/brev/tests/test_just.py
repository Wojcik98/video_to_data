"""Check argument forwarding through the installed just executable."""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


@unittest.skipUnless(shutil.which("just"), "Install just for alias checks.")
class JustTests(unittest.TestCase):
    def invoke(self, *args):
        with tempfile.TemporaryDirectory() as temporary:
            executable = Path(temporary) / "python with spaces"
            executable.write_text(
                "#!/usr/bin/env python3\nimport json,sys\nprint(json.dumps(sys.argv[1:]))\n"
            )
            executable.chmod(0o755)
            result = subprocess.run(
                ["just", *args],
                cwd=ROOT,
                env=dict(os.environ, PYTHON=str(executable)),
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout)

    def test_e2e_preserves_spaces_and_shell_characters(self):
        value = "space 'quote' $HOME; $(literal)"
        self.assertEqual(
            self.invoke("e2e", "init", "--sequence-id", value),
            ["-m", "tools.e2e.cli", "init", "--sequence-id", value],
        )

    def test_remote_job_preserves_command_arguments(self):
        self.assertEqual(
            self.invoke("brev-job", "train-1", "printf", "%s", "a b"),
            [
                "-m",
                "tools.brev.cli",
                "exec",
                "--",
                "python3",
                "-m",
                "tools.brev.jobs",
                "start",
                "train-1",
                "printf",
                "%s",
                "a b",
            ],
        )

    def test_forward_has_no_empty_default_argument(self):
        self.assertEqual(
            self.invoke("brev-forward", "8000"),
            ["-m", "tools.brev.cli", "forward", "8000"],
        )
