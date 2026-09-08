"""Configuration loaded from CML project environment variables (os.environ)."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

# Keys defined in .project-metadata.yaml environment_variables.
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

# Defaults aligned with .project-metadata.yaml (local development fallback only).
METADATA_DEFAULTS: dict[str, str] = {
    "GIT_REPO_URL": "https://github.com/terasolunaorg/terasoluna-tourreservation-mybatis3",
    "GIT_REF": "release/5.7.1.SP1.RELEASE",
    "NEO4J_USERNAME": "neo4j",
    "NEO4J_PASSWORD": "Neo4jPass1234",
    "CLONE_DIR": "/tmp/source",
    "EXCLUDE_DIRS": ".git,target,node_modules,venv,.venv,dist,build,__pycache__,.m2",
}

_CORRUPTED_MARKERS = ("dispatchConfig", "_dispatchListeners", "nativeEvent", "isTrusted")


def _in_cml_runtime() -> bool:
    return bool(os.environ.get("CDSW_PROJECT_ID"))


def _looks_corrupted(value: str) -> bool:
    text = value.strip()
    if not text:
        return False
    if any(marker in text for marker in _CORRUPTED_MARKERS):
        return True
    return text.startswith("{") and "}" in text


def _validate_env_value(name: str, value: str) -> bool:
    if name == "GIT_REPO_URL":
        return value.startswith(("http://", "https://", "git@"))
    if name == "NEO4J_URI":
        return value.startswith(("bolt://", "neo4j://", "neo4j+s://", "neo4j+ssc://"))
    if name == "GIT_REF":
        return not _looks_corrupted(value) and len(value) <= 256
    if name == "SOURCE_PATH":
        return not _looks_corrupted(value)
    return not _looks_corrupted(value) or name == "EXCLUDE_DIRS"


def _normalize_env_value(name: str, value: str) -> str:
    text = value.strip()
    if name == "NEO4J_URI" and "://" not in text:
        text = f"bolt://{text}"
    return text


def _env(name: str, default: str | None = None) -> str | None:
    """Read a managed environment variable from os.environ."""
    raw = os.environ.get(name)
    if raw is not None:
        text = raw.strip()
        if text:
            if _looks_corrupted(text):
                print(
                    f"Warning: ignoring corrupted {name} in os.environ "
                    "(React event object; set a plain string in "
                    "Project Settings > Advanced > Environment Variables)."
                )
                return default
            normalized = _normalize_env_value(name, text)
            if _validate_env_value(name, normalized):
                return normalized
            print(f"Warning: ignoring invalid {name} in os.environ.")
            return default

    if default is not None and default.strip():
        return default.strip()

    if not _in_cml_runtime():
        metadata_default = METADATA_DEFAULTS.get(name)
        if metadata_default and metadata_default.strip():
            return metadata_default.strip()
    return None


def _mask_value(name: str, value: str) -> str:
    if name in SENSITIVE_ENV_VARS:
        if len(value) <= 4:
            return "***"
        return f"{value[:3]}...{value[-2:]}"
    return value


def diagnose_environment() -> None:
    """Print managed environment variables visible in os.environ."""
    print("=== Environment variable diagnostic ===")
    print(
        "AMP Configuration values are stored as CML project environment variables "
        "and injected into os.environ at task startup "
        "(Project Settings > Advanced > Environment Variables)."
    )
    for name in MANAGED_ENV_VARS:
        raw = os.environ.get(name)
        if raw is None or not str(raw).strip():
            print(f"  {name}: MISSING in os.environ")
            continue
        if _looks_corrupted(str(raw)):
            print(f"  {name}: CORRUPTED (React event object in os.environ)")
            continue
        resolved = _env(name)
        if resolved is None:
            print(f"  {name}: INVALID in os.environ ({_mask_value(name, str(raw).strip())})")
            continue
        print(f"  {name}: SET ({_mask_value(name, resolved)}) [os.environ]")
    print(f"  CDSW_PROJECT_ID: {os.environ.get('CDSW_PROJECT_ID', 'MISSING')}")
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
        diagnose_environment()

        neo4j_uri = _env("NEO4J_URI")
        if not neo4j_uri:
            raise ValueError(
                "NEO4J_URI is required in os.environ. Set it in "
                "Project Settings > Advanced > Environment Variables, then run the "
                "'Analyze and Ingest' AMP task (do not re-run notebook cells manually)."
            )

        source_path = _env("SOURCE_PATH")
        git_repo_url = _env("GIT_REPO_URL")

        if not source_path and not git_repo_url:
            raise ValueError(
                "GIT_REPO_URL is required when SOURCE_PATH is not set. Set it in "
                "Project Settings > Advanced > Environment Variables."
            )

        if git_repo_url:
            default_id = derive_project_id(git_repo_url)
            default_name = derive_project_name(git_repo_url)
        else:
            default_id = Path(source_path).name
            default_name = derive_project_name(default_id)

        return cls(
            neo4j_uri=neo4j_uri,
            neo4j_username=_env("NEO4J_USERNAME", "neo4j") or "neo4j",
            neo4j_password=_env("NEO4J_PASSWORD", "Neo4jPass1234") or "Neo4jPass1234",
            git_repo_url=git_repo_url,
            git_ref=_env("GIT_REF", METADATA_DEFAULTS["GIT_REF"]) or METADATA_DEFAULTS["GIT_REF"],
            clone_dir=_env("CLONE_DIR", "/tmp/source") or "/tmp/source",
            source_path=source_path,
            project_id=_env("PROJECT_ID") or default_id,
            project_name=_env("PROJECT_NAME") or default_name,
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

    def validate_for_ingest(self) -> None:
        if not self.neo4j_uri:
            raise ValueError("NEO4J_URI is required")
        if not self.source_path and not self.git_repo_url:
            raise ValueError("GIT_REPO_URL is required when SOURCE_PATH is not set")
        if not self.source_path and not self.git_ref:
            raise ValueError("GIT_REF is required when cloning from GIT_REPO_URL")

    def log_summary(self) -> str:
        lines = [
            f"project_id={self.project_id}",
            f"project_name={self.project_name}",
            f"git_ref={self.git_ref}",
            f"neo4j_uri={self.neo4j_uri}",
        ]
        if self.source_path:
            lines.append(f"source_path={self.source_path}")
        else:
            lines.append(f"git_repo_url={self.git_repo_url}")
        return ", ".join(lines)
