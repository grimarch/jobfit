"""Dashboard page cache: cached render functions and background rebuild."""

import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from asyncio import to_thread

from fastapi_cache import FastAPICache
from fastapi_cache.decorator import cache
from loguru import logger

from jobfit.dashboards import cv, listings, skills, targets
from jobfit.roles import DEFAULT_ROLE, ROLES

NAMESPACE = "dashboards"


def _role_obj(role: str):
    return ROLES.get(role) or ROLES[DEFAULT_ROLE]


@cache(expire=3600, namespace=NAMESPACE)
async def render_targets(role: str) -> str:
    return await to_thread(targets.render, _role_obj(role))


@cache(expire=3600, namespace=NAMESPACE)
async def render_cv(role: str) -> str:
    return await to_thread(cv.run, _role_obj(role))


@cache(expire=3600, namespace=NAMESPACE)
async def render_listings(role: str) -> str:
    return await to_thread(listings.run, _role_obj(role))


@cache(expire=3600, namespace=NAMESPACE)
async def render_skills(role: str) -> str:
    return await to_thread(skills.run, _role_obj(role))


_PAGES = [
    ("targets", render_targets, 15),
    ("cv", render_cv, 10),
    ("listings", render_listings, 10),
    ("skills", render_skills, 35),
]


def trigger_rebuild() -> None:
    """POST /api/cache/rebuild to the running jobfit-serve server."""
    port = os.environ.get("APP_HOST_PORT", "8888")
    url = f"http://localhost:{port}/api/cache/rebuild"
    try:
        with urllib.request.urlopen(
            urllib.request.Request(url, method="POST"), timeout=5
        ) as resp:
            data = json.loads(resp.read())
        logger.info(f"Server: {data.get('message', 'ok')}")
        logger.info(f"Dashboards refreshing at http://localhost:{port}")
    except urllib.error.URLError as exc:
        logger.error(f"Could not reach {url}: {exc.reason}")
        raise SystemExit(1)


_building = False


async def build_all() -> None:
    """Clear the page cache and rebuild all dashboards for DEFAULT_ROLE.

    Guards against concurrent runs: a second call while a build is in progress
    is silently dropped so the in-flight build completes cleanly.
    """
    global _building
    if _building:
        return
    _building = True
    await FastAPICache.clear(namespace=NAMESPACE)

    from tqdm import tqdm

    import jobfit._log as _log_mod

    if _log_mod.stdout_handler_id is not None:
        logger.remove(_log_mod.stdout_handler_id)
        _log_mod.stdout_handler_id = None

    tqdm_id = logger.add(
        lambda msg: tqdm.write(msg.rstrip("\n"), file=sys.stdout),
        format="<level>{level:<8}</level> | {message}",
        level="INFO",
        colorize=True,
        filter=lambda r: r["level"].no < 40,
    )

    try:
        with tqdm(
            total=len(_PAGES),
            desc="All dashboards",
            unit="page",
            position=0,
            ncols=72,
            file=sys.stdout,
        ) as outer:
            for name, fn, expected_s in _PAGES:
                inner = tqdm(
                    total=expected_s * 2,
                    desc=f"  {name:<12}",
                    bar_format="{desc}: {percentage:3.0f}%|{bar}| {elapsed}",
                    position=1,
                    leave=False,
                    ncols=72,
                    file=sys.stdout,
                )
                stop = threading.Event()

                def _tick(b=inner, e=stop):
                    while not e.is_set():
                        if b.n < b.total:
                            b.update(1)
                        else:
                            b.update(0)
                        e.wait(0.5)

                ticker = threading.Thread(target=_tick, daemon=True)
                ticker.start()
                t0 = time.monotonic()
                try:
                    await fn(DEFAULT_ROLE)
                finally:
                    stop.set()
                    ticker.join(timeout=1)
                    elapsed_s = time.monotonic() - t0
                    inner.close()

                tqdm.write(f"  {name:<12}: {elapsed_s:.0f}s ✓", file=sys.stdout)
                outer.update(1)
    finally:
        _building = False
        logger.remove(tqdm_id)
        _log_mod.stdout_handler_id = logger.add(
            sys.stdout,
            format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}",
            level="INFO",
            colorize=True,
            filter=lambda r: r["level"].no < 40,
        )
