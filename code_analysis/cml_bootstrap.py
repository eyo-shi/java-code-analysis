"""Bootstrap CML project environment variables (Churn AMP pattern)."""

from __future__ import annotations

import os

from code_analysis.config import MANAGED_ENV_VARS, _looks_corrupted, _normalize_env_value, _validate_env_value


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


def _resolve_neo4j_uri(neo4j_uri_override: str | None = None) -> str | None:
    raw = os.environ.get("NEO4J_URI", "").strip()
    if raw and not _looks_corrupted(raw):
        normalized = _normalize_env_value("NEO4J_URI", raw)
        if normalized and _validate_env_value("NEO4J_URI", normalized):
            return normalized

    override = (neo4j_uri_override or "").strip()
    if override:
        normalized = _normalize_env_value("NEO4J_URI", override)
        if normalized and _validate_env_value("NEO4J_URI", normalized):
            return normalized
    return None


def ensure_project_environment(neo4j_uri_override: str | None = None) -> dict[str, str]:
    """Persist required env vars with cmlbootstrap.create_environment_variable()."""
    updates: dict[str, str] = {}

    neo4j_uri = _resolve_neo4j_uri(neo4j_uri_override)
    if neo4j_uri:
        updates["NEO4J_URI"] = neo4j_uri

    if not updates:
        raise ValueError(
            "NEO4J_URI is not set. Do one of the following:\n"
            "  1. Project Settings > Advanced > Environment Variables: NEO4J_URI=bolt://...\n"
            "  2. Edit NEO4J_URI_OVERRIDE in 0_session-bootstrap/bootstrap.py\n"
            "Then run the 'Bootstrap' AMP task before 'Analyze and Ingest'."
        )

    cml = _cml_bootstrap_client()
    cml.create_environment_variable(updates)
    for key, value in updates.items():
        if key in MANAGED_ENV_VARS:
            os.environ[key] = value

    print(f"Bootstrap: persisted project environment variables: {sorted(updates.keys())}")
    return updates
