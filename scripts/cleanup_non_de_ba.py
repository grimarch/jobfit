"""One-time cleanup: remove Bundesagentur job files with no German location.

The BA fetcher now filters by adresse.land == DEUTSCHLAND, but jobs fetched
before that change may already be in data/jobs/. This script removes them.

Usage:
    uv run python scripts/cleanup_non_de_ba.py
    uv run python scripts/cleanup_non_de_ba.py --role sre --dry-run
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from jobfit.config import jobs_dir
from jobfit.fetchers.direct.bundesagentur import _is_germany_ba
from jobfit.roles import DEFAULT_ROLE, ROLES

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--role", default=DEFAULT_ROLE, choices=list(ROLES), metavar="ROLE")
parser.add_argument("--dry-run", action="store_true")
args = parser.parse_args()

role = ROLES[args.role]
removed = 0

for f in jobs_dir(role.slug).glob("*.json"):
    try:
        job = json.loads(f.read_text())
    except Exception:
        continue
    if job.get("_via") is not None:
        continue  # jobhive jobs have _via; BA jobs don't
    if "stellenlokationen" not in job:
        continue  # not a BA job
    if not _is_germany_ba(job):
        print(f"{'[dry-run] ' if args.dry_run else ''}Remove: {f.name}  ({job.get('stellenangebotsTitel', '')[:60]})")
        if not args.dry_run:
            f.unlink()
        removed += 1

print(f"\n{'Would remove' if args.dry_run else 'Removed'}: {removed} file(s)")
