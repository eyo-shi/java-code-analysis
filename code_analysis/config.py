"""Configuration loaded from environment variables."""

from __future__ import annotations

import json
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

SNAPSHOT_FILENAME = ".cml-project-env.json"


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


def _parse_project_environment(raw: object) -> dict[str, str]:
    """Normalize CML project.environment which may be a dict or JSON string."""
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return {str(key): str(value) for key, value in raw.items() if value is not None}

    if not isinstance(raw, str):
        return {}

    text = raw.strip()
    if not text:
        return {}

    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return {str(key): str(value) for key, value in parsed.items() if value is not None}
    except json.JSONDecodeError:
        pass

    result: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if key:
            result[key] = value
    return result


def _sanitize_empty_managed_env() -> None:
    """Remove empty placeholders CML may inject for unset AMP configuration fields."""
    for key in MANAGED_ENV_VARS:
        value = os.environ.get(key)
        if value is not None and not str(value).strip():
            os.environ.pop(key, None)


def hydrate_environment_from_cml() -> int:
    """Load variables from CML project settings via API."""
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
        project_env = _parse_project_environment(getattr(project, "environment", None))
        if not project_env:
            print("CML project settings contain no deploy configuration environment variables.")
            return 0

        loaded = 0
        for key, value in project_env.items():
            if key not in MANAGED_ENV_VARS:
                continue
            text = str(value).strip()
            if not text:
                continue
            # Deploy Configuration in project settings is authoritative in CML.
            os.environ[key] = text
            loaded += 1
        return loaded
    except Exception as exc:
        print(f"Warning: could not load CML project environment: {exc}")
        return 0


def _snapshot_paths() -> list[Path]:
    candidates = [Path.cwd() / SNAPSHOT_FILENAME]
    parent = Path.cwd().parent
    if parent != Path.cwd():
        candidates.append(parent / SNAPSHOT_FILENAME)
    return candidates


def load_environment_snapshot() -> int:
    """Load variables saved during AMP install from a local snapshot file."""
    loaded = 0
    for path in _snapshot_paths():
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"Warning: could not read environment snapshot {path}: {exc}")
            continue
        if not isinstance(data, dict):
            continue
        for key, value in data.items():
            if key not in MANAGED_ENV_VARS or value is None:
                continue
            text = str(value).strip()
            if not text:
                continue
            current = os.environ.get(key)
            if current is None or not str(current).strip():
                os.environ[key] = text
                loaded += 1
        break
    return loaded


def save_environment_snapshot() -> Path | None:
    """Persist managed environment variables for later sessions."""
    values = {
        key: os.environ[key]
        for key in MANAGED_ENV_VARS
        if os.environ.get(key) and str(os.environ[key]).strip()
    }
    if not values:
        return None
    path = Path.cwd() / SNAPSHOT_FILENAME
    path.write_text(json.dumps(values, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def hydrate_environment() -> int:
    """Load deploy configuration from CML project settings and local snapshot."""
    _sanitize_empty_managed_env()
    loaded = hydrate_environment_from_cml()
    loaded += load_environment_snapshot()
    return loaded


def bootstrap_deploy_configuration() -> dict[str, int | bool]:
    """Load deploy configuration and persist a snapshot for later sessions."""
    _sanitize_empty_managed_env()
    from_cml = hydrate_environment_from_cml()
    from_snapshot = load_environment_snapshot()
    snapshot_path = save_environment_snapshot()
    return {
        "from_cml_api": from_cml,
        "from_snapshot": from_snapshot,
        "snapshot_saved": snapshot_path is not None,
    }


def diagnose_environment() -> None:
    """Print whether each managed variable is visible to the process."""
    print("=== Environment variable diagnostic ===")
    loaded = hydrate_environment()
    if loaded:
        print(f"Loaded {loaded} variable(s) from CML project settings or local snapshot.")

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
        hydrate_environment()

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
