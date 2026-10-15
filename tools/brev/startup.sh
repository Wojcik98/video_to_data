#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Brev runs this small script when it creates the VM.
set -euo pipefail
if [ "$(id -u)" -eq 0 ]; then
    SUDO=()
else
    SUDO=(sudo -n)
fi
"${SUDO[@]}" apt-get update
"${SUDO[@]}" apt-get install -y git git-lfs rsync tmux python3-venv curl ca-certificates vim
# Create user-owned workspace directories later, through the SSH user.
echo "Base tools are ready. Transfer the repository and run tools/brev/bootstrap.sh."
