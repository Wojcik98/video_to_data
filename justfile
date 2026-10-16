# Run `just` to list the commands. Run package commands from the remote host.
set shell := ["bash", "-cu"]
set positional-arguments

default:
    @just --list

# Forward all arguments to the E2E launcher.
e2e *args:
    @bash run_e2e.sh "$@"

# Control the Isaac Lab container: build, start, shell, exec, or stop.
grounding *args:
    @cd robotic_grounding && bash workflow/run.sh "$@"

# Run the retarget pipeline from the host.
retarget *args:
    @cd robotic_grounding && "${PYTHON:-python3}" scripts/run_pipeline_docker.py "$@"

# Run a reconstruction host module: for example, `just reconstruction -m v2d.moge.docker.run_video_to_depth --help`.
reconstruction +args:
    @cd reconstruction && "${PYTHON:-python3}" "$@"

# Run an ingestion command in its own uv environment.
ingestion +args:
    @cd video_ingestion_agent && uv run "$@"

# Control the separate FlashCHORD container.
flash-chord *args:
    @cd robotic_grounding/flash_chord && bash docker/run.sh "$@"

# Run a command in the external Isaac-GR00T uv environment.
groot +args:
    @cd "${V2D_GROOT_DIR:-$HOME/workspace/Isaac-GR00T}" && uv run "$@"

# Show current L40S offers with the required disk size.
brev-offers:
    @brev search gpu --gpu-name L40S --stoppable --min-disk 500 --sort price --wide

# Create or resume the configured L40S VM and check SSH/GPU/Docker access.
brev-up:
    @"${PYTHON:-python3}" -m tools.brev.cli up

# Show provider state for this instance.
brev-status:
    @"${PYTHON:-python3}" -m tools.brev.cli status

# Stop compute and check the provider's resulting state. Files remain on the VM.
brev-stop:
    @"${PYTHON:-python3}" -m tools.brev.cli stop

# Transfer the current committed branch into a new remote repository.
brev-install:
    @"${PYTHON:-python3}" -m tools.brev.cli install

# Fast-forward a clean remote branch with local commits. Refuse divergence.
brev-sync-code:
    @"${PYTHON:-python3}" -m tools.brev.cli sync-code

# Transfer selected local Git preferences. Keep remote credentials separate.
brev-git-config:
    @"${PYTHON:-python3}" -m tools.brev.cli git-config

# Start host package setup and the Track 3 download in a detached remote job.
brev-setup name='setup-1':
    @"${PYTHON:-python3}" -m tools.brev.cli exec -- python3 -m tools.brev.jobs start "$1" -- bash tools/brev/bootstrap.sh

# Open an interactive remote shell in the repository.
brev-shell:
    @"${PYTHON:-python3}" -m tools.brev.cli shell

# Open the remote repository in local VS Code with Remote SSH.
brev-code:
    @"${PYTHON:-python3}" -m tools.brev.cli code

# Run a short remote command. Use brev-job for long commands.
brev-exec +command:
    @"${PYTHON:-python3}" -m tools.brev.cli exec -- "$@"

# Run a remote command in a named detached tmux job.
brev-job name +command:
    @"${PYTHON:-python3}" -m tools.brev.cli exec -- python3 -m tools.brev.jobs start "$@"

# Reconnect to a remote job while it is running.
brev-attach name:
    @"${PYTHON:-python3}" -m tools.brev.cli exec --tty -- python3 -m tools.brev.jobs attach "$1"

# Follow a remote log. Ctrl+C stops this log view, not the job.
brev-logs name:
    @"${PYTHON:-python3}" -m tools.brev.cli exec -- python3 -m tools.brev.jobs logs "$1"

# Show a remote job result. Return its saved exit code.
brev-job-status name:
    @"${PYTHON:-python3}" -m tools.brev.cli exec -- python3 -m tools.brev.jobs status "$1"

# Copy selected local files to a remote directory. Preserve existing files.
brev-push source destination:
    @"${PYTHON:-python3}" -m tools.brev.cli push "$@"

# Download selected remote files to a local directory. Preserve existing files.
brev-pull source destination:
    @"${PYTHON:-python3}" -m tools.brev.cli pull "$@"

# Forward one remote TCP port to localhost. Keep this command running.
brev-forward port *args:
    @"${PYTHON:-python3}" -m tools.brev.cli forward "$@"

# Start a detached job on the current host.
job name +command:
    @"${PYTHON:-python3}" -m tools.brev.jobs start "$@"

# Follow a job log on the current host.
job-logs name:
    @"${PYTHON:-python3}" -m tools.brev.jobs logs "$1"

# Show a saved job result on the current host.
job-status name:
    @"${PYTHON:-python3}" -m tools.brev.jobs status "$1"

# Attach to a running job on the current host.
job-attach name:
    @"${PYTHON:-python3}" -m tools.brev.jobs attach "$1"

# Build the E2E images with the canonical package scripts.
images-build *args:
    @"${PYTHON:-python3}" -m tools.brev.images build "$@"

# Upload built images to GHCR and write a manifest with their digests.
images-push +args:
    @"${PYTHON:-python3}" -m tools.brev.images push "$@"

# Restore images by digest and give them the local names used by the launchers.
images-pull manifest:
    @"${PYTHON:-python3}" -m tools.brev.images pull "$1"

# Save a selected result folder directly to HF. Default visibility is private.
hf-upload +args:
    @"${PYTHON:-python3}" -m tools.brev.artifacts upload "$@"

# Restore an HF result folder to a new path and verify checksums.
hf-download +args:
    @"${PYTHON:-python3}" -m tools.brev.artifacts download "$@"

# Serve a generated Three.js scene or result folder on the current host.
serve directory port='8000':
    @"${PYTHON:-python3}" -m http.server "$2" --bind 127.0.0.1 --directory "$1"

# Serve the existing retargeting gallery on the current host.
gallery *args:
    @"${PYTHON:-python3}" robotic_grounding/visualizer/serve.py --host 127.0.0.1 "$@"

# Run root CPU tests. This does not qualify Docker or GPU execution.
test:
    @"${PYTHON:-python3}" -m unittest discover -s tools/brev/tests -v
    @"${PYTHON:-python3}" -m unittest -v tools.e2e.tests.test_e2e tools.e2e.tests.test_workflow_run

# Run the scoped hooks; install pre-commit and ruff in the active environment.
check:
    @pre-commit run --config tools/brev/pre-commit.yaml --all-files
