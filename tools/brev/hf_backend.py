"""HF operations. Run with the Python environment made by bootstrap.sh."""

import io
import json
import sys
from pathlib import Path

from huggingface_hub import HfApi, hf_hub_download, snapshot_download

from .artifacts import check_visibility, checksum


def main():
    action, repo, repo_type, run_id, directory, option = sys.argv[1:]
    api = HfApi()
    prefix = f"runs/{run_id}"
    if action == "download":
        revision = api.repo_info(repo, repo_type=repo_type, revision=option).sha
        snapshot_download(
            repo_id=repo,
            repo_type=repo_type,
            revision=revision,
            allow_patterns=[prefix + "/**"],
            local_dir=directory,
        )
        print(f"HF source revision: {revision}")
        return
    public = option == "public"
    api.create_repo(repo, repo_type=repo_type, private=not public, exist_ok=True)
    check_visibility(
        is_private=api.repo_info(repo, repo_type=repo_type).private, allow_public=public
    )
    staging = Path(directory)
    manifest_hash = checksum(staging / "_v2d/manifest.json")
    files = set(api.list_repo_files(repo, repo_type=repo_type))
    marker = prefix + "/_v2d/complete.json"
    if marker in files:
        raise ValueError("This run ID is already complete. Use a new run ID.")
    # Resume only a partial upload with the exact same manifest.
    remote_manifest = prefix + "/_v2d/manifest.json"
    if any(path.startswith(prefix + "/") for path in files):
        if remote_manifest not in files:
            raise ValueError("A different partial upload uses this run ID.")
        previous = Path(hf_hub_download(repo, remote_manifest, repo_type=repo_type))
        if checksum(previous) != manifest_hash:
            raise ValueError("A different upload uses this run ID.")
    # Upload the manifest first so an interrupted transfer has an identity.
    api.upload_file(
        path_or_fileobj=str(staging / "_v2d/manifest.json"),
        path_in_repo=remote_manifest,
        repo_id=repo,
        repo_type=repo_type,
    )
    api.upload_folder(
        repo_id=repo, repo_type=repo_type, folder_path=str(staging), path_in_repo=prefix
    )
    result = api.upload_file(
        path_or_fileobj=io.BytesIO(
            json.dumps(
                {
                    "manifest_sha256": manifest_hash,
                }
            ).encode()
        ),
        path_in_repo=marker,
        repo_id=repo,
        repo_type=repo_type,
    )
    print(f"HF completed revision: {result.oid}")


if __name__ == "__main__":
    main()
