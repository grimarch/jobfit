"""DevOps / SRE / Platform Engineering role definition.

Skills, practices, and title matching live in devops.yaml (edit that file, not this one).
"""

from pathlib import Path

from jobfit.roles._base import load_role

ROLE = load_role(Path(__file__).with_suffix(".yaml"))
