"""Shared utility helpers."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

from loguru import logger


def write_output(content: str | bytes, path: Path) -> Path:
    """Write str or bytes to path, return path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")
    return path


def generate_doc(mod: Any, refnr: str, output: str | None, open_after: bool, html: bool, preview: bool, print_prompt: bool, role_obj: Any) -> None:
    """Shared dispatch handler for cv generate and cv anschreiben commands."""
    from jobfit.llm import resolve_key

    try:
        if preview:
            out = mod.preview(refnr, role_obj.slug, output)
            logger.info(f"Preview HTML: file://{out.resolve()}")
        elif print_prompt:
            from jobfit.llm import resolve_model, resolve_provider
            from jobfit.prompt_display import print_llm_prompt

            print_llm_prompt(
                system=getattr(mod, "SYSTEM_PROMPT", ""),
                user=mod.build_prompt_for_job(refnr, role_obj.slug, role_obj.skills),
                refnr=refnr,
                doc_label=getattr(mod, "PROMPT_DOC_LABEL", "LLM"),
                model=resolve_model(getattr(mod, "PROMPT_MODEL_VAR", "CV_MODEL")),
                provider=resolve_provider(getattr(mod, "PROMPT_COMMAND_PREFIX", "CV")),
            )
        else:
            api_key = resolve_key()
            if html:
                out_path = Path(output) if output else mod.output_path(refnr, role_obj.slug).with_suffix(".html")
                write_output(mod.generate_html(refnr, role_obj.slug, api_key), out_path)
                logger.info(f"Saved HTML: file://{out_path.resolve()}")
            else:
                out_path = Path(output) if output else mod.output_path(refnr, role_obj.slug)
                if output:
                    write_output(mod.generate(refnr, role_obj.slug, api_key), out_path)
                else:
                    mod.generate(refnr, role_obj.slug, api_key)
                logger.info(f"Generated: file://{out_path.resolve()}")
                if open_after:
                    open_file(str(out_path))
    except (FileNotFoundError, ValueError, RuntimeError) as e:
        logger.error(str(e))
        raise SystemExit(1)


def open_file(path: str) -> None:
    """Open a file with the system default viewer."""
    try:
        if sys.platform == "darwin":
            subprocess.run(["open", path], check=False)
        elif sys.platform.startswith("linux"):
            subprocess.run(["xdg-open", path], check=False)
        else:
            subprocess.run(["start", path], shell=True, check=False)
    except FileNotFoundError:
        logger.warning("--open not supported in this environment (no xdg-open/open)")
