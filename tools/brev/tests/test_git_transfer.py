"""Exercise Git bundles and remote edit checks with two real local repositories."""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.brev import cli


class GitTransferTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "client"
        self.remote = self.root / "remote workspace" / "checkout"
        self.source.mkdir()
        self.home = self.root / "remote-home"
        self.home.mkdir()
        self.env = dict(os.environ, HOME=str(self.home), GIT_CONFIG_NOSYSTEM="1")
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Test Author")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "alias.literal", "!printf '%s' 'quote; $HOME'")
        self.git("remote", "add", "origin", "git@github.com:author/example.git")
        self.commit("one")
        self.patch = mock.patch.multiple(
            cli,
            ROOT=self.source,
            workspace=lambda: str(self.remote),
            ssh=self.local_ssh,
            run=self.local_run,
        )
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def git(self, *args, directory=None):
        return subprocess.run(
            ["git", *args],
            cwd=directory or self.source,
            env=self.env,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def commit(self, content):
        (self.source / "file.txt").write_text(content)
        self.git("add", "file.txt")
        self.git("commit", "-m", content)

    def local_ssh(self, command, **kwargs):
        return subprocess.run(
            ["bash", "-c", command],
            env=self.env,
            check=True,
            capture_output=True,
            text=True,
        )

    def local_run(self, argv, *, capture=False, **kwargs):
        if argv[0] == "rsync":
            destination = argv[-1].split(":", 1)[1]
            shutil.copy2(argv[-2], destination)
            return subprocess.CompletedProcess(argv, 0, "")
        return subprocess.run(
            [str(a) for a in argv],
            check=True,
            env=self.env,
            capture_output=True,
            text=True,
            **kwargs,
        )

    def test_install_transfers_unpushed_commits_and_literal_preferences(self):
        cli.install()
        self.assertEqual(
            self.git("rev-parse", "HEAD"),
            self.git("rev-parse", "HEAD", directory=self.remote),
        )
        self.assertEqual(
            self.git("remote", "get-url", "origin", directory=self.remote),
            "https://github.com/author/example.git",
        )
        self.assertEqual(
            self.git("config", "alias.literal", directory=self.remote),
            "!printf '%s' 'quote; $HOME'",
        )
        self.assertEqual(
            self.git("config", "user.email", directory=self.remote),
            "test@example.invalid",
        )

    def test_sync_fast_forwards_but_preserves_dirty_or_diverged_remote(self):
        cli.install()
        self.commit("two")
        (self.remote / "file.txt").write_text("remote edit")
        with self.assertRaises(subprocess.CalledProcessError):
            cli.install(update=True)
        self.assertEqual((self.remote / "file.txt").read_text(), "remote edit")
        self.git("restore", "file.txt", directory=self.remote)
        cli.install(update=True)
        self.assertEqual((self.remote / "file.txt").read_text(), "two")
        (self.remote / "file.txt").write_text("remote commit")
        self.git("add", "file.txt", directory=self.remote)
        self.git("commit", "-m", "remote", directory=self.remote)
        self.commit("three")
        with self.assertRaises(subprocess.CalledProcessError):
            cli.install(update=True)
        self.assertEqual((self.remote / "file.txt").read_text(), "remote commit")
