"""Anschreiben generation pipeline: job context, LLM call, identity restore."""

from __future__ import annotations

import json
import re
from datetime import date
from typing import Any

from loguru import logger

from jobfit.cv.generator.pipeline import (
    _detect_language,
    _load_job_context,
)
from jobfit.cv.io import load_cv_contact
from jobfit.cv.privacy import extract_candidate_name
from jobfit.llm import complete as llm_complete, resolve_model
from jobfit.anschreiben.generator.prompts import _SYSTEM_PROMPT

_CV_COMMAND_PREFIX = "CV"

_CLOSING_PHRASES = frozenset({
    "mit freundlichen grüßen",
    "mit besten grüßen",
    "freundliche grüße",
    "viele grüße",
    "kind regards",
    "best regards",
    "yours sincerely",
    "sincerely",
    "regards",
    "yours faithfully",
})

_DE_CLOSING_PHRASES = frozenset({
    "mit freundlichen grüßen",
    "mit besten grüßen",
    "freundliche grüße",
    "viele grüße",
})


def _normalize_closing(text: str) -> str:
    return re.sub(r"[,.\s]+$", "", text.lower().strip())


def _format_closing(text: str) -> str:
    stripped = text.strip()
    if _normalize_closing(stripped) in _DE_CLOSING_PHRASES:
        return stripped.rstrip(",").strip()
    return stripped


def _is_closing_line(text: str) -> bool:
    if len(text) > 80:
        return False
    return _normalize_closing(text) in _CLOSING_PHRASES


def _is_salutation_line(text: str) -> bool:
    if len(text) > 120:
        return False
    lower = text.lower().strip()
    return (
        lower.startswith("sehr geehrte")
        or lower.startswith("dear ")
        or lower.startswith("hallo ")
        or lower.startswith("guten tag")
    )


def _sanitize_letter_data(data: dict[str, Any]) -> None:
    """Remove salutation/closing lines mistakenly placed in body_paragraphs."""
    paragraphs = data.get("body_paragraphs")
    if not isinstance(paragraphs, list):
        return

    cleaned: list[str] = []
    extracted_closing: str | None = None
    removed: list[str] = []

    for index, para in enumerate(paragraphs):
        if not isinstance(para, str):
            logger.debug(
                "Anschreiben sanitize: skipped non-string body_paragraphs[{index}] ({type_name})",
                index=index,
                type_name=type(para).__name__,
            )
            continue
        text = para.strip()
        if not text:
            logger.debug(
                "Anschreiben sanitize: skipped empty body_paragraphs[{index}]",
                index=index,
            )
            continue
        if _is_closing_line(text):
            extracted_closing = _format_closing(text)
            removed.append(f"body_paragraphs[{index}] closing: {text!r}")
            continue
        if _is_salutation_line(text):
            removed.append(f"body_paragraphs[{index}] salutation: {text!r}")
            continue
        cleaned.append(para)

    data["body_paragraphs"] = cleaned

    closing = data.get("closing")
    if not isinstance(closing, str) or not closing.strip():
        if extracted_closing:
            data["closing"] = extracted_closing
            logger.debug(
                "Anschreiben sanitize: promoted closing field from body_paragraphs: {closing!r}",
                closing=extracted_closing,
            )
    elif _is_closing_line(closing):
        formatted = _format_closing(closing)
        if formatted != closing.strip():
            logger.debug(
                "Anschreiben sanitize: normalized closing field: {before!r} -> {after!r}",
                before=closing,
                after=formatted,
            )
        data["closing"] = formatted

    if removed:
        logger.debug(
            "Anschreiben sanitize: removed {count} misplaced line(s) from body_paragraphs: {items}",
            count=len(removed),
            items=removed,
        )


def _strip_fences(text: str) -> str:
    text = re.sub(r"^```(?:json)?\s*", "", text)
    return re.sub(r"\s*```$", "", text)


def _call_llm(prompt: str, api_key: str) -> dict[str, Any]:
    """Call LLM, parse JSON response. Retries once on invalid JSON."""
    model = resolve_model("CV_MODEL")

    text = _strip_fences(llm_complete(
        [{"role": "user", "content": prompt}],
        system=_SYSTEM_PROMPT,
        model=model,
        api_key=api_key,
        fallback_model_var="CV_FALLBACK_MODEL",
        command_prefix=_CV_COMMAND_PREFIX,
    ))
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        logger.warning(f"Invalid JSON, retrying: {e}")
        retry_text = _strip_fences(llm_complete(
            [
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": text},
                {"role": "user", "content": "The JSON was invalid. Return only the raw JSON object."},
            ],
            system=_SYSTEM_PROMPT + "\n\nCRITICAL: Your previous response was not valid JSON. Return ONLY a raw JSON object, nothing else.",
            model=model,
            api_key=api_key,
            fallback_model_var="CV_FALLBACK_MODEL",
            command_prefix=_CV_COMMAND_PREFIX,
        ))
        data = json.loads(retry_text)

    _sanitize_letter_data(data)
    return data


_DE_MONTHS = (
    "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember",
)

_EN_MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)


def format_letter_date(language: str, today: date | None = None) -> str:
    """Return today's date formatted for a German or English business letter."""
    today = today or date.today()
    if str(language).lower().startswith("en"):
        return f"{_EN_MONTHS[today.month - 1]} {today.day}, {today.year}"
    return f"{today.day}. {_DE_MONTHS[today.month - 1]} {today.year}"


def _set_letter_date(letter_data: dict[str, Any], today: date | None = None) -> None:
    """Override LLM-generated date with the current local date."""
    language = str(letter_data.get("language", "de"))
    letter_data["date"] = format_letter_date(language, today)


_RE_WORK_COMP = re.compile(r"\[WORK_COMP_(\d+)\]")

_EN_WORK_COMP_PHRASES: dict[int, str] = {1: "my most recent employer"}
_EN_WORK_COMP_DEFAULT = "a previous employer"

_DE_WORK_COMP_PHRASES: dict[int, str] = {1: "meinem letzten Arbeitgeber"}
_DE_WORK_COMP_DEFAULT = "einem früheren Arbeitgeber"


def _work_comp_generic_phrase(index: int, language: str) -> str:
    """Return a generic employer reference for a redacted [WORK_COMP_N] token."""
    if str(language).lower().startswith("en"):
        return _EN_WORK_COMP_PHRASES.get(index, _EN_WORK_COMP_DEFAULT)
    return _DE_WORK_COMP_PHRASES.get(index, _DE_WORK_COMP_DEFAULT)


def _replace_work_comp_placeholders(text: str, language: str) -> str:
    """Replace leaked [WORK_COMP_N] tokens with language-appropriate generic phrases."""
    return _RE_WORK_COMP.sub(
        lambda match: _work_comp_generic_phrase(int(match.group(1)), language),
        text,
    )


def _replace_work_comp_placeholders_in_letter(letter_data: dict[str, Any]) -> None:
    """Sanitize free-text letter fields where the LLM copied redacted employer tokens."""
    language = str(letter_data.get("language", "de"))
    replaced = 0

    paragraphs = letter_data.get("body_paragraphs")
    if isinstance(paragraphs, list):
        for index, para in enumerate(paragraphs):
            if not isinstance(para, str):
                continue
            cleaned = _replace_work_comp_placeholders(para, language)
            if cleaned != para:
                paragraphs[index] = cleaned
                replaced += len(_RE_WORK_COMP.findall(para))

    if replaced:
        logger.info(
            "Anschreiben restore: replaced {count} [WORK_COMP_N] placeholder(s) "
            "with generic employer phrases",
            count=replaced,
        )


def _restore_identity(letter_data: dict[str, Any], cv_text: str, role_slug: str) -> None:
    """Restore candidate name and contacts from local CV source (overrides LLM placeholders)."""
    name = extract_candidate_name(cv_text)
    if name:
        letter_data["candidate_name"] = name

    contact = load_cv_contact(role_slug)
    if "contact" not in letter_data or not isinstance(letter_data["contact"], dict):
        letter_data["contact"] = {}
    for key, value in contact.items():
        if value is not None:
            letter_data["contact"][key] = value

    _replace_work_comp_placeholders_in_letter(letter_data)
    _set_letter_date(letter_data)


__all__ = [
    "_call_llm",
    "_detect_language",
    "_load_job_context",
    "_replace_work_comp_placeholders",
    "_replace_work_comp_placeholders_in_letter",
    "_restore_identity",
    "_sanitize_letter_data",
    "format_letter_date",
]
