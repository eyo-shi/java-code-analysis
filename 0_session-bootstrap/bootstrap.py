"""Bootstrap: install deps and persist project environment variables (Churn AMP pattern)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _project_root() -> Path:
    try:
        return Path(__file__).resolve().parents[1]
    except NameError:
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

print(subprocess.run(["sh 0_session-install-dependencies/setup.sh"], shell=True, check=False))

from code_analysis.cml_bootstrap import ensure_project_environment
from code_analysis.config import diagnose_environment

ensure_project_environment()
diagnose_environment()
