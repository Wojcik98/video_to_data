"""Control a persistent L40S workspace through the Brev CLI."""

import argparse
import json
import os
import shlex
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit

from .common import INSTANCE_TYPE, ROOT, instance, remote_path, run


def ssh(command, *, capture=False, terminal=False):
    options = ["-t"] if terminal else ["-o", "BatchMode=yes"]
    return run(
        ["ssh", *options, "-o", "ConnectTimeout=15", instance(), command],
        capture=capture,
    )


def workspace():
    configured = os.environ.get("V2D_BREV_DIR")
    value = (
        configured
        or ssh(
            'printf "%s" "$HOME/workspace/video_to_data"', capture=True
        ).stdout.strip()
    )
    if not Path(value).is_absolute() or value in ("/", "/home", "/tmp"):
        raise ValueError(
            "The remote repository path must be an absolute workspace path."
        )
    return value


def listing():
    data = json.loads(run(["brev", "ls", "--all", "--json"], capture=True).stdout)
    if not isinstance(data, dict) or "workspaces" not in data:
        raise ValueError("Unknown Brev JSON format. No instance was created.")
    records = data["workspaces"]
    if records is None:
        records = []
    if not isinstance(records, list) or any(
        not isinstance(row, dict) or "name" not in row for row in records
    ):
        raise ValueError("Invalid Brev workspace list.")
    matches = [row for row in records if row["name"] == instance()]
    if len(matches) > 1:
        raise ValueError(
            "More than one instance has this name. Select the correct organization."
        )
    return matches[0] if matches else None


def up():
    record = listing()
    if record is None:
        offers = json.loads(
            run(
                [
                    "brev",
                    "search",
                    "gpu",
                    "--gpu-name",
                    "L40S",
                    "--provider",
                    "nebius",
                    "--stoppable",
                    "--min-disk",
                    "500",
                    "--sort",
                    "price",
                    "--json",
                ],
                capture=True,
            ).stdout
        )
        selected = [
            offer
            for offer in offers
            if offer.get("type") == INSTANCE_TYPE
            and offer.get("gpu_count") == 1
            and offer.get("stoppable") is True
            and offer.get("target_disk_gb") == 500
        ]
        if len(selected) != 1:
            raise ValueError(
                "The selected single-L40S, 500 GB offer is unavailable. No fallback was used."
            )
        # Explicit --type loses DiskGB in Brev. JSON input retains target_disk_gb.
        help_text = run(["brev", "create", "--help"], capture=True).stdout
        stdin_flag = ["--stdin"] if "--stdin" in help_text else []
        run(
            [
                "brev",
                "create",
                instance(),
                *stdin_flag,
                "--mode",
                "vm",
                "--jupyter=false",
                "--timeout",
                "1200",
                "--startup-script",
                "@" + str(ROOT / "tools/brev/startup.sh"),
            ],
            input=json.dumps(selected),
        )
    else:
        if record.get("instance_type") != INSTANCE_TYPE:
            raise ValueError(
                "The existing instance is not the selected Nebius L40S type."
            )
        status = str(record.get("status", "")).upper()
        if status in ("STOPPED", "OFF", "PAUSED"):
            run(["brev", "start", instance()])
        elif status != "RUNNING":
            raise ValueError(
                f"Instance state is {status!r}. Inspect it with 'brev ls'."
            )
    run(["brev", "refresh"])
    # SSH readiness is checked separately from the provider's reported state.
    deadline = time.monotonic() + 600
    while True:
        try:
            ssh(
                "command -v git rsync tmux python3 && "
                "nvidia-smi --query-gpu=name,memory.total --format=csv && "
                'docker info >/dev/null && mkdir -p "$HOME/workspace" && df -h "$HOME/workspace"'
            )
            break
        except subprocess.CalledProcessError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(10)
    parent = shlex.quote(str(Path(workspace()).parent))
    capacity = ssh(
        f"mkdir -p {parent} && df -B1 --output=size -- {parent}", capture=True
    ).stdout
    if int(capacity.strip().splitlines()[-1]) < 500_000_000_000:
        raise ValueError(
            "The workspace disk is smaller than 500 GB. Resize it in Brev; no replacement VM was created."
        )


def remote_command(argv, *, terminal=False):
    directory = shlex.quote(workspace())
    return ssh(
        f"cd {directory} && "
        "if [ -f .local-data/brev/env.sh ]; then . .local-data/brev/env.sh; fi && "
        + shlex.join(argv),
        terminal=terminal,
    )


def git_origin(value):
    """Use remote GitHub authentication instead of a client SSH key."""
    if value.startswith("git@github.com:"):
        value = "https://github.com/" + value.split(":", 1)[1]
    parsed = urlsplit(value)
    if parsed.scheme in ("https", "http"):
        if parsed.username or parsed.password:
            raise ValueError("Remove embedded credentials from the Git origin URL.")
        return value
    if value.startswith("git@") and ":" in value:
        return value
    raise ValueError("Use a network Git origin, not a path on the client.")


def install(update=False):
    if run(["git", "status", "--porcelain"], cwd=ROOT, capture=True).stdout:
        raise ValueError("Commit or stash local changes before the first transfer.")
    branch = run(
        ["git", "branch", "--show-current"], cwd=ROOT, capture=True
    ).stdout.strip()
    if not branch:
        raise ValueError("Check out a branch before the first transfer.")
    origin = git_origin(
        run(
            ["git", "remote", "get-url", "origin"], cwd=ROOT, capture=True
        ).stdout.strip()
    )
    target = workspace()
    quoted = shlex.quote(target)
    if update:
        ssh(
            f'test -z "$(git -C {quoted} status --porcelain)" && '
            f'test "$(git -C {quoted} branch --show-current)" = {shlex.quote(branch)}'
        )
    else:
        ssh(f"test ! -e {quoted}")
    with tempfile.TemporaryDirectory() as temporary:
        bundle = Path(temporary) / "repo.bundle"
        run(
            ["git", "bundle", "create", bundle, "HEAD", f"refs/heads/{branch}"],
            cwd=ROOT,
        )
        staging = str(Path(target).parent / (".v2d-transfer-" + uuid.uuid4().hex))
        ssh("mkdir -p " + shlex.quote(staging))
        try:
            run(
                [
                    "rsync",
                    "-a",
                    "--protect-args",
                    str(bundle),
                    instance() + ":" + staging + "/",
                ]
            )
            bundle_path = shlex.quote(staging + "/repo.bundle")
            if update:
                ssh(
                    f'test -z "$(git -C {quoted} status --porcelain)" && '
                    f"git -C {quoted} fetch {bundle_path} {shlex.quote('refs/heads/' + branch)} && "
                    f"git -C {quoted} merge --ff-only FETCH_HEAD"
                )
            else:
                ssh(
                    f"GIT_LFS_SKIP_SMUDGE=1 git clone --branch {shlex.quote(branch)} {bundle_path} {quoted}"
                    f" && git -C {quoted} remote set-url origin {shlex.quote(origin)}"
                )
        finally:
            ssh("rm -rf -- " + shlex.quote(staging))
    git_config()


GIT_PATTERN = r"^(user\.(name|email)|core\.(editor|autocrlf|eol)|init\.defaultbranch|pull\.(rebase|ff)|push\.default|fetch\.prune|alias\..*)$"


def git_settings(raw):
    """Read Git's NUL records without evaluating alias values."""
    return [tuple(record.split("\n", 1)) for record in raw.split("\0") if record]


def git_config():
    result = run(
        ["git", "config", "--null", "--get-regexp", GIT_PATTERN], cwd=ROOT, capture=True
    )
    settings = git_settings(result.stdout)
    target = workspace()
    config = str(Path(target).parent / ".v2d-gitconfig")
    script = "set -eu\numask 077\n"
    temporary = config + ".new"
    script += ": > " + shlex.quote(temporary) + "\n"
    for key, value in settings:
        script += (
            shlex.join(["git", "config", "--file", temporary, "--add", key, value])
            + "\n"
        )
    script += shlex.join(["mv", temporary, config]) + "\n"
    # Include once, and retain existing remote credential configuration.
    script += f"git config --global --get-all include.path | grep -Fx -- {shlex.quote(config)} >/dev/null || "
    script += shlex.join(["git", "config", "--global", "--add", "include.path", config])
    ssh(script)
    print(
        "Git identity and preferences installed. Authenticate GitHub on the remote for push access."
    )


def transfer(direction, source, destination):
    source = remote_path(source)
    destination = remote_path(destination)
    if any(
        part in (".git", ".ssh")
        for part in Path(source).parts + Path(destination).parts
    ):
        raise ValueError("Use Git commands for repository history and credentials.")
    target = workspace()
    flags = [
        "rsync",
        "-a",
        "--partial-dir=.rsync-partial",
        "--protect-args",
        "--safe-links",
        "--ignore-existing",
    ]
    if direction == "push":
        local = (ROOT / source).resolve()
        if not local.is_relative_to(ROOT) or not local.exists():
            raise ValueError("The source must exist inside this checkout.")
        remote = str(Path(target) / destination)
        ssh("mkdir -p " + shlex.quote(remote))
        run(
            [
                *flags,
                str(local) + ("/" if local.is_dir() else ""),
                instance() + ":" + remote + "/",
            ]
        )
    else:
        local = (ROOT / destination).resolve()
        if not local.is_relative_to(ROOT):
            raise ValueError("The destination must be inside this checkout.")
        local.mkdir(parents=True, exist_ok=True)
        run([*flags, instance() + ":" + str(Path(target) / source), str(local) + "/"])


def stop():
    # The CLI can require a terminal for its confirmation prompt.
    run(
        [
            "timeout",
            "180",
            "script",
            "-q",
            "-e",
            "-c",
            shlex.join(["brev", "stop", instance()]),
            "/dev/null",
        ]
    )
    deadline = time.monotonic() + 180
    while True:
        record = listing()
        if record and str(record.get("status", "")).upper() in (
            "STOPPED",
            "OFF",
            "PAUSED",
        ):
            print("The provider reports that the instance is stopped.")
            return
        if time.monotonic() >= deadline:
            raise ValueError(
                "Stop is not confirmed. Check the Brev console for compute charges."
            )
        time.sleep(5)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    for action in (
        "up",
        "status",
        "stop",
        "install",
        "sync-code",
        "git-config",
        "shell",
        "code",
    ):
        sub.add_parser(action)
    command = sub.add_parser("exec")
    command.add_argument(
        "--tty",
        action="store_true",
        help="allocate a terminal for tmux or interactive commands",
    )
    command.add_argument("command", nargs=argparse.REMAINDER)
    for action in ("push", "pull"):
        command = sub.add_parser(action)
        command.add_argument("source")
        command.add_argument("destination")
    command = sub.add_parser("forward")
    command.add_argument("port", type=int)
    command.add_argument("--local-port", type=int)
    args = parser.parse_args(argv)
    if args.action == "up":
        up()
    elif args.action == "status":
        print(json.dumps(listing(), indent=2))
    elif args.action == "stop":
        stop()
    elif args.action == "install":
        install()
    elif args.action == "sync-code":
        install(update=True)
    elif args.action == "git-config":
        git_config()
    elif args.action == "shell":
        remote_command(["bash", "-i"], terminal=True)
    elif args.action == "code":
        run(["brev", "open", instance(), "code", "--dir", workspace()])
    elif args.action in ("push", "pull"):
        transfer(args.action, args.source, args.destination)
    elif args.action == "forward":
        local = args.local_port or args.port
        if not all(0 < port < 65536 for port in (local, args.port)):
            raise ValueError("Use port numbers from 1 to 65535.")
        run(
            [
                "ssh",
                "-o",
                "ExitOnForwardFailure=yes",
                "-N",
                "-L",
                f"127.0.0.1:{local}:127.0.0.1:{args.port}",
                instance(),
            ]
        )
    else:
        command = args.command
        if command[:1] == ["--"]:
            command = command[1:]
        if not command:
            parser.error("Supply a remote command after '--'.")
        remote_command(command, terminal=args.tty)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)
