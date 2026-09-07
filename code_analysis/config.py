"""Configuration loaded from environment variables."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


def _env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None:
        return default
    stripped = value.strip()
    if not stripped:
        return default
    return stripped


def derive_project_id(repo_url: str) -> str:
    """Derive a stable project id from a git repository URL."""
    parsed = urlparse(repo_url)
    path = parsed.path.rstrip("/")
    if path.endswith(".git"):
        path = path[:-4]
    name = path.split("/")[-1] if path else repo_url
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-")
    return normalized or "java-project"


def derive_project_name(repo_url: str) -> str:
    project_id = derive_project_id(repo_url)
    return project_id.replace("-", " ").replace("_", " ").title()


@dataclass
class Config:
    neo4j_uri: str
    neo4j_username: str
    neo4j_password: str
    git_repo_url: str | None
    git_ref: str
    clone_dir: str
    source_path: str | None
    project_id: str
    project_name: str
    exclude_dirs: tuple[str, ...]

    @classmethod
    def from_env(cls) -> Config:
        neo4j_uri = _env("NEO4J_URI")
        if not neo4j_uri:
            raise ValueError("NEO4J_URI is required")

        source_path = _env("SOURCE_PATH")
        git_repo_url = _env("GIT_REPO_URL")

        if not source_path and not git_repo_url:
            raise ValueError(
                "GIT_REPO_URL is required when SOURCE_PATH is not set. "
                "Set GIT_REPO_URL in CML Configuration to the repository to analyze."
            )

        if git_repo_url:
            default_id = derive_project_id(git_repo_url)
            default_name = derive_project_name(git_repo_url)
        else:
            default_id = Path(source_path).name
            default_name = derive_project_name(default_id)

        project_id = _env("PROJECT_ID") or default_id
        project_name = _env("PROJECT_NAME") or default_name

        return cls(
            neo4j_uri=neo4j_uri,
            neo4j_username=_env("NEO4J_USERNAME", "neo4j") or "neo4j",
            neo4j_password=_env("NEO4J_PASSWORD", "Neo4jPass1234") or "Neo4jPass1234",
            git_repo_url=git_repo_url,
            git_ref=_env("GIT_REF", "main") or "main",
            clone_dir=_env("CLONE_DIR", "/tmp/source") or "/tmp/source",
            source_path=source_path,
            project_id=project_id,
            project_name=project_name,
            exclude_dirs=tuple(
                part.strip()
                for part in (
                    _env(
                        "EXCLUDE_DIRS",
                        ".git,target,node_modules,venv,.venv,dist,build,__pycache__,.m2",
                    )
                    or ".git,target,node_modules,venv,.venv,dist,build,__pycache__,.m2"
                ).split(",")
                if part.strip()
            ),
        )

    def log_summary(self) -> str:
        lines = [
            f"project_id={self.project_id}",
            f"project_name={self.project_name}",
            f"git_ref={self.git_ref}",
        ]
        if self.source_path:
            lines.append(f"source_path={self.source_path}")
        else:
            lines.append(f"git_repo_url={self.git_repo_url}")
        return ", ".join(lines)
