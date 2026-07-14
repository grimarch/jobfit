"""Job fetchers — one module per data source.

Each fetcher exposes a single ``run(args)`` entry point and writes
standard job JSON files to data/jobs/.

Available fetchers
------------------
- jobhive              : jobhive Parquet snapshots (covers 13 ATS platforms)
- direct.softgarden    : softgarden public career page feeds (no auth)
- direct.bundesagentur : Bundesagentur für Arbeit REST API
- direct.everjobs      : Ever Jobs sidecar (germantechjobs, berlinstartupjobs, adzuna)
"""

import argparse

from jobfit.fetchers import direct, jobhive
from jobfit.fetchers.direct import bundesagentur, everjobs, softgarden
from jobfit.config import RAW_DIR, ensure_raw_dir

__all__ = ["jobhive", "direct", "bundesagentur", "everjobs", "softgarden", "run_all"]

_ATS_SEEN_FILE = RAW_DIR / "ats_seen.json"


def run_all(args: argparse.Namespace) -> None:
    """Run all fetchers in sequence."""
    ensure_raw_dir()
    # Reset so mark_closed can detect jobs removed from feeds this run
    _ATS_SEEN_FILE.write_text("[]")
    jobhive.run(args)
    softgarden.run(args)
    bundesagentur.run(args)
    everjobs.run(args)


def run_source(source: str, args: argparse.Namespace) -> None:
    """Dispatch to the correct fetcher by source name."""
    ensure_raw_dir()
    if source == "all":
        run_all(args)
    elif source == "jobhive":
        jobhive.run(args)
    elif source == "softgarden":
        softgarden.run(args)
    elif source == "ba":
        bundesagentur.run(args)
    elif source == "everjobs":
        everjobs.run(args)
