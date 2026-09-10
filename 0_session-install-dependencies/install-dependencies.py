import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

print(subprocess.run(["sh 0_session-install-dependencies/setup.sh"], shell=True, check=False))

from code_analysis.seed_project_env import seed_project_environment

seed_project_environment()
