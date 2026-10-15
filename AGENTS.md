# AGENTS.md

Video to Data (V2D) is a monorepo. It turns human demonstration videos into simulation-ready assets and robot training data. It holds three **self-contained** subprojects plus a root E2E launcher. `AGENTS.md` is the single source of agent instructions for both Claude Code and Codex. Each `CLAUDE.md` is a one-line `@AGENTS.md` import shim, so never put content in it. Each subproject has its own `AGENTS.md`, README, pyproject or Docker setup, `.gitignore`, and `.pre-commit-config.yaml`. **Read the subproject's `AGENTS.md` before working in it**, because it is the authoritative guide for that package.

| Path | What it is | Runtime | Agent guide |
| --- | --- | --- | --- |
| `video_ingestion_agent/` | Video → action segments, entity graph (`graph.db`), embeddings (`vector.db`), and NL retrieval (LangGraph + vLLM) | `uv` venv, `src/` layout | `video_ingestion_agent/AGENTS.md` |
| `reconstruction/` | Video/rosbag → depth, masks, meshes, 6-DoF poses, SMPL. Uses ~35 `modules/v2d_*` modules plus `v2d_pipelines` | Thin host wrappers that `docker run` per-module images | `reconstruction/AGENTS.md` |
| `robotic_grounding/` | Retargeting to Sharpa/Dex3/G1, plus RL in Isaac Lab 2.3.1 (RSL-RL). Also contains `flash_chord/` (Newton/Warp/JAX) and `groot_finetune/` | Docker; run code **inside** the container and git **on the host** | `robotic_grounding/AGENTS.md` |
| `tools/e2e/`, `run_e2e.sh` | Reconstruction → retarget → expert → GR00T E2E orchestrator (state in `.e2e/`) | Host Python | `docs/e2e_workflow.md` |
| `docs/` | GitHub Pages site (CHORD page, V2D challenge, leaderboard JS) | Static HTML | — |

## Rules

- **Never install CUDA or PyTorch on the host for reconstruction.** Model dependencies live in each module's Docker image. Modules pass typed `v2d_common` dataclasses and exchange data as files on disk, never raw arrays across package boundaries.
- **Keep package-specific rules out of root files.** CI (`.github/scripts/check_root_files.py`) fails if the root `.gitignore` or `.gitattributes` contains `video_ingestion_agent/`, `reconstruction/` or `robotic_grounding/` patterns. It also fails if a root `.pre-commit-config.yaml` or `.envrc` exists. Put such rules in the subproject's own copy.
- Never gitignore `CLAUDE.md` or `AGENTS.md` at the root (`agent_context_check.py` enforces this).
- Workflow skills cover onboard, run and doctor for ingestion, HOI/ego reconstruction, mesh-to-USD, robotic grounding and Sharpa datagen. Prefer a matching skill over improvising commands. Claude Code's set is in `.claude/skills/`. Codex has a smaller, partly different set in `.codex/skills/`; it includes `groot-finetune` and `run-mv-hoi-reconstruction` but not the ingestion or robotic_grounding skills. Codex agents can read a `.claude/skills/*/SKILL.md` directly as a runbook.
- Don't duplicate run commands in docs. Link to the package README or `--help`, which are canonical.

## Verifying changes

Run commands from the relevant subproject directory:

```bash
# video_ingestion_agent/
pytest && ruff check . && ruff format . && mypy src/video_ingestion_agent && pre-commit run --all-files

# robotic_grounding/ (inside the container: ./workflow/run.sh exec latest 0 -- <cmd>)
pytest tests/ && pre-commit run --all-files

# reconstruction/: tests are per-module and need Docker plus a GPU, e.g.
python modules/v2d_mesh/docker/build.py && python -m v2d.mesh.docker.run_tests

# repo root: E2E launcher tests (stdlib + numpy)
bash -n run_e2e.sh && python -m unittest -v tools.e2e.tests.test_e2e tools.e2e.tests.test_workflow_run
```

## PRs

- Sign off commits (`git commit -s`, DCO).
- Run `pre-commit` and `pytest` for every package you touched.
- Update the docs (`docs/pages/...` or the package README) for architectural or user-facing changes.
- See `.github/pull_request_template.md`.
- This repo is mirrored to the public `nvidia-isaac/video_to_data` repo via Copybara, so don't commit secrets or internal-only paths.
