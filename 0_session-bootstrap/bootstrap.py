"""Legacy entry point; use the Install Dependencies and Analyze and Ingest jobs instead."""

from __future__ import annotations

import subprocess

print(
    "This script is no longer run on AMP deploy. "
    "Set environment variables in Project Settings > Advanced > Environment Variables, "
    "then run the 'Analyze and Ingest' job from the Jobs page."
)
print(subprocess.run(["sh 0_session-install-dependencies/setup.sh"], shell=True, check=False))
