"""Interrupt real rsync and check that retry restores a complete file."""

import os
import shutil
import signal
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from tools.brev import cli


@unittest.skipUnless(shutil.which("rsync"), "Install rsync for the retry check.")
class TransferTests(unittest.TestCase):
    def test_interrupted_push_retries_without_skipping_the_partial_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            client = root / "client"
            remote = root / "remote"
            (client / "input").mkdir(parents=True)
            (client / "input/mesh.bin").write_bytes(os.urandom(1024 * 1024))
            attempts = 0

            def ssh(command, **kwargs):
                return subprocess.run(["bash", "-c", command], check=True)

            def run(argv, **kwargs):
                nonlocal attempts
                mapped = [
                    str(arg).split(":", 1)[1]
                    if str(arg).startswith(cli.instance() + ":")
                    else str(arg)
                    for arg in argv
                ]
                attempts += 1
                if attempts == 1:
                    process = subprocess.Popen(
                        [*mapped[:1], "--bwlimit=128", *mapped[1:]],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    try:
                        for _ in range(100):
                            if any(
                                p.is_file() and p.stat().st_size > 0
                                for p in remote.rglob("*")
                            ):
                                break
                            time.sleep(0.02)
                        process.send_signal(signal.SIGINT)
                        code = process.wait(timeout=10)
                    finally:
                        if process.poll() is None:
                            process.kill()
                            process.wait()
                    self.assertNotEqual(code, 0)
                    raise subprocess.CalledProcessError(code, argv)
                return subprocess.run(mapped, check=True, capture_output=True)

            with mock.patch.multiple(
                cli, ROOT=client, workspace=lambda: str(remote), ssh=ssh, run=run
            ):
                with self.assertRaises(subprocess.CalledProcessError):
                    cli.transfer("push", "input", "results")
                cli.transfer("push", "input", "results")
            self.assertEqual(
                (remote / "results/mesh.bin").read_bytes(),
                (client / "input/mesh.bin").read_bytes(),
            )
