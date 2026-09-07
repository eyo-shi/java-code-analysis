"""AMP bootstrap: load Deploy Configuration from CML project settings."""

from __future__ import annotations

import sys
from pathlib import Path


def _project_root() -> Path:
    cwd = Path.cwd()
    if (cwd / "code_analysis").is_dir():
        return cwd
    parent = cwd.parent
    if (parent / "code_analysis").is_dir():
        return parent
    return cwd


ROOT = _project_root()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from code_analysis.config import bootstrap_deploy_configuration, diagnose_environment, _parse_project_environment
import os

stats = bootstrap_deploy_configuration()

project_id = os.environ.get("CDSW_PROJECT_ID")
if project_id:
    try:
        import cmlapi

        project = cmlapi.default_client().get_project(project_id)
        raw_env = getattr(project, "environment", None)
        parsed = _parse_project_environment(raw_env)
        print(f"CML project.environment type: {type(raw_env).__name__}")
        if isinstance(raw_env, str):
            print(f"CML project.environment preview: {raw_env[:200]}...")
        print(f"Accepted configuration keys: {sorted(parsed.keys())}")
        missing_required = [
            key
            for key in ("GIT_REPO_URL", "NEO4J_URI")
            if key not in parsed
        ]
        if missing_required:
            print(
                "Deploy configuration is missing valid values for: "
                + ", ".join(missing_required)
                + ". Set them in Project Settings > Advanced > Environment Variables."
            )
    except Exception as exc:
        print(f"Warning: could not inspect raw CML project.environment: {exc}")

diagnose_environment()
print(
    "Deploy configuration bootstrap complete: "
    f"{stats['from_cml_api']} from CML API, "
    f"{stats['from_snapshot']} from snapshot, "
    f"snapshot={'saved' if stats['snapshot_saved'] else 'not saved'}."
)
