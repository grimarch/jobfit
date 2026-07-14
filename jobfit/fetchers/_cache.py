"""Cache layer for jobhive Parquet snapshots.

Downloads jobs.parquet from storage.stapply.ai/jobhive/v1/{ats}/jobs.parquet,
saves locally with a 24-hour TTL. On repeated calls within the TTL window,
reads from disk instead of fetching over the network.
"""

import time
import urllib.request
from pathlib import Path

import pandas as pd
from loguru import logger
from tqdm import tqdm

from jobfit.config import RAW_DIR

CACHE_DIR = RAW_DIR / "jobhive_cache"
BASE_URL = "https://storage.stapply.ai/jobhive/v1/{ats}/jobs.parquet"
TTL_SECONDS = 24 * 3600


def get_jobs(ats: str, force_refresh: bool = False) -> pd.DataFrame:
    """Return a DataFrame of all jobs for the given ATS, using a 24-hour local cache."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_DIR / f"{ats}.parquet"

    if not force_refresh and cache_path.exists():
        age = time.time() - cache_path.stat().st_mtime
        if age < TTL_SECONDS:
            return pd.read_parquet(cache_path)

    url = BASE_URL.format(ats=ats)
    req = urllib.request.Request(url, headers={"User-Agent": "jobfit-cache/1.0"})
    with urllib.request.urlopen(req, timeout=300) as r:
        total = int(r.headers.get("Content-Length", 0))
        chunk = 1024 * 256  # 256 KB
        chunks: list[bytes] = []
        with tqdm(
            total=total or None,
            unit="B",
            unit_scale=True,
            unit_divisor=1024,
            desc=f"{ats}.parquet",
            leave=False,
        ) as bar:
            while True:
                buf = r.read(chunk)
                if not buf:
                    break
                chunks.append(buf)
                bar.update(len(buf))
    data = b"".join(chunks)
    cache_path.write_bytes(data)
    logger.info(f"Cached {ats}.parquet  {len(data) // 1024} KB → {cache_path}")
    return pd.read_parquet(cache_path)
