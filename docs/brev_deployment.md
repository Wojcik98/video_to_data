# Brev L40S workspace

Use this guide to work on one remote VM from several client computers. Code,
data, images, and jobs stay on the VM. A client computer provides SSH, VS Code,
and a browser. It does not need a large GPU.

## Default machine and paths

| Setting | Default |
| --- | --- |
| Instance name | `v2d-l40s` |
| Type | `gpu-l40s-d.1gpu-16vcpu-96gb` |
| Hardware | One L40S, 48 GB VRAM, 16 vCPUs, 96 GB RAM |
| Disk | 500 GB |
| Repository | Remote `$HOME/workspace/video_to_data` |
| Input data | `<repository>/.local-data/track_3` |
| Setup state and job logs | `<repository>/.local-data/brev` |

Run `just brev-offers` to see current prices before creating a VM. Compute and
storage have separate charges. Stop the VM when you do not need compute.
Storage charges continue while the VM is stopped. Restart requires available
capacity for the same type and provider. See [Brev instance lifecycle][lifecycle].

Optional client environment variables:

```bash
export V2D_BREV_NAME=v2d-l40s
# Set this only if the remote checkout uses a different absolute path:
# export V2D_BREV_DIR=/home/ubuntu/workspace/video_to_data
```

The helper reads the remote user's home directory. Do not put a local computer's
home path into `V2D_BREV_DIR`. Use the same instance name on each client.

## First use from this computer

The client needs Brev 0.6.335 or later, `just` 1.36 or later, Python 3.10 or later,
Git, OpenSSH, `rsync`, `script`, and `timeout`. Brev is already configured on the
computer used to prepare this guide. On another computer, use [Brev setup][connect].

From the repository root on the **client**:

```bash
just brev-offers
just brev-up
just brev-install
just brev-shell
```

`brev-up` checks the active organization for the selected name. It resumes a
stopped VM or creates one VM if none exists. It selects only the exact single-L40S
offer with 500 GB. It passes the selected JSON record to Brev so the disk size
is retained. It does not fall back to a different GPU or a larger GPU count.
It then refreshes SSH and checks GPU, Docker, and basic tool access.
It also rejects a workspace filesystem smaller than 500 GB, including when it
reuses an existing VM. It does not replace an undersized VM automatically.

Creation uploads [startup.sh](../tools/brev/startup.sh). This small script installs
Git LFS, GitHub CLI, tmux, rsync, FFmpeg, and basic host tools. Brev supplies the
driver and Docker environment. The script contains no tokens and performs no ML
builds. Resume does not request a new deployment or re-run repository setup.

`brev-install` requires a clean local working tree. It sends a Git bundle for the
current branch, including commits that have not been pushed. It refuses an
existing destination. It sets the remote `origin` and transfers selected Git
preferences. LFS content is fetched during setup; the bundle contains Git history,
not the large LFS objects. Keep unpushed LFS objects on the client until you have
pushed them or transferred the required files separately.
GitHub SSH origin URLs are changed to HTTPS on the remote, so GitHub CLI
authentication works without copying the client's SSH private key.

In the **remote shell**, authenticate GitHub once if the repository or LFS objects
need authentication, or if you want to push commits:

```bash
gh auth login --git-protocol https --scopes read:packages,write:packages
gh auth setup-git
exit
```

Back on the **client**, start the separate setup job:

```bash
just brev-setup setup-1
just brev-logs setup-1
```

Ctrl+C closes the log view. The job continues. Check its result with:

```bash
just brev-job-status setup-1
```

Exit code 0 means the host setup and Track 3 download finished. The setup creates
an isolated host Python environment, installs the existing reconstruction Docker
wrappers and HF tools, and fetches Git LFS objects. It does not install host
PyTorch or CUDA for reconstruction.

The HF download selects `track_3/**` from `nvidia/video_to_data_challenge`. It writes
both `public/` and `evaluation/` under `.local-data/track_3`, with no extra dataset
directory. It resolves the HF revision before downloading and records that SHA
in `.local-data/brev/track3-revision.json`. The complete Track 3 input was about
1.47 GB when checked on 2026-10-15. Evaluation includes the released videos;
this setup does not create unreleased evaluation labels.

If setup fails, fix the reported cause and use a new job name:

```bash
just brev-setup setup-2
```

Install and download commands can run again. Existing files and package caches
are reused. To repeat an exact Track 3 download, set `V2D_TRACK3_REVISION` to the
recorded SHA in a remote shell, then run the setup job there.

## Complete the selected runtime

Open a **remote shell** and activate the prepared host environment:

```bash
cd "$HOME/workspace/video_to_data"
source .local-data/brev/env.sh
just
hf auth login
```

Use an HF token with access to the gated models you need. The shell opened by
`just brev-shell` sources this environment automatically. In a new VS Code
terminal or a plain SSH shell, source it as shown above.

The host/data setup is the first part of runtime preparation. Complete these
package-specific requirements before starting a pipeline:

| Work | Required preparation |
| --- | --- |
| Ego reconstruction | [Ego setup](../reconstruction/docs/ego_e2e_setup.md): model access, weights, and MANO where needed |
| Isaac Lab / retargeting | [Robotic Grounding setup](../robotic_grounding/docs/SETUP.md): assets, MANO, and selected motion input |
| GR00T fine-tuning | [E2E requirements](e2e_workflow.md#requirements) and [Isaac-GR00T installation][groot]: a separate Python 3.10 environment |
| Ingestion | [Ingestion README](../video_ingestion_agent/README.md): its own uv environment and selected model backend |
| FlashCHORD | [FlashCHORD setup](../robotic_grounding/flash_chord/README.md#setup): its separate container |

Place an external Isaac-GR00T checkout at `$HOME/workspace/Isaac-GR00T`, or set
`V2D_GROOT_DIR`. Follow its installation instructions in that directory. The E2E
launcher needs this checkout to support `uv run python`. `just groot ...` runs
commands there. Its ML environment is separate from the reconstruction host
environment. The `uv` tool is included in host setup.

For the first image set, build on the **remote host**:

```bash
just job build-1 just images-build --profile all
just job-logs build-1
just job-status build-1
```

This calls the existing HaMeR-route reconstruction build script, the MANO loader
build, and the Isaac Lab build. It excludes unused reconstruction routes. Use
`--profile ego` or `--profile grounding` to select a smaller set. These profiles
do not include the separate ingestion or FlashCHORD environments.

Follow the [E2E guide](e2e_workflow.md) to initialize a run and provide its task,
MANO directory, and Isaac-GR00T directory. Use `just e2e` in place of `./run_e2e.sh`.
When the images were built or pulled already, add `--skip-image-builds` to E2E
`setup`. This skips builds but retains host installs, model downloads, and container
startup. Run the E2E `doctor` gate before the first GPU job.

Track 3 is raw challenge input. Downloading it does not perform reconstruction,
retargeting, or policy training. Select inputs and tasks through the package
instructions; a runtime setup check is not a task-success result.

## Jobs that survive a dropped connection

Run long commands with the detached job helper. From the **client**:

```bash
just brev-job train-1 just e2e train-expert
just brev-logs train-1
just brev-job-status train-1
```

The example uses the active E2E run. Configure it through the E2E guide first.
From the **remote host**, the equivalent launcher is:

```bash
just job train-2 just e2e train-expert
just job-logs train-2
just job-status train-2
```

Each job gets a unique tmux session and a directory in `.local-data/brev/jobs/`.
`output.log` contains stdout and stderr. `command.json` records the argument list,
working directory, and start time. `exit-code` records the final status. Missing
status plus a missing tmux session is reported as interrupted. An existing job
name is never overwritten: choose a new name for a new attempt.

To enter a running session, use `just brev-attach train-1` on the client, or
`just job-attach train-1` on the remote. Press **Ctrl-b**, then **d** to detach.
Job output goes to the log, so use the log command to read it. A completed job's
tmux session closes; its log and result remain.

For an interactive work session, run this on the **remote**:

```bash
tmux new-session -A -s v2d-work
```

Run commands there, detach, and attach again from another computer. SSH loss and
closing VS Code do not stop tmux jobs. A VM stop, reboot, or deletion does stop
them. Save application checkpoints for restart recovery. The helper does not
automatically restart a training process or restore its in-memory state.

## Work from another computer

Install Brev, authenticate to the same account or an authorized account in the
same organization, and install VS Code with Remote SSH. Then:

```bash
brev refresh
brev shell v2d-l40s
```

Inside the remote, open the same directory and attach to `v2d-work` or inspect the
job logs. To open it directly in VS Code from the second client:

```bash
brev open v2d-l40s code --dir /home/ubuntu/workspace/video_to_data
```

Use the actual path printed on the first connection if the remote user is not
`ubuntu`. If the second client has this setup branch checked out, the same
`just brev-shell`, `just brev-code`, and viewer aliases work there too. There is
no need to run `brev-install` or setup again. Confirm the organization with
`brev org` if the VM is not visible.

Each client opens its own tunnels. Closing a client closes that client's tunnel,
while remote jobs continue. Reopen the tunnel on the new client. HF and registry
authentication stored on the remote does not depend on the first client.

## Git on the remote and code updates

The initial transfer copies the effective local author name, email, aliases,
editor, line-ending settings, and selected pull/push preferences. It writes a
separate Git include file under the remote workspace. It does not copy credential
helpers, access tokens, SSH keys, signing keys, or local include paths. To update
the preferences later, run `just brev-git-config` from the original client.

Commit on the **remote host**, outside the Isaac Lab container:

```bash
git status
git add path/to/changed_file
git commit -s -m "Describe the change"
git push
```

The DCO `-s` flag adds a sign-off; it does not need a signing key. If you also
want cryptographic commit signing, configure a key on the remote separately.
The copied editor is installed by base setup when it is Vim. Configure another
editor if your local setting names software that is absent on the VM.

`just brev-sync-code` sends local commits and fast-forwards the same clean remote
branch. It refuses a dirty or diverged branch. When you commit on the remote,
push and reconcile those commits locally before using this command. It is not
continuous file synchronization. Do not edit the same branch on both machines
at the same time without first exchanging commits.

## Inspect meshes and simulation results

For generated Three.js scenes, start a server on the **remote**. Select the
directory that contains the generated `index.html`:

```bash
just job scene-view just serve .local-data/results/run-1/threejs_scene 8000
```

On either **client**:

```bash
just brev-forward 8000
```

Open [localhost:8000](http://localhost:8000). Use the actual output path reported
by reconstruction. Keep the tunnel command running. Serve only the selected
result directory. The server binds to remote loopback.

`just gallery` serves the existing [retargeting gallery](../robotic_grounding/visualizer/README.md).
Its recordings must first be generated through the package workflow. Forward its
port, normally 8080. The same tunnel method works for Viser and TensorBoard;
use the port printed by the service. Simulation MP4 files can be served from a
selected results directory or downloaded for local playback.

For selected file transfers from the **client**:

```bash
just brev-push .local-data/my-inputs .local-data/inputs/run-1
just brev-pull .local-data/results/run-1 .local-data/from-brev
```

Paths are relative to the repository on each side. A pushed folder copies its
contents into the destination. A pulled folder is placed inside the destination.
Transfers can be repeated after an interruption. Existing destination files are
preserved, including files with the same name. Use a new destination to obtain a
new version. Incomplete transfers stay in a separate `.rsync-partial` directory,
so a retry does not skip an incomplete file at its final path. These commands do
not delete files or overwrite remote code.

### Optional interactive Isaac Sim streaming

Brev SSH tunnels carry TCP. Isaac Sim's WebRTC stream also needs UDP, so a TCP
forward alone is insufficient. The selected offer does not advertise
configurable firewall ports through Brev. Use a private VPN for this optional
route. Browser scenes and MP4 inspection above need no VPN.

Install [Tailscale][tailscale-install] on the VM and each client that will stream.
On the **remote**, after following its Linux installation steps:

```bash
sudo tailscale up
tailscale ip -4
```

Sign in and join the same private network on each client. Test access with
`tailscale ping <remote-tailscale-ip>` from that client. Allow the client to reach
remote TCP 49100 and UDP 47998 through the private network and any host firewall.
Do not expose these ports publicly for this workflow.

Start your Isaac Lab command with its `--livestream 2` option inside the normal
Isaac Lab container. `just grounding exec latest 0 -- ...` forwards a command
to that container. Use the existing package command for your selected task,
motion, and checkpoint, with one rendered environment for the first check.
The container uses host networking, which gives it access to the VPN interface.

Install the [Isaac Sim WebRTC Streaming Client][stream] on the current client.
Use a client version compatible with the container's Isaac Sim version. Connect
to the VM's Tailscale IP. If the stream advertises a different address, set
`--kit_args "--/app/livestream/publicEndpointAddress=<remote-tailscale-ip> --/app/livestream/port=49100"`
on the Isaac Lab command. Check that `--livestream` and `--kit_args` appear in
that command's `--help` before launch.

Only one streaming client can connect to one Isaac Sim process at a time.
Disconnect it on the first computer before connecting from the second. A
[Tailscale relay][tailscale-connections] can work when direct connectivity fails,
but stream latency and throughput can be worse. This route needs a live network
and GPU test; the local CPU checks do not qualify it.

## Reuse images through private GHCR packages

Normal stop and resume retains Docker images. GHCR is useful after deleting or
replacing the VM. First build the required profile through `just images-build`.
This records the Git revision and image IDs. Rebuild if Dockerfiles, dependencies,
or code baked into an image change. A bind-mounted source edit can take effect
without a build where the package supports development mounts.

On the **remote**, log in to GHCR using the GitHub account that owns the packages:

```bash
gh auth token | docker login ghcr.io -u YOUR_GITHUB_NAME --password-stdin
just job publish-1 just images-push --profile all --namespace YOUR_GITHUB_NAME/v2d
just job-logs publish-1
just job-status publish-1
```

Use a token with `read:packages` and `write:packages`. For an organization namespace,
add `--organization` and use an account with the required organization access.
See [GHCR authentication][ghcr].

The helper checks that each local image matches its build record. It refuses an
existing public package unless you pass `--allow-public`. New GHCR packages start
private; the helper checks visibility after publishing as well. It tags images
with the build's Git revision and saves immutable registry digests in
`.local-data/brev/images.lock.json`. Build tags can change; restore uses digests.

Back up this manifest. For example, on the **remote**:

```bash
mkdir -p .local-data/image-catalog
cp .local-data/brev/images.lock.json .local-data/image-catalog/
just job save-images-1 just hf-upload .local-data/image-catalog \
  --repo YOUR_HF_NAME/v2d-results --run image-catalog-1
```

On a replacement VM, complete host setup and HF/GHCR authentication, then:

```bash
just hf-download --repo YOUR_HF_NAME/v2d-results --run image-catalog-1 \
  --destination .local-data/restored-image-catalog
just job pull-images-1 just images-pull .local-data/restored-image-catalog/images.lock.json
```

The pull verifies registry content and restores the local image names expected by
the launchers. Use E2E `setup --skip-image-builds` after pulling. Restore model
weights separately or run the model download steps again.

GHCR currently provides container image storage and bandwidth free of charge,
including private images. This is a current policy, not a permanent guarantee.
It limits individual layers to 10 GB and uploads to ten minutes. An inherited
CUDA/Isaac layer can exceed those limits; a failed push is reported and no
complete image manifest is written. Keep the VM's images until you have confirmed
the upload and a restore. See [billing][ghcr-billing] and [registry limits][ghcr].

## Save and restore results directly through HF

Run these commands on the **remote** after `hf auth login`. Use a token with write
access for uploads. Save a checkpoint and select completed output files first.

```bash
just job backup-1 just hf-upload .local-data/results/run-1 \
  --repo YOUR_HF_NAME/v2d-results --run run-1
just job-status backup-1
```

This creates a private dataset repository if needed. It refuses an existing
public repository unless you explicitly add `--public`. It never makes a
private repository public automatically. Use `--repo-type model` for a model
repository when saving a checkpoint directory.

The helper copies the selected folder to a local snapshot under
`.local-data/brev/uploads/<run-id>`. Allow disk space for this extra copy.
It checks hashes before upload, rejects links and common credential files, and
keeps the snapshot after a failure. Tokens, `.git`, SSH keys, and MANO model files
are not accepted as artifact inputs. Select output folders rather than the whole
checkout or the setup-state directory.

Each run is stored under `runs/<run-id>/`. Its manifest contains file sizes,
SHA-256 hashes, the current source revision, and available image/data provenance.
A completion marker is uploaded last. A completed run ID cannot be overwritten.
An interrupted upload can be retried with the same unchanged source and run ID,
using a new job name. Choose a new run ID if any input file changed. Do not upload
the same run ID concurrently from two processes.

Restore directly onto the **remote**, with no local computer transfer:

```bash
just hf-download --repo YOUR_HF_NAME/v2d-results --run run-1 \
  --destination .local-data/restored/run-1
```

The command resolves the selected HF revision to a SHA, downloads the run into a
temporary directory, requires its completion marker, and verifies every data
file against the manifest. It refuses an existing destination. Add `--revision`
to select a known HF commit. Metadata remains under the restored `_v2d/` directory.
For large downloads, put this command in a `just job` too.

HF currently includes 100 GB of private storage for free accounts. Public storage
is subject to its reuse and storage policies. There is no automatic public
fallback if an upload exceeds a private quota. See [HF storage limits][hf-storage].

## Daily stop and recovery

Before stopping, save checkpoints, commit and push code, and complete HF backups
for outputs that must survive VM deletion or a capacity shortage. Check each
job's result before treating its backup as complete. Then on a **client**:

```bash
just brev-stop
```

This runs the interactive Brev stop command through a terminal and checks the
provider listing until it reports a stopped state. If confirmation fails, inspect
the Brev console; do not assume compute billing stopped. To resume:

```bash
just brev-up
just brev-code
```

Do not repeat installation or image builds after a normal resume. Re-enter the
environment and restart needed containers and applications through their normal
launchers. Applications resume from their own saved checkpoints and E2E state.
Deleting the VM removes its local files and Docker images. This guide provides no
delete alias; use the Brev console after checking your Git, GHCR, and HF backups.

## Local verification

`just test` runs the Brev CPU tests and existing root E2E tests. `just check` runs
the scoped hooks in `tools/brev/pre-commit.yaml`; there is no root pre-commit
configuration. GPU builds, actual HF/GHCR transfers, provider stop/resume, and
WebRTC streaming need separate live verification. Shell syntax and fake-client
tests do not establish that those remote operations succeeded.

[connect]: https://docs.nvidia.com/brev/cli/connectivity
[lifecycle]: https://docs.nvidia.com/brev/concepts/gpu-instances
[groot]: https://github.com/NVIDIA/Isaac-GR00T#installation
[ghcr]: https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry
[ghcr-billing]: https://docs.github.com/en/billing/concepts/product-billing/github-packages
[hf-storage]: https://huggingface.co/docs/hub/storage-limits
[stream]: https://docs.isaacsim.omniverse.nvidia.com/5.1.0/installation/manual_livestream_clients.html
[tailscale-install]: https://tailscale.com/docs/install/linux
[tailscale-connections]: https://tailscale.com/docs/reference/connection-types
