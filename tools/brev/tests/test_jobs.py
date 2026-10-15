"""Check command values, logs, and saved job status."""

import importlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
from pathlib import Path


class JobTests(unittest.TestCase):
    @unittest.skipUnless(
        os.environ.get("V2D_TEST_TMUX") == "1",
        "Set V2D_TEST_TMUX=1 for the real tmux check.",
    )
    def test_detached_job_finishes_after_launcher_exits(self):
        from tools.brev import jobs

        job_name = "smoke-" + uuid.uuid4().hex[:10]
        directory = jobs.job_directory(job_name)
        self.addCleanup(shutil.rmtree, directory, True)
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.brev.jobs",
                "start",
                job_name,
                "--",
                sys.executable,
                "-c",
                "import time; time.sleep(.2); print('detached'); raise SystemExit(7)",
            ],
            cwd=jobs.ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        for _ in range(100):
            if (directory / "exit-code").exists():
                break
            time.sleep(0.05)
        self.assertEqual((directory / "exit-code").read_text().strip(), "7")
        self.assertIn("detached", (directory / "output.log").read_text())

    def test_failed_command_keeps_log_and_exit_code(self):
        try:
            jobs = importlib.import_module("tools.brev.jobs")
        except ModuleNotFoundError:
            self.fail("The job runner is missing.")
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "job"
            args = [
                sys.executable,
                "-c",
                "import sys; print(sys.argv[1]); sys.exit(7)",
                "space ' quote $HOME ; literal",
            ]
            self.assertEqual(jobs.run_job(directory, args, Path(temporary)), 7)
            self.assertEqual((directory / "exit-code").read_text().strip(), "7")
            self.assertIn(args[-1], (directory / "output.log").read_text())
            self.assertEqual(
                json.loads((directory / "command.json").read_text())["argv"], args
            )

    def test_job_name_cannot_escape_state_directory(self):
        try:
            jobs = importlib.import_module("tools.brev.jobs")
        except ModuleNotFoundError:
            self.fail("The job runner is missing.")
        for name in ("../other", "a/b", "bad;name", "", "-option"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                jobs.job_directory(name)


if __name__ == "__main__":
    unittest.main()
