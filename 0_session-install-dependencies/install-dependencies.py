import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()
if (ROOT / "code_analysis").is_dir():
    sys.path.insert(0, str(ROOT))
elif (ROOT.parent / "code_analysis").is_dir():
    sys.path.insert(0, str(ROOT.parent))

from code_analysis.config import bootstrap_deploy_configuration

print(subprocess.run(["sh 0_session-install-dependencies/setup.sh"], shell=True))

stats = bootstrap_deploy_configuration()
if stats["from_cml_api"]:
    print(f"Loaded {stats['from_cml_api']} deploy configuration variable(s) from CML project settings.")
if stats["snapshot_saved"]:
    print("Saved environment snapshot to .cml-project-env.json")
