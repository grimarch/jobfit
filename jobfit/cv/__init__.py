"""CV parsing, privacy, extraction, and tailored generation."""

from importlib import import_module
from typing import Any

_LAZY: dict[str, tuple[str, str]] = {
    "anonymize_enabled": ("jobfit.cv.privacy", "anonymize_enabled"),
    "anonymize_for_llm": ("jobfit.cv.privacy", "anonymize_for_llm"),
    "cv_read": ("jobfit.cv.io", "cv_read"),
    "extract_profile": ("jobfit.cv.extract", "extract_profile"),
    "extract_run": ("jobfit.cv.extract", "run"),
    "extract_text": ("jobfit.cv.extract", "extract_text"),
    "generate": ("jobfit.cv.generator", "generate"),
    "generate_html": ("jobfit.cv.generator", "generate_html"),
    "load_cv_contact": ("jobfit.cv.io", "load_cv_contact"),
    "load_cv_profile": ("jobfit.cv.io", "load_cv_profile"),
    "output_json_path": ("jobfit.cv.generator", "output_json_path"),
    "output_path": ("jobfit.cv.generator", "output_path"),
}

__all__ = list(_LAZY)


def __getattr__(name: str) -> Any:
    if name not in _LAZY:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr_name = _LAZY[name]
    return getattr(import_module(module_name), attr_name)
