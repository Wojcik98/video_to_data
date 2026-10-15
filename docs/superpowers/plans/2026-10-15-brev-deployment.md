# Brev Deployment Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan
> in this chat. Use tests before behavior changes and make signed-off commits.

**Goal:** Prepare a reusable L40S workspace that can be used from several clients.

**Architecture:** Keep local Brev control separate from remote jobs and storage.
Use a small boot script, a repeatable setup script, and standard-library Python
commands. Keep the existing package launchers as the source of run behavior.

**Tech Stack:** Python 3.10+, Bash, just, Brev CLI 0.6.335+, Docker, tmux, HF, GHCR.

**Spec:** `docs/superpowers/specs/2026-10-15-brev-deployment-design.md`.

## Global constraints

- Use `main`; preserve unrelated edits; sign off each commit.
- Use one stoppable Nebius L40S VM with at least 500 GB of disk.
- Keep reconstruction ML dependencies inside Docker.
- Keep secrets and private user paths out of commits.
- Use private storage by default. Never change visibility after a failed upload.
- Do not create paid resources or publish data during local verification.

## Review focus

- Unknown or duplicate Brev state must not create an extra VM.
- Remote edits must survive code transfer attempts.
- Quoted command arguments and file paths must retain their values.
- A failed detached command must have a nonzero saved exit status.
- A registry pull must use the recorded digest, not a mutable tag.

## Task 1: Remote control and jobs

Files: `tools/brev/{common,cli,jobs}.py`, `startup.sh`, `bootstrap.sh`, tests.

- [x] Write failing tests for lifecycle decisions, paths, Git settings, and jobs.
- [x] Run `python3 -m unittest discover -s tools/brev/tests -v`; observed 5 failures.
- [x] Add CLI control, Git bundle transfer, guarded file transfer, and tmux jobs.
- [x] Add startup and setup scripts with logged, repeatable steps.
- [x] Run 10 new tests, 63 root E2E tests, lint, and Bash syntax checks; all pass.

## Task 2: Image and HF storage

Files: `tools/brev/{images,artifacts}.py`, tests, `tools/e2e/{cli,stages}.py`.

- [x] Add tests for digest checks, artifact boundaries, and setup without builds.
- [x] Observe failures for missing storage modules and the missing setup option.
- [x] Add GHCR build/push/pull and private HF upload/download with manifests.
- [x] Add `setup --skip-image-builds` while retaining installs and model downloads.
- [x] Run 18 Brev tests (one opt-in tmux check), the real tmux check, and 65 root
  E2E tests. All executed tests pass. Verify the pinned HF API in a temporary venv.

## Task 3: Commands, guide, and review

Files: root `justfile`, `README.md`, `docs/brev_deployment.md`, CI.

- [ ] Add argument-preserving aliases and a guide for both client and remote use.
- [ ] Cover tmux, second clients, Git auth, HF recovery, and optional streaming.
- [ ] Validate aliases with `just --list`, dry runs, and fake external commands.
- [ ] Run tests, lint, formatting, Bash syntax, and root hygiene checks.
- [ ] Review the complete change with a fresh reviewer. Fix material findings.
- [ ] Commit with `-s`; report exact checks and live checks that were not run.

## Execution record

- Approved scope is recorded in the linked design. The user gave final approval
  and requested implementation and commits on `main`.
- No cloud VM will be created during implementation.
