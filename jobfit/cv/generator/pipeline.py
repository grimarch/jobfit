"""LLM pipeline: language detection, job context, identity restore, and JSON parsing."""

from __future__ import annotations

import json
import re
from typing import Any

from loguru import logger

import jobfit.cv.generator as _gen
from jobfit.cv.restore import override_identity as _override_identity_impl
from jobfit.cv.generator.prompts import _SYSTEM_PROMPT
from jobfit.llm import resolve_model

_CV_COMMAND_PREFIX = "CV"

_DE_WORDS = re.compile(
    r"\b(und|oder|für|mit|den|der|die|das|eine|einer|ist|sind|haben|werden|"
    r"wir|sie|ihr|uns|nicht|auch|bei|von|nach|auf|als|an|zu|im|ein|wird|"
    r"suchen|bieten|arbeiten|team|unser|mehr|über|alle|neue|unsere)\b",
    re.IGNORECASE,
)
_EN_WORDS = re.compile(
    r"\b(the|and|or|for|with|our|you|your|we|are|is|have|will|that|this|"
    r"their|been|not|from|they|were|but|can|all|about|which|when|also|"
    r"team|role|work|build|join|experience|looking|help|strong|great)\b",
    re.IGNORECASE,
)


def _detect_language(text: str) -> str:
    """Return 'de' or 'en' based on word frequency in text."""
    sample = text[:3000]
    de_count = len(_DE_WORDS.findall(sample))
    en_count = len(_EN_WORDS.findall(sample))
    return "de" if de_count > en_count else "en"


def _load_job_context(refnr: str, role_slug: str) -> dict[str, Any]:
    """Load job + classification from DB. Raises ValueError if not found."""
    from jobfit.db import get_session
    from jobfit.db.models import Classification as ClsModel
    from jobfit.db.models import Job as JobModel

    with get_session() as session:
        job = session.get(JobModel, refnr)
        if job is None:
            raise ValueError(f"Job not found: {refnr}")
        cls = session.get(ClsModel, refnr)
        if cls is None:
            raise ValueError(f"Classification not found for: {refnr}")

        salary_parts = []
        if cls.salary_min:
            salary_parts.append(f"{cls.salary_min:,} €")
        if cls.salary_max:
            salary_parts.append(f"{cls.salary_max:,} €")
        salary_range = " – ".join(salary_parts) if salary_parts else "not specified"

        return {
            "refnr": refnr,
            "titel": cls.titel or job.titel or "",
            "firma": cls.firma or job.firma or "",
            "beschreibung": job.beschreibung or "",
            "company_stage": cls.company_stage or "unknown",
            "company_type": cls.company_type or "unknown",
            "work_mode": cls.work_mode or "unknown",
            "english_ok": cls.english_ok,
            "german_level": cls.german_level or "not required",
            "salary_range": salary_range,
            "externe_url": job.externe_url or "",
            "ort": cls.ort or job.ort_raw or "",
            "ats_source": job.ats_source or "",
            "via": job.via or "",
        }


def _strip_fences(text: str) -> str:
    text = re.sub(r"^```(?:json)?\s*", "", text)
    return re.sub(r"\s*```$", "", text)


def _override_identity(cv_data: dict[str, Any], cv_text: str, role_slug: str) -> None:
    """Restore candidate name, contacts, and locations from local CV source."""
    _override_identity_impl(
        cv_data,
        cv_text,
        role_slug,
        load_cv_contact_fn=_gen.load_cv_contact,
    )


def _filter_invented_skills(cv_data: dict[str, Any], cv_text: str) -> None:
    """Remove skill items not found in the source CV text (case-insensitive substring match)."""
    cv_lower = cv_text.lower()
    for group in cv_data.get("skills", []):
        before = list(group["items"])
        group["items"] = [item for item in before if item.lower() in cv_lower]
        removed = [x for x in before if x not in group["items"]]
        if removed:
            logger.warning(f"Removed invented skills not in CV: {removed}")


def _call_llm(prompt: str, api_key: str, cv_text: str = "") -> dict[str, Any]:
    """Call LLM, parse JSON response. Retries once on invalid JSON."""
    model = resolve_model("CV_MODEL")

    text = _strip_fences(_gen.llm_complete(
        [{"role": "user", "content": prompt}],
        system=_SYSTEM_PROMPT,
        model=model,
        api_key=api_key,
        fallback_model_var="CV_FALLBACK_MODEL",
        command_prefix=_CV_COMMAND_PREFIX,
    ))
    try:
        cv_data = json.loads(text)
    except json.JSONDecodeError as e:
        logger.warning(f"Invalid JSON, retrying: {e}")
        retry_text = _strip_fences(_gen.llm_complete(
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
        cv_data = json.loads(retry_text)
    if cv_text:
        _filter_invented_skills(cv_data, cv_text)
    return cv_data
