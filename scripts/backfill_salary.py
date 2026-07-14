"""One-time backfill: patch existing jobhive DB records with salary data from cached Parquet.

Run once after the salary fields were added to _row_to_job().
New jobs fetched after that point already have the fields; this script only
patches records that were written before the change (missing salary_min_raw).

Usage:
    uv run python scripts/backfill_salary.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from jobfit.fetchers.jobhive import backfill_salary

backfill_salary()
