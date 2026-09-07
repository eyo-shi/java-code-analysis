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

from code_analysis.config import bootstrap_deploy_configuration, diagnose_environment

stats = bootstrap_deploy_configuration()
diagnose_environment()
print(
    "Deploy configuration bootstrap complete: "
    f"{stats['from_cml_api']} from CML API, "
    f"{stats['from_snapshot']} from snapshot, "
    f"snapshot={'saved' if stats['snapshot_saved'] else 'not saved'}."
)
