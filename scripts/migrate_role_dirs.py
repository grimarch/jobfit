#!/usr/bin/env python3
"""Migrate data layout from flat structure to per-role directories.

Before:
    data/jobs/                         → job JSON files (devops)
    data/job_classifications.json      → classifications

After:
    data/devops/jobs/                  → job JSON files
    data/devops/classifications.json   → classifications

Usage:
    python scripts/migrate_role_dirs.py [--dry-run]

The old paths are left in place as backups until you manually remove them.
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from jobfit.config import DATA_DIR

ROLE = "devops"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be done without making changes")
    args = parser.parse_args()
    dry = args.dry_run

    old_jobs = DATA_DIR / "jobs"
    old_cls = DATA_DIR / "job_classifications.json"
    new_jobs = DATA_DIR / ROLE / "jobs"
    new_cls = DATA_DIR / ROLE / "classifications.json"

    if new_jobs.exists() or new_cls.exists():
        print(f"Target paths already exist ({new_jobs} or {new_cls}).")
        print("Migration may have already run. Aborting to avoid overwriting.")
        sys.exit(1)

    errors = []
    if not old_jobs.exists():
        errors.append(f"  ✗ {old_jobs} not found")
    if not old_cls.exists():
        errors.append(f"  ✗ {old_cls} not found")
    if errors:
        print("Missing source paths:")
        for e in errors:
            print(e)
        sys.exit(1)

    job_files = list(old_jobs.glob("*.json"))
    print(f"Migration plan (--role {ROLE}):")
    print(f"  {old_jobs}/  ({len(job_files)} files)  →  {new_jobs}/")
    print(f"  {old_cls}  →  {new_cls}")

    if dry:
        print("\n(dry-run: no changes made)")
        return

    new_jobs.mkdir(parents=True, exist_ok=True)

    copied = 0
    for f in job_files:
        shutil.copy2(f, new_jobs / f.name)
        copied += 1

    shutil.copy2(old_cls, new_cls)

    print(f"\nDone: {copied} job files copied, classifications.json copied.")
    print(f"\nOld paths kept as backup:")
    print(f"  {old_jobs}/")
    print(f"  {old_cls}")
    print(f"\nVerify the new layout works, then remove backups:")
    print(f"  rm -rf {old_jobs}")
    print(f"  rm {old_cls}")


if __name__ == "__main__":
    main()
