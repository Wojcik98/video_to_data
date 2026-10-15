# Brev deployment design

The user approved this design in chat on 2026-10-15. The user also requested
commits after each logical group of changes, on `main`.

## Required behavior

- Use one stoppable Nebius L40S VM with at least 500 GB of disk.
- Create or resume a named VM. Refresh SSH and verify the resulting state.
- Upload a small startup script. Run repository setup as a separate logged job.
- Transfer the selected Git revision, including commits that are not pushed.
- Keep code and data in the remote user's persistent `workspace` directory.
- Download the HF `nvidia/video_to_data_challenge` Track 3 files into
  `.local-data/track_3`, including `public` and `evaluation`.
- Keep reconstruction ML dependencies inside Docker. Use existing package
  scripts for installs, builds, and model downloads.
- Run long commands in named `tmux` sessions. Retain logs and exit status.
- Support SSH, VS Code, browser tunnels, and file transfers from a second client.
- Document optional Isaac Sim streaming over a private VPN.
- Transfer selected local Git preferences without copying credentials or keys.
- Support private GHCR images and private HF artifact repositories by default.
- Store image digests and artifact checksums. Do not change visibility on failure.
- Add a root `justfile` that forwards arguments to the existing launchers.

## Boundaries

Implementation and CPU verification are authorized. Creating a paid VM, running
GPU jobs, publishing images, and uploading user data are commands for the user to
run. This change does not execute those operations.

Connection loss must not stop a detached job. A VM stop or reboot does stop jobs;
application checkpoints are required for recovery. A registry is for replacement
VMs, since Docker images persist across normal Brev stop and resume.

## Verification

Use offline tests for lifecycle decisions, quoting, transfer boundaries, job exit
status, private HF behavior, image digest validation, and E2E setup without builds.
Run the existing root E2E suite and repository hygiene checks. Report cloud,
registry, model, and streaming checks as unrun until there is live evidence.
