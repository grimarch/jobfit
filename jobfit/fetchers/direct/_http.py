"""Shared HTTP helpers for direct fetchers."""

import json
import urllib.request
from typing import Any

_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def get_json(url: str, *, headers: dict[str, str] | None = None, timeout: int = 10) -> dict[str, Any] | list[Any]:
    """GET url, decode JSON. Raises urllib.error.URLError / json.JSONDecodeError on failure."""
    h: dict[str, str] = {"User-Agent": _UA}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)  # type: ignore[no-any-return]


def post_json(url: str, data: dict[str, Any], *, timeout: int = 30) -> dict[str, Any] | list[Any]:
    """POST JSON body to url, decode JSON response. Raises urllib.error.URLError on failure."""
    body = json.dumps(data).encode()
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": _UA},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)  # type: ignore[no-any-return]
