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

_EVENT_MARKERS = ("dispatchConfig", "_dispatchListeners", "nativeEvent", "isTrusted")


def _env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    ingested = _ingest_env_pair(name, value)
    if ingested is not None:
        return ingested
    return default


def _coerce_env_value(value: object) -> str | None:
    """Convert CML project.environment values to plain strings."""
    if value is None:
        return None
    if isinstance(value, (dict, list, tuple)):
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if not isinstance(value, str):
        return None

    text = value.strip()
    if not text:
        return None
    if text.startswith("{") and any(marker in text for marker in _EVENT_MARKERS):
        return None
    return text


def _validate_env_value(name: str, value: str) -> bool:
    if name == "GIT_REPO_URL":
        return value.startswith(("http://", "https://", "git@"))
    if name == "NEO4J_URI":
        return value.startswith(("bolt://", "neo4j://", "neo4j+s://", "neo4j+ssc://"))
    if name == "GIT_REF":
        return "{" not in value and "dispatchConfig" not in value and len(value) <= 256
    if name == "SOURCE_PATH":
        return "{" not in value
    return "{" not in value or name in {"EXCLUDE_DIRS"}


def _mask_value(name: str, value: str) -> str:
    if name in SENSITIVE_ENV_VARS:
        if len(value) <= 4:
            return "***"
        return f"{value[:3]}...{value[-2:]}"
    return value


def _ingest_env_pair(name: str, value: object) -> str | None:
    text = _coerce_env_value(value)
    if text is None:
        return None
    if not _validate_env_value(name, text):
        return None
    return text


def _parse_project_environment(raw: object) -> dict[str, str]:
    """Normalize CML project.environment which may be a dict or JSON string."""
    if raw is None:
        return {}

    parsed: dict[object, object]
    if isinstance(raw, dict):
        parsed = raw
    elif isinstance(raw, str):
        text = raw.strip()
        if not text:
            return {}
        try:
            loaded = json.loads(text)
            if not isinstance(loaded, dict):
                parsed = {}
            else:
                parsed = loaded
        except json.JSONDecodeError:
            parsed = {}
            result: dict[str, str] = {}
            for line in text.splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                ingested = _ingest_env_pair(key, value.strip())
                if ingested is not None:
                    result[key] = ingested
            return result
    else:
        return {}

    result: dict[str, str] = {}
    for key, value in parsed.items():
        ingested = _ingest_env_pair(str(key), value)
        if ingested is not None:
            result[str(key)] = ingested
    return result


def _sanitize_empty_managed_env() -> None:
    """Remove empty or invalid placeholders from the process environment."""
    for key in MANAGED_ENV_VARS:
        value = os.environ.get(key)
        if value is None:
            continue
        ingested = _ingest_env_pair(key, value)
        if ingested is None:
            print(f"Warning: ignoring invalid {key} value from environment.")
            os.environ.pop(key, None)
        elif ingested != value:
            os.environ[key] = ingested


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
            if not value:
                continue
            os.environ[key] = value
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
            if key not in MANAGED_ENV_VARS:
                continue
            ingested = _ingest_env_pair(key, value)
            if ingested is None:
                continue
            current = os.environ.get(key)
            if current is None or not str(current).strip():
                os.environ[key] = ingested
                loaded += 1
        break
    return loaded


def save_environment_snapshot() -> Path | None:
    """Persist managed environment variables for later sessions."""
    values: dict[str, str] = {}
    for key in MANAGED_ENV_VARS:
        ingested = _ingest_env_pair(key, os.environ.get(key))
        if ingested is not None:
            values[key] = ingested
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
        ingested = _ingest_env_pair(name, raw) if raw is not None else None
        if ingested is None:
            if raw is not None and str(raw).strip():
                print(f"  {name}: INVALID (ignored corrupted value)")
                continue
            default = DEFAULT_ENV_VALUES.get(name)
            if default is not None:
                print(f"  {name}: MISSING (will use default: {default})")
            else:
                print(f"  {name}: MISSING")
            continue
        print(f"  {name}: SET ({_mask_value(name, ingested)})")

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
                "NEO4J_URI is required. The AMP Deploy UI may not have saved your input. "
                "Set NEO4J_URI in Project Settings > Advanced > Environment Variables "
                "as a plain text value (e.g. bolt://host:7687), then restart the session."
            )

        source_path = _env("SOURCE_PATH")
        git_repo_url = _env("GIT_REPO_URL")

        if not source_path and not git_repo_url:
            diagnose_environment()
            raise ValueError(
                "GIT_REPO_URL is required when SOURCE_PATH is not set. "
                "Set GIT_REPO_URL in Project Settings > Advanced > Environment Variables "
                "as a plain text URL, then restart the session."
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
