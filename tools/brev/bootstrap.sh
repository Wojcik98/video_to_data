#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Run through the job helper so a client disconnect does not stop setup.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"
STATE_DIR="$REPO_ROOT/.local-data/brev"
mkdir -p "$STATE_DIR"
export PATH="$HOME/.local/bin:$PATH"
nvidia-smi
docker info >/dev/null
git lfs install --local
git lfs pull
if [ ! -x "$STATE_DIR/venv/bin/python" ]; then
    python3 -m venv "$STATE_DIR/venv"
fi
export VIRTUAL_ENV="$STATE_DIR/venv"
export PATH="$VIRTUAL_ENV/bin:$PATH"
export PYTHON="$VIRTUAL_ENV/bin/python"
"$PYTHON" -m pip install --upgrade pip
"$PYTHON" -m pip install 'huggingface_hub>=1,<2' pre-commit
if ! command -v just >/dev/null; then
    # Install a fixed release through the remote Python environment.
    "$PYTHON" -m pip install rust-just==1.36.0
fi
printf 'export VIRTUAL_ENV=%q\nexport PYTHON=%q\nexport PATH=%q:"$PATH"\n' \
    "$VIRTUAL_ENV" "$PYTHON" "$VIRTUAL_ENV/bin:$HOME/.local/bin" > "$STATE_DIR/env.sh"
bash reconstruction/scripts/install_ego_reconstruction_packages.sh
"$PYTHON" -m pip install -e reconstruction/modules/v2d_task_library_loader/docker
DATA_REVISION="${V2D_TRACK3_REVISION:-main}"
DATA_REVISION="$("$PYTHON" -c 'from huggingface_hub import HfApi; import sys; print(HfApi().dataset_info("nvidia/video_to_data_challenge", revision=sys.argv[1]).sha)' "$DATA_REVISION")"
hf download nvidia/video_to_data_challenge --repo-type dataset \
    --revision "$DATA_REVISION" --include 'track_3/**' --local-dir "$REPO_ROOT/.local-data"
test -d .local-data/track_3/public/data
test -d .local-data/track_3/evaluation/videos
"$PYTHON" -c 'import json; from pathlib import Path; import sys; Path(".local-data/brev/track3-revision.json").write_text(json.dumps({"repo": "nvidia/video_to_data_challenge", "revision": sys.argv[1]}, indent=2)+"\n")' "$DATA_REVISION"
echo "Host setup and Track 3 download are complete."
echo "Next: authenticate HF/GHCR as needed, then build or pull images."
echo "Follow docs/brev_deployment.md for model weights, MANO, and Isaac-GR00T setup."
