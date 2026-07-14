"""Tailored Anschreiben (cover letter) generation."""

from importlib import import_module
from typing import Any

_LAZY: dict[str, tuple[str, str]] = {
    "generate": ("jobfit.anschreiben.generator", "generate"),
    "generate_html": ("jobfit.anschreiben.generator", "generate_html"),
    "output_path": ("jobfit.anschreiben.generator", "output_path"),
    "output_json_path": ("jobfit.anschreiben.generator", "output_json_path"),
}

__all__ = list(_LAZY)


def __getattr__(name: str) -> Any:
    if name not in _LAZY:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr_name = _LAZY[name]
    return getattr(import_module(module_name), attr_name)
