import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()
if (ROOT / "code_analysis").is_dir():
    sys.path.insert(0, str(ROOT))
elif (ROOT.parent / "code_analysis").is_dir():
    sys.path.insert(0, str(ROOT.parent))

from code_analysis.config import hydrate_environment, save_environment_snapshot

print(subprocess.run(["sh 0_session-install-dependencies/setup.sh"], shell=True))

loaded = hydrate_environment()
snapshot = save_environment_snapshot()
if loaded:
    print(f"Loaded {loaded} deploy configuration variable(s) from CML project settings.")
if snapshot:
    print(f"Saved environment snapshot to {snapshot}")
