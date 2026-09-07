"""Fetch source code via git clone or an existing path."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def resolve_source_path(
    source_path: str | None,
    git_repo_url: str | None,
    git_ref: str,
    clone_dir: str,
) -> Path:
    if source_path:
        path = Path(source_path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"SOURCE_PATH does not exist: {path}")
        print(f"Using existing source path: {path}")
        return path

    if not git_repo_url:
        raise ValueError("GIT_REPO_URL is required when SOURCE_PATH is not set")

    target = Path(clone_dir).resolve()
    if target.exists():
        shutil.rmtree(target)

    print(f"Cloning {git_repo_url} (ref={git_ref}) into {target}")
    subprocess.run(
        [
            "git",
            "clone",
            "--depth",
            "1",
            "--branch",
            git_ref,
            git_repo_url,
            str(target),
        ],
        check=True,
    )
    return target
