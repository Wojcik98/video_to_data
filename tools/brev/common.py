"""Shared process and file operations."""

import json
import os
import re
import shlex
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / ".local-data/brev"


def run(argv, *, capture=False, **kwargs):
    """Run an argument list and stop on failure."""
    print("+ " + shlex.join([str(arg) for arg in argv]), flush=True)
    return subprocess.run(
        [str(arg) for arg in argv],
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        **kwargs,
    )


def name(value):
    """Accept a name that is safe for SSH and tmux."""
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,62}", value):
        raise ValueError("Use a name with letters, digits, underscores, or hyphens.")
    return value


def instance():
    return name(os.environ.get("V2D_BREV_NAME", "v2d-l40s"))


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def remote_path(value):
    """Reject paths that can escape a selected transfer root."""
    path = Path(value)
    if (
        path.is_absolute()
        or not path.parts
        or ".." in path.parts
        or value.startswith("-")
    ):
        raise ValueError("Use a nonempty relative path without '..'.")
    return path.as_posix()
