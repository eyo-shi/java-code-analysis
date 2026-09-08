"""Configuration loaded from CML project environment variables (os.environ)."""

from __future__ import annotations

import json
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

# Defaults aligned with .project-metadata.yaml environment_variables.default.
METADATA_DEFAULTS: dict[str, str] = {
    "GIT_REPO_URL": "https://github.com/terasolunaorg/terasoluna-tourreservation-mybatis3",
    "GIT_REF": "release/5.7.1.SP1.RELEASE",
    "NEO4J_URI": "bolt://localhost:7687",
    "NEO4J_USERNAME": "neo4j",
    "NEO4J_PASSWORD": "Neo4jPass1234",
    "CLONE_DIR": "/tmp/source",
    "EXCLUDE_DIRS": ".git,target,node_modules,venv,.venv,dist,build,__pycache__,.m2",
}


def _coerce_config_value(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, dict):
        for key in ("value", "defaultValue"):
            nested = value.get(key)
            if isinstance(nested, str) and nested.strip():
                return nested.strip()
        target = value.get("target")
        if isinstance(target, dict):
            nested = target.get("value")
            if isinstance(nested, str) and nested.strip():
                return nested.strip()
    return None


def _parse_project_environment(raw: object) -> dict[str, str]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        items = raw.items()
    elif isinstance(raw, str):
        text = raw.strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return {}
        if not isinstance(parsed, dict):
            return {}
        items = parsed.items()
    else:
        return {}

    result: dict[str, str] = {}
    for key, value in items:
        coerced = _coerce_config_value(value)
        if coerced:
            result[str(key)] = coerced
    return result


def _load_project_environment_from_cml() -> dict[str, str]:
    """Return project environment variables stored by CML (Configuration screen)."""
    project_id = os.environ.get("CDSW_PROJECT_ID")
    if not project_id:
        return {}

    try:
        import cmlapi
    except ImportError:
        return {}

    try:
        client = cmlapi.default_client()
        project = client.get_project(project_id)
        project_env = _parse_project_environment(getattr(project, "environment", None))
        for key, value in project_env.items():
            if key in MANAGED_ENV_VARS:
                # Project Settings values are authoritative for AMP Configuration.
                os.environ[key] = value
        return project_env
    except Exception as exc:
        print(f"Warning: could not load CML project environment: {exc}")
        return {}


def _env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is not None:
        stripped = value.strip()
        if stripped:
            return stripped
    if default is not None and default.strip():
        return default.strip()
    metadata_default = METADATA_DEFAULTS.get(name)
    if metadata_default and metadata_default.strip():
        return metadata_default.strip()
    return None


def _resolve_env(name: str, project_env: dict[str, str] | None = None) -> tuple[str | None, str]:
    """Return (value, source)."""
    if project_env and project_env.get(name):
        return project_env[name], "CML project environment"
    raw = os.environ.get(name)
    if raw is not None and str(raw).strip():
        return str(raw).strip(), "os.environ"
    metadata_default = METADATA_DEFAULTS.get(name)
    if metadata_default and metadata_default.strip():
        return metadata_default.strip(), "metadata default"
    return None, "missing"


def _mask_value(name: str, value: str) -> str:
    if name in SENSITIVE_ENV_VARS:
        if len(value) <= 4:
            return "***"
        return f"{value[:3]}...{value[-2:]}"
    return value


def diagnose_environment(project_env: dict[str, str] | None = None) -> None:
    """Print values visible in os.environ for troubleshooting."""
    if project_env is None:
        project_env = _load_project_environment_from_cml()
    print("=== Environment variable diagnostic ===")
    print(
        "AMP Configuration is stored in CML project environment variables "
        "(Project Settings > Advanced) and injected into os.environ at task startup."
    )
    if project_env:
        print(f"CML project environment keys: {sorted(project_env.keys())}")
    for name in MANAGED_ENV_VARS:
        value, source = _resolve_env(name, project_env)
        if value is None:
            print(f"  {name}: MISSING")
            continue
        print(f"  {name}: SET ({_mask_value(name, value)}) [{source}]")
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
        project_env = _load_project_environment_from_cml()

        neo4j_uri = _env("NEO4J_URI")
        if not neo4j_uri:
            diagnose_environment(project_env)
            raise ValueError(
                "NEO4J_URI is required. Set it in AMP Configuration or "
                "Project Settings > Advanced > Environment Variables, then run the "
                "'Analyze and Ingest' AMP task (do not re-run notebook cells manually)."
            )

        source_path = _env("SOURCE_PATH")
        git_repo_url = _env("GIT_REPO_URL")

        if not source_path and not git_repo_url:
            diagnose_environment(project_env)
            raise ValueError(
                "GIT_REPO_URL is required when SOURCE_PATH is not set. Set it in AMP "
                "Configuration or Project Settings > Advanced, then re-run the AMP task."
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
            git_ref=_env("GIT_REF") or METADATA_DEFAULTS["GIT_REF"],
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
        ]
        if self.source_path:
            lines.append(f"source_path={self.source_path}")
        else:
            lines.append(f"git_repo_url={self.git_repo_url}")
        return ", ".join(lines)
