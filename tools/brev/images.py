"""Build, publish, and restore the Docker images used by the E2E launcher."""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from .common import ROOT, STATE, run, write_json

EGO_IMAGES = [
    "v2d_" + module + ":latest"
    for module in (
        "anycalib",
        "moge",
        "grounding_dino",
        "sam2",
        "sam3d",
        "foundation_pose",
        "hamer",
        "wilor",
        "geocalib",
        "droid_slam",
        "gsplat_refinement",
    )
]
GROUNDING_IMAGES = ["v2d_task_library_loader:latest", "robotic-grounding:latest"]


def profile_images(profile):
    return {
        "ego": EGO_IMAGES,
        "grounding": GROUNDING_IMAGES,
        "all": EGO_IMAGES + GROUNDING_IMAGES,
    }[profile]


def validate_manifest(data):
    if data.get("schema_version") != 1 or not re.fullmatch(
        r"[0-9a-f]{40,64}", data.get("source_revision", "")
    ):
        raise ValueError("Invalid image manifest version or source revision.")
    records = data.get("images")
    if not isinstance(records, list) or not records:
        raise ValueError("The image manifest must contain images.")
    seen = set()
    for record in records:
        local = record.get("local", "")
        digest = record.get("digest", "")
        if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]*:[A-Za-z0-9_.-]+", local):
            raise ValueError("Invalid local image name.")
        if not re.fullmatch(
            r"ghcr\.io/[a-z0-9][a-z0-9_./-]*@sha256:[0-9a-f]{64}", digest
        ):
            raise ValueError("Each image must have an immutable GHCR digest.")
        if local in seen:
            raise ValueError("The manifest repeats a local image name.")
        seen.add(local)
    return records


def inspect(image):
    return json.loads(run(["docker", "image", "inspect", image], capture=True).stdout)[
        0
    ]


def build(profile):
    if run(["git", "status", "--porcelain"], cwd=ROOT, capture=True).stdout:
        raise ValueError("Commit or stash changes before a reproducible image build.")
    revision = run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture=True).stdout.strip()
    if profile in ("ego", "all"):
        run(
            ["bash", "scripts/build_ego_reconstruction_packages.sh", "--mode", "hamer"],
            cwd=ROOT / "reconstruction",
        )
    if profile in ("grounding", "all"):
        run(
            [sys.executable, "modules/v2d_task_library_loader/docker/build.py"],
            cwd=ROOT / "reconstruction",
        )
        run(
            ["bash", "workflow/run.sh", "build", "latest", "0"],
            cwd=ROOT / "robotic_grounding",
        )
    write_json(
        STATE / f"build-{profile}.json",
        {
            "source_revision": revision,
            "images": {
                image: inspect(image)["Id"] for image in profile_images(profile)
            },
        },
    )


def package_visibility(namespace, image, organization=False):
    owner, _, prefix = namespace.partition("/")
    package = prefix + "/" + image.split(":")[0] if prefix else image.split(":")[0]
    token = run(["gh", "auth", "token"], capture=True).stdout.strip()
    endpoint = f"https://api.github.com/{'orgs' if organization else 'users'}/{quote(owner, safe='')}/packages/container/{quote(package, safe='')}"
    request = Request(
        endpoint,
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)["visibility"]
    except HTTPError as error:
        if error.code == 404:
            return None
        raise


def push(profile, namespace, manifest, allow_public=False, organization=False):
    if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]*(/[a-z0-9][a-z0-9_.-]*)*", namespace):
        raise ValueError("Use a GHCR namespace such as 'account/v2d'.")
    stamp = json.loads((STATE / f"build-{profile}.json").read_text())
    records = []
    # Check every image and visibility before the first upload.
    for image in profile_images(profile):
        if inspect(image)["Id"] != stamp["images"].get(image):
            raise ValueError(f"Image {image} changed since its recorded build.")
        visibility = package_visibility(namespace, image, organization)
        if visibility not in (None, "private") and not allow_public:
            raise ValueError(
                f"{image} has {visibility} visibility. Use a private package or --allow-public."
            )
    for image in profile_images(profile):
        repository = f"ghcr.io/{namespace}/{image.split(':')[0]}"
        tag = repository + ":git-" + stamp["source_revision"]
        run(["docker", "tag", image, tag])
        run(["docker", "push", tag])
        if (
            not allow_public
            and package_visibility(namespace, image, organization) != "private"
        ):
            raise ValueError(
                "The uploaded package is not confirmed private. Check GHCR permissions."
            )
        digests = [
            value
            for value in inspect(tag).get("RepoDigests", [])
            if value.startswith(repository + "@sha256:")
        ]
        if len(digests) != 1:
            raise ValueError(f"Cannot resolve one published digest for {tag}.")
        records.append({"local": image, "digest": digests[0]})
    data = {
        "schema_version": 1,
        "source_revision": stamp["source_revision"],
        "images": records,
    }
    validate_manifest(data)
    write_json(manifest, data)
    print(f"Image manifest: {manifest}. Back up this file to HF or commit it to Git.")


def pull(manifest):
    data = json.loads(manifest.read_text())
    for record in validate_manifest(data):
        digest = record["digest"]
        # Docker verifies the content against the registry digest on pull.
        run(["docker", "pull", digest])
        run(["docker", "tag", digest, record["local"]])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    for action in ("build", "push"):
        command = sub.add_parser(action)
        command.add_argument(
            "--profile", choices=("ego", "grounding", "all"), default="all"
        )
        if action == "push":
            command.add_argument(
                "--namespace",
                required=True,
                help="GHCR account/prefix, without ghcr.io",
            )
            command.add_argument(
                "--manifest", type=Path, default=STATE / "images.lock.json"
            )
            command.add_argument("--allow-public", action="store_true")
            command.add_argument("--organization", action="store_true")
    command = sub.add_parser("pull")
    command.add_argument("manifest", type=Path)
    args = parser.parse_args(argv)
    if args.action == "build":
        build(args.profile)
    elif args.action == "push":
        push(
            args.profile,
            args.namespace,
            args.manifest,
            args.allow_public,
            args.organization,
        )
    else:
        pull(args.manifest)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)
