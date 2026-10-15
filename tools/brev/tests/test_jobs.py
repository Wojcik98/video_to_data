"""Check command values, logs, and saved job status."""

import importlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


class JobTests(unittest.TestCase):
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
