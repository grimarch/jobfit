#!/usr/bin/env python3
"""Add industry_canonical field to classifications.json (migration to Variant C).

Reads the raw 'industry' field from each classified job, normalizes it via
jobfit.industry.normalize(), and writes the result into 'industry_canonical'.
The original 'industry' field is preserved unchanged.

Run this once when the taxonomy is stable. Subsequent classify runs will still
produce free-form 'industry' labels; the canonical value is always derived
on-the-fly by normalize() in dashboard code. This migration just pre-computes
it for convenience (e.g. grep, direct analysis without importing jobfit).

Usage:
    python scripts/migrate_industry.py [--dry-run] [--role ROLE]
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from jobfit.config import classifications_file
from jobfit.industry import CANONICAL, normalize
from jobfit.roles import DEFAULT_ROLE


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would change without writing anything",
    )
    parser.add_argument(
        "--role", default=DEFAULT_ROLE,
        help=f"Role slug (default: {DEFAULT_ROLE})",
    )
    args = parser.parse_args()

    path = classifications_file(args.role)
    if not path.exists():
        print(f"✗ Not found: {path}")
        sys.exit(1)

    with open(path) as f:
        cls: dict = json.load(f)

    total = len(cls)
    already = sum(1 for v in cls.values() if "industry_canonical" in v)
    changed = 0
    dist: Counter = Counter()

    for meta in cls.values():
        raw = meta.get("industry") or ""
        canon = normalize(raw)
        dist[canon] += 1
        if meta.get("industry_canonical") != canon:
            changed += 1
            if not args.dry_run:
                meta["industry_canonical"] = canon

    print(f"File:    {path}")
    print(f"Total:   {total} records")
    print(f"Already had industry_canonical: {already}")
    print(f"Would update: {changed}")
    print()
    print(f"{'Canonical category':<25} {'Count':>6}")
    print("-" * 33)
    for canon in CANONICAL:
        n = dist.get(canon, 0)
        if n:
            print(f"  {canon:<23} {n:>6}")

    if args.dry_run:
        print("\n(dry-run: no changes written)")
        return

    with open(path, "w") as f:
        json.dump(cls, f, indent=2, ensure_ascii=False)

    print(f"\n✓ Written {changed} updated records to {path}")


if __name__ == "__main__":
    main()
