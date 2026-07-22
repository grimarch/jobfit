"""LLM refine for prep personas draft → personas.llm.md."""

from __future__ import annotations

import re
from pathlib import Path

from loguru import logger

from jobfit.llm import complete as llm_complete, resolve_key, resolve_model, resolve_provider
from jobfit.prep_context.personas import default_draft_path, extract_llm_input

_COMMAND_PREFIX = "PREP_PERSONAS"
_MODEL_VAR = "PREP_PERSONAS_MODEL"
_FALLBACK_MODEL_VAR = "PREP_PERSONAS_FALLBACK_MODEL"
PROMPT_DOC_LABEL = "Prep personas refine"
PROMPT_MODEL_VAR = _MODEL_VAR
PROMPT_COMMAND_PREFIX = _COMMAND_PREFIX

_LLM_INPUT_BEGIN = "<!-- jobfit:prep-personas:llm-input -->"
_LLM_INPUT_END = "<!-- /jobfit:prep-personas:llm-input -->"
_CLAIMS_GAPS_BEGIN = "<!-- jobfit:prep-claims:gaps -->"
_CLAIMS_GAPS_END = "<!-- /jobfit:prep-claims:gaps -->"
_SYSTEM_MARKER = "## System / user prompt"
_AFTER_LLM_MARKER = "## After LLM"


def default_llm_path(role_slug: str) -> Path:
    return Path(f"prompts/prep/{role_slug}") / "personas.llm.md"


def default_prompt_path(role_slug: str) -> Path:
    return Path(f"prompts/prep/{role_slug}") / "personas_review_prompt.md"


def default_draft_input_path(role_slug: str) -> Path:
    return default_draft_path(role_slug)


def load_system_prompt(prompt_path: Path) -> str:
    """Extract system instructions from personas_review_prompt.md."""
    text = prompt_path.read_text(encoding="utf-8")
    if _SYSTEM_MARKER not in text:
        raise ValueError(f"{prompt_path}: missing {_SYSTEM_MARKER!r} section")
    rest = text.split(_SYSTEM_MARKER, 1)[1]
    start_match = re.search(r"^---\s*$", rest, re.MULTILINE)
    if not start_match:
        raise ValueError(f"{prompt_path}: expected --- after system marker")
    body_start = start_match.end()
    end_match = re.search(r"^---\s*\n## After LLM", rest[body_start:], re.MULTILINE)
    body = (
        rest[body_start : body_start + end_match.start()] if end_match else rest[body_start:]
    )
    body = body.strip()
    if not body:
        raise ValueError(f"{prompt_path}: empty system prompt body")
    return body


def _extract_claims_excerpt(claims_text: str) -> str:
    """Extract gaps + do-not-claim + quick reference from claims.md for user prompt."""
    parts: list[str] = []

    if _CLAIMS_GAPS_BEGIN in claims_text and _CLAIMS_GAPS_END in claims_text:
        start = claims_text.index(_CLAIMS_GAPS_BEGIN)
        end = claims_text.index(_CLAIMS_GAPS_END) + len(_CLAIMS_GAPS_END)
        parts.append(claims_text[start:end])

    dnc_marker = "## Do not claim (hard stop)"
    if dnc_marker in claims_text:
        rest = claims_text.split(dnc_marker, 1)[1]
        next_sec = re.search(r"^## ", rest, re.MULTILINE)
        section = rest[: next_sec.start()] if next_sec else rest[:600]
        parts.append(dnc_marker + section.rstrip())

    qr_marker = "## Quick reference"
    if qr_marker in claims_text:
        rest = claims_text.split(qr_marker, 1)[1]
        next_sec = re.search(r"^## ", rest, re.MULTILINE)
        section = rest[: next_sec.start()] if next_sec else rest
        parts.append(qr_marker + section.rstrip())

    return "\n\n".join(parts)


def build_user_prompt(*, cv_text: str, claims_text: str, draft_text: str) -> str:
    claims_excerpt = _extract_claims_excerpt(claims_text)
    return "\n".join(
        [
            "## CANDIDATE CV (read-only context — do not add employers/tools not in CV)",
            "",
            cv_text.strip(),
            "",
            "## CLAIMS SoT (honest lines — do not contradict)",
            "",
            claims_excerpt,
            "",
            "## PERSONAS DRAFT (preserve structure; gaps lines must stay verbatim)",
            "",
            draft_text.strip(),
            "",
            "Return the full refined markdown document only. No preamble.",
        ]
    )


def strip_markdown_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:markdown|md)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _extract_gap_lines(text: str) -> list[str]:
    """Extract all Gaps for this job bullet lines from draft or refined text."""
    gap_lines: list[str] = []
    in_gaps = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "**Gaps for this job:**":
            in_gaps = True
            continue
        if in_gaps:
            if stripped.startswith("- **") and "—" in stripped:
                gap_lines.append(stripped)
            elif stripped and not stripped.startswith("- "):
                in_gaps = False
    return gap_lines


def validate_refine_output(draft_text: str, refined_text: str) -> list[str]:
    """Log validation warnings (do not raise). Returns list of warning strings."""
    warnings: list[str] = []

    if not refined_text.lstrip().startswith("#"):
        warnings.append("Output does not start with a markdown heading")

    if _LLM_INPUT_BEGIN in draft_text and _LLM_INPUT_BEGIN not in refined_text:
        warnings.append("llm-input begin marker missing in LLM output")
    if _LLM_INPUT_END in draft_text and _LLM_INPUT_END not in refined_text:
        warnings.append("llm-input end marker missing in LLM output")

    if "**Draft**" not in refined_text and "**Reviewed:**" not in refined_text:
        warnings.append("Output header missing Draft/Reviewed marker")

    draft_sections = re.findall(r"^## (S\d+)", draft_text, re.MULTILINE)
    for sid in draft_sections:
        if f"## {sid}" not in refined_text:
            warnings.append(f"Section ## {sid} missing in LLM output")

    draft_gap_lines = set(_extract_gap_lines(draft_text))
    refined_gap_lines = set(_extract_gap_lines(refined_text))
    for line in sorted(draft_gap_lines - refined_gap_lines):
        warnings.append(f"Gap line changed or missing: {line[:70]}")

    if "[COMPANY]" in refined_text:
        warnings.append("Unreplaced [COMPANY] placeholder in output")

    return warnings


def prepare_prompts(
    *,
    cv_path: Path,
    claims_path: Path,
    draft_path: Path,
    prompt_path: Path,
) -> tuple[str, str]:
    if not cv_path.is_file():
        raise FileNotFoundError(f"CV not found: {cv_path}")
    if not claims_path.is_file():
        raise FileNotFoundError(f"Claims not found: {claims_path}")
    if not draft_path.is_file():
        raise FileNotFoundError(
            f"Draft not found: {draft_path} — run prep-personas draft first"
        )
    if not prompt_path.is_file():
        raise FileNotFoundError(f"Prompt file not found: {prompt_path}")

    system = load_system_prompt(prompt_path)
    draft_text = draft_path.read_text(encoding="utf-8")
    claims_text = claims_path.read_text(encoding="utf-8")
    user = build_user_prompt(
        cv_text=cv_path.read_text(encoding="utf-8"),
        claims_text=claims_text,
        draft_text=extract_llm_input(draft_text),
    )
    return system, user


def run(
    *,
    role_slug: str,
    cv_path: Path,
    claims_path: Path,
    draft_path: Path,
    out_path: Path,
    prompt_path: Path,
    api_key: str | None = None,
    dry_run: bool = False,
    force: bool = False,
) -> dict[str, object]:
    if out_path.exists() and not force and not dry_run:
        raise FileExistsError(f"{out_path} exists — use --force to overwrite")

    system, user = prepare_prompts(
        cv_path=cv_path,
        claims_path=claims_path,
        draft_path=draft_path,
        prompt_path=prompt_path,
    )
    summary: dict[str, object] = {
        "role": role_slug,
        "cv": str(cv_path),
        "claims": str(claims_path),
        "draft": str(draft_path),
        "out": str(out_path),
        "prompt": str(prompt_path),
        "system_chars": len(system),
        "user_chars": len(user),
    }

    if dry_run:
        summary["mode"] = "dry-run"
        logger.info(
            "prep-personas refine dry-run: role={} out={} system_chars={} user_chars={}",
            role_slug,
            out_path,
            len(system),
            len(user),
        )
        return summary

    key = api_key or resolve_key(command_prefix=_COMMAND_PREFIX)
    model = resolve_model(_MODEL_VAR)
    provider = resolve_provider(_COMMAND_PREFIX)
    logger.info(
        "prep-personas refine: role={} model={} provider={}", role_slug, model, provider
    )

    draft_text = draft_path.read_text(encoding="utf-8")
    raw = llm_complete(
        [{"role": "user", "content": user}],
        system=system,
        model=model,
        api_key=key,
        max_tokens=16384,
        fallback_model_var=_FALLBACK_MODEL_VAR,
        command_prefix=_COMMAND_PREFIX,
    )
    refined = strip_markdown_fences(raw)
    if not refined:
        raise RuntimeError("LLM returned empty output")

    warnings = validate_refine_output(draft_text, refined)
    for warning in warnings:
        logger.warning("prep-personas refine: {}", warning)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(refined + "\n", encoding="utf-8")
    summary.update(
        {
            "mode": "write",
            "out_chars": len(refined),
            "warnings": warnings,
            "model": model,
            "provider": provider,
        }
    )
    logger.info(
        "prep-personas refine: wrote {} ({} chars, {} warnings)",
        out_path,
        len(refined),
        len(warnings),
    )
    return summary
