"""Run remote commands in tmux and save their results."""

import argparse
import datetime
import json
import shlex
import subprocess
import sys

from .common import ROOT, STATE, name, run, write_json


def job_directory(job_name):
    return STATE / "jobs" / name(job_name)


def run_job(directory, argv, cwd):
    """Save output and the exit code, including a launch failure."""
    directory.mkdir(parents=True, exist_ok=True)
    write_json(
        directory / "command.json",
        {
            "argv": argv,
            "cwd": str(cwd),
            "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        },
    )
    (directory / "exit-code").unlink(missing_ok=True)
    with (directory / "output.log").open("w") as output:
        try:
            result = subprocess.run(
                argv, cwd=cwd, stdout=output, stderr=subprocess.STDOUT
            )
            code = result.returncode
            if code < 0:
                code = 128 - code
        except OSError as error:
            output.write(str(error) + "\n")
            code = 127
    (directory / "exit-code").write_text(f"{code}\n")
    return code


def start(job_name, argv):
    directory = job_directory(job_name)
    # Keep old output until the user selects a new job name.
    directory.parent.mkdir(parents=True, exist_ok=True)
    directory.mkdir()
    write_json(directory / "request.json", {"argv": argv})
    command = shlex.join(
        [
            sys.executable,
            "-m",
            "tools.brev.jobs",
            "run",
            job_name,
        ]
    )
    environment = STATE / "env.sh"
    command = (
        f"if [ -f {shlex.quote(str(environment))} ]; then . {shlex.quote(str(environment))}; fi; exec "
        + command
    )
    try:
        run(
            [
                "tmux",
                "new-session",
                "-d",
                "-s",
                f"v2d-{job_name}",
                "-c",
                ROOT,
                shlex.join(["bash", "-c", command]),
            ]
        )
    except (OSError, subprocess.CalledProcessError):
        (directory / "exit-code").write_text("127\n")
        raise
    print(f"Job: {job_name}\nLog: {directory / 'output.log'}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    for action in ("start", "run", "attach", "status", "logs"):
        command = sub.add_parser(action)
        command.add_argument("name")
        if action == "start":
            command.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    directory = job_directory(args.name)
    if args.action == "start":
        command = args.command
        if command[:1] == ["--"]:
            command = command[1:]
        if not command:
            parser.error("Supply a command after '--'.")
        start(args.name, command)
    elif args.action == "run":
        request = json.loads((directory / "request.json").read_text())
        return run_job(directory, request["argv"], ROOT)
    elif args.action == "attach":
        run(["tmux", "attach-session", "-t", f"v2d-{args.name}"])
    elif args.action == "logs":
        run(["tail", "-n", "80", "-F", directory / "output.log"])
    else:
        if not directory.is_dir():
            raise ValueError("This job does not exist.")
        result = directory / "exit-code"
        if result.exists():
            code = int(result.read_text())
            print(f"Finished: exit code {code}")
            return code
        alive = subprocess.run(
            ["tmux", "has-session", "-t", f"v2d-{args.name}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if alive.returncode:
            print("Interrupted: no session and no saved exit code.")
            return 1
        print("Running")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)
