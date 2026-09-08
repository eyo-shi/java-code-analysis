"""Bootstrap CML project environment variables (Churn AMP / SKILL section 5 pattern)."""

from __future__ import annotations

import json
import os

from code_analysis.config import (
    MANAGED_ENV_VARS,
    METADATA_DEFAULTS,
    parse_env_value,
)


def _cml_bootstrap_client():
    from cmlbootstrap import CMLBootstrap

    host = os.getenv("CDSW_API_URL", "").split(":")[0] + "://" + os.getenv("CDSW_DOMAIN", "")
    username = os.getenv("CDSW_PROJECT_URL", "").split("/")[6]
    api_key = os.getenv("CDSW_API_KEY", "")
    project_name = os.getenv("CDSW_PROJECT", "")
    if not all([host, username, api_key, project_name]):
        raise RuntimeError(
            "CML platform variables are missing (CDSW_API_URL, CDSW_DOMAIN, "
            "CDSW_PROJECT_URL, CDSW_API_KEY, CDSW_PROJECT)."
        )
    return CMLBootstrap(host, username, api_key, project_name)


def _read_from_project_environment(name: str) -> str | None:
    """Read a value from CML project environment variables (SKILL section 2)."""
    project_id = os.environ.get("CDSW_PROJECT_ID")
    if not project_id:
        return None

    try:
        import cmlapi
    except ImportError:
        return None

    try:
        project = cmlapi.default_client().get_project(project_id)
        raw_env = getattr(project, "environment", None)
        if raw_env is None:
            return None
        if isinstance(raw_env, str):
            parsed = json.loads(raw_env)
        elif isinstance(raw_env, dict):
            parsed = raw_env
        else:
            return None
        if not isinstance(parsed, dict):
            return None
        return parse_env_value(name, parsed.get(name))
    except Exception as exc:
        print(f"Warning: could not read {name} from CML project environment: {exc}")
        return None


def resolve_managed_env_value(name: str) -> tuple[str | None, str]:
    """
    Resolve a managed variable in SKILL order:
    1. os.environ (injected at task startup)
    2. CML project environment variables
    3. .project-metadata.yaml default
    """
    raw = os.environ.get(name)
    if raw is not None:
        parsed = parse_env_value(name, raw)
        if parsed:
            return parsed, "os.environ"

    from_project = _read_from_project_environment(name)
    if from_project:
        return from_project, "CML project environment"

    metadata_default = METADATA_DEFAULTS.get(name, "").strip()
    if metadata_default:
        parsed = parse_env_value(name, metadata_default)
        if parsed:
            return parsed, "metadata default"

    return None, "missing"


def ensure_project_environment() -> dict[str, str]:
    """
    Persist required env vars with cmlbootstrap.create_environment_variable().

    Mirrors Churn AMP 0_bootstrap.py which sets STORAGE / STORAGE_MODE via
    create_environment_variable() so later tasks receive them in os.environ.
    """
    neo4j_uri, source = resolve_managed_env_value("NEO4J_URI")
    if not neo4j_uri:
        raise ValueError(
            "NEO4J_URI is not available. Per CML AMP Configuration:\n"
            "  1. Set NEO4J_URI in Project Settings > Advanced > Environment Variables\n"
            "     (same store as AMP Configuration; use a plain string, not the UI event object)\n"
            "  2. Or set a non-empty default in .project-metadata.yaml and redeploy\n"
            "Then run the 'Bootstrap' AMP task, then 'Analyze and Ingest'."
        )

    updates = {"NEO4J_URI": neo4j_uri}
    cml = _cml_bootstrap_client()
    cml.create_environment_variable(updates)
    for key, value in updates.items():
        if key in MANAGED_ENV_VARS:
            os.environ[key] = value

    print(
        f"Bootstrap: persisted project environment variables from {source}: "
        f"{sorted(updates.keys())}"
    )
    return updates
