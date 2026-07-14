"""CV text extraction and structured profile extraction via Claude API."""

import json
import re
from pathlib import Path
from typing import Any

import pypdf
from jobfit.cv.io import parse_frontmatter
from jobfit.cv.privacy import anonymize_for_llm, extract_location_city
from jobfit.dashboards.scoring import skills_from_text
from jobfit.llm import complete as llm_complete, resolve_key, resolve_model, resolve_provider
from loguru import logger

_CV_EXTRACT_COMMAND_PREFIX = "CV_EXTRACT"

_PROFILE_SYSTEM = """\
You are a CV/resume parser. Extract structured information from the CV text provided.
Return ONLY a valid JSON object with these exact fields:
{
  "german_level": string or null,  // CEFR level: A1/A2/B1/B2/C1/C2/native, null if not mentioned
  "english_level": string or null, // CEFR or descriptive: basic/intermediate/advanced/fluent/native
  "experience_years": integer,     // years of experience relevant to the role (DevOps/SRE/infra), not total career length
  "seniority": string,             // one of: junior / mid / senior / lead
  "education": string or null,     // one of: ausbildung / bachelor / master / phd, null if unclear
  "certifications": [string],      // official vendor/industry certifications only (e.g. CKA, AWS SAA, RHCSA) — exclude online courses and bootcamps
  "target_locations": [],          // always empty — user configures this separately
  "work_mode_preference": string   // one of: remote / hybrid / onsite
}
No extra text, no markdown fences, just the raw JSON object."""

_PROFILE_FIELDS = (
    "german_level",
    "english_level",
    "experience_years",
    "seniority",
    "education",
    "certifications",
    "target_locations",
    "work_mode_preference",
)


def _condense_cv_for_extract(text: str, max_chars: int = 5000) -> str:
    """Drop long experience bullets; keep titles, dates, education, and languages."""
    lines: list[str] = []
    for line in text.splitlines():
        if len(line) - len(line.lstrip()) >= 3 and len(line.strip()) > 50:
            continue
        lines.append(line)
    return "\n".join(lines)[:max_chars]


def _profile_from_frontmatter(cv_text: str) -> dict[str, Any]:
    fm = parse_frontmatter(cv_text)
    if not fm:
        return {}
    profile: dict[str, Any] = {"target_locations": []}
    for key in _PROFILE_FIELDS:
        if key in fm:
            profile[key] = fm[key]
    return profile


def _merge_profile(llm_profile: dict[str, Any], frontmatter: dict[str, Any]) -> dict[str, Any]:
    merged = dict(llm_profile)
    for key, value in frontmatter.items():
        if value is None or value == "" or value == []:
            continue
        merged[key] = value
    merged.setdefault("target_locations", [])
    return merged


def extract_text(path: Path) -> str:
    """Extract plain text from PDF, MD, or TXT."""
    if path.suffix.lower() == ".pdf":
        reader = pypdf.PdfReader(str(path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    return path.read_text(encoding="utf-8")


def _strip_fences(text: str) -> str:
    text = re.sub(r"^```(?:json)?\s*", "", text.strip())
    return re.sub(r"\s*```$", "", text)


def _parse_profile_json(text: str) -> dict[str, Any]:
    cleaned = _strip_fences(text)
    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError:
        logger.debug(f"LLM raw response (failed to parse):\n{text!r}")
        raise
    if not isinstance(result, dict):
        raise ValueError(f"Expected JSON object, got {type(result).__name__}")
    return result


def extract_profile(cv_text: str, api_key: str) -> dict[str, Any]:
    """Call LLM to extract structured profile from CV text."""
    model = resolve_model("CV_EXTRACT_MODEL")
    llm_input = _condense_cv_for_extract(anonymize_for_llm(cv_text))
    messages: list[dict[str, str]] = [{"role": "user", "content": llm_input}]
    llm_call_kwargs = {
        "model": model,
        "api_key": api_key,
        "max_tokens": 2048,
        "fallback_model_var": "CV_EXTRACT_FALLBACK_MODEL",
        "json_mode": True,
        "command_prefix": _CV_EXTRACT_COMMAND_PREFIX,
    }

    text = llm_complete(messages, system=_PROFILE_SYSTEM, **llm_call_kwargs)
    try:
        profile = _parse_profile_json(text)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning(f"Invalid profile JSON, retrying: {exc}")
        retry_text = llm_complete(
            [
                *messages,
                {"role": "assistant", "content": text},
                {"role": "user", "content": "The JSON was invalid. Return only the raw JSON object."},
            ],
            system=_PROFILE_SYSTEM + "\n\nCRITICAL: Return ONLY a raw JSON object, nothing else.",
            **llm_call_kwargs,
        )
        try:
            profile = _parse_profile_json(retry_text)
        except (json.JSONDecodeError, ValueError) as retry_exc:
            frontmatter = _profile_from_frontmatter(cv_text)
            if frontmatter.get("seniority"):
                logger.warning(
                    f"LLM profile extraction failed ({retry_exc}); using CV frontmatter fallback"
                )
                return frontmatter
            raise retry_exc from exc

    return _merge_profile(profile, _profile_from_frontmatter(cv_text))


def run(args: Any) -> None:
    """Handle `jobfit cv extract <file> --role ROLE`."""
    from jobfit.cv.io import cv_profile_path

    try:
        api_key = resolve_key(command_prefix=_CV_EXTRACT_COMMAND_PREFIX)
    except RuntimeError as e:
        logger.error(str(e))
        raise SystemExit(1)

    input_path = Path(args.file)
    if not input_path.exists():
        logger.error(f"File not found: {input_path}")
        raise SystemExit(1)

    role_slug = args.role_obj.slug
    logger.info(f"Extracting text from {input_path}...")
    cv_text = extract_text(input_path)

    provider = resolve_provider(_CV_EXTRACT_COMMAND_PREFIX)
    model = resolve_model("CV_EXTRACT_MODEL")
    logger.info(f"Calling LLM ({provider}/{model}) to extract profile...")
    profile = extract_profile(cv_text, api_key)
    profile["location_city"] = extract_location_city(cv_text)
    profile["skills"] = sorted(skills_from_text(cv_text, args.role_obj.skills))

    out_json = cv_profile_path(role_slug)
    out_json.write_text(
        json.dumps(profile, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    logger.info(f"Saved: {out_json}")

    logger.info("Extracted profile:")
    for k, v in profile.items():
        logger.info(f"  {k}: {v}")
