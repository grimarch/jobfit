"""Tailored CV generation.

Entry point: generate(refnr, role_slug, api_key) -> bytes (PDF)
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from loguru import logger

from jobfit.config import role_output_dir
from jobfit.cv.io import cv_read, load_cv_contact, load_cv_profile
from jobfit.cv.privacy import anonymize_for_llm
from jobfit.dashboards.scoring import skills_from_text
from jobfit.llm import complete as llm_complete
from jobfit.llm import resolve_key, resolve_model, resolve_provider

_CV_COMMAND_PREFIX = "CV"
from jobfit.cv.generator.pipeline import (
    _call_llm,
    _detect_language,
    _load_job_context,
    _override_identity,
)
from jobfit.cv.generator.prompts import _SYSTEM_PROMPT as SYSTEM_PROMPT
from jobfit.cv.generator.prompts import _build_prompt
from jobfit.cv.generator.render import _load_photo, _render_html, _render_pdf
from jobfit.roles import ROLES

_GENERATED_DIR_NAME = "generated_cvs"
PROMPT_DOC_LABEL = "CV generate"
PROMPT_MODEL_VAR = "CV_MODEL"
PROMPT_COMMAND_PREFIX = "CV"


def output_path(refnr: str, role_slug: str) -> Path:
    """Return path where generated CV PDF is saved."""
    out_dir = role_output_dir(role_slug) / _GENERATED_DIR_NAME
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_refnr = re.sub(r"[^\w\-]", "_", refnr)
    return out_dir / f"cv_{safe_refnr}.pdf"


def output_json_path(refnr: str, role_slug: str) -> Path:
    """Return path where generated CV JSON (Claude output) is saved."""
    pdf = output_path(refnr, role_slug)
    return pdf.with_suffix(".json")


def generate(refnr: str, role_slug: str, api_key: str | None = None) -> bytes:
    """Generate a tailored CV PDF for the given job refnr.

    Returns PDF as bytes. Also saves the file to data/{role}/output/generated_cvs/.
    Raises ValueError if job not found, RuntimeError on generation failure.
    """
    api_key = resolve_key(api_key, command_prefix=_CV_COMMAND_PREFIX)

    role = ROLES.get(role_slug)
    if role is None:
        raise ValueError(f"Unknown role: {role_slug}")

    logger.info(f"Loading job context for {refnr}...")
    job_ctx = _load_job_context(refnr, role_slug)

    if len(job_ctx["beschreibung"]) < 100:
        raise ValueError(
            f"Job description too short ({len(job_ctx['beschreibung'])} chars). "
            "Cannot generate a meaningful tailored CV."
        )

    logger.info("Loading CV and profile...")
    cv_text = cv_read(role_slug)
    cv_profile = load_cv_profile(role_slug)

    job_skills = skills_from_text(job_ctx["beschreibung"], role.skills)
    cv_skills = set(cv_profile.get("skills", []))
    matched = sorted(job_skills & cv_skills)
    missing = sorted(job_skills - cv_skills)

    language = _detect_language(job_ctx["titel"] + " " + job_ctx["beschreibung"])
    logger.info(
        f"Job: {job_ctx['titel']} @ {job_ctx['firma']} "
        f"| lang={language} | matched={len(matched)} | missing={len(missing)}"
    )

    prompt = _build_prompt(
        job_ctx, anonymize_for_llm(cv_text), cv_profile, matched, missing, language
    )

    model = resolve_model("CV_MODEL")
    provider = resolve_provider(_CV_COMMAND_PREFIX)
    logger.info(f"Calling LLM ({provider}/{model}) to generate tailored CV...")
    cv_data = _call_llm(prompt, api_key, cv_text=cv_text)
    cv_data["_model"] = model
    _override_identity(cv_data, cv_text, role_slug)

    logger.info("Rendering PDF...")
    pdf_bytes = _render_pdf(cv_data, role_slug)

    out = output_path(refnr, role_slug)
    out.write_bytes(pdf_bytes)
    output_json_path(refnr, role_slug).write_text(
        json.dumps(cv_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info(f"Saved: {out} ({len(pdf_bytes):,} bytes)")

    return pdf_bytes


def generate_html(refnr: str, role_slug: str, api_key: str | None = None) -> str:
    """Generate tailored CV as HTML string (for preview/debugging)."""
    api_key = resolve_key(api_key, command_prefix=_CV_COMMAND_PREFIX)

    role = ROLES.get(role_slug)
    if role is None:
        raise ValueError(f"Unknown role: {role_slug}")

    job_ctx = _load_job_context(refnr, role_slug)
    cv_text = cv_read(role_slug)
    cv_profile = load_cv_profile(role_slug)

    job_skills = skills_from_text(job_ctx["beschreibung"], role.skills)
    cv_skills = set(cv_profile.get("skills", []))
    matched = sorted(job_skills & cv_skills)
    missing = sorted(job_skills - cv_skills)

    language = _detect_language(job_ctx["titel"] + " " + job_ctx["beschreibung"])
    prompt = _build_prompt(
        job_ctx, anonymize_for_llm(cv_text), cv_profile, matched, missing, language
    )
    cv_data = _call_llm(prompt, api_key, cv_text=cv_text)
    _override_identity(cv_data, cv_text, role_slug)
    return _render_html(cv_data, photo_b64=_load_photo(role_slug))


def preview(refnr: str, role_slug: str, output: str | None = None) -> Path:
    """Render HTML preview from existing generated JSON (no LLM call).

    Raises FileNotFoundError if JSON not found.
    """
    json_path = output_json_path(refnr, role_slug)
    if not json_path.exists():
        raise FileNotFoundError(
            f"No generated JSON at {json_path} — run without --preview first."
        )
    cv_data = json.loads(json_path.read_text(encoding="utf-8"))
    html = _render_html(
        cv_data, photo_b64=_load_photo(role_slug), refnr=refnr, role=role_slug
    )
    out_path = (
        Path(output) if output else output_path(refnr, role_slug).with_suffix(".html")
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    return out_path


def build_prompt_for_job(
    refnr: str, role_slug: str, role_skills: frozenset[str]
) -> str:
    """Build the LLM prompt for a job without calling the LLM."""
    job_ctx = _load_job_context(refnr, role_slug)
    cv_text = cv_read(role_slug)
    cv_profile = load_cv_profile(role_slug)
    job_skills = skills_from_text(job_ctx["beschreibung"], role_skills)
    cv_skills = set(cv_profile.get("skills", []))
    matched = sorted(job_skills & cv_skills)
    missing = sorted(job_skills - cv_skills)
    language = _detect_language(job_ctx["titel"] + " " + job_ctx["beschreibung"])
    return _build_prompt(
        job_ctx, anonymize_for_llm(cv_text), cv_profile, matched, missing, language
    )


__all__ = [
    "_build_prompt",
    "_call_llm",
    "_detect_language",
    "_load_job_context",
    "_load_photo",
    "_override_identity",
    "_render_html",
    "_render_pdf",
    "build_prompt_for_job",
    "generate",
    "generate_html",
    "llm_complete",
    "load_cv_contact",
    "output_json_path",
    "output_path",
    "preview",
]
