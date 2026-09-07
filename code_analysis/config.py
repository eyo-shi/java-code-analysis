"""Configuration loaded from environment variables."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

MANAGED_ENV_VARS: tuple[str, ...] = (
    "GIT_REPO_URL",
    "GIT_REF",
    "NEO4J_URI",
    "NEO4J_USERNAME",
    "NEO4J_PASSWORD",
    "CLONE_DIR",
    "SOURCE_PATH",
    "PROJECT_ID",
    "PROJECT_NAME",
    "EXCLUDE_DIRS",
)

SENSITIVE_ENV_VARS: frozenset[str] = frozenset({"NEO4J_PASSWORD"})

DEFAULT_ENV_VALUES: dict[str, str] = {
    "GIT_REF": "main",
    "NEO4J_USERNAME": "neo4j",
    "NEO4J_PASSWORD": "Neo4jPass1234",
    "CLONE_DIR": "/tmp/source",
    "EXCLUDE_DIRS": ".git,target,node_modules,venv,.venv,dist,build,__pycache__,.m2",
}


def _env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None:
        return default
    stripped = value.strip()
    if not stripped:
        return default
    return stripped


def _mask_value(name: str, value: str) -> str:
    if name in SENSITIVE_ENV_VARS:
        if len(value) <= 4:
            return "***"
        return f"{value[:3]}...{value[-2:]}"
    return value


def hydrate_environment_from_cml() -> int:
    """Load missing variables from CML project settings via API."""
    project_id = os.environ.get("CDSW_PROJECT_ID")
    if not project_id:
        return 0

    try:
        import cmlapi
    except ImportError:
        return 0

    try:
        client = cmlapi.default_client()
        project = client.get_project(project_id)
        project_env = getattr(project, "environment", None) or {}
        loaded = 0
        for key, value in project_env.items():
            if value is None:
                continue
            text = str(value).strip()
            if not text:
                continue
            current = os.environ.get(key)
            if current is None or not str(current).strip():
                os.environ[key] = text
                loaded += 1
        return loaded
    except Exception as exc:
        print(f"Warning: could not load CML project environment: {exc}")
        return 0


def diagnose_environment() -> None:
    """Print whether each managed variable is visible to the process."""
    print("=== Environment variable diagnostic ===")
    loaded = hydrate_environment_from_cml()
    if loaded:
        print(f"Loaded {loaded} variable(s) from CML project settings (Project Settings > Advanced).")

    for name in MANAGED_ENV_VARS:
        raw = os.environ.get(name)
        if raw is None or not str(raw).strip():
            default = DEFAULT_ENV_VALUES.get(name)
            if default is not None:
                print(f"  {name}: MISSING (will use default: {default})")
            else:
                print(f"  {name}: MISSING")
            continue
        print(f"  {name}: SET ({_mask_value(name, raw)})")

    cml_project_id = os.environ.get("CDSW_PROJECT_ID")
    print(f"  CDSW_PROJECT_ID: {cml_project_id or 'MISSING (not running inside CML)'}")
    print("========================================")


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
        hydrate_environment_from_cml()

        neo4j_uri = _env("NEO4J_URI")
        if not neo4j_uri:
            diagnose_environment()
            raise ValueError(
                "NEO4J_URI is required. Set it in AMP Deploy Configuration or "
                "Project Settings > Advanced > Environment Variables, then restart the session."
            )

        source_path = _env("SOURCE_PATH")
        git_repo_url = _env("GIT_REPO_URL")

        if not source_path and not git_repo_url:
            diagnose_environment()
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
