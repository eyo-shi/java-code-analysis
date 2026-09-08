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

OPTIONAL_ENV_VARS: frozenset[str] = frozenset(
    {"SOURCE_PATH", "PROJECT_ID", "PROJECT_NAME"}
)

LOCAL_ENV_FILENAMES: tuple[str, ...] = ("amp.local.env", "amp.deploy.env")

# Defaults aligned with .project-metadata.yaml environment_variables.default.
METADATA_DEFAULTS: dict[str, str] = {
    "GIT_REPO_URL": "https://github.com/terasolunaorg/terasoluna-tourreservation-mybatis3",
    "GIT_REF": "release/5.7.1.SP1.RELEASE",
    "NEO4J_URI": "",
    "NEO4J_USERNAME": "neo4j",
    "NEO4J_PASSWORD": "Neo4jPass1234",
    "CLONE_DIR": "/tmp/source",
    "EXCLUDE_DIRS": ".git,target,node_modules,venv,.venv,dist,build,__pycache__,.m2",
}

# In CML, do not silently substitute metadata defaults for deploy-time user inputs.
CML_USER_SUPPLIED_VARS: frozenset[str] = frozenset(
    {
        "GIT_REPO_URL",
        "NEO4J_URI",
        "SOURCE_PATH",
        "PROJECT_ID",
        "PROJECT_NAME",
    }
)

_EVENT_MARKERS = ("dispatchConfig", "_dispatchListeners", "nativeEvent", "isTrusted")
_NEO4J_URI_PATTERN = re.compile(
    r"(?:bolt|neo4j\+s?|neo4j\+ssc)://[^\s\"'\\{}]+",
    re.IGNORECASE,
)
_GIT_URL_PATTERN = re.compile(r"https?://[^\s\"'\\{}]+|git@[^\s\"'\\{}]+")


def _project_root_candidates() -> list[Path]:
    candidates = [Path.cwd()]
    parent = Path.cwd().parent
    if parent != Path.cwd():
        candidates.append(parent)
    return candidates


def _deep_collect_strings(value: object, depth: int = 0) -> list[str]:
    if depth > 8 or value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, (int, float, bool)):
        return [str(value)]
    if isinstance(value, dict):
        strings: list[str] = []
        for nested in value.values():
            strings.extend(_deep_collect_strings(nested, depth + 1))
        return strings
    if isinstance(value, (list, tuple)):
        strings: list[str] = []
        for nested in value:
            strings.extend(_deep_collect_strings(nested, depth + 1))
        return strings
    return []


def _looks_like_react_shell(value: object) -> bool:
    if isinstance(value, str):
        text = value.strip()
        if not text.startswith("{"):
            return False
        return any(marker in text for marker in _EVENT_MARKERS)
    if isinstance(value, dict):
        return any(marker in value for marker in _EVENT_MARKERS)
    return False


def _extract_scalar(value: object, depth: int = 0) -> str | None:
    """Extract a plain string from CML values, including React event wrappers."""
    if depth > 6 or value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.startswith("{") or text.startswith("["):
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                return text if not any(marker in text for marker in _EVENT_MARKERS) else None
            return _extract_scalar(parsed, depth + 1)
        if any(marker in text for marker in _EVENT_MARKERS):
            return None
        return text
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, dict):
        for key in ("value", "defaultValue", "currentValue"):
            extracted = _extract_scalar(value.get(key), depth + 1)
            if extracted:
                return extracted
        for key in ("target", "currentTarget"):
            extracted = _extract_scalar(value.get(key), depth + 1)
            if extracted:
                return extracted
        native_event = value.get("nativeEvent")
        if native_event is not None:
            extracted = _extract_scalar(native_event, depth + 1)
            if extracted:
                return extracted
    return None


def _regex_extract_for_name(name: str, value: object) -> str | None:
    serialized = value if isinstance(value, str) else json.dumps(value, default=str)
    if name == "NEO4J_URI":
        match = _NEO4J_URI_PATTERN.search(serialized)
        if match:
            return match.group(0)
    if name == "GIT_REPO_URL":
        match = _GIT_URL_PATTERN.search(serialized)
        if match:
            return match.group(0)
    return None


def _validate_env_value(name: str, value: str) -> bool:
    if name == "GIT_REPO_URL":
        return value.startswith(("http://", "https://", "git@"))
    if name == "NEO4J_URI":
        return (
            value.startswith(("bolt://", "neo4j://", "neo4j+s://", "neo4j+ssc://"))
            and "{" not in value
            and "dispatchConfig" not in value
        )
    if name == "GIT_REF":
        return "{" not in value and "dispatchConfig" not in value and len(value) <= 256
    if name == "SOURCE_PATH":
        return "{" not in value and "dispatchConfig" not in value
    return "{" not in value or name == "EXCLUDE_DIRS"


def _apply_name_specific_normalization(name: str, text: str) -> str:
    if name == "NEO4J_URI" and "://" not in text:
        if "{" in text or "dispatchConfig" in text:
            return text
        return f"bolt://{text}"
    return text


def _normalize_env_value(name: str, value: object) -> str | None:
    candidates: list[object] = [value]
    candidates.extend(_deep_collect_strings(value))

    regex_candidate = _regex_extract_for_name(name, value)
    if regex_candidate:
        candidates.append(regex_candidate)

    for candidate in candidates:
        text = _extract_scalar(candidate)
        if text is None:
            continue
        text = _apply_name_specific_normalization(name, text)
        if _validate_env_value(name, text):
            return text
    return None


def _in_cml_runtime() -> bool:
    return bool(os.environ.get("CDSW_PROJECT_ID"))


def _parse_key_value_lines(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, raw_value = line.partition("=")
        key = key.strip()
        normalized = _normalize_env_value(key, raw_value.strip())
        if normalized:
            result[key] = normalized
    return result


def _parse_project_environment(raw: object) -> dict[str, str]:
    if raw is None:
        return {}

    items: list[tuple[object, object]]
    if isinstance(raw, dict):
        items = list(raw.items())
    elif isinstance(raw, str):
        text = raw.strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return _parse_key_value_lines(text)
        if not isinstance(parsed, dict):
            return {}
        items = list(parsed.items())
    else:
        return {}

    result: dict[str, str] = {}
    for key, value in items:
        key_str = str(key)
        normalized = _normalize_env_value(key_str, value)
        if normalized:
            result[key_str] = normalized
            continue
        if key_str in MANAGED_ENV_VARS and value not in (None, "", {}):
            if key_str in OPTIONAL_ENV_VARS and _looks_like_react_shell(value):
                continue
            print(
                f"Warning: could not parse {key_str} from CML project environment "
                f"(stored type={type(value).__name__}; CML Configuration UI may have "
                "saved a React event object instead of your input)."
            )
    return result


def _extract_raw_project_environment(project: object) -> object:
    for attr in ("environment", "env", "environment_variables"):
        if hasattr(project, attr):
            raw = getattr(project, attr)
            if raw:
                return raw
    to_dict = getattr(project, "to_dict", None)
    if callable(to_dict):
        data = to_dict()
        if isinstance(data, dict):
            for attr in ("environment", "env", "environment_variables"):
                raw = data.get(attr)
                if raw:
                    return raw
    return None


def _load_local_env_file() -> dict[str, str]:
    for root in _project_root_candidates():
        for filename in LOCAL_ENV_FILENAMES:
            path = root / filename
            if not path.is_file():
                continue
            parsed = _parse_key_value_lines(path.read_text(encoding="utf-8"))
            if parsed:
                print(f"Loaded configuration overrides from {path}")
            return parsed
    return {}


def _merge_project_environments(*sources: dict[str, str]) -> dict[str, str]:
    merged: dict[str, str] = {}
    for source in sources:
        for key, value in source.items():
            if key in MANAGED_ENV_VARS and value:
                merged[key] = value
    return merged


def _sync_project_environment_to_cml(updates: dict[str, str]) -> None:
    """Write plain-string overrides back to CML project.environment."""
    if not updates or not _in_cml_runtime():
        return

    try:
        import cmlapi
    except ImportError:
        return

    project_id = os.environ.get("CDSW_PROJECT_ID")
    if not project_id:
        return

    try:
        client = cmlapi.default_client()
        project = client.get_project(project_id)
        raw = _extract_raw_project_environment(project)
        if isinstance(raw, dict):
            merged: dict[str, object] = dict(raw)
        elif isinstance(raw, str) and raw.strip().startswith("{"):
            merged = json.loads(raw)
            if not isinstance(merged, dict):
                merged = {}
        else:
            merged = {}

        for key, value in updates.items():
            if key in MANAGED_ENV_VARS:
                merged[key] = value

        client.update_project(project_id, body={"environment": merged})
        print(
            "Synced configuration overrides to CML project environment: "
            f"{sorted(updates.keys())}"
        )
    except Exception as exc:
        print(f"Warning: could not sync configuration to CML project environment: {exc}")


def _sanitize_managed_env() -> None:
    """Drop corrupted placeholders from os.environ before resolving config."""
    for key in MANAGED_ENV_VARS:
        value = os.environ.get(key)
        if value is None:
            continue
        normalized = _normalize_env_value(key, value)
        if normalized is None:
            if key in OPTIONAL_ENV_VARS and _looks_like_react_shell(value):
                os.environ.pop(key, None)
                continue
            print(f"Warning: ignoring invalid {key} value from os.environ.")
            os.environ.pop(key, None)
        elif normalized != value:
            os.environ[key] = normalized


def _load_project_environment_from_cml() -> tuple[dict[str, str], dict[str, str]]:
    """Return (values, sources) from CML project environment and local overrides."""
    sources: dict[str, str] = {}

    project_id = os.environ.get("CDSW_PROJECT_ID")
    if not project_id:
        local_env = _load_local_env_file()
        for key in local_env:
            sources[key] = "amp.local.env"
        return local_env, sources

    try:
        import cmlapi
    except ImportError:
        local_env = _load_local_env_file()
        for key in local_env:
            sources[key] = "amp.local.env"
        return local_env, sources

    try:
        client = cmlapi.default_client()
        project = client.get_project(project_id)
        cml_env = _parse_project_environment(_extract_raw_project_environment(project))
        for key in cml_env:
            sources[key] = "CML project environment"

        local_env = _load_local_env_file()
        if local_env:
            _sync_project_environment_to_cml(local_env)

        project_env = _merge_project_environments(cml_env, local_env)
        for key in local_env:
            sources[key] = "amp.local.env"

        for key, value in project_env.items():
            if key in MANAGED_ENV_VARS:
                os.environ[key] = value
        return project_env, sources
    except Exception as exc:
        print(f"Warning: could not load CML project environment: {exc}")
        local_env = _load_local_env_file()
        for key in local_env:
            sources[key] = "amp.local.env"
        return local_env, sources


def _env(
    name: str,
    project_env: dict[str, str] | None = None,
    default: str | None = None,
    config_sources: dict[str, str] | None = None,
) -> str | None:
    """Resolve an env var. CML project environment wins over os.environ."""
    value, _source = _resolve_env_value(name, project_env, default, config_sources)
    return value


def _resolve_env_value(
    name: str,
    project_env: dict[str, str] | None = None,
    default: str | None = None,
    config_sources: dict[str, str] | None = None,
) -> tuple[str | None, str]:
    """Return (value, source). Mirrors the resolution order used by Config.from_env."""
    if project_env and name in project_env:
        value = project_env[name].strip()
        if value:
            source = (config_sources or {}).get(name, "CML project environment")
            return value, source

    normalized = _normalize_env_value(name, os.environ.get(name))
    if normalized:
        return normalized, "os.environ"

    if default is not None and default.strip():
        return default.strip(), "code default"

    metadata_default = METADATA_DEFAULTS.get(name)
    if metadata_default and metadata_default.strip():
        if _in_cml_runtime() and name in CML_USER_SUPPLIED_VARS:
            return None, "missing"
        return metadata_default.strip(), "metadata default"
    return None, "missing"


def _resolve_env(
    name: str,
    project_env: dict[str, str] | None = None,
    config_sources: dict[str, str] | None = None,
) -> tuple[str | None, str]:
    """Return (value, source) for diagnostics."""
    return _resolve_env_value(name, project_env, config_sources=config_sources)


def _mask_value(name: str, value: str) -> str:
    if name in SENSITIVE_ENV_VARS:
        if len(value) <= 4:
            return "***"
        return f"{value[:3]}...{value[-2:]}"
    return value


def diagnose_environment(
    project_env: dict[str, str] | None = None,
    config_sources: dict[str, str] | None = None,
) -> None:
    """Print values visible in os.environ for troubleshooting."""
    if project_env is None or config_sources is None:
        project_env, config_sources = _load_project_environment_from_cml()
    print("=== Environment variable diagnostic ===")
    print(
        "AMP Configuration is stored in CML project environment variables "
        "(Project Settings > Advanced). The Configuration UI may save React event "
        "objects for edited fields; use amp.local.env or Project Settings if a value is MISSING."
    )
    if project_env:
        print(f"Resolved configuration keys: {sorted(project_env.keys())}")
    else:
        print("Resolved configuration keys: (none)")
    for name in MANAGED_ENV_VARS:
        value, source = _resolve_env(name, project_env, config_sources)
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
        _sanitize_managed_env()
        project_env, config_sources = _load_project_environment_from_cml()
        diagnose_environment(project_env, config_sources)

        neo4j_uri = _env("NEO4J_URI", project_env, config_sources=config_sources)
        if not neo4j_uri:
            raise ValueError(
                "NEO4J_URI is required. The CML Configuration screen may not save edited "
                "values correctly. Set NEO4J_URI in one of these places:\n"
                "  1. Project Settings > Advanced > Environment Variables\n"
                "  2. Project file amp.local.env (see amp.local.env.example)\n"
                "Then run the 'Analyze and Ingest' AMP task."
            )

        source_path = _env("SOURCE_PATH", project_env, config_sources=config_sources)
        git_repo_url = _env("GIT_REPO_URL", project_env, config_sources=config_sources)

        if not source_path and not git_repo_url:
            raise ValueError(
                "GIT_REPO_URL is required when SOURCE_PATH is not set. Set it in AMP "
                "Configuration, Project Settings > Advanced, or amp.local.env."
            )

        if git_repo_url:
            default_id = derive_project_id(git_repo_url)
            default_name = derive_project_name(git_repo_url)
        else:
            default_id = Path(source_path).name
            default_name = derive_project_name(default_id)

        project_id = _env("PROJECT_ID", project_env, config_sources=config_sources) or default_id
        project_name = _env("PROJECT_NAME", project_env, config_sources=config_sources) or default_name

        return cls(
            neo4j_uri=neo4j_uri,
            neo4j_username=_env("NEO4J_USERNAME", project_env, "neo4j", config_sources) or "neo4j",
            neo4j_password=_env("NEO4J_PASSWORD", project_env, "Neo4jPass1234", config_sources)
            or "Neo4jPass1234",
            git_repo_url=git_repo_url,
            git_ref=_env("GIT_REF", project_env, config_sources=config_sources) or METADATA_DEFAULTS["GIT_REF"],
            clone_dir=_env("CLONE_DIR", project_env, "/tmp/source", config_sources) or "/tmp/source",
            source_path=source_path,
            project_id=project_id,
            project_name=project_name,
            exclude_dirs=tuple(
                part.strip()
                for part in (
                    _env(
                        "EXCLUDE_DIRS",
                        project_env,
                        ".git,target,node_modules,venv,.venv,dist,build,__pycache__,.m2",
                        config_sources,
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

    @classmethod
    def env_sources(cls, project_env: dict[str, str] | None = None) -> dict[str, str]:
        """Return where each managed variable was resolved from."""
        config_sources: dict[str, str] = {}
        if project_env is None:
            project_env, config_sources = _load_project_environment_from_cml()
        sources: dict[str, str] = {}
        for name in MANAGED_ENV_VARS:
            _, source = _resolve_env_value(name, project_env, config_sources=config_sources)
            sources[name] = source
        return sources
