"""Save selected result folders to HF and verify restored files."""

import argparse
import datetime
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .common import ROOT, STATE, name, remote_path, run, write_json

FORBIDDEN = {
    ".git",
    ".ssh",
    ".aws",
    ".brev",
    ".env",
    "token",
    "stored_tokens",
    "credentials",
    "credentials.json",
    "id_rsa",
    "id_ed25519",
    "MANO_LEFT.pkl",
    "MANO_RIGHT.pkl",
}


def checksum(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def inventory(directory):
    if not directory.is_dir():
        raise ValueError("Select a result directory.")
    records = {}
    for path in sorted(directory.rglob("*")):
        relative = path.relative_to(directory)
        if relative.parts[0] == "_v2d":
            continue
        if path.is_symlink() or any(
            part in FORBIDDEN or part.startswith(".env.") for part in relative.parts
        ):
            raise ValueError(
                f"Remove credentials, licensed MANO files, and links from the upload: {relative}"
            )
        if path.is_file():
            records[relative.as_posix()] = {
                "size": path.stat().st_size,
                "sha256": checksum(path),
            }
    if not records:
        raise ValueError("The result directory has no files.")
    return records


def check_visibility(*, is_private, allow_public):
    if not is_private and not allow_public:
        raise ValueError(
            "This HF repository is public. Use a private repository or pass --public explicitly."
        )


def verify(directory, expected):
    for relative in expected:
        remote_path(relative)
    if inventory(directory) != expected:
        raise ValueError(
            "The file list, sizes, or checksums do not match the manifest."
        )


def upload(source, repo, run_id, public=False, repo_type="dataset"):
    source = source.resolve()
    name(run_id)
    if (source / "_v2d").exists():
        raise ValueError("The '_v2d' name is reserved for upload metadata.")
    records = inventory(source)
    staging = STATE / "uploads" / run_id
    if staging.is_relative_to(source):
        raise ValueError(
            "Select a result folder outside the upload snapshot directory."
        )
    # Keep the snapshot after failure so the same files can be retried.
    staging.parent.mkdir(parents=True, exist_ok=True)
    if not staging.exists():
        staging.mkdir()
        for relative in records:
            destination = staging / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source / relative, destination)
        verify(staging, records)
        manifest = {
            "schema_version": 1,
            "files": records,
            "source_revision": run(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, capture=True
            ).stdout.strip(),
            "source_dirty": bool(
                run(["git", "status", "--porcelain"], cwd=ROOT, capture=True).stdout
            ),
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        for filename in ("images.lock.json", "track3-revision.json"):
            path = STATE / filename
            if path.exists():
                manifest[filename] = json.loads(path.read_text())
        write_json(staging / "_v2d/manifest.json", manifest)
    else:
        manifest_path = staging / "_v2d/manifest.json"
        if not manifest_path.exists():
            raise ValueError(
                "An incomplete local snapshot exists. Use a new run ID or remove that snapshot."
            )
        manifest = json.loads(manifest_path.read_text())
        verify(staging, manifest["files"])
        if records != manifest["files"]:
            raise ValueError("The source changed. Use a new run ID.")
    run(
        [
            sys.executable,
            "-m",
            "tools.brev.hf_backend",
            "upload",
            repo,
            repo_type,
            run_id,
            str(staging),
            "public" if public else "private",
        ]
    )
    print(f"Saved {repo}/runs/{run_id}. Local snapshot: {staging}")


def download(repo, run_id, destination, revision="main", repo_type="dataset"):
    name(run_id)
    destination = destination.resolve()
    if destination.exists():
        raise ValueError(
            "Choose a new download destination. Existing files are preserved."
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as temporary:
        run(
            [
                sys.executable,
                "-m",
                "tools.brev.hf_backend",
                "download",
                repo,
                repo_type,
                run_id,
                temporary,
                revision,
            ]
        )
        restored = Path(temporary) / "runs" / run_id
        manifest = json.loads((restored / "_v2d/manifest.json").read_text())
        complete = json.loads((restored / "_v2d/complete.json").read_text())
        if checksum(restored / "_v2d/manifest.json") != complete["manifest_sha256"]:
            raise ValueError("The completion marker does not match the manifest.")
        verify(restored, manifest["files"])
        shutil.move(str(restored), destination)
    print(f"Restored and verified: {destination}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    command = sub.add_parser("upload")
    command.add_argument("source", type=Path)
    command.add_argument("--repo", required=True)
    command.add_argument("--run", required=True)
    command.add_argument("--repo-type", choices=("dataset", "model"), default="dataset")
    command.add_argument("--public", action="store_true")
    command = sub.add_parser("download")
    command.add_argument("--repo", required=True)
    command.add_argument("--run", required=True)
    command.add_argument("--repo-type", choices=("dataset", "model"), default="dataset")
    command.add_argument("--revision", default="main")
    command.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.action == "upload":
        upload(args.source, args.repo, args.run, args.public, args.repo_type)
    else:
        download(args.repo, args.run, args.destination, args.revision, args.repo_type)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)
